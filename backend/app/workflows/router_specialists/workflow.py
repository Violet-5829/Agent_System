"""
路由专家工作流 —— 路由器根据用户意图选择专家子图执行。
"""

from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from ...datalayer.models import DataContext
from ...runtime import llm_gateway
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
from .prompts import FINALIZER_PROMPT, ROUTER_SYSTEM_PROMPT


class RouterState(TypedDict, total=False):
    user_input: str
    selected_agent_id: str
    selected_agent_name: str
    route_reason: str
    specialist_answer: str
    assistant_message: str
    data_context: Any


def _event(event_type: str, title: str, detail: str = "", payload: dict | None = None) -> TraceEvent:
    return TraceEvent(type=event_type, title=title, detail=detail, payload=payload or {})  # type: ignore


# ── Graph 构建 ──────────────────────────────────────────────

def _compile_router_app(workflow, agents, router_node, make_specialist_node, route_next, finalizer_node):
    builder = StateGraph(RouterState)

    builder.add_node("router", router_node, metadata={"kind": "logic", "label": "意图路由"})
    builder.add_edge(START, "router")

    for agent in agents:
        builder.add_node(
            agent.id,
            make_specialist_node(agent),
            metadata={"kind": "agent", "label": agent.name},
        )

    route_map = {a.id: a.id for a in agents}
    builder.add_conditional_edges("router", route_next, route_map)

    if finalizer_node and workflow.finalizer_enabled:
        builder.add_node("finalize", finalizer_node, metadata={"kind": "final", "label": "结果综合"})
        for agent in agents:
            builder.add_edge(agent.id, "finalize")
        builder.add_edge("finalize", END)
    else:
        for agent in agents:
            builder.add_edge(agent.id, END)

    return builder.compile()


def build_router_specialists_graph(workflow: WorkflowDefinition, agents: list[AgentDefinition]) -> WorkflowGraph:
    if len(agents) < 2:
        raise ValueError("路由专家至少需要 2 个 Agent")

    def _router(state: RouterState) -> dict:
        return {}

    def _route_next(state: RouterState) -> str:
        return agents[0].id

    def _make_spec(agent: AgentDefinition):
        def _spec(state: RouterState) -> dict:
            return {}
        return _spec

    def _noop(state: RouterState) -> dict:
        return {}

    app = _compile_router_app(workflow, agents, _router, _make_spec, _route_next, _noop)
    agent_names = {a.id: a.name for a in agents}
    return workflow_graph_from_compiled(app, agent_names)


# ── Run ────────────────────────────────────────────────────

def run_router_specialists(
    store: SQLitePlaygroundStore,
    workflow: WorkflowDefinition,
    user_input: str,
    history: list[dict[str, str]] | None = None,
    on_event: Callable[[TraceEvent], None] | None = None,
    data_context: DataContext | None = None,
    conversation_id: str | None = None,
) -> WorkflowRunResponse:
    trace: list[TraceEvent] = []

    def push(ev: TraceEvent):
        trace.append(ev)
        if on_event:
            on_event(ev)

    push(_event("run_started", "运行开始", f"工作流: {workflow.name}"))

    agents = [a for a in store.list_agents() if a.id in workflow.specialist_agent_ids]
    if len(agents) < 2:
        push(_event("run_finished", "运行结束", "错误: Agent 不足"))
        return WorkflowRunResponse(
            workflow_id=workflow.id, user_input=user_input,
            assistant_message="错误：需要至少 2 个 Agent。",
            trace=trace, graph=WorkflowGraph(nodes=[], edges=[]),
            artifacts=RunArtifacts(), conversation_id=conversation_id,
        )

    # 路由
    push(_event("node_entered", "意图路由", "分析用户意图..."))
    selected_id, selected_name = llm_gateway.route(user_input, agents)
    push(_event("route_selected", f"选择专家: {selected_name}", f"Agent ID: {selected_id}"))

    specialist = next((a for a in agents if a.id == selected_id), agents[0])

    # 专家执行
    push(_event("node_entered", f"专家执行: {specialist.name}", specialist.description))

    def tool_trace_hook(meta: dict):
        stage = meta.get("stage", "")
        tool = meta.get("tool", "")
        if stage == "tool_started":
            push(_event("state_updated", f"工具调用: {tool}", str(meta.get("args", {}))[:200]))
        elif stage == "tool_finished":
            ok = meta.get("ok", True)
            push(_event("state_updated", f"工具{'完成' if ok else '失败'}: {tool}"))

    answer = llm_gateway.run_agent(
        specialist, user_input,
        history=history,
        tool_trace_hook=tool_trace_hook,
        data_context=data_context,
    )
    push(_event("message_generated", f"{specialist.name} 回答", answer[:500]))

    # Finalizer
    final_answer = answer
    if workflow.finalizer_enabled:
        try:
            prompt = FINALIZER_PROMPT.format(user_input=user_input, specialist_answer=answer)
            final_answer = llm_gateway.finalize(user_input, specialist, answer)
            push(_event("message_generated", "最终回答", final_answer[:500]))
        except Exception:
            pass

    graph = build_router_specialists_graph(workflow, agents)

    artifacts = RunArtifacts(
        route_agent_id=specialist.id,
        route_agent_name=specialist.name,
        route_reason=f"路由选择: {specialist.name}",
        specialist_answer=answer,
        final_answer=final_answer,
        dataset_summary=data_context.schema_summary if data_context else None,
        materialized_paths=[data_context.materialized_uri] if data_context and data_context.materialized_uri else None,
        queries_used=data_context.sql_log if data_context else None,
    )

    push(_event("run_finished", "运行完成", f"输出长度: {len(final_answer)} 字符"))

    return WorkflowRunResponse(
        workflow_id=workflow.id, user_input=user_input,
        assistant_message=final_answer, trace=trace, graph=graph,
        artifacts=artifacts, conversation_id=conversation_id,
    )
