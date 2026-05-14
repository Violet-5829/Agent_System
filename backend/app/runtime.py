"""
LLM 运行时 —— LLMGateway + 工具注册与执行。

与参考仓库 runtime.py 模式对齐，扩展数据分析 Skill 工具支持。
Skill 工具内部调用 datalayer（sql_runner/excel_loader），注入 DataContext。
"""

from __future__ import annotations

import json
import os
import subprocess
import traceback
from typing import Any, Callable

from openai import OpenAI

from .schemas import AgentDefinition, SkillDefinition
from .settings_bridge import settings

ToolTraceHook = Callable[[dict[str, Any]], None]


class LLMGateway:
    """LLM 网关 —— 管理 OpenAI 客户端、工具注册与 Agent 执行。"""

    def __init__(self):
        self.client: OpenAI | None = None
        self.api_configured = False
        self.refresh_client()

    def refresh_client(self):
        api_key = settings.OPENAI_API_KEY
        base_url = settings.OPENAI_BASE_URL
        if api_key and base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.api_configured = True
        else:
            self.client = None
            self.api_configured = False

    # ── Agent 执行 ──────────────────────────────────────────

    def run_agent(
        self,
        agent: AgentDefinition,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        tool_trace_hook: ToolTraceHook | None = None,
        data_context: Any = None,
    ) -> str:
        """
        执行 Agent —— 合并 BuiltinCapability 工具 + Skill 工具，
        调用 OpenAI chat completions API，处理工具调用循环。
        """
        if not self.api_configured or self.client is None:
            return self._fallback(agent, user_input, data_context)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": agent.system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        tools = self._build_tools(agent)
        tool_registry = self._build_tool_registry(agent, data_context)

        max_rounds = 4
        for _round in range(max_rounds):
            try:
                response = self.client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=messages,
                    tools=tools if tools else None,
                    temperature=0.1,
                )
            except Exception as e:
                return f"[LLM 调用失败] {e}"

            choice = response.choices[0]
            msg = choice.message

            # 构建 assistant 消息（含 tool_calls + reasoning_content）
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                assistant_msg["content"] = msg.content
            # DeepSeek V4 thinking mode: 必须回传 reasoning_content
            reasoning = getattr(msg, "reasoning_content", None) or (
                msg.model_extra.get("reasoning_content") if hasattr(msg, "model_extra") and msg.model_extra else None
            )
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if not msg.tool_calls:
                return msg.content or ""

            # 处理工具调用
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                if tool_trace_hook:
                    tool_trace_hook({"stage": "tool_started", "tool": tool_name, "args": tool_args})

                handler = tool_registry.get(tool_name)
                if handler:
                    try:
                        result = handler(tool_args)
                        if tool_trace_hook:
                            tool_trace_hook({"stage": "tool_finished", "tool": tool_name, "ok": True})
                    except Exception as e:
                        result = {"error": str(e)}
                        if tool_trace_hook:
                            tool_trace_hook({"stage": "tool_finished", "tool": tool_name, "ok": False, "error": str(e)})
                else:
                    result = {"error": f"未知工具: {tool_name}"}
                    if tool_trace_hook:
                        tool_trace_hook({"stage": "tool_blocked", "tool": tool_name})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return messages[-1].get("content", "")

    def _fallback(self, agent: AgentDefinition, user_input: str, data_context: Any = None) -> str:
        """无 API 时的回退响应。"""
        if data_context:
            return (
                f"[离线模式] Agent「{agent.name}」收到任务：{user_input}\n"
                f"数据源类型：{data_context.data_source_kind}\n"
                f"物化路径：{data_context.materialized_uri}\n"
                f"（请配置 OPENAI_API_KEY 以启用 LLM 分析）"
            )
        return f"[离线模式] Agent「{agent.name}」收到任务：{user_input}（请配置 OPENAI_API_KEY）"

    # ── 工具构建 ──────────────────────────────────────────

    def _build_tools(self, agent: AgentDefinition) -> list[dict[str, Any]]:
        """构建 OpenAI tools 定义列表。"""
        tools: list[dict[str, Any]] = []

        # BuiltinCapability → 内置文件系统工具
        for cap in agent.builtin_capabilities:
            builtin = self._builtin_tool_defs().get(cap)
            if builtin:
                tools.extend(builtin)

        # Skill 工具
        from .store import store as _store
        for sid in agent.skill_ids:
            skill = _store.get_skill(sid)
            if skill and skill.tool:
                tools.append(self._skill_to_openai_tool(skill))

        return tools

    def _build_tool_registry(self, agent: AgentDefinition, data_context: Any = None) -> dict[str, Callable]:
        """构建工具名 → 处理函数的注册表。"""
        registry: dict[str, Callable] = {}

        # 内置文件系统工具
        for cap in agent.builtin_capabilities:
            handlers = self._builtin_handlers().get(cap, {})
            registry.update(handlers)

        # Skill 工具 → 映射到 datalayer
        from .store import store as _store
        for sid in agent.skill_ids:
            skill = _store.get_skill(sid)
            if skill and skill.tool:
                tool_name = skill.tool["name"]
                registry[tool_name] = self._make_skill_handler(skill, data_context)

        return registry

    def _make_skill_handler(self, skill: SkillDefinition, data_context: Any = None) -> Callable:
        """为 Skill 工具创建处理函数，内部调用 datalayer。"""
        tool = skill.tool or {}
        tool_name = tool.get("name", "")

        def handler(args: dict[str, Any]) -> dict[str, Any]:
            return self._execute_skill_tool(tool_name, args, data_context)

        return handler

    def _execute_skill_tool(self, tool_name: str, args: dict[str, Any], data_context: Any = None) -> dict[str, Any]:
        """执行数据分析 Skill 工具（安全沙箱内）。"""
        artifact_dir = data_context.artifact_dir if data_context else os.getcwd()

        if tool_name == "analytics_run_sql":
            if not data_context or not data_context.sql_source:
                return {"error": "未绑定 SQL 数据源"}
            from .datalayer.sql_runner import SqlRunner, SqlRunnerError
            try:
                runner = SqlRunner(
                    data_context.sql_source.connection_string,
                    data_context.sql_source.dialect,
                )
                result = runner.execute(args.get("query", ""))
                # 记录到 sql_log
                if data_context:
                    data_context.sql_log.append(
                        f"[{data_context.sql_source.dialect}] {args.get('query', '')[:200]}"
                    )
                return {
                    "columns": result.columns,
                    "rows": result.rows[:20],
                    "row_count": result.row_count,
                    "truncated": result.truncated,
                }
            except SqlRunnerError as e:
                return {"error": str(e)}

        elif tool_name == "analytics_load_excel":
            if not data_context or not data_context.excel_dataset:
                return {"error": "未绑定 Excel 数据集"}
            from .datalayer.excel_loader import ExcelLoader, ExcelLoaderError
            try:
                loader = ExcelLoader()
                result = loader.load(
                    data_context.excel_dataset.file_path,
                    artifact_dir,
                    sheet_name=args.get("sheet_name"),
                )
                # 更新 DataContext
                data_context.materialized_uri = result.materialized_path
                data_context.schema_summary = (
                    f"列: {result.columns}, 类型: {result.dtypes}, 行数: {result.row_count}"
                )
                return {
                    "columns": result.columns,
                    "dtypes": result.dtypes,
                    "row_count": result.row_count,
                    "materialized_path": result.materialized_path,
                }
            except ExcelLoaderError as e:
                return {"error": str(e)}

        elif tool_name == "analytics_save_chart":
            args["artifact_dir"] = artifact_dir
            return self._run_subprocess_tool(
                ["python", "-m", "app.datalayer.chart_writer"], args, tool_name
            )

        elif tool_name == "analytics_write_report_md":
            args["artifact_dir"] = artifact_dir
            return self._run_subprocess_tool(
                ["python", "-m", "app.datalayer.report_writer"], args, tool_name
            )

        return {"error": f"不支持的工具: {tool_name}"}

    def _run_subprocess_tool(self, command: list[str], args: dict[str, Any], tool_name: str) -> dict[str, Any]:
        """通过子进程执行工具（沙箱隔离）。"""
        try:
            proc = subprocess.run(
                command,
                input=json.dumps(args, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.dirname(os.path.dirname(__file__)),
            )
            if proc.returncode != 0:
                return {"error": proc.stderr or f"{tool_name} 执行失败"}
            return json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            return {"error": f"{tool_name} 执行超时"}
        except Exception as e:
            return {"error": str(e)}

    # ── 内置文件系统工具 ─────────────────────────────────

    @staticmethod
    def _builtin_tool_defs() -> dict[str, list[dict[str, Any]]]:
        """返回 BuiltinCapability → OpenAI tool defs 的映射。"""
        return {
            "filesystem": [
                {
                    "type": "function",
                    "function": {
                        "name": "fs_list_directory",
                        "description": "列出目录内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "目录路径"}
                            },
                            "required": ["path"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "fs_read_file",
                        "description": "读取文件内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "文件路径"}
                            },
                            "required": ["path"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "fs_write_file",
                        "description": "写入文件",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "文件路径"},
                                "content": {"type": "string", "description": "文件内容"},
                            },
                            "required": ["path", "content"],
                        },
                    },
                },
            ],
            "fs_list": [
                {
                    "type": "function",
                    "function": {
                        "name": "fs_list_directory",
                        "description": "列出目录内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "目录路径"}
                            },
                            "required": ["path"],
                        },
                    },
                },
            ],
            "fs_read": [
                {
                    "type": "function",
                    "function": {
                        "name": "fs_read_file",
                        "description": "读取文件内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "文件路径"}
                            },
                            "required": ["path"],
                        },
                    },
                },
            ],
            "fs_write": [
                {
                    "type": "function",
                    "function": {
                        "name": "fs_write_file",
                        "description": "写入文件",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "文件路径"},
                                "content": {"type": "string", "description": "文件内容"},
                            },
                            "required": ["path", "content"],
                        },
                    },
                },
            ],
        }

    @staticmethod
    def _builtin_handlers() -> dict[str, dict[str, Callable]]:
        """返回 BuiltinCapability → {tool_name: handler} 的映射。"""
        return {
            "filesystem": {
                "fs_list_directory": lambda a: {"files": os.listdir(a.get("path", "."))},
                "fs_read_file": lambda a: {"content": open(a["path"], encoding="utf-8").read()},
                "fs_write_file": lambda a: (
                    os.makedirs(os.path.dirname(a["path"]) or ".", exist_ok=True),
                    open(a["path"], "w", encoding="utf-8").write(a["content"]),
                    {"written": a["path"]},
                )[-1],
            },
            "fs_list": {
                "fs_list_directory": lambda a: {"files": os.listdir(a.get("path", "."))},
            },
            "fs_read": {
                "fs_read_file": lambda a: {"content": open(a["path"], encoding="utf-8").read()},
            },
            "fs_write": {
                "fs_write_file": lambda a: (
                    os.makedirs(os.path.dirname(a["path"]) or ".", exist_ok=True),
                    open(a["path"], "w", encoding="utf-8").write(a["content"]),
                    {"written": a["path"]},
                )[-1],
            },
        }

    @staticmethod
    def _skill_to_openai_tool(skill: SkillDefinition) -> dict[str, Any]:
        """将 Skill 的 tool 定义转为 OpenAI function-calling 格式。"""
        t = skill.tool or {}
        return {
            "type": "function",
            "function": {
                "name": t.get("name", "unknown"),
                "description": t.get("description", skill.description),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }

    # ── 辅助方法 ──────────────────────────────────────────

    def route(self, user_input: str, agents: list[AgentDefinition]) -> tuple[str, str]:
        """LLM 路由（含关键词回退）。"""
        if not self.api_configured or self.client is None:
            return self._fallback_route(user_input, agents)

        names = "\n".join(f"- {a.id}: {a.name} - {a.description}" for a in agents)
        prompt = (
            f"用户输入：{user_input}\n\n"
            f"可用专家：\n{names}\n\n"
            "请选择最合适的专家。只返回专家 ID（如 agent_xxx），不要返回其他内容。"
        )
        try:
            resp = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            choice = (resp.choices[0].message.content or "").strip()
            # 尝试匹配 agent_id
            for a in agents:
                if a.id in choice:
                    return a.id, a.name
        except Exception:
            pass
        return self._fallback_route(user_input, agents)

    def _fallback_route(self, user_input: str, agents: list[AgentDefinition]) -> tuple[str, str]:
        """关键词回退路由。"""
        keywords_map = {
            "sql": ["sql", "查询", "数据库", "表", "select", "数据源", "工程", "加载"],
            "分析": ["分析", "统计", "趋势", "相关", "描述", "洞察"],
            "图表": ["图表", "可视化", "图", "柱状", "折线", "饼", "散点"],
            "报表": ["报表", "报告", "markdown", "总结", "综合"],
        }
        for agent in agents:
            patterns = keywords_map.get(agent.name, [])
            for kw in patterns:
                if kw in user_input:
                    return agent.id, agent.name
        # 默认返回第一个
        return agents[0].id, agents[0].name if agents else ("", "")

    def plan_tasks(self, user_input: str, max_tasks: int = 5, force_multi: bool = False, agents: list[AgentDefinition] | None = None) -> tuple[list[str], str]:
        """LLM 任务分解（含回退）。"""
        if not self.api_configured or self.client is None:
            return self._fallback_plan(user_input, max_tasks)

        prompt = f"将以下数据分析任务分解为 {max_tasks} 个以内的子任务，每行一个：\n{user_input}"
        try:
            resp = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            tasks = [t.strip("- ").strip() for t in (resp.choices[0].message.content or "").split("\n") if t.strip()]
            return (tasks[:max_tasks], "llm")
        except Exception:
            return self._fallback_plan(user_input, max_tasks)

    def _fallback_plan(self, user_input: str, max_tasks: int = 5) -> tuple[list[str], str]:
        """回退任务分解。"""
        return ([user_input], "fallback")

    def finalize(self, user_input: str, agent: AgentDefinition, specialist_answer: str) -> str:
        """生成最终摘要。"""
        if not self.api_configured or self.client is None:
            return specialist_answer
        prompt = (
            f"用户问题：{user_input}\n"
            f"专家回答：{specialist_answer}\n"
            "请基于以上内容生成一份简洁的最终摘要（中文，200字以内）。"
        )
        try:
            resp = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return specialist_answer

    def build_skill_preflight(self, skill: SkillDefinition) -> dict[str, Any]:
        """验证 Skill 工具可执行性。"""
        t = skill.tool or {}
        if not t:
            return {"ready": False, "reason": "无 tool 定义"}
        return {"ready": True, "tool_name": t.get("name"), "command": t.get("command")}


# 模块级单例
llm_gateway = LLMGateway()


def call_llm(prompt: str, temperature: float = 0, model: str | None = None) -> str:
    """独立 LLM 调用（供工作流内部 prompt 使用）。"""
    gateway = LLMGateway()
    if not gateway.api_configured or gateway.client is None:
        raise RuntimeError("OpenAI API 未配置")
    response = gateway.client.chat.completions.create(
        model=model or settings.OPENAI_MODEL,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return (response.choices[0].message.content or "").strip()
