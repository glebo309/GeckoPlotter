"""LC-MS VWD (UV detector) CDF reader for GeckoPlotter V2."""
from __future__ import annotations

import logging

import os
from typing import Any, Dict, Optional

import netCDF4 as nc
import numpy as np
import pandas as pd

from .base_reader import BaseReader



log = logging.getLogger(__name__)

class LCMSVWDCDFReader(BaseReader):
    """Parser for LC-MS UV/VWD NetCDF files."""

    def __init__(self) -> None:
        super().__init__()
        self.metadata: Dict[str, Any] = {}
        self.chromatogram: Optional[pd.DataFrame] = None
        self.wavelength_nm: Optional[int] = None
        self.channel: str = "Unknown"

    # ------------------------------------------------------------------
    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")

            with nc.Dataset(path, "r") as dataset:
                self._extract_metadata(dataset)
                self._extract_chromatogram(dataset)

            return True
        except Exception as exc:  # pragma: no cover - defensive logging helper
            log.error(f"LCMS VWD CDF analysis error for {path}: {exc}")
            return False

    def _process_file(self) -> None:
        return

    # ------------------------------------------------------------------
    def _extract_metadata(self, dataset: nc.Dataset) -> None:
        self.metadata.clear()

        for attr in dataset.ncattrs():
            value = getattr(dataset, attr)
            if isinstance(value, bytes):
                value = value.decode("utf-8", "ignore").strip()
            self.metadata[attr] = value

        detector_name = self.metadata.get("detector_name", "")
        if isinstance(detector_name, bytes):
            detector_name = detector_name.decode("utf-8", "ignore")

        if detector_name:
            if "Wavelength=" in detector_name:
                try:
                    number = detector_name.split("Wavelength=")[1].split()[0]
                    self.wavelength_nm = int(number)
                except Exception:
                    self.wavelength_nm = None

            if detector_name.endswith("A") or "VWD1A" in detector_name:
                self.channel = "A"
            elif detector_name.endswith("B") or "VWD1B" in detector_name:
                self.channel = "B"

        # Fallback to filename heuristics
        name_lower = (self.file_name or "").lower()
        if self.channel == "Unknown":
            if "vwd1a" in name_lower or "_a." in name_lower:
                self.channel = "A"
            elif "vwd1b" in name_lower or "_b." in name_lower:
                self.channel = "B"

    def _extract_chromatogram(self, dataset: nc.Dataset) -> None:
        intensity_var = dataset.variables.get("ordinate_values")
        retention_var = dataset.variables.get("raw_data_retention")

        if intensity_var is None:
            raise KeyError("Missing 'ordinate_values' variable in UV CDF")
        if retention_var is None:
            retention_var = dataset.variables.get("raw_data_retention_time")
        if retention_var is None:
            raise KeyError("Missing 'raw_data_retention' variable in UV CDF")

        intensity = np.asarray(intensity_var[:], dtype=float)
        retention_seconds = np.asarray(retention_var[:], dtype=float)

        if retention_seconds.size == 0:
            interval = float(dataset.variables.get("actual_sampling_interval", [0.4])[0])
            retention_seconds = np.arange(len(intensity)) * interval

        rt_minutes = retention_seconds / 60.0
        self.chromatogram = pd.DataFrame(
            {
                "Time (min)": rt_minutes,
                "Intensity (mAU)": intensity,
            }
        )

        self.metadata.update(
            {
                "retention_time_min": float(rt_minutes.min()) if rt_minutes.size else 0.0,
                "retention_time_max": float(rt_minutes.max()) if rt_minutes.size else 0.0,
                "retention_time_range": self._format_time_range(rt_minutes),
                "max_intensity": float(intensity.max()) if intensity.size else 0.0,
                "data_points": int(len(self.chromatogram)),
            }
        )

    # ------------------------------------------------------------------
    def get_metadata(self) -> Dict[str, Any]:
        meta = self.metadata.copy()
        meta.update(
            {
                "detector_channel": self.channel,
                "wavelength": self.wavelength_nm,
                "is_uv_data": True,
            }
        )
        return meta

    def get_data(self) -> Optional[pd.DataFrame]:
        return self.chromatogram

    def get_wavelength(self) -> Optional[int]:
        return self.wavelength_nm

    def get_channel(self) -> str:
        return self.channel

    @staticmethod
    def _format_time_range(times: np.ndarray) -> str:
        if times.size == 0:
            return "Unknown"
        return f"{times.min():.2f}-{times.max():.2f} min"
