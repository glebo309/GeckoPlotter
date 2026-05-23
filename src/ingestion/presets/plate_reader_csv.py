"""UV-Vis plate reader CSV format (e.g. SpectraMax, Tecan).

Detected by presence of "Wavelength" as the first field in a comma-separated line
within the first 50 lines, indicating it's a column header (not a metadata footer).
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


class PlateReaderCSVPreset(FormatPreset):
    name = "plate_reader_csv"
    extensions = {"csv"}
    priority = 90

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        """Detect plate reader format: "Wavelength" as first field in CSV header row."""
        for line in head_lines:
            fields = [f.strip() for f in line.split(",")]
            if fields and fields[0] == "Wavelength" and len(fields) >= 3:
                return True
        return False

    def parse(self, path: str) -> dict:
        """Parse plate reader CSV file.

        Returns dict with:
        - data: DataFrame with Wavelength as X, well columns as Y
        - column_roles: ColumnRole mappings
        - plot_hint: PlotHint.MULTI_Y
        - sample_name: None
        - metadata: file_type_detail
        """
        lines: list[str] = []
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(path, "r", encoding=enc) as f:
                    lines = [l.rstrip("\n\r") for l in f.readlines()]
                break
            except UnicodeDecodeError:
                continue

        # Find the header row containing "Wavelength" as first field
        header_row = 0
        for i, line in enumerate(lines):
            fields = [f.strip() for f in line.split(",")]
            if fields and fields[0] == "Wavelength":
                header_row = i
                break

        data_text = "\n".join(lines[header_row:])
        df = pd.read_csv(StringIO(data_text))
        df.dropna(axis=1, how="all", inplace=True)

        # Coerce numeric columns
        for col in df.columns:
            if col != "Wavelength":
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Wavelength"] = pd.to_numeric(df["Wavelength"], errors="coerce")
        df.dropna(axis=0, how="all", inplace=True)

        column_roles: Dict[str, ColumnRole] = {}
        for col in df.columns:
            if col == "Wavelength":
                column_roles[col] = ColumnRole.X
            elif col.startswith("_") or col == "row_id":
                column_roles[col] = ColumnRole.IGNORE
            else:
                column_roles[col] = ColumnRole.Y

        # Compute filled wells (wells with actual signal)
        well_cols = [c for c in df.columns if c != "Wavelength" and not c.startswith("_") and c != "row_id"]
        filled_wells = []
        for col in well_cols:
            values = df[col].dropna()
            if len(values) > 0 and (values.abs() > 0.001).any():
                filled_wells.append(col)

        # Parse pre-header metadata
        pre_header_meta = {}
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(path, "r", encoding=enc) as f:
                    pre_lines = [l.rstrip("\n\r") for l in f.readlines()[:header_row]]
                break
            except UnicodeDecodeError:
                continue
        else:
            pre_lines = []

        for line in pre_lines:
            parts = line.split(",", 1)
            if len(parts) >= 2:
                key = parts[0].strip().rstrip(":")
                val = parts[1].strip().rstrip(",").strip()
                if key and val:
                    pre_header_meta[key] = val

        # Wavelength range
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
