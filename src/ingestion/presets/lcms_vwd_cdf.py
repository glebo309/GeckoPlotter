"""LC-MS VWD (UV detector) netCDF format.

Detected by .cdf extension + filename containing vwd/uvw/uv- tags.
Delegates parsing to existing LCMSVWDCDFReader.
"""
from __future__ import annotations
import os
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


_VWD_TAGS = ("vwd", "uvw", "uv-")


class LCMSVWDCDFPreset(FormatPreset):
    name = "lcms_vwd_cdf"
    extensions = {"cdf", "cdfx"}
    priority = 75

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        name_lower = os.path.basename(path).lower()
        return any(tag in name_lower for tag in _VWD_TAGS)

    def parse(self, path: str) -> dict:
        from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader

        reader = LCMSVWDCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"LCMSVWDCDFReader failed to parse {path}")

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
            "sample_name": None,
            "metadata": metadata,
        }
