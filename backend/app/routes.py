"""
API 路由 —— 与参考仓库路由结构对齐，新增数据源路由。

对 Claude Code 阅读者：
- 保留所有参考仓库路由（health, settings, skills, agents, workflows, runs, conversations）
- 新增 /api/sql-data-sources 和 /api/excel-datasets 路由
- _dispatch_run 扩展了 data_context 参数
"""

from __future__ import annotations

import json
import os
import queue
import threading
import traceback
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .datalayer.context_builder import ContextBuilder, ContextBuilderError
from .runtime import llm_gateway
from .schemas import (
    AgentDefinition,
    AgentDefinitionCreate,
    AgentDefinitionUpdate,
    AppSettings,
    Conversation,
    ConversationCreate,
    ConversationDetail,
    ExcelDataset,
    ExcelDatasetCreate,
    Message,
    RunArtifacts,
    SkillDefinition,
    SkillDefinitionCreate,
    SkillInstallResponse,
    SkillSyncRequest,
    SkillSyncResponse,
    SqlDataSource,
    SqlDataSourceCreate,
    SqlDataSourceResponse,
    TraceEvent,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowGraph,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowTemplate,
)
from .store import store
from .workflows import (
    peer_handoff,
    planner_executor,
    router_specialists,
    single_agent_chat,
    supervisor_dynamic,
)

router = APIRouter(prefix="/api")

# ── 辅助函数 ──────────────────────────────────────────────────

_DISPATCH_TABLE = {
    "single_agent_chat": single_agent_chat.run_single_agent_chat,
    "router_specialists": router_specialists.run_router_specialists,
    "planner_executor": planner_executor.run_planner_executor,
    "supervisor_dynamic": supervisor_dynamic.run_supervisor_dynamic,
    "peer_handoff": peer_handoff.run_peer_handoff,
}


def _dispatch_run(
    store: Any,
    workflow: WorkflowDefinition,
    user_input: str,
    *,
    history: list[dict[str, str]] | None = None,
    on_event: Any = None,
    data_context: Any = None,
    conversation_id: str | None = None,
) -> WorkflowRunResponse:
    """根据 workflow.type 分发到对应的 run_* 函数。"""
    runner = _DISPATCH_TABLE.get(workflow.type)
    if not runner:
        raise HTTPException(400, f"不支持的工作流类型: {workflow.type}")
    result = runner(
        store=store,
        workflow=workflow,
        user_input=user_input,
        history=history,
        on_event=on_event,
        data_context=data_context,
        conversation_id=conversation_id,
    )
    # 保存会话消息
    if conversation_id and store:
        store.add_message(conversation_id, "user", user_input)
        agent_name = result.artifacts.route_agent_name or result.artifacts.final_answer[:20] if result.artifacts.final_answer else None
        store.add_message(conversation_id, "assistant", result.assistant_message, agent_name=agent_name)
        # 自动标题
        conv = store.get_conversation(conversation_id)
        if conv and not conv.title:
            store.update_conversation_title(conversation_id, user_input[:50])
    return result


# ── Health ────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok"}


# ── Settings ──────────────────────────────────────────────────

@router.get("/settings", response_model=AppSettings)
def get_app_settings():
    stored = store.get_app_settings_payload()
    return stored or AppSettings()


@router.put("/settings", response_model=AppSettings)
def update_app_settings(payload: AppSettings):
    store.save_app_settings(payload)
    llm_gateway.refresh_client()
    return payload


# ── Workflow Templates ────────────────────────────────────────

@router.get("/workflow-templates", response_model=list[WorkflowTemplate])
def list_workflow_templates():
    return store.get_templates()


# ── Skills ────────────────────────────────────────────────────

@router.get("/skills", response_model=list[SkillDefinition])
def list_skills():
    return store.list_skills()


@router.post("/skills", response_model=SkillDefinition)
def create_skill(payload: SkillDefinitionCreate):
    return store.create_skill(payload)


@router.post("/skills/{skill_id}/install", response_model=SkillInstallResponse)
def install_skill(skill_id: str):
    skill = store.get_skill(skill_id)
    if not skill:
        raise HTTPException(404, "技能不存在")
    return SkillInstallResponse(
        skill_id=skill_id,
        skill_name=skill.name,
        message="已安装（首版为本地 Skill，无需额外安装步骤）",
        tool_enabled=skill.tool is not None,
    )


@router.post("/skills/sync", response_model=SkillSyncResponse)
def sync_skills(payload: SkillSyncRequest):
    return SkillSyncResponse(
        provider=payload.provider,
        query=payload.query or "search",
        fetched=0,
        imported=0,
        updated=0,
    )


# ── Agents ────────────────────────────────────────────────────

@router.get("/agents", response_model=list[AgentDefinition])
def list_agents():
    return store.list_agents()


