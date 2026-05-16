"""
专家交接工作流 —— 数据工程→分析→可视化→报告流水线式交接，直至收敛。
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
    WorkflowNode,
    WorkflowEdge,
    WorkflowRunResponse,
)
from ...store import SQLitePlaygroundStore
from .prompts import FIRST_OWNER_PROMPT, HANDOFF_DECISION_PROMPT, FINALIZE_HANDOFF_PROMPT


class PeerState(TypedDict, total=False):
    user_input: str
    current_task_title: str
    current_owner_id: str
    current_owner_name: str
    last_worker_id: str
    last_worker_name: str
    route_reason: str
    reports: list[str]
    hop_count: int
    max_hops: int
    assistant_message: str
    terminal_status: str
    pending_action: str
    pending_target_agent_id: str
    pending_task_title: str
    data_context: Any


def _event(event_type: str, title: str, detail: str = "", payload: dict | None = None) -> TraceEvent:
    return TraceEvent(type=event_type, title=title, detail=detail, payload=payload or {})  # type: ignore


# ── Graph 构建 ──────────────────────────────────────────────

def build_peer_handoff_graph(workflow: WorkflowDefinition, agents: list[AgentDefinition]) -> WorkflowGraph:
    """
    手动构建 WorkflowGraph —— 采用分组展示专家协作区。
    与参考仓库 peer_handoff 一致，直接构造 WorkflowGraph。
    """
    if len(agents) < 2:
        raise ValueError("专家交接至少需要 2 个 Agent")

    nodes: list[WorkflowNode] = [
        WorkflowNode(id="start", label="开始", kind="start"),
        WorkflowNode(id="first_owner_router", label="首个执行者路由", kind="logic"),
        WorkflowNode(id="peer_collab", label="专家协作区", kind="group"),
        WorkflowNode(id="handoff_decision", label="交接决策", kind="logic"),
        WorkflowNode(id="finalize", label="综合报告", kind="final"),
        WorkflowNode(id="end", label="结束", kind="end"),
    ]

    for agent in agents:
        nodes.append(WorkflowNode(
            id=f"peer_exec_{agent.id}",
            label=agent.name,
            kind="agent",
            parent_id="peer_collab",
        ))

    edges: list[WorkflowEdge] = [
        WorkflowEdge(source="start", target="first_owner_router"),
    ]
    for agent in agents:
        edges.append(WorkflowEdge(
            source="first_owner_router",
            target=f"peer_exec_{agent.id}",
            label=agent.name,
        ))
        edges.append(WorkflowEdge(
            source=f"peer_exec_{agent.id}",
            target="handoff_decision",
            label="完成",
        ))
    edges.append(WorkflowEdge(source="handoff_decision", target="finalize", label="完成"))
    edges.append(WorkflowEdge(source="handoff_decision", target="peer_collab", label="继续交接"))
    edges.append(WorkflowEdge(source="finalize", target="end"))

    return WorkflowGraph(nodes=nodes, edges=edges)


# ── Run ────────────────────────────────────────────────────

def run_peer_handoff(
    store: SQLitePlaygroundStore,
    workflow: WorkflowDefinition,
    user_input: str,
    history: list[dict[str, str]] | None = None,
    on_event: Callable[[TraceEvent], None] | None = None,
    data_context: DataContext | None = None,
    conversation_id: str | None = None,
) -> WorkflowRunResponse:
    trace: list[TraceEvent] = []
    workers = [a for a in store.list_agents() if a.id in workflow.specialist_agent_ids]

    def push(ev: TraceEvent):
        trace.append(ev)
        if on_event:
            on_event(ev)

    push(_event("run_started", "运行开始", f"工作流: {workflow.name}", {"node_id": "start"}))

    if len(workers) < 2:
        push(_event("run_finished", "运行结束", "错误: Agent 不足"))
        return WorkflowRunResponse(
            workflow_id=workflow.id, user_input=user_input,
            assistant_message="错误: 至少需要 2 个 Agent。",
            trace=trace, graph=WorkflowGraph(nodes=[], edges=[]),
            artifacts=RunArtifacts(), conversation_id=conversation_id,
        )

    # 定义流水线顺序
    pipeline_order = ["数据工程师", "数据分析师", "可视化专家", "报表专家"]
    ordered_workers = []
    for role in pipeline_order:
        for w in workers:
            if w.name == role:
                ordered_workers.append(w)
                break
    if not ordered_workers:
        ordered_workers = workers

    # Step 1: 第一个执行者
    push(_event("node_entered", "首个执行者路由", "", {"node_id": "first_owner_router"}))
    current_idx = 0
    reports: list[str] = []
    max_hops = len(ordered_workers)
    hop_count = 0

    while hop_count < max_hops:
        worker = ordered_workers[current_idx] if current_idx < len(ordered_workers) else ordered_workers[-1]
        push(_event("route_selected", f"交接 → {worker.name}", f"Hop {hop_count+1}/{max_hops}"))
        push(_event("node_entered", f"执行: {worker.name}", f"流水线阶段: {worker.name}", {"node_id": f"peer_exec_{worker.id}"}))

        def tool_trace_hook(meta: dict):
            stage = meta.get("stage", "")
            tool = meta.get("tool", "")
            if stage == "tool_started":
                push(_event("state_updated", f"工具调用: {tool}", str(meta.get("args", {}))[:200]))

        task_prompt = user_input if hop_count == 0 else f"基于前面的分析结果，继续完成你的专业工作：\n{reports[-1][:500]}"
        answer = llm_gateway.run_agent(
            worker, task_prompt,
            history=history,
            tool_trace_hook=tool_trace_hook,
            data_context=data_context,
        )
        reports.append(f"[{worker.name}] {answer}")
        push(_event("message_generated", f"{worker.name} 输出", answer[:300]))

        hop_count += 1
        current_idx += 1

        # 交接决策
        if current_idx < len(ordered_workers):
            push(_event("state_updated", "交接决策", f"是否继续 → {ordered_workers[current_idx].name}?"))
            # 默认继续流水线
        else:
            push(_event("state_updated", "流水线完成", "所有阶段已完成"))
            break

    # Step 2: 最终报告
    push(_event("node_entered", "综合报告", "", {"node_id": "finalize"}))
    try:
        final_prompt = FINALIZE_HANDOFF_PROMPT.format(
            user_input=user_input,
            reports="\n---\n".join(reports),
        )
        final_answer = call_llm(final_prompt, temperature=0.3)
    except Exception:
        final_answer = "\n---\n".join(reports)

    push(_event("message_generated", "最终报告", final_answer[:500]))

    graph = build_peer_handoff_graph(workflow, workers)

    artifacts = RunArtifacts(
        specialist_answer="\n---\n".join(reports),
        final_answer=final_answer,
        dataset_summary=data_context.schema_summary if data_context else None,
        materialized_paths=[data_context.materialized_uri] if data_context and data_context.materialized_uri else None,
        queries_used=data_context.sql_log if data_context else None,
    )

    push(_event("run_finished", "运行完成", f"输出长度: {len(final_answer)} 字符", {"node_id": "end"}))

    return WorkflowRunResponse(
        workflow_id=workflow.id, user_input=user_input,
        assistant_message=final_answer, trace=trace, graph=graph,
        artifacts=artifacts, conversation_id=conversation_id,
    )
