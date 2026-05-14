"""
LangGraph 适配器 —— 将编译后的 StateGraph 转换为前端可用的 WorkflowGraph。

与参考仓库 langgraph_adapter.py 模式对齐。
"""

from __future__ import annotations

from ..schemas import WorkflowEdge, WorkflowGraph, WorkflowNode

# 节点 ID 规范化
_ID_NORMALIZE = {
    "__start__": "start",
    "__end__": "end",
}

# 根据 metadata.kind 推断节点类型，参考仓库用 metadata={"kind": "...", "label": "..."}
_DEFAULT_KIND_MAP: dict[str, str] = {
    "start": "start",
    "end": "end",
    "router": "logic",
    "planner_core": "logic",
    "planner_validator": "logic",
    "task_dispatcher": "logic",
    "supervisor_intake": "logic",
    "delegation_policy": "logic",
    "supervisor_review": "logic",
    "handoff_decision": "logic",
    "first_owner_router": "logic",
    "single_agent": "agent",
    "finalize": "final",
    "synthesizer": "final",
}


def workflow_graph_from_compiled(compiled_app, agent_names: dict[str, str] | None = None) -> WorkflowGraph:
    """
    从编译后的 LangGraph StateGraph 提取 WorkflowGraph（节点 + 边）。

    agent_names: 可选的 agent_id → name 映射，用于 agent 节点的 label。
    """
    if agent_names is None:
        agent_names = {}

    raw = compiled_app.get_graph().to_json()
    nodes_data = raw.get("nodes", [])
    edges_data = raw.get("edges", [])

    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []

    for nd in nodes_data:
        node_id = nd.get("id", "")
        normalized_id = _ID_NORMALIZE.get(node_id, node_id)
        metadata = nd.get("metadata") or {}

        kind = metadata.get("kind")
        if not kind:
            # 根据 id 推断
            kind = _DEFAULT_KIND_MAP.get(normalized_id)
            if not kind:
                kind = "agent" if normalized_id in agent_names else "logic"

        label = metadata.get("label")
        if not label:
            if normalized_id in agent_names:
                label = agent_names[normalized_id]
            elif normalized_id == "start":
                label = "开始"
            elif normalized_id == "end":
                label = "结束"
            else:
                label = normalized_id

        nodes.append(WorkflowNode(
            id=normalized_id,
            label=str(label),
            kind=kind,  # type: ignore
        ))

    for ed in edges_data:
        source_id = ed.get("source", "")
        target_id = ed.get("target", "")
        edges.append(WorkflowEdge(
            source=_ID_NORMALIZE.get(source_id, source_id),
            target=_ID_NORMALIZE.get(target_id, target_id),
            label=ed.get("label"),
        ))

    return WorkflowGraph(nodes=nodes, edges=edges)
