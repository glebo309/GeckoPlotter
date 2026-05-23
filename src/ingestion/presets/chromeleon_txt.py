"""Chromeleon chromatogram .txt export format.

Structure:
  Possible header lines before data
  "Raw Data:" marker line
  "Time (min)\tValue (mAU)" header
  Tab-separated numeric data
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


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

        # Extract header metadata
        header_lines = lines[:data_start]
        header_meta = {}
        for line in header_lines:
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            if "\t" in line:
                parts = line.split("\t")
                for i in range(0, len(parts) - 1, 2):
                    if i + 1 < len(parts):
                        key = parts[i].strip().rstrip(":")
                        val = parts[i + 1].strip()
                        if key and val:
                            clean_key = key.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").lower()
                            header_meta[clean_key] = val
            elif ":" in line and not line.startswith("chrom://"):
                key, val = line.split(":", 1)
                key, val = key.strip(), val.strip()
                if key and val:
                    clean_key = key.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").lower()
                    header_meta[clean_key] = val

        # Extract wavelength
        wl_match = re.search(r"WVL:\s*(\d{3})\s*nm", "\n".join(header_lines))
        if wl_match:
            header_meta["wavelength_nm"] = wl_match.group(1)

        # German number conversion (1.234,56 → 1234.56)
        def _convert_german(text):
            text = re.sub(r"\d{1,3}(?:\.\d{3})*,\d+", lambda m: m.group().replace(".", "").replace(",", "."), text)
            return re.sub(r"(\d+),(\d+)", r"\1.\2", text)

        data_text = "\n".join(lines[data_start:])
        data_text = _convert_german(data_text)
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
            "source_category": SourceCategory.CHROMATOGRAM,
            "sample_name": None,
            "metadata": {
                "file_type_detail": "chromeleon_chromatogram",
                "data_points": len(df),
                "time_range": f"{df[cols[0]].min():.2f} - {df[cols[0]].max():.2f} min" if cols else None,
                "value_range": f"{df[cols[1]].min():.1f} - {df[cols[1]].max():.1f} mAU" if len(cols) > 1 else None,
                **header_meta,
            },
        }