@router.post("/agents", response_model=AgentDefinition)
def create_agent(payload: AgentDefinitionCreate):
    # 验证 skill_ids 存在
    for sid in payload.skill_ids:
        if not store.get_skill(sid):
            raise HTTPException(400, f"Skill 不存在: {sid}")
    return store.create_agent(payload)


@router.put("/agents/{agent_id}", response_model=AgentDefinition)
def update_agent(agent_id: str, payload: AgentDefinitionUpdate):
    result = store.update_agent(agent_id, payload)
    if not result:
        raise HTTPException(404, "Agent 不存在")
    return result


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    if not store.delete_agent(agent_id):
        raise HTTPException(404, "Agent 不存在")
    return {"ok": True}


# ── Workflows ─────────────────────────────────────────────────

@router.get("/workflows", response_model=list[WorkflowDefinition])
def list_workflows():
    return store.list_workflows()


@router.post("/workflows", response_model=WorkflowDefinition)
def create_workflow(payload: WorkflowDefinitionCreate):
    # 验证 agent 数量
    templates = {t.type: t for t in store.get_templates()}
    tmpl = templates.get(payload.type)
    if tmpl and len(payload.specialist_agent_ids) < tmpl.required_agent_count:
        raise HTTPException(400, f"工作流类型 '{payload.type}' 至少需要 {tmpl.required_agent_count} 个 Agent")
    return store.create_workflow(payload)


@router.put("/workflows/{workflow_id}", response_model=WorkflowDefinition)
def update_workflow(workflow_id: str, payload: WorkflowDefinitionUpdate):
    result = store.update_workflow(workflow_id, payload)
    if not result:
        raise HTTPException(404, "工作流不存在")
    return result


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    if not store.delete_workflow(workflow_id):
        raise HTTPException(404, "工作流不存在")
    return {"ok": True}


@router.get("/workflows/{workflow_id}/graph", response_model=WorkflowGraph)
def get_workflow_graph(workflow_id: str):
    wf = store.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")
    # 动态 import 对应的 build_*_graph
    graph_builders = {
        "single_agent_chat": single_agent_chat.build_single_agent_graph,
        "router_specialists": router_specialists.build_router_specialists_graph,
        "planner_executor": planner_executor.build_planner_executor_graph,
        "supervisor_dynamic": supervisor_dynamic.build_supervisor_dynamic_graph,
        "peer_handoff": peer_handoff.build_peer_handoff_graph,
    }
    builder = graph_builders.get(wf.type)
    if not builder:
        raise HTTPException(400, f"不支持的工作流类型: {wf.type}")
    agents = [a for a in store.list_agents() if a.id in wf.specialist_agent_ids]
    return builder(wf, agents)


# ── Runs ──────────────────────────────────────────────────────

