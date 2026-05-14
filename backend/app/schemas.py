from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── 枚举类型（与参考仓库字面量完全一致） ──────────────────────────

WorkflowType = Literal[
    "router_specialists",
    "planner_executor",
    "supervisor_dynamic",
    "single_agent_chat",
    "peer_handoff",
]

BuiltinCapability = Literal[
    "filesystem",
    "fs_list",
    "fs_read",
    "fs_write",
]

TraceEventType = Literal[
    "run_started",
    "node_entered",
    "node_exited",
    "route_selected",
    "message_generated",
    "state_updated",
    "run_finished",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Skill ──────────────────────────────────────────────────────

class SkillDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=200)
    instruction: str = Field(min_length=1)


class SkillDefinition(SkillDefinitionCreate):
    id: str
    source_provider: str | None = None
    source_skill_id: str | None = None
    tool: dict[str, Any] | None = None
    local_path: str | None = None
    runtime_preflight: dict[str, Any] | None = None


class SkillSyncRequest(BaseModel):
    provider: Literal["skillhub"] = "skillhub"
    query: str | None = Field(default="search", max_length=80)
    limit: int = Field(default=40, ge=1, le=100)


class SkillSyncResponse(BaseModel):
    provider: str
    query: str
    fetched: int
    imported: int
    updated: int


class SkillInstallResponse(BaseModel):
    skill_id: str
    skill_name: str
    source_provider: str | None = None
    source_skill_id: str | None = None
    downloaded_files: int = 0
    tool_enabled: bool = False
    message: str


# ── Agent ──────────────────────────────────────────────────────

class AgentDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1)
    model: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    builtin_capabilities: list[BuiltinCapability] = Field(default_factory=list)


class AgentDefinition(AgentDefinitionCreate):
    id: str


class AgentDefinitionUpdate(AgentDefinitionCreate):
    pass


# ── Workflow ───────────────────────────────────────────────────

class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: WorkflowType
    specialist_agent_ids: list[str] = Field(default_factory=list)
    router_prompt: str = "你是一个工作流路由器。根据用户意图选择最合适的专家。"
    finalizer_enabled: bool = True


class WorkflowDefinition(WorkflowDefinitionCreate):
    id: str


class WorkflowDefinitionUpdate(WorkflowDefinitionCreate):
    pass


class WorkflowTemplate(BaseModel):
    type: WorkflowType
    label: str
    description: str
    required_agent_count: int


class WorkflowNode(BaseModel):
    id: str
    label: str
    kind: Literal["start", "logic", "agent", "final", "end", "group"]
    parent_id: str | None = None


class WorkflowEdge(BaseModel):
    source: str
    target: str
    label: str | None = None


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]


# ── Trace ──────────────────────────────────────────────────────

class TraceEvent(BaseModel):
    type: TraceEventType
    title: str
    detail: str
    at: str = Field(default_factory=utc_now_iso)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Run ────────────────────────────────────────────────────────

class RunArtifacts(BaseModel):
    # 参考字段
    route_agent_id: str | None = None
    route_agent_name: str | None = None
    route_reason: str | None = None
    specialist_answer: str | None = None
    final_answer: str | None = None
    # 新增数据分析字段（均为可选）
    dataset_summary: str | None = None
    materialized_paths: list[str] | None = None
    chart_paths: list[str] | None = None
    report_path: str | None = None
    queries_used: list[str] | None = None


class WorkflowRunRequest(BaseModel):
    workflow_id: str
    user_input: str = Field(min_length=1)
    conversation_id: str | None = None
    # 新增：数据源绑定
    sql_data_source_id: str | None = None
    excel_dataset_id: str | None = None


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    user_input: str
    assistant_message: str
    trace: list[TraceEvent]
    graph: WorkflowGraph
    artifacts: RunArtifacts
    conversation_id: str | None = None


# ── Conversation ───────────────────────────────────────────────

class ConversationCreate(BaseModel):
    workflow_id: str


class Conversation(ConversationCreate):
    id: str
    title: str | None = None
    created_at: str
    updated_at: str


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    agent_name: str | None = None
    created_at: str


class ConversationDetail(Conversation):
    messages: list[Message] = Field(default_factory=list)


# ── Settings ───────────────────────────────────────────────────

class ModelProfile(BaseModel):
    id: str
    provider: str = "custom"
    name: str = "Default"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"


class EnvVarEntry(BaseModel):
    key: str = Field(min_length=1)
    value: str = ""


class AppSettings(BaseModel):
    model_profiles: list[ModelProfile] = Field(default_factory=list)
    active_model_profile_id: str | None = None
    env_vars: list[EnvVarEntry] = Field(default_factory=list)
    env_path: str = ""


# ── 数据源（新增） ──────────────────────────────────────────────

class SqlDataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dialect: Literal["sqlite", "postgresql"] = "sqlite"
    connection_string: str = Field(min_length=1)
    read_only: bool = True


class SqlDataSource(SqlDataSourceCreate):
    id: str
    has_secret: bool = True
    created_at: str = Field(default_factory=utc_now_iso)


class SqlDataSourceResponse(BaseModel):
    """API 响应中不返回明文连接串"""
    id: str
    name: str
    dialect: str
    read_only: bool
    has_secret: bool
    created_at: str


class ExcelDatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    file_path: str = Field(min_length=1)


class ExcelDataset(ExcelDatasetCreate):
    id: str
    created_at: str = Field(default_factory=utc_now_iso)
