"""
单智能体对话工作流 —— 最简子图：prepare_tools → model → tool_node → emit_artifact。

用于在已绑定 DataContext 上做问答、简单查询/脚本、小图表。
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from ...datalayer.models import DataContext
from ...runtime import call_llm, llm_gateway
from ...schemas import (
    AgentDefinition,
    RunArtifacts,
    TraceEvent,
    WorkflowDefinition,
    WorkflowGraph,
    WorkflowRunResponse,
)
from ...store import SQLitePlaygroundStore
from ..langgraph_adapter import workflow_graph_from_compiled


class SingleAgentState(TypedDict, total=False):
    user_input: str
    specialist_answer: str
    assistant_message: str
    data_context: Any
    artifact_dir: str


def _event(
    event_type: str,
    title: str,
    detail: str = "",
    payload: dict[str, Any] | None = None,
) -> TraceEvent:
    return TraceEvent(
        type=event_type,  # type: ignore
        title=title,
        detail=detail,
        payload=payload or {},
    )


# ── Graph 构建 ──────────────────────────────────────────────

def _noop_node(state: SingleAgentState) -> dict:
    return {}


def _compile_single_agent_app(
    workflow: WorkflowDefinition,
    agent: AgentDefinition,
    agent_node: Callable,
    finalizer_node: Callable | None,
):
    builder = StateGraph(SingleAgentState)

    builder.add_node("single_agent", agent_node, metadata={"kind": "agent", "label": agent.name})
    builder.add_edge(START, "single_agent")

    if finalizer_node and workflow.finalizer_enabled:
        builder.add_node("finalize", finalizer_node, metadata={"kind": "final", "label": "摘要生成"})
        builder.add_edge("single_agent", "finalize")
        builder.add_edge("finalize", END)
    else:
        builder.add_edge("single_agent", END)

    return builder.compile()


def build_single_agent_graph(workflow: WorkflowDefinition, agents: list[AgentDefinition]) -> WorkflowGraph:
    """构建单智能体图预览。"""
    if len(agents) < 1:
        raise ValueError("单智能体对话至少需要 1 个 Agent")
    agent = agents[0]

    def _agent(state: SingleAgentState) -> dict:
        return {}

    finalizer = _noop_node if workflow.finalizer_enabled else None
    app = _compile_single_agent_app(workflow, agent, _agent, finalizer)
    return workflow_graph_from_compiled(app, {agent.id: agent.name})


# ── Run ─────────────────────────────────────────────────────

def run_single_agent_chat(
    store: SQLitePlaygroundStore,
    workflow: WorkflowDefinition,
    user_input: str,
    history: list[dict[str, str]] | None = None,
    on_event: Callable[[TraceEvent], None] | None = None,
    data_context: DataContext | None = None,
    conversation_id: str | None = None,
) -> WorkflowRunResponse:
    """执行单智能体分析对话。"""
    trace: list[TraceEvent] = []

    def push(ev: TraceEvent):
        trace.append(ev)
        if on_event:
            on_event(ev)

    push(_event("run_started", "运行开始", f"工作流: {workflow.name}", {"node_id": "start"}))
    push(_event("node_entered", "进入单智能体节点", f"类型: {workflow.type}", {"node_id": "single_agent"}))

    # 获取绑定的 Agent
    agents = [a for a in store.list_agents() if a.id in workflow.specialist_agent_ids]
    if not agents:
        push(_event("run_finished", "运行结束", "错误: 无可用 Agent"))
        return WorkflowRunResponse(
            workflow_id=workflow.id,
            user_input=user_input,
            assistant_message="错误：没有绑定到此工作流的 Agent。",
            trace=trace,
            graph=WorkflowGraph(nodes=[], edges=[]),
            artifacts=RunArtifacts(),
            conversation_id=conversation_id,
        )

    agent = agents[0]
    push(_event("node_entered", f"Agent: {agent.name}", agent.description, {"node_id": agent.id}))

    # 注入数据分析系统提示
    system_prompt = agent.system_prompt
    if data_context:
        data_info = f"\n\n[当前数据上下文]\n数据源类型: {data_context.data_source_kind}\n物化路径: {data_context.materialized_uri or '待加载'}\n"
        if data_context.schema_summary:
            data_info += f"Schema 摘要: {data_context.schema_summary}\n"
        system_prompt += data_info

    # 构建增强 Agent
    enhanced_agent = AgentDefinition(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        system_prompt=system_prompt,
        model=agent.model,
        skill_ids=agent.skill_ids,
        builtin_capabilities=agent.builtin_capabilities,
    )

    # 定义 tool trace hook
    def tool_trace_hook(meta: dict):
        stage = meta.get("stage", "")
        if stage == "tool_started":
            push(_event("state_updated", f"工具调用: {meta.get('tool')}", str(meta.get("args", {}))[:200]))
        elif stage == "tool_finished":
            ok = meta.get("ok", True)
            push(_event("state_updated", f"工具{'完成' if ok else '失败'}: {meta.get('tool')}", meta.get("error", "")))

    # 执行 Agent
    try:
        answer = llm_gateway.run_agent(
            enhanced_agent,
            user_input,
            history=history,
            tool_trace_hook=tool_trace_hook,
            data_context=data_context,
        )
    except Exception as e:
        push(_event("run_finished", "运行异常", str(e)))
        return WorkflowRunResponse(
            workflow_id=workflow.id,
            user_input=user_input,
            assistant_message=f"执行出错: {e}",
            trace=trace,
            graph=WorkflowGraph(nodes=[], edges=[]),
            artifacts=RunArtifacts(),
            conversation_id=conversation_id,
        )

    push(_event("message_generated", "Agent 回答", answer[:500]))

    # Finalizer（可选）
    final_answer = answer
    if workflow.finalizer_enabled:
        try:
            final_answer = llm_gateway.finalize(user_input, agent, answer)
            push(_event("node_entered", "摘要生成", "生成最终摘要", {"node_id": "finalize"}))
            push(_event("message_generated", "最终摘要", final_answer[:500]))
        except Exception:
            pass

    # 构建 Artifacts
    artifacts = RunArtifacts(
        route_agent_id=agent.id,
        route_agent_name=agent.name,
        specialist_answer=answer,
        final_answer=final_answer,
        dataset_summary=data_context.schema_summary if data_context else None,
        materialized_paths=[data_context.materialized_uri] if data_context and data_context.materialized_uri else None,
        queries_used=data_context.sql_log if data_context else None,
    )

    # 扫描 artifacts 目录寻找图表和报表
    import os
    if data_context and data_context.artifact_dir:
        ad = data_context.artifact_dir
        if os.path.isdir(ad):
            artifacts.chart_paths = sorted(
                [os.path.join(ad, f) for f in os.listdir(ad) if f.endswith(".png")]
            )
            reports = [f for f in os.listdir(ad) if f.endswith(".md")]
            if reports:
                artifacts.report_path = os.path.join(ad, reports[0])

    # 构建 Graph
    graph = build_single_agent_graph(workflow, agents)

    push(_event("run_finished", "运行完成", f"输出长度: {len(final_answer)} 字符", {"node_id": "end"}))

    return WorkflowRunResponse(
        workflow_id=workflow.id,
        user_input=user_input,
        assistant_message=final_answer,
        trace=trace,
        graph=graph,
        artifacts=artifacts,
        conversation_id=conversation_id,
    )