@router.post("/runs", response_model=WorkflowRunResponse)
def run_workflow(payload: WorkflowRunRequest):
    # 验证数据源
    if not payload.sql_data_source_id and not payload.excel_dataset_id:
        raise HTTPException(400, "必须指定 sql_data_source_id 或 excel_dataset_id")

    if payload.sql_data_source_id and payload.excel_dataset_id:
        raise HTTPException(400, "只能选择 SQL 数据源或 Excel 数据集，不能同时选择")

    wf = store.get_workflow(payload.workflow_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")

    # 构建 DataContext
    cb = ContextBuilder(store)
    try:
        data_context = cb.build(
            sql_data_source_id=payload.sql_data_source_id,
            excel_dataset_id=payload.excel_dataset_id,
            artifact_dir=None,  # 在 workflow run 中创建
        )
    except ContextBuilderError as e:
        raise HTTPException(400, str(e))

    if not data_context:
        raise HTTPException(400, "无法构建数据上下文，请检查数据源配置")

    # 加载历史
    history = None
    if payload.conversation_id:
        conv = store.get_conversation(payload.conversation_id)
        if conv:
            recent = conv.messages[-2:] if len(conv.messages) >= 2 else conv.messages
            history = [{"role": m.role, "content": m.content} for m in recent]

    # 创建 artifact 目录
    from uuid import uuid4
    run_id = uuid4().hex[:8]
    data_context.artifact_dir = str(
        __import__("pathlib").Path(store.db_path).parent / "artifacts" / run_id
    )
    os.makedirs(data_context.artifact_dir, exist_ok=True)

    # 执行
    conv_id = payload.conversation_id
    if not conv_id:
        conv = store.create_conversation(ConversationCreate(workflow_id=payload.workflow_id))
        conv_id = conv.id

    return _dispatch_run(
        store,
        wf,
        payload.user_input,
        history=history,
        data_context=data_context,
        conversation_id=conv_id,
    )


@router.post("/runs/stream")
def run_workflow_stream(payload: WorkflowRunRequest):
    if not payload.sql_data_source_id and not payload.excel_dataset_id:
        raise HTTPException(400, "必须指定 sql_data_source_id 或 excel_dataset_id")

    if payload.sql_data_source_id and payload.excel_dataset_id:
        raise HTTPException(400, "只能选择 SQL 数据源或 Excel 数据集，不能同时选择")

    wf = store.get_workflow(payload.workflow_id)
    if not wf:
        raise HTTPException(404, "工作流不存在")

    cb = ContextBuilder(store)
    try:
        data_context = cb.build(
            sql_data_source_id=payload.sql_data_source_id,
            excel_dataset_id=payload.excel_dataset_id,
        )
    except ContextBuilderError as e:
        raise HTTPException(400, str(e))

    if not data_context:
        raise HTTPException(400, "无法构建数据上下文")

    from uuid import uuid4
    run_id = uuid4().hex[:8]
    data_context.artifact_dir = str(
        __import__("pathlib").Path(store.db_path).parent / "artifacts" / run_id
    )
    os.makedirs(data_context.artifact_dir, exist_ok=True)

    history = None
    if payload.conversation_id:
        conv = store.get_conversation(payload.conversation_id)
        if conv:
            recent = conv.messages[-2:] if len(conv.messages) >= 2 else conv.messages
            history = [{"role": m.role, "content": m.content} for m in recent]

    conv_id = payload.conversation_id
    if not conv_id:
        conv = store.create_conversation(ConversationCreate(workflow_id=payload.workflow_id))
        conv_id = conv.id

    q: queue.Queue[Any] = queue.Queue()

    def on_trace(event: TraceEvent):
        q.put(("trace", event.model_dump()))

    def _runner():
        try:
            result = _dispatch_run(
                store, wf, payload.user_input,
                history=history,
                on_event=on_trace,
                data_context=data_context,
                conversation_id=conv_id,
            )
            q.put(("final", result.model_dump()))
        except Exception as e:
            q.put(("error", {"message": str(e), "traceback": traceback.format_exc()}))
        finally:
            q.put(("end", None))

    t = threading.Thread(target=_runner, daemon=True)
    t.start()

    def event_stream():
        while True:
            item = q.get()
            if item[0] == "end":
                yield "event: end\ndata: {}\n\n"
                break
            event_type, data = item
            yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Conversations ─────────────────────────────────────────────

@router.get("/conversations", response_model=list[Conversation])
def list_conversations(workflow_id: str | None = None):
    return store.list_conversations(workflow_id)


@router.post("/conversations", response_model=Conversation)
def create_conversation(payload: ConversationCreate):
    return store.create_conversation(payload)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str):
    conv = store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    return conv


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    if not store.delete_conversation(conversation_id):
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


# ── SQL 数据源（新增） ────────────────────────────────────────

@router.get("/sql-data-sources", response_model=list[SqlDataSourceResponse])
def list_sql_data_sources():
    """列表（隐藏连接串）"""
    sources = store.list_sql_data_sources()
    return [
        SqlDataSourceResponse(
            id=s.id, name=s.name, dialect=s.dialect,
            read_only=s.read_only, has_secret=True, created_at=s.created_at,
        )
        for s in sources
    ]


@router.post("/sql-data-sources", response_model=SqlDataSourceResponse)
def create_sql_data_source(payload: SqlDataSourceCreate):
    s = store.create_sql_data_source(payload)
    return SqlDataSourceResponse(
        id=s.id, name=s.name, dialect=s.dialect,
        read_only=s.read_only, has_secret=True, created_at=s.created_at,
    )


@router.delete("/sql-data-sources/{ds_id}")
def delete_sql_data_source(ds_id: str):
    if not store.delete_sql_data_source(ds_id):
        raise HTTPException(404, "SQL 数据源不存在")
    return {"ok": True}


@router.post("/sql-data-sources/{ds_id}/probe")
def probe_sql_data_source(ds_id: str):
    """测试连接，返回可见表名列表（不含数据）。"""
    ds = store.get_sql_data_source(ds_id)
    if not ds:
        raise HTTPException(404, "SQL 数据源不存在")
    from .datalayer.sql_runner import SqlRunner, SqlRunnerError
    try:
        runner = SqlRunner(ds.connection_string, ds.dialect)
        tables = runner.probe()
        return {"ok": True, "tables": tables}
    except SqlRunnerError as e:
        raise HTTPException(400, str(e))


# ── Excel 数据集（新增） ──────────────────────────────────────

@router.get("/excel-datasets", response_model=list[ExcelDataset])
def list_excel_datasets():
    return store.list_excel_datasets()


@router.post("/excel-datasets", response_model=ExcelDataset)
def create_excel_dataset(payload: ExcelDatasetCreate):
    # 验证路径在 EXCEL_DATA_ROOT 下
    from .datalayer.excel_loader import _validate_path, ExcelLoaderError
    try:
        _validate_path(payload.file_path)
    except ExcelLoaderError as e:
        raise HTTPException(400, str(e))
    return store.create_excel_dataset(payload)


@router.delete("/excel-datasets/{ds_id}")
def delete_excel_dataset(ds_id: str):
    if not store.delete_excel_dataset(ds_id):
        raise HTTPException(404, "Excel 数据集不存在")
    return {"ok": True}
