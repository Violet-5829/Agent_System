"""
监督者动态调度工作流 —— 监督者拆分子任务分发给不同专家，循环直至收敛。
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
from .prompts import DELEGATION_PROMPT, FINALIZE_SUPERVISOR_PROMPT, REVIEW_PROMPT, SUPERVISOR_INTAKE_PROMPT


class SupervisorState(TypedDict, total=False):
    user_input: str
    max_cycles: int
    cycle: int
    current_focus_task: str
    current_worker_id: str
    current_worker_name: str
    current_route_reason: str
    reports: list[str]
    combined_report: str
    continue_loop: bool
    assistant_message: str
    data_context: Any


def _event(event_type: str, title: str, detail: str = "", payload: dict | None = None) -> TraceEvent:
    return TraceEvent(type=event_type, title=title, detail=detail, payload=payload or {})  # type: ignore


# ── Graph 构建 ──────────────────────────────────────────────

def _compile_supervisor_app(workflow, workers, intake_node, delegation_node, make_worker_node,
                            review_node, delegation_next, review_next, finalize_node):
    builder = StateGraph(SupervisorState)

    builder.add_node("supervisor_intake", intake_node, metadata={"kind": "logic", "label": "任务接收"})
    builder.add_node("delegation_policy", delegation_node, metadata={"kind": "logic", "label": "任务委派"})
    builder.add_node("supervisor_review", review_node, metadata={"kind": "logic", "label": "结果审查"})
    builder.add_node("finalize", finalize_node, metadata={"kind": "final", "label": "最终报告"})

    for w in workers:
        builder.add_node(w.id, make_worker_node(w), metadata={"kind": "agent", "label": w.name})

    builder.add_edge(START, "supervisor_intake")
    builder.add_edge("supervisor_intake", "delegation_policy")
    builder.add_conditional_edges("delegation_policy", delegation_next, {w.id: w.id for w in workers})
    for w in workers:
        builder.add_edge(w.id, "supervisor_review")
    builder.add_conditional_edges("supervisor_review", review_next, {
        "continue": "delegation_policy",
        "stop": "finalize",
    })
    builder.add_edge("finalize", END)

    return builder.compile()


def build_supervisor_dynamic_graph(workflow: WorkflowDefinition, agents: list[AgentDefinition]) -> WorkflowGraph:
    if len(agents) < 2:
        raise ValueError("监督者动态调度至少需要 2 个 Agent")

    def _noop(state: SupervisorState) -> dict:
        return {}

    def _next_noop(state: SupervisorState) -> str:
        return agents[0].id if agents else "end"

    def _review_noop(state: SupervisorState) -> str:
        return "continue"

    app = _compile_supervisor_app(workflow, agents, _noop, _noop, lambda a: _noop, _noop, _next_noop, _review_noop, _noop)
    return workflow_graph_from_compiled(app, {a.id: a.name for a in agents})


# ── Run ────────────────────────────────────────────────────

def run_supervisor_dynamic(
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

    max_cycles = 3
    reports: list[str] = []

    # Step 1: 任务接收与分析
    push(_event("node_entered", "监督者接收", "分析需求...", {"node_id": "supervisor_intake"}))
    worker_names = ", ".join(f"{w.name}({w.id})" for w in workers)
    intake_prompt = SUPERVISOR_INTAKE_PROMPT.format(user_input=user_input, workers=worker_names)
    try:
        intake_plan = call_llm(intake_prompt, temperature=0.3)
        push(_event("state_updated", "执行计划", intake_plan[:300]))
    except Exception:
        intake_plan = user_input

    # Step 2: 委派-执行-审查 循环
    focus_task = user_input

    for cycle in range(max_cycles):
        push(_event("state_updated", f"周期 {cycle+1}/{max_cycles}", f"当前焦点: {focus_task[:100]}"))

        # 委派
        push(_event("node_entered", "委派任务", "选择专家...", {"node_id": "delegation_policy"}))
        selected_id, selected_name = llm_gateway.route(focus_task, workers)
        worker = next((w for w in workers if w.id == selected_id), workers[0])
        push(_event("route_selected", f"委派到: {worker.name}"))

        # 执行
        push(_event("node_entered", f"执行: {worker.name}", "", {"node_id": worker.id}))

        def tool_trace_hook(meta: dict):
            stage = meta.get("stage", "")
            tool = meta.get("tool", "")
            if stage == "tool_started":
                push(_event("state_updated", f"工具调用: {tool}", str(meta.get("args", {}))[:200]))

        answer = llm_gateway.run_agent(
            worker, focus_task,
            history=history,
            tool_trace_hook=tool_trace_hook,
            data_context=data_context,
        )
        reports.append(f"[周期{cycle+1}] [{worker.name}] {focus_task}\n{answer}")
        push(_event("message_generated", f"{worker.name} 回答", answer[:300]))

        # 审查
        push(_event("node_entered", "监督者审查", "", {"node_id": "supervisor_review"}))
        try:
            review_prompt = REVIEW_PROMPT.format(
                reports="\n---\n".join(reports),
                user_input=user_input,
            )
            decision = call_llm(review_prompt, temperature=0).strip().lower()
        except Exception:
            decision = "stop"

        push(_event("state_updated", f"审查决定: {decision}"))
        if decision == "continue" and cycle < max_cycles - 1:
            focus_task = f"基于已有发现继续深入分析：{user_input}"
        else:
            break

    # Step 3: 最终报告
    push(_event("node_entered", "生成最终报告", "综合所有分析结果...", {"node_id": "finalize"}))
    try:
        final_prompt = FINALIZE_SUPERVISOR_PROMPT.format(user_input=user_input, reports="\n---\n".join(reports))
        final_answer = call_llm(final_prompt, temperature=0.3)
    except Exception:
        final_answer = "\n---\n".join(reports)

    push(_event("message_generated", "最终报告", final_answer[:500]))

    graph = build_supervisor_dynamic_graph(workflow, workers)

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
