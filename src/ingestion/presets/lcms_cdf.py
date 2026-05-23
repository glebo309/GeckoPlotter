"""LC-MS netCDF (TIC) format.

Detected by .cdf extension + filename NOT containing vwd/uvw/uv- tags.
Delegates parsing to existing LCMSCDFReader.
"""
from __future__ import annotations
import os
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


_VWD_TAGS = ("vwd", "uvw", "uv-")


class LCMSCDFPreset(FormatPreset):
    name = "lcms_cdf"
    extensions = {"cdf", "cdfx"}
    priority = 70

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        name_lower = os.path.basename(path).lower()
        return not any(tag in name_lower for tag in _VWD_TAGS)

    def parse(self, path: str) -> dict:
        from services.readers.lcms_cdf_reader import LCMSCDFReader

        reader = LCMSCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"LCMSCDFReader failed to parse {path}")

        data = reader.get_data()
        metadata = reader.get_metadata()

        column_roles: Dict[str, ColumnRole] = {}
        cols = list(data.columns)
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        return {
            "data": data,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "source_category": SourceCategory.LCMS_MS,
            "sample_name": metadata.get("experiment_title"),
            "metadata": metadata,
        }
