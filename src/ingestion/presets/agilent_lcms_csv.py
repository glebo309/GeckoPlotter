"""Agilent OpenLAB LC-MS CSV sidecar format.

OpenLAB can export simple two-column CSV traces next to richer CDF files:
``.dx_MS1 +/-TIC ...CSV`` for TIC traces and ``.dx_VWD1A/B.CSV`` for UV.
These files have no header, so detection is deliberately filename-driven.
"""
from __future__ import annotations

import os
import re
from typing import Dict

import numpy as np
import pandas as pd

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory


_AGILENT_DX_RE = re.compile(r"\.dx_(?:ms\d.*tic|vwd1[ab])", re.IGNORECASE)


def _infer_run_title(filename: str) -> str | None:
    match = re.search(r"(LCMS-.+?)\.dx_", filename, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}.dx"
    return None


def _infer_ionization_mode(filename: str) -> str:
    lower = filename.lower()
    if re.search(r"(?:^|[\s_])\+tic\b", lower):
        return "positive"
    if re.search(r"(?:^|[\s_])-tic\b", lower):
        return "negative"
    if re.search(r"[_\s-]pos(?:itive)?(?:[_\s.]|$)", lower):
        return "positive"
    if re.search(r"[_\s-]neg(?:ative)?(?:[_\s.]|$)", lower):
        return "negative"
    return "unknown"


class AgilentLCMSCSVPreset(FormatPreset):
    name = "agilent_lcms_csv"
    extensions = {"csv"}
    priority = 90

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        return _AGILENT_DX_RE.search(os.path.basename(path)) is not None

    def parse(self, path: str) -> dict:
        filename = os.path.basename(path)
        lower = filename.lower()

        df = pd.read_csv(path, header=None, names=["Time (min)", "Intensity"])
        df = df.apply(pd.to_numeric, errors="coerce").dropna(how="any")
        if df.empty:
            raise ValueError(f"Agilent LC-MS CSV contains no numeric trace data: {path}")

        is_uv = "vwd1" in lower
        channel = None
        if "vwd1a" in lower:
            channel = "A"
        elif "vwd1b" in lower:
            channel = "B"

        if is_uv:
            df = df.rename(columns={"Intensity": "Intensity (mAU)"})
            y_col = "Intensity (mAU)"
            source_category = SourceCategory.LCMS_UV
        else:
            y_col = "Intensity"
            source_category = SourceCategory.LCMS_MS

        values = df[y_col].to_numpy(dtype=float)
        times = df["Time (min)"].to_numpy(dtype=float)
        metadata = {
            "file_type_detail": "agilent_lcms_csv",
            "experiment_title": _infer_run_title(filename),
            "retention_time_min": float(np.min(times)) if times.size else 0.0,
            "retention_time_max": float(np.max(times)) if times.size else 0.0,
            "retention_time_range": (
                f"{float(np.min(times)):.2f}-{float(np.max(times)):.2f} min"
                if times.size
                else "Unknown"
            ),
            "max_intensity": float(np.max(values)) if values.size else 0.0,
            "data_points": int(len(df)),
        }

        if is_uv:
            metadata.update(
                {
                    "detector_channel": channel or "Unknown",
                    "detector_name": f"VWD1{channel}" if channel else "VWD",
                    "is_uv_data": True,
                    "wavelength": None,
                }
            )
        else:
            mode = _infer_ionization_mode(filename)
            metadata.update(
                {
                    "ionization_mode": mode,
                    "detector_name": f"MS1 {'+' if mode == 'positive' else '-' if mode == 'negative' else ''}TIC".strip(),
                    "is_tic_only": True,
                }
            )

        return {
            "data": df,
            "column_roles": {
                "Time (min)": ColumnRole.X,
                y_col: ColumnRole.Y,
            },
            "plot_hint": PlotHint.LINE,
            "source_category": source_category,
            "sample_name": None,
            "metadata": metadata,
        }
