"""UV-Vis plate reader CSV format (e.g. SpectraMax, Tecan, Synergy H1).

Detected by presence of "Wavelength" among the first few fields in a
comma-separated line within the file header.  Handles leading empty
columns (common in Synergy H1 exports).
"""
from __future__ import annotations
import pandas as pd
from io import StringIO
from typing import Dict, List, Optional, Tuple

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


def _find_wavelength_field(fields: List[str]) -> int:
    """Return the index of the 'Wavelength' field, or -1 if not found."""
    for i, f in enumerate(fields[:3]):
        if f == "Wavelength":
            return i
    return -1


class PlateReaderCSVPreset(FormatPreset):
    name = "plate_reader_csv"
    extensions = {"csv"}
    priority = 90

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        for line in head_lines:
            fields = [f.strip() for f in line.split(",")]
            if _find_wavelength_field(fields) >= 0 and len(fields) >= 3:
                return True
        return False

    def parse(self, path: str) -> dict:
        lines = _read_lines(path)

        header_row, leading_empty_cols = _find_header(lines)

        data_lines = lines[header_row:]
        if leading_empty_cols > 0:
            data_lines = [
                ",".join(line.split(",")[leading_empty_cols:])
                for line in data_lines
            ]

        data_text = "\n".join(data_lines)
        df = pd.read_csv(StringIO(data_text))
        df.dropna(axis=1, how="all", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(axis=0, how="all", inplace=True)

        column_roles: Dict[str, ColumnRole] = {}
        for col in df.columns:
            if col == "Wavelength":
                column_roles[col] = ColumnRole.X
            elif col.startswith("_") or col.startswith("Unnamed") or col == "row_id":
                column_roles[col] = ColumnRole.IGNORE
            else:
                column_roles[col] = ColumnRole.Y

        well_cols = [c for c, r in column_roles.items() if r == ColumnRole.Y]
        filled_wells = []
        for col in well_cols:
            values = df[col].dropna()
            if len(values) > 0 and (values.abs() > 0.001).any():
                filled_wells.append(col)

        pre_header_meta = _parse_pre_header(lines[:header_row])

        wl_range = (float(df["Wavelength"].min()), float(df["Wavelength"].max())) if "Wavelength" in df.columns else None

        return {
            "data": df,
            "column_roles": column_roles,
            "plot_hint": PlotHint.MULTI_Y,
            "source_category": SourceCategory.SPECTRUM,
            "sample_name": None,
            "metadata": {
                "file_type_detail": "plate_reader",
                "filled_wells": filled_wells,
                "intensity_columns": well_cols,
                "filled_well_count": len(filled_wells),
                "total_wells": len(well_cols),
                "wavelength_range": wl_range,
                **pre_header_meta,
            },
        }


def _read_lines(path: str) -> List[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [l.rstrip("\n\r") for l in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def _find_header(lines: List[str]) -> Tuple[int, int]:
    """Return (header_row_index, leading_empty_columns_to_strip)."""
    for i, line in enumerate(lines):
        fields = [f.strip() for f in line.split(",")]
        wl_idx = _find_wavelength_field(fields)
        if wl_idx >= 0:
            return i, wl_idx
    return 0, 0


def _parse_pre_header(lines: List[str]) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in lines:
        parts = line.split(",", 1)
        if len(parts) >= 2:
            key = parts[0].strip().rstrip(":")
            val = parts[1].strip().rstrip(",").strip()
            if key and val:
                meta[key] = val
    return meta
