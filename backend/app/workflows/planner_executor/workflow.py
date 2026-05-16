"""
规划执行者工作流 —— 规划 → 校验 → 分发 → 执行 → 合成。
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
from .prompts import PLANNER_PROMPT, SYNTH_PROMPT, VALIDATOR_PROMPT


class PlannerState(TypedDict, total=False):
    user_input: str
    tasks: list[str]
    plan_source: str
    planning_round: int
    replan_required: bool
    task_index: int
    current_task: str
    current_worker_id: str
    current_worker_name: str
    current_route_reason: str
    task_reports: list[str]
    combined_report: str
    assistant_message: str
    data_context: Any


def _event(event_type: str, title: str, detail: str = "", payload: dict | None = None) -> TraceEvent:
    return TraceEvent(type=event_type, title=title, detail=detail, payload=payload or {})  # type: ignore


# ── Graph 构建 ──────────────────────────────────────────────

def _compile_planner_app(workflow, workers, planner_node, validator_node, dispatcher_node,
                         make_worker_node, validator_next, dispatch_next, worker_next, synth_node):
    builder = StateGraph(PlannerState)

    builder.add_node("planner_core", planner_node, metadata={"kind": "logic", "label": "任务规划"})
    builder.add_node("planner_validator", validator_node, metadata={"kind": "logic", "label": "规划校验"})
    builder.add_node("task_dispatcher", dispatcher_node, metadata={"kind": "logic", "label": "任务分发"})
    builder.add_node("synthesizer", synth_node, metadata={"kind": "final", "label": "结果合成"})

    for w in workers:
        builder.add_node(w.id, make_worker_node(w), metadata={"kind": "agent", "label": w.name})

    builder.add_edge(START, "planner_core")
    builder.add_edge("planner_core", "planner_validator")
    builder.add_conditional_edges("planner_validator", validator_next, {
        "ok": "task_dispatcher",
        "replan": "planner_core",
    })
    builder.add_conditional_edges("task_dispatcher", dispatch_next, {
        **{w.id: w.id for w in workers},
        "synthesize": "synthesizer",
    })
    for w in workers:
        builder.add_conditional_edges(w.id, worker_next, {
            "next": "task_dispatcher",
            "synthesize": "synthesizer",
        })
    builder.add_edge("synthesizer", END)

    return builder.compile()


def build_planner_executor_graph(workflow: WorkflowDefinition, agents: list[AgentDefinition]) -> WorkflowGraph:
    if len(agents) < 2:
        raise ValueError("规划执行者至少需要 2 个 Agent")

    def _noop(state: PlannerState) -> dict:
        return {}

    def _next_noop(state: PlannerState) -> str:
        return "ok"

    def _dispatch_noop(state: PlannerState) -> str:
        return agents[0].id

    def _make_w(a: AgentDefinition):
        return _noop

    app = _compile_planner_app(workflow, agents, _noop, _noop, _noop, _make_w, _next_noop, _dispatch_noop, _next_noop, _noop)
    return workflow_graph_from_compiled(app, {a.id: a.name for a in agents})


# ── Run ────────────────────────────────────────────────────

def run_planner_executor(
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

    # Step 1: 规划
    push(_event("node_entered", "任务规划", "分解用户需求...", {"node_id": "planner_core"}))
    tasks, plan_source = llm_gateway.plan_tasks(user_input, max_tasks=5, force_multi=True, agents=workers)
    push(_event("state_updated", "规划结果", str(tasks)))

    # Step 2: 校验
    push(_event("node_entered", "规划校验", "验证任务...", {"node_id": "planner_validator"}))
    # 简单校验：检查是否有数据获取任务
    has_data_task = any("数据" in t or "加载" in t or "SQL" in t or "查询" in t for t in tasks)
    if not has_data_task and data_context:
        tasks.insert(0, "数据工程师：探查数据源结构和内容")

    # Step 3: 分发执行
    task_reports: list[str] = []
    for i, task in enumerate(tasks):
        push(_event("state_updated", f"执行任务 {i+1}/{len(tasks)}", task))

        # 简单路由：根据关键词分配 worker
        task_lower = task.lower()
        for worker in workers:
            role_keywords = {
                "数据工程师": ["数据", "sql", "查询", "加载", "excel", "表", "结构"],
                "数据分析师": ["分析", "统计", "趋势", "相关", "描述"],
                "可视化专家": ["图表", "可视化", "画图", "柱状", "折线"],
                "报表专家": ["报表", "报告", "总结", "markdown", "综合"],
            }
            keywords = role_keywords.get(worker.name, [])
            if any(k in task_lower for k in keywords):
                selected = worker
                break
        else:
            selected = workers[0]

        push(_event("node_entered", f"分发到: {selected.name}", task, {"node_id": selected.id}))

        def tool_trace_hook(meta: dict):
            stage = meta.get("stage", "")
            tool = meta.get("tool", "")
            if stage == "tool_started":
                push(_event("state_updated", f"工具调用: {tool}", str(meta.get("args", {}))[:200]))

        answer = llm_gateway.run_agent(
            selected, task,
            history=history,
            tool_trace_hook=tool_trace_hook,
            data_context=data_context,
        )
        task_reports.append(f"[{selected.name}] {task}\n{answer}")
        push(_event("message_generated", f"{selected.name} 完成", answer[:300]))

    # Step 4: 合成
    push(_event("node_entered", "结果合成", "汇总分析报告...", {"node_id": "synthesizer"}))
    combined = "\n\n---\n\n".join(task_reports)
    try:
        synth_prompt = SYNTH_PROMPT.format(user_input=user_input, task_reports=combined)
        final_answer = call_llm(synth_prompt, temperature=0.3)
    except Exception:
        final_answer = combined

    push(_event("message_generated", "最终报告", final_answer[:500]))

    graph = build_planner_executor_graph(workflow, workers)

    artifacts = RunArtifacts(
        specialist_answer=combined,
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
