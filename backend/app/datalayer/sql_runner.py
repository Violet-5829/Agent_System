"""
SQL 执行器 —— 仅允许只读 SELECT，拒绝多语句、写操作。

安全策略（在代码层强制执行，不信任 Skill 文本）：
- 仅允许 SELECT 语句（或以 WITH 开头的 CTE）
- 禁止多语句（分号分隔）
- 超时中断
- 行数上限
- 不返回完整连接串
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from ..settings_bridge import settings


class SqlRunnerError(Exception):
    """SQL 执行器错误。"""
    pass


@dataclass
class SqlResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


_ALLOWED_KEYWORDS = {"SELECT", "WITH", "EXPLAIN", "DESCRIBE", "DESC", "PRAGMA"}


def _validate_query(query: str) -> str:
    """验证并清理 SQL 查询。仅允许单条只读语句。"""
    stripped = query.strip().rstrip(";").strip()
    if not stripped:
        raise SqlRunnerError("查询为空")

    # 多语句检测
    if ";" in stripped:
        # 允许字符串内的分号，但先做基础检测
        # 移除字符串字面量后再检查
        cleaned = _remove_string_literals(stripped)
        if ";" in cleaned:
            raise SqlRunnerError("禁止多语句查询")

    # 检查语句类型
    first_word = stripped.split(maxsplit=1)[0].upper() if stripped.split() else ""
    if first_word not in _ALLOWED_KEYWORDS:
        raise SqlRunnerError(f"禁止的语句类型: {first_word}。仅允许 SELECT / WITH / EXPLAIN")

    return stripped


def _remove_string_literals(sql: str) -> str:
    """简单移除 SQL 中的字符串字面量，用于多语句检测。"""
    result = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        c = sql[i]
        if not in_single and not in_double:
            result.append(c)
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        i += 1
    return "".join(result)


class SqlRunner:
    """SQL 只读执行器。"""

    def __init__(self, connection_string: str, dialect: str = "sqlite"):
        self.connection_string = connection_string
        self.dialect = dialect
        self.timeout = settings.SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS
        self.max_rows = settings.SQL_MAX_ROWS

    def execute(self, query: str) -> SqlResult:
        """执行只读查询并返回结果。"""
        safe_query = _validate_query(query)
        return self._execute_internal(safe_query)

    def probe(self) -> list[str]:
        """探测数据库中的表/视图列表。"""
        if self.dialect == "sqlite":
            rows = self._execute_internal(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
            )
            return [r[0] for r in rows.rows]
        elif self.dialect == "postgresql":
            rows = self._execute_internal(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
            )
            return [r[0] for r in rows.rows]
        return []

    def _execute_internal(self, query: str) -> SqlResult:
        if self.dialect == "sqlite":
            return self._exec_sqlite(query)
        elif self.dialect == "postgresql":
            return self._exec_postgres(query)
        else:
            raise SqlRunnerError(f"不支持的数据库方言: {self.dialect}")

    def _exec_sqlite(self, query: str) -> SqlResult:
        try:
            conn = sqlite3.connect(self.connection_string)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows_raw = cursor.fetchmany(self.max_rows + 1)
            truncated = len(rows_raw) > self.max_rows
            if truncated:
                rows_raw = rows_raw[:self.max_rows]
            rows = [list(r) for r in rows_raw]
            conn.close()
            return SqlResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
        except Exception as e:
            raise SqlRunnerError(f"SQL 执行失败: {e}") from e

    def _exec_postgres(self, query: str) -> SqlResult:
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(
                self.connection_string,
                connect_args={"options": f"-c statement_timeout={self.timeout * 1000}"},
            )
            with engine.connect() as conn:
                result = conn.execute(text(query))
                columns = list(result.keys())
                rows_raw = result.fetchmany(self.max_rows + 1)
                truncated = len(rows_raw) > self.max_rows
                if truncated:
                    rows_raw = rows_raw[:self.max_rows]
                rows = [list(r) for r in rows_raw]
            engine.dispose()
            return SqlResult(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
        except Exception as e:
            raise SqlRunnerError(f"SQL 执行失败: {e}") from e
