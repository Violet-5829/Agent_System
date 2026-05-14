"""数据访问层内部模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SqlDataSourceHandle:
    """已解析的 SQL 数据源句柄——由 context_builder 根据 sql_data_source_id 创建。"""
    id: str
    name: str
    dialect: str  # "sqlite" | "postgresql"
    connection_string: str
    read_only: bool = True


@dataclass
class ExcelDatasetHandle:
    """已解析的 Excel 数据集句柄——由 context_builder 根据 excel_dataset_id 创建。"""
    id: str
    name: str
    file_path: str  # 相对于 EXCEL_DATA_ROOT 的路径


@dataclass
class DataContext:
    """
    共享分析上下文 —— 注入到每个子图和 Skill 工具。

    子图不区分 Excel/SQL，只认 materialized_uri + schema_summary。
    """
    # 数据源类型
    data_source_kind: str  # "sql" | "excel"

    # SQL 路径
    sql_source: SqlDataSourceHandle | None = None

    # Excel 路径
    excel_dataset: ExcelDatasetHandle | None = None

    # 统一物化结果（下游子图只读这些）
    materialized_uri: str | None = None  # parquet 路径或逻辑表名 + connection_id
    schema_summary: str | None = None   # 列名、类型、行数估算
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    sql_log: list[str] = field(default_factory=list)  # 已执行 SQL 摘要（脱敏）

    # 产物目录
    artifact_dir: str | None = None

    # 错误信息
    errors: list[dict[str, Any]] = field(default_factory=list)
