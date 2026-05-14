"""
Excel 加载器 —— 将 Excel 文件物化为 Parquet 格式。

安全策略：
- 路径必须在 EXCEL_DATA_ROOT 白名单下
- 拒绝路径穿越攻击（.. 等）
- 物化结果写入 artifacts 目录，下游统一使用 parquet
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..settings_bridge import settings


class ExcelLoaderError(Exception):
    """Excel 加载器错误。"""
    pass


@dataclass
class ExcelLoadResult:
    columns: list[str]
    dtypes: dict[str, str]
    row_count: int
    materialized_path: str
    sheet_name: str | None = None


def _validate_path(file_path: str) -> Path:
    """校验路径在 EXCEL_DATA_ROOT 下，拒绝路径穿越。"""
    root = Path(settings.EXCEL_DATA_ROOT).resolve()
    # 支持相对路径
    p = (root / file_path).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ExcelLoaderError(f"文件路径不在允许的目录下: {file_path}")
    # 拒绝路径穿越
    if ".." in file_path:
        raise ExcelLoaderError(f"路径包含非法字符: {file_path}")
    return p


class ExcelLoader:
    """Excel 文件 → DataFrame → Parquet 物化。"""

    def load(
        self,
        file_path: str,
        artifact_dir: str,
        sheet_name: str | None = None,
    ) -> ExcelLoadResult:
        """加载 Excel 并物化为 parquet。"""
        abs_path = _validate_path(file_path)
        if not abs_path.exists():
            raise ExcelLoaderError(f"文件不存在: {abs_path}")

        try:
            suffix = abs_path.suffix.lower()
            if suffix == ".csv":
                df = pd.read_csv(abs_path)
            elif suffix in (".xls", ".xlsx", ".xlsm"):
                if sheet_name:
                    df = pd.read_excel(abs_path, sheet_name=sheet_name, engine="openpyxl")
                else:
                    df = pd.read_excel(abs_path, engine="openpyxl")
            else:
                raise ExcelLoaderError(f"不支持的文件格式: {suffix}，支持 .csv/.xls/.xlsx")
        except Exception as e:
            raise ExcelLoaderError(f"文件读取失败: {e}") from e

        if df.empty:
            raise ExcelLoaderError("Excel 文件为空")

        # 物化
        os.makedirs(artifact_dir, exist_ok=True)
        parquet_path = os.path.join(artifact_dir, "input.parquet")
        df.to_parquet(parquet_path, index=False)

        return ExcelLoadResult(
            columns=list(df.columns),
            dtypes={c: str(df[c].dtype) for c in df.columns},
            row_count=len(df),
            materialized_path=parquet_path,
            sheet_name=sheet_name,
        )

    @staticmethod
    def read_parquet(parquet_path: str, max_rows: int = 100) -> pd.DataFrame:
        """读取已物化的 parquet 文件（用于下游子图）。"""
        return pd.read_parquet(parquet_path).head(max_rows)
