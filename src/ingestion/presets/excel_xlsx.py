"""Excel (.xlsx / .xls) format support.

Reads all sheets from an Excel workbook. The first non-empty sheet
becomes the primary data; all sheets are stored in metadata['sheets']
so the UI can offer sheet-tab switching.
"""
from __future__ import annotations
import logging
import pandas as pd
from typing import Dict, Any

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory
from ..stage_3_heuristic import _detect_column_roles, _infer_source_category, _choose_plot_hint

log = logging.getLogger(__name__)

_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


class ExcelPreset(FormatPreset):
    name = "excel"
    extensions = {"xlsx", "xls"}
    priority = 85

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        return (
            head_bytes[:4] == _XLSX_MAGIC
            or head_bytes[:4] == _XLS_MAGIC
        )

    def parse(self, path: str) -> dict:
        all_sheets = pd.read_excel(path, sheet_name=None, engine=None)

        sheets_clean: Dict[str, pd.DataFrame] = {}
        primary_name = None
        primary_df = None

        for name, df in all_sheets.items():
            df = _clean_sheet(df)
            if df.empty or df.shape[1] < 2:
                continue
            sheets_clean[name] = df
            if primary_df is None:
                primary_name = name
                primary_df = df

        if primary_df is None:
            raise ValueError("No usable sheets found in workbook")

        column_roles = _detect_column_roles(primary_df)
        cat = _infer_source_category(primary_df, column_roles)
        plot_hint = _choose_plot_hint(primary_df, column_roles)

        sheet_names = list(sheets_clean.keys())

        metadata: Dict[str, Any] = {
            "sheet_names": sheet_names,
            "active_sheet": primary_name,
            "sheet_count": len(sheet_names),
        }

        # Store all sheet DataFrames for tab switching
        sheets_data = {}
        for sname, sdf in sheets_clean.items():
            roles = _detect_column_roles(sdf)
            sheets_data[sname] = {
                "data": sdf,
                "column_roles": roles,
                "source_category": _infer_source_category(sdf, roles),
                "plot_hint": _choose_plot_hint(sdf, roles),
            }
        metadata["sheets"] = sheets_data

        return {
            "data": primary_df,
            "column_roles": column_roles,
            "plot_hint": plot_hint,
            "source_category": cat,
            "sample_name": None,
            "metadata": metadata,
        }


def _clean_sheet(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")

    unnamed_count = sum(1 for c in df.columns if str(c).startswith("Unnamed"))
    if unnamed_count > len(df.columns) * 0.5:
        df = _find_header_and_reparse(df)

    drop = [c for c in df.columns if str(c).startswith("Unnamed")]
    if drop:
        df = df.drop(columns=drop)

    df.columns = [str(c).strip() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().sum() > len(df) * 0.5:
                df[col] = numeric

    return df


def _find_header_and_reparse(df: pd.DataFrame) -> pd.DataFrame:
    """When pandas couldn't find headers, scan rows for a plausible header."""
    for i in range(min(20, len(df))):
        row = df.iloc[i]
        non_null = row.dropna()
        if len(non_null) < 2:
            continue
        text_vals = [str(v) for v in non_null.values]
        numeric_count = sum(1 for v in text_vals if _is_numeric(v))
        text_count = len(text_vals) - numeric_count
        # Header row: mostly text, at least 2 text labels, and the row below has data
        if text_count >= 2 and text_count > numeric_count:
            if i + 1 < len(df):
                next_row = df.iloc[i + 1].dropna()
                if len(next_row) >= 2:
                    new_headers = [str(v).strip() if pd.notna(v) else f"col_{j}"
                                   for j, v in enumerate(df.iloc[i])]
                    df = df.iloc[i + 1:].reset_index(drop=True)
                    df.columns = new_headers
                    return df
    return df


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False
