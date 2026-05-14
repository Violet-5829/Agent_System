"""
SQLite 元数据存储 —— 与参考仓库表结构对齐，扩展数据分析领域表。

对 Claude Code 阅读者：表结构与参考仓库 Jasper-zh/Multi-Agent-Playground 对齐，
仅新增 sql_data_sources、excel_datasets 两张表，并在 seed 中提供数据分析领域的
默认 Agent、Skill 和 WorkflowTemplate。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

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
    SqlDataSource,
    SqlDataSourceCreate,
    WorkflowDefinition,
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowTemplate,
    WorkflowType,
)
from .settings_bridge import settings


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class SQLitePlaygroundStore:
    """SQLite 持久化存储，兼容 InMemoryPlaygroundStore 接口。"""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(settings.APP_HOME / "playground.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_tables()

    # ── 表初始化 ──────────────────────────────────────────────

    def _ensure_tables(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                model TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                skill_ids TEXT NOT NULL DEFAULT '[]',
                builtin_capabilities TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                specialist_agent_ids TEXT NOT NULL,
                router_prompt TEXT NOT NULL,
                finalizer_enabled INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                instruction TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_provider TEXT,
                source_skill_id TEXT,
                local_path TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_source
                ON skills(source_provider, source_skill_id)
                WHERE source_provider IS NOT NULL AND source_skill_id IS NOT NULL;

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sql_data_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                dialect TEXT NOT NULL,
                connection_string TEXT NOT NULL,
                read_only INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS excel_datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self._conn.commit()

    # ── Agent CRUD ─────────────────────────────────────────────

    def list_agents(self) -> list[AgentDefinition]:
        rows = self._conn.execute("SELECT * FROM agents ORDER BY created_at").fetchall()
        return [self._row_to_agent(r) for r in rows]

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        row = self._conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return self._row_to_agent(row) if row else None

    def create_agent(self, payload: AgentDefinitionCreate) -> AgentDefinition:
        agent_id = _new_id("agent")
        self._conn.execute(
            "INSERT INTO agents (id, name, description, system_prompt, model, skill_ids, builtin_capabilities) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, payload.name, payload.description, payload.system_prompt,
             payload.model, json.dumps(payload.skill_ids), json.dumps(payload.builtin_capabilities)),
        )
        self._conn.commit()
        return self.get_agent(agent_id)  # type: ignore

    def update_agent(self, agent_id: str, payload: AgentDefinitionUpdate) -> AgentDefinition | None:
        existing = self.get_agent(agent_id)
        if not existing:
            return None
        self._conn.execute(
            "UPDATE agents SET name=?, description=?, system_prompt=?, model=?, skill_ids=?, builtin_capabilities=? "
            "WHERE id=?",
            (payload.name, payload.description, payload.system_prompt,
             payload.model, json.dumps(payload.skill_ids), json.dumps(payload.builtin_capabilities), agent_id),
        )
        self._conn.commit()
        return self.get_agent(agent_id)

    def delete_agent(self, agent_id: str) -> bool:
        existing = self.get_agent(agent_id)
        if not existing:
            return False
        self._conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        self._conn.commit()
        return True

    def _row_to_agent(self, row: sqlite3.Row) -> AgentDefinition:
        d = dict(row)
        d["skill_ids"] = json.loads(d.get("skill_ids", "[]"))
        d["builtin_capabilities"] = json.loads(d.get("builtin_capabilities", "[]"))
        return AgentDefinition(**d)

    # ── Workflow CRUD ──────────────────────────────────────────

    def list_workflows(self) -> list[WorkflowDefinition]:
        rows = self._conn.execute("SELECT * FROM workflows ORDER BY created_at").fetchall()
        return [self._row_to_workflow(r) for r in rows]

    def get_workflow(self, workflow_id: str) -> WorkflowDefinition | None:
        row = self._conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        return self._row_to_workflow(row) if row else None

    def create_workflow(self, payload: WorkflowDefinitionCreate) -> WorkflowDefinition:
        wf_id = _new_id("workflow")
        self._conn.execute(
            "INSERT INTO workflows (id, name, type, specialist_agent_ids, router_prompt, finalizer_enabled) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (wf_id, payload.name, payload.type, json.dumps(payload.specialist_agent_ids),
             payload.router_prompt, int(payload.finalizer_enabled)),
        )
        self._conn.commit()
        return self.get_workflow(wf_id)  # type: ignore

    def update_workflow(self, workflow_id: str, payload: WorkflowDefinitionUpdate) -> WorkflowDefinition | None:
        existing = self.get_workflow(workflow_id)
        if not existing:
            return None
        self._conn.execute(
            "UPDATE workflows SET name=?, type=?, specialist_agent_ids=?, router_prompt=?, finalizer_enabled=? "
            "WHERE id=?",
            (payload.name, payload.type, json.dumps(payload.specialist_agent_ids),
             payload.router_prompt, int(payload.finalizer_enabled), workflow_id),
        )
        self._conn.commit()
        return self.get_workflow(workflow_id)

    def delete_workflow(self, workflow_id: str) -> bool:
        existing = self.get_workflow(workflow_id)
        if not existing:
            return False
        self._conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        self._conn.commit()
        return True

    def _row_to_workflow(self, row: sqlite3.Row) -> WorkflowDefinition:
        d = dict(row)
        d["specialist_agent_ids"] = json.loads(d.get("specialist_agent_ids", "[]"))
        d["finalizer_enabled"] = bool(d.get("finalizer_enabled", True))
        return WorkflowDefinition(**d)

    def get_templates(self) -> list[WorkflowTemplate]:
        """返回 5 种工作流模板——描述改为数据分析场景。"""
        return [
            WorkflowTemplate(
                type="single_agent_chat",
                label="单智能体对话",
                description="单一数据分析师在已绑定的数据源上做问答、查询、简单图表与执行摘要。",
                required_agent_count=1,
            ),
            WorkflowTemplate(
                type="router_specialists",
                label="路由专家",
                description="根据用户分析意图自动路由到数据工程、统计分析、可视化或报表专家。",
                required_agent_count=2,
            ),
            WorkflowTemplate(
                type="planner_executor",
                label="规划执行者",
                description="端到端分析任务：规划→校验→分发→执行→合成，含中间产物一致性检查。",
                required_agent_count=2,
            ),
            WorkflowTemplate(
                type="supervisor_dynamic",
                label="监督者动态调度",
                description="监督者动态拆分子任务并分发，适合复杂多步探索性分析。",
                required_agent_count=2,
            ),
            WorkflowTemplate(
                type="peer_handoff",
                label="专家交接",
                description="专家之间流水线式交接：数据工程→分析→可视化→报告，直至收敛。",
                required_agent_count=2,
            ),
        ]

    # ── Skill CRUD ─────────────────────────────────────────────

    def list_skills(self) -> list[SkillDefinition]:
        rows = self._conn.execute("SELECT * FROM skills ORDER BY created_at").fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        row = self._conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
        return self._row_to_skill(row) if row else None

    def create_skill(self, payload: SkillDefinitionCreate) -> SkillDefinition:
        skill_id = _new_id("skill")
        self._conn.execute(
            "INSERT INTO skills (id, name, description, instruction) VALUES (?, ?, ?, ?)",
            (skill_id, payload.name, payload.description, payload.instruction),
        )
        self._conn.commit()
        # 写入文件系统
        skill_dir = settings.APP_HOME / "skills" / f"{payload.name.replace(' ', '_').lower()}__{skill_id}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(payload.instruction, encoding="utf-8")
        self._conn.execute("UPDATE skills SET local_path=? WHERE id=?", (str(skill_dir), skill_id))
        self._conn.commit()
        return self.get_skill(skill_id)  # type: ignore

    def update_skill_tool(self, skill_id: str, tool: dict[str, Any]) -> bool:
        self._conn.execute("UPDATE skills SET source_provider='builtin' WHERE id=?", (skill_id,))
        self._conn.commit()
        return True

    def delete_skill(self, skill_id: str) -> bool:
        skill = self.get_skill(skill_id)
        if not skill:
            return False
        self._conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        self._conn.commit()
        if skill.local_path and os.path.isdir(skill.local_path):
            shutil.rmtree(skill.local_path, ignore_errors=True)
        return True

    def _row_to_skill(self, row: sqlite3.Row) -> SkillDefinition:
        d = dict(row)
        if d.get("local_path"):
            tool_path = Path(d["local_path"]) / "tool.json"
            if tool_path.exists():
                d["tool"] = json.loads(tool_path.read_text(encoding="utf-8"))
        return SkillDefinition(**d)

    # ── Conversation CRUD ──────────────────────────────────────

    def create_conversation(self, payload: ConversationCreate) -> Conversation:
        conv_id = _new_id("conv")
        now = self._now()
        self._conn.execute(
            "INSERT INTO conversations (id, workflow_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, payload.workflow_id, now, now),
        )
        self._conn.commit()
        return Conversation(id=conv_id, workflow_id=payload.workflow_id, title=None, created_at=now, updated_at=now)

    def list_conversations(self, workflow_id: str | None = None) -> list[Conversation]:
        if workflow_id:
            rows = self._conn.execute(
                "SELECT * FROM conversations WHERE workflow_id=? ORDER BY updated_at DESC", (workflow_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [Conversation(**dict(r)) for r in rows]

    def get_conversation(self, conv_id: str) -> ConversationDetail | None:
        row = self._conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if not row:
            return None
        msgs = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conv_id,)
        ).fetchall()
        return ConversationDetail(
            **dict(row),
            messages=[Message(**dict(m)) for m in msgs],
        )

    def update_conversation_title(self, conv_id: str, title: str):
        self._conn.execute(
            "UPDATE conversations SET title=?, updated_at=? WHERE id=?", (title, self._now(), conv_id)
        )
        self._conn.commit()

    def delete_conversation(self, conv_id: str) -> bool:
        existing = self._conn.execute("SELECT id FROM conversations WHERE id=?", (conv_id,)).fetchone()
        if not existing:
            return False
        self._conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        self._conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        self._conn.commit()
        return True

    def add_message(self, conv_id: str, role: str, content: str, agent_name: str | None = None) -> Message:
        msg_id = _new_id("msg")
        now = self._now()
        self._conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, agent_name, created_at) VALUES (?,?,?,?,?,?)",
            (msg_id, conv_id, role, content, agent_name, now),
        )
        self._conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        self._conn.commit()
        return Message(id=msg_id, conversation_id=conv_id, role=role, content=content, agent_name=agent_name, created_at=now)

    def get_recent_messages(self, conv_id: str, limit: int = 2) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?", (conv_id, limit)
        ).fetchall()
        return [Message(**dict(r)) for r in reversed(rows)]

    # ── Settings ───────────────────────────────────────────────

    def get_app_settings_payload(self) -> AppSettings | None:
        row = self._conn.execute("SELECT value FROM app_settings WHERE key='app_settings'").fetchone()
        if not row:
            return None
        return AppSettings(**json.loads(row["value"]))

    def save_app_settings(self, payload: AppSettings):
        self._conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("app_settings", payload.model_dump_json(), self._now()),
        )
        self._conn.commit()

    # ── SQL 数据源 CRUD（新增） ────────────────────────────────

    def list_sql_data_sources(self) -> list[SqlDataSource]:
        rows = self._conn.execute("SELECT * FROM sql_data_sources ORDER BY created_at").fetchall()
        return [SqlDataSource(**dict(r)) for r in rows]

    def get_sql_data_source(self, ds_id: str) -> SqlDataSource | None:
        row = self._conn.execute("SELECT * FROM sql_data_sources WHERE id=?", (ds_id,)).fetchone()
        return SqlDataSource(**dict(row)) if row else None

    def create_sql_data_source(self, payload: SqlDataSourceCreate) -> SqlDataSource:
        ds_id = _new_id("sqlds")
        self._conn.execute(
            "INSERT INTO sql_data_sources (id, name, dialect, connection_string, read_only) VALUES (?,?,?,?,?)",
            (ds_id, payload.name, payload.dialect, payload.connection_string, int(payload.read_only)),
        )
        self._conn.commit()
        return self.get_sql_data_source(ds_id)  # type: ignore

    def delete_sql_data_source(self, ds_id: str) -> bool:
        existing = self.get_sql_data_source(ds_id)
        if not existing:
            return False
        self._conn.execute("DELETE FROM sql_data_sources WHERE id=?", (ds_id,))
        self._conn.commit()
        return True

    # ── Excel 数据集 CRUD（新增） ──────────────────────────────

    def list_excel_datasets(self) -> list[ExcelDataset]:
        rows = self._conn.execute("SELECT * FROM excel_datasets ORDER BY created_at").fetchall()
        return [ExcelDataset(**dict(r)) for r in rows]

    def get_excel_dataset(self, ds_id: str) -> ExcelDataset | None:
        row = self._conn.execute("SELECT * FROM excel_datasets WHERE id=?", (ds_id,)).fetchone()
        return ExcelDataset(**dict(row)) if row else None

    def create_excel_dataset(self, payload: ExcelDatasetCreate) -> ExcelDataset:
        ds_id = _new_id("excelds")
        self._conn.execute(
            "INSERT INTO excel_datasets (id, name, file_path) VALUES (?,?,?)",
            (ds_id, payload.name, payload.file_path),
        )
        self._conn.commit()
        return self.get_excel_dataset(ds_id)  # type: ignore

    def delete_excel_dataset(self, ds_id: str) -> bool:
        existing = self.get_excel_dataset(ds_id)
        if not existing:
            return False
        self._conn.execute("DELETE FROM excel_datasets WHERE id=?", (ds_id,))
        self._conn.commit()
        return True

    # ── Seed ───────────────────────────────────────────────────

    def seed_defaults(self):
        """初始化数据分析领域的默认 Agent、Skill 和工作流模板。"""
        self._seed_skills()
        self._seed_agents()
        self._seed_workflow()

    def _seed_skills(self):
        if self._conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0] > 0:
            return
        skills_def = [
            {
                "name": "SQL 只读查询",
                "description": "在绑定的 SQL 数据源上执行只读 SELECT 查询，自动应用行数限制与超时保护。",
                "instruction": "使用此技能执行 SQL 只读查询。工具会自动注入当前运行绑定的数据源连接，无需手动指定连接串。查询结果将被截断至安全行数上限。",
                "tool": {
                    "name": "analytics_run_sql",
                    "description": "在已绑定的 SQL 数据源上执行只读 SELECT 查询。仅允许 SELECT 语句，禁止多语句、写操作。",
                    "command": ["python", "-m", "app.datalayer.sql_runner"],
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "只读 SQL SELECT 语句"}
                        },
                        "required": ["query"],
                    },
                    "input_mode": "stdin_json",
                    "timeout_seconds": 30,
                },
            },
            {
                "name": "Excel 数据加载",
                "description": "将已注册的 Excel 数据集文件物化为标准化 Parquet 格式，供下游分析子图使用。",
                "instruction": "使用此技能加载 Excel 数据。文件路径来自服务端已注册的 ExcelDataset，由工具自动解析。加载后数据将被标准化为 Parquet 格式。",
                "tool": {
                    "name": "analytics_load_excel",
                    "description": "将已注册的 Excel 数据集物化为 Parquet，返回物化路径和 Schema 摘要。",
                    "command": ["python", "-m", "app.datalayer.excel_loader"],
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "sheet_name": {"type": "string", "description": "可选，指定 Sheet 名称"}
                        },
                    },
                    "input_mode": "stdin_json",
                    "timeout_seconds": 30,
                },
            },
            {
                "name": "图表保存",
                "description": "使用 matplotlib 生成图表并保存到当前运行的 artifacts 目录中。",
                "instruction": "使用此技能生成并保存数据可视化图表。图表将自动保存到本次运行的 artifacts 输出目录。",
                "tool": {
                    "name": "analytics_save_chart",
                    "description": "生成 matplotlib 图表并保存为 PNG 到 artifacts 目录。",
                    "command": ["python", "-m", "app.datalayer.chart_writer"],
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "chart_type": {"type": "string", "description": "图表类型：bar/line/scatter/pie/histogram"},
                            "title": {"type": "string", "description": "图表标题"},
                            "code": {"type": "string", "description": "生成图表的 Python 代码（使用 matplotlib），数据从已物化的 parquet 读取"},
                        },
                        "required": ["chart_type", "title", "code"],
                    },
                    "input_mode": "stdin_json",
                    "timeout_seconds": 30,
                },
            },
            {
                "name": "报表生成",
                "description": "将分析结论写入 Markdown 报表文件，保存到当前运行的 artifacts 目录。",
                "instruction": "使用此技能生成 Markdown 格式的报表，保存到 artifacts 目录。",
                "tool": {
                    "name": "analytics_write_report_md",
                    "description": "将分析结论写入 Markdown 报表文件到 artifacts 目录。",
                    "command": ["python", "-m", "app.datalayer.report_writer"],
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "报表标题"},
                            "content": {"type": "string", "description": "Markdown 格式的报表内容"},
                        },
                        "required": ["title", "content"],
                    },
                    "input_mode": "stdin_json",
                    "timeout_seconds": 30,
                },
            },
        ]
        for s in skills_def:
            tool = s.pop("tool")
            skill_id = _new_id("skill")
            skill_dir = settings.APP_HOME / "skills" / f"{s['name'].replace(' ', '_').lower()}__{skill_id}"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(s["instruction"], encoding="utf-8")
            (skill_dir / "tool.json").write_text(json.dumps(tool, ensure_ascii=False, indent=2), encoding="utf-8")
            self._conn.execute(
                "INSERT INTO skills (id, name, description, instruction, source_provider, local_path) "
                "VALUES (?,?,?,?,?,?)",
                (skill_id, s["name"], s["description"], s["instruction"], "builtin", str(skill_dir)),
            )
        self._conn.commit()

    def _seed_agents(self):
        if self._conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0] > 0:
            return
        skills = {s.name: s for s in self.list_skills()}

        def _skill_ids(*names):
            return [skills[n].id for n in names if n in skills]

        agents_def = [
            {
                "name": "数据工程师",
                "description": "负责数据接入、SQL 查询、Excel 物化、数据清洗与预处理。",
                "system_prompt": (
                    "你是一名数据工程师。你的职责是：\n"
                    "1. 使用 analytics_run_sql 工具执行只读 SQL 查询，探索数据源结构（表名、列名、类型、行数）。\n"
                    "2. 使用 analytics_load_excel 工具加载 Excel 文件并物化为 Parquet。\n"
                    "3. 返回数据的 schema_summary（列名、类型、行数估算）和样本行。\n"
                    "4. 不要执行写操作或多语句；查询失败时报告明确的错误信息。\n"
                    "输出格式：返回数据概要和物化路径，供下游分析专家使用。"
                ),
                "skill_ids": _skill_ids("SQL 只读查询", "Excel 数据加载"),
                "builtin_capabilities": ["filesystem"],
            },
            {
                "name": "数据分析师",
                "description": "负责统计描述、相关性分析、趋势发现、假设检验与数据洞察。",
                "system_prompt": (
                    "你是一名数据分析师。你的职责是：\n"
                    "1. 如果数据源是 Excel/CSV，先用 analytics_load_excel 加载数据，从返回结果中获取列名、类型和行数。\n"
                    "2. 如果数据源是 SQL 数据库，用 analytics_run_sql 查询数据。\n"
                    "3. 获得数据后，基于工具返回的 columns/dtypes/row_count 直接进行分析描述。\n"
                    "4. 计算描述统计量，发现趋势、异常和关联关系。\n"
                    "5. 将分析结论以结构化文本输出，标注关键数字。\n"
                    "重要：Excel/CSV 数据源不支持 SQL 查询！用 analytics_load_excel 加载后直接使用返回结果中的列信息即可。\n"
                    "输出格式：分析报告文本，含关键统计量和洞察。"
                ),
                "skill_ids": _skill_ids("SQL 只读查询", "Excel 数据加载"),
                "builtin_capabilities": ["filesystem"],
            },
            {
                "name": "可视化专家",
                "description": "负责将数据与分析结果转化为图表，输出到 artifacts 目录。",
                "system_prompt": (
                    "你是一名数据可视化专家。你的职责是：\n"
                    "1. 基于上游分析结果和数据，使用 analytics_save_chart 生成图表。\n"
                    "2. 根据数据特点选择合适的图表类型（柱状图、折线图、散点图、饼图、直方图等）。\n"
                    "3. 图表必须包含清晰的标题、轴标签和图例。\n"
                    "4. 图表保存到当前运行的 artifacts 目录。\n"
                    "输出格式：图表文件路径列表和每张图表的简要说明。"
                ),
                "skill_ids": _skill_ids("图表保存"),
                "builtin_capabilities": ["filesystem"],
            },
            {
                "name": "报表专家",
                "description": "负责综合前面的分析结果，撰写结构化的 Markdown 分析报表。",
                "system_prompt": (
                    "你是一名报表专家。你的职责是：\n"
                    "1. 综合所有上游输出（数据概览、分析结论、图表），撰写完整的 Markdown 报表。\n"
                    "2. 报表结构：摘要 → 数据概览 → 分析过程 → 关键发现 → 图表 → 建议。\n"
                    "3. 使用 analytics_write_report_md 将报表保存到 artifacts 目录。\n"
                    "4. 报表语言应专业但不晦涩，面向业务决策者。\n"
                    "输出格式：报表文本内容和报表文件路径。"
                ),
                "skill_ids": _skill_ids("报表生成"),
                "builtin_capabilities": ["filesystem"],
            },
        ]
        for a in agents_def:
            agent_id = _new_id("agent")
            self._conn.execute(
                "INSERT INTO agents (id, name, description, system_prompt, skill_ids, builtin_capabilities) "
                "VALUES (?,?,?,?,?,?)",
                (agent_id, a["name"], a["description"], a["system_prompt"],
                 json.dumps(a["skill_ids"]), json.dumps(a["builtin_capabilities"])),
            )
        self._conn.commit()

    def _seed_workflow(self):
        if self._conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] > 0:
            return
        agents = self.list_agents()
        if len(agents) < 4:
            return
        engineer_id = agents[0].id
        analyst_id = agents[1].id
        viz_id = agents[2].id
        reporter_id = agents[3].id

        defaults = [
            {
                "name": "单分析师快速查询",
                "type": "single_agent_chat",
                "specialist_agent_ids": [analyst_id],
                "router_prompt": "用户输入数据分析问题，直接交给分析师处理。",
                "finalizer_enabled": True,
            },
            {
                "name": "分析任务路由",
                "type": "router_specialists",
                "specialist_agent_ids": [engineer_id, analyst_id, viz_id, reporter_id],
                "router_prompt": (
                    "根据用户意图选择最合适的专家：\n"
                    "- 涉及数据加载、SQL 查询、数据预处理 → 数据工程师\n"
                    "- 涉及统计分析、趋势发现、相关性 → 数据分析师\n"
                    "- 涉及图表生成、可视化 → 可视化专家\n"
                    "- 涉及报告撰写、综合分析 → 报表专家"
                ),
                "finalizer_enabled": True,
            },
            {
                "name": "端到端分析流水线",
                "type": "planner_executor",
                "specialist_agent_ids": [engineer_id, analyst_id, viz_id, reporter_id],
                "router_prompt": "端到端数据分析：规划→校验→分发→执行→合成。",
                "finalizer_enabled": True,
            },
            {
                "name": "动态监督分析",
                "type": "supervisor_dynamic",
                "specialist_agent_ids": [engineer_id, analyst_id, viz_id, reporter_id],
                "router_prompt": "监督者动态拆分子任务并分发给最合适的专家，适合复杂多步探索。",
                "finalizer_enabled": True,
            },
            {
                "name": "专家交接流水线",
                "type": "peer_handoff",
                "specialist_agent_ids": [engineer_id, analyst_id, viz_id, reporter_id],
                "router_prompt": "数据工程→分析→可视化→报告顺序交接。",
                "finalizer_enabled": True,
            },
        ]
        for wf in defaults:
            wf_id = _new_id("workflow")
            self._conn.execute(
                "INSERT INTO workflows (id, name, type, specialist_agent_ids, router_prompt, finalizer_enabled) "
                "VALUES (?,?,?,?,?,?)",
                (wf_id, wf["name"], wf["type"], json.dumps(wf["specialist_agent_ids"]),
                 wf["router_prompt"], int(wf["finalizer_enabled"])),
            )
        self._conn.commit()

    # ── 工具方法 ───────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def close(self):
        self._conn.close()


# 单例 / 兼容别名
store = SQLitePlaygroundStore()
InMemoryPlaygroundStore = SQLitePlaygroundStore
