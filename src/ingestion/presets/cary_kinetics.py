"""Cary 300/3500 spectrophotometer kinetics CSV format.

Structure:
  Row 0: sample name (single field)
  Row 1: "Time (min),Abs," (headers with possible trailing comma)
  Rows 2-N: numeric data with trailing commas
  Footer: instrument metadata (Collection Time, Instrument, Wavelength, etc.)
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict, Any

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


_FOOTER_MARKERS = re.compile(
    r"^(Collection Time|Instrument|Current Wavelength|Kinetics Version|"
    r"Operator Name|Method Name|Date/Time stamp|Saved as|End Method)",
    re.IGNORECASE,
)


class CaryKineticsPreset(FormatPreset):
    name = "cary_kinetics"
    extensions = {"csv"}
    priority = 80

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        if len(head_lines) < 3:
            return False
        fields_row0 = [f.strip() for f in head_lines[0].split(",") if f.strip()]
        if len(fields_row0) != 1:
            return False
        row1 = head_lines[1].lower()
        if "time" in row1 and ("abs" in row1 or "value" in row1):
            return True
        return False

    def parse(self, path: str) -> dict:
        lines = _read_lines(path)

        sample_name = lines[0].split(",")[0].strip()
        header_row = 1

        data_end = len(lines)
        for i in range(header_row + 1, len(lines)):
            line = lines[i].strip()
            if not line or _FOOTER_MARKERS.match(line):
                data_end = i
                break

        data_text = "\n".join(lines[header_row:data_end])
        df = pd.read_csv(StringIO(data_text))
        df.columns = [str(c).strip().rstrip(",") for c in df.columns]
        drop = [c for c in df.columns if c.startswith("Unnamed") or c == ""]
        if drop:
            df.drop(columns=drop, inplace=True)
        df.dropna(axis=1, how="all", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        cols = list(df.columns)
        column_roles: Dict[str, ColumnRole] = {}
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        metadata = _parse_footer(lines, data_end)

        return {
            "data": df,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "source_category": SourceCategory.KINETICS,
            "sample_name": sample_name,
            "metadata": metadata,
        }


def _read_lines(path: str) -> list[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [line.rstrip("\n\r") for line in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def _parse_footer(lines: list[str], start: int) -> dict:
    meta: Dict[str, Any] = {"instrument": {}}
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        for sep in [":", "  "]:
            if sep in line:
                parts = line.split(sep, 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                if key and val:
                    meta["instrument"][key] = val
                break
    inst = meta["instrument"].get("Instrument", "")
    if inst:
        meta["instrument_name"] = inst
    wl = meta["instrument"].get("Current Wavelength (nm)", "")
    if wl:
        meta["wavelength"] = wl
    return meta
