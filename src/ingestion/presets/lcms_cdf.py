"""LC-MS netCDF format.

Handles any non-VWD CDF file from LC-MS instruments. Inspects the actual
netCDF variables to choose the right reader:
  - ANDI-MS variables (scan_acquisition_time, total_intensity, mass_values)
    → LCMSCDFReader  (MS spectral data + TIC)
  - AIA-chrom variables (ordinate_values, raw_data_retention)
    → LCMSVWDCDFReader used as a generic AIA chromatogram reader
"""
from __future__ import annotations
import os
from typing import Dict

import netCDF4 as nc

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
        with nc.Dataset(path, "r") as ds:
            has_ms = "scan_acquisition_time" in ds.variables and "total_intensity" in ds.variables
            has_chrom = "ordinate_values" in ds.variables

        if has_ms:
            return self._parse_ms(path)
        elif has_chrom:
            return self._parse_aia_chrom(path)
        else:
            raise ValueError(f"CDF file has neither ANDI-MS nor AIA-chrom variables: {path}")

    def _parse_ms(self, path: str) -> dict:
        from services.readers.lcms_cdf_reader import LCMSCDFReader

        reader = LCMSCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"LCMSCDFReader failed to parse {path}")

        data = reader.get_data()
        metadata = reader.get_metadata()

        if reader.mass_spectral_data:
            metadata["mass_spectral_data"] = reader.mass_spectral_data

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

    def _parse_aia_chrom(self, path: str) -> dict:
        """Parse an AIA chromatogram CDF (TIC exported as chromatogram)."""
        from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader

        reader = LCMSVWDCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"AIA chromatogram reader failed for {path}")

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
