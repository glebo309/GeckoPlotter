"""Chromeleon chromatogram .txt export format.

Structure:
  Possible header lines before data
  "Raw Data:" marker line
  "Time (min)\tValue (mAU)" header
  Tab-separated numeric data
"""
from __future__ import annotations
import pandas as pd
from io import StringIO
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


class ChromeleonTxtPreset(FormatPreset):
    name = "chromeleon_txt"
    extensions = {"txt"}
    priority = 80

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        for line in head_lines:
            stripped = line.strip()
            if stripped == "Raw Data:":
                return True
            lower = stripped.lower()
            if "time (min)" in lower and ("value (mau)" in lower or "step (s)" in lower):
                return True
        return False

    def parse(self, path: str) -> dict:
        lines: list[str] = []
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(path, "r", encoding=enc) as f:
                    lines = [l.rstrip("\n\r") for l in f.readlines()]
                break
            except UnicodeDecodeError:
                continue

        data_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "Raw Data:":
                data_start = i + 1
                break
            if "Time (min)" in line:
                data_start = i
                break

        data_text = "\n".join(lines[data_start:])
        df = pd.read_csv(StringIO(data_text), sep="\t")
        df.dropna(axis=1, how="all", inplace=True)
        df.dropna(axis=0, how="all", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(axis=0, how="any", inplace=True)

        cols = list(df.columns)
        column_roles: Dict[str, ColumnRole] = {}
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        return {
            "data": df,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "sample_name": None,
            "metadata": {"file_type_detail": "chromeleon_chromatogram"},
        }
