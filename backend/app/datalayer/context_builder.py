"""
DataContext 构建器 —— 根据请求参数构建注入子图的共享分析上下文。
"""

from __future__ import annotations

from pathlib import Path

from ..store import SQLitePlaygroundStore
from .excel_loader import ExcelLoader, _validate_path
from .models import DataContext, ExcelDatasetHandle, SqlDataSourceHandle


class ContextBuilderError(Exception):
    """上下文构建错误。"""
    pass


class ContextBuilder:
    """从 store 和请求参数构建 DataContext。"""

    def __init__(self, store: SQLitePlaygroundStore):
        self.store = store

    def build(
        self,
        sql_data_source_id: str | None = None,
        excel_dataset_id: str | None = None,
        artifact_dir: str | None = None,
    ) -> DataContext | None:
        """
        构建 DataContext。sql_data_source_id 和 excel_dataset_id 至多选一。
        如果两者都未提供，返回 None（调用方需报错）。
        """
        if sql_data_source_id and excel_dataset_id:
            raise ContextBuilderError("只能选择 SQL 数据源或 Excel 数据集，不能同时选择")

        if not sql_data_source_id and not excel_dataset_id:
            return None

        if sql_data_source_id:
            return self._build_sql(sql_data_source_id, artifact_dir)
        else:
            return self._build_excel(excel_dataset_id, artifact_dir)  # type: ignore

    def _build_sql(self, ds_id: str, artifact_dir: str | None) -> DataContext:
        ds = self.store.get_sql_data_source(ds_id)
        if not ds:
            raise ContextBuilderError(f"SQL 数据源不存在: {ds_id}")

        handle = SqlDataSourceHandle(
            id=ds.id,
            name=ds.name,
            dialect=ds.dialect,
            connection_string=ds.connection_string,
            read_only=ds.read_only,
        )

        return DataContext(
            data_source_kind="sql",
            sql_source=handle,
            materialized_uri=f"sql://{ds.dialect}/{ds.id}",
            artifact_dir=artifact_dir,
        )

    def _build_excel(self, ds_id: str, artifact_dir: str | None) -> DataContext:
        ds = self.store.get_excel_dataset(ds_id)
        if not ds:
            raise ContextBuilderError(f"Excel 数据集不存在: {ds_id}")

        handle = ExcelDatasetHandle(
            id=ds.id,
            name=ds.name,
            file_path=ds.file_path,
        )

        return DataContext(
            data_source_kind="excel",
            excel_dataset=handle,
            materialized_uri=f"excel://{ds.id}/{Path(ds.file_path).name}",
            artifact_dir=artifact_dir,
        )
