"""LC-MS CDF reader for GeckoPlotter V2.

This module is adapted from the legacy DashPlotter implementation and is
responsible for extracting Total Ion Chromatogram (TIC) information and rich
metadata from Agilent/Chromeleon-style NetCDF exports. The reader returns a
`pandas.DataFrame` with `Time (min)` and `Intensity` columns together with a
comprehensive metadata dictionary.
"""

from __future__ import annotations

import logging

import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import netCDF4 as nc
import numpy as np
import pandas as pd

from .base_reader import BaseReader

log = logging.getLogger(__name__)


class LCMSCDFReader(BaseReader):
    """Parser for LC-MS (MS detector) NetCDF files."""

    def __init__(self) -> None:
        super().__init__()
        self.metadata: Dict[str, Any] = {}
        self.instrument_info: Dict[str, Any] = {}
        self.ionization_mode: Optional[str] = None
        self.tic_data: Optional[pd.DataFrame] = None
        self.mass_range: Tuple[float, float] = (0.0, 0.0)
        self.scan_count: int = 0
        self.mass_spectral_data: Optional[Dict[str, np.ndarray]] = None

    # ------------------------------------------------------------------
    # BaseReader overrides
    # ------------------------------------------------------------------
    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        """Load and analyse a CDF file from *path*."""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")

            with nc.Dataset(path, "r") as dataset:
                self._extract_metadata(dataset)
                self._detect_ionization_mode(dataset)
                self._extract_tic_data(dataset)
                self._extract_mass_spectral_data(dataset)

            return True
        except Exception as exc:  # pragma: no cover - defensive logging helper
            log.error(f"LCMS CDF analysis error for {path}: {exc}")
            return False

    def _process_file(self) -> None:
        """Not used – the processing happens inside :meth:`load_file`."""
        # Intentionally left blank. BaseReader requires this method.
        return

    # ------------------------------------------------------------------
    # Metadata extraction helpers
    # ------------------------------------------------------------------
    def _extract_metadata(self, dataset: nc.Dataset) -> None:
        """Extract global attributes and instrument details."""
        self.metadata.clear()
        self.instrument_info.clear()

        # Global attributes
        for attr in dataset.ncattrs():
            value = getattr(dataset, attr)
            if isinstance(value, bytes):
                value = value.decode("utf-8", "ignore").strip()
            self.metadata[f"global_{attr}"] = value

        # Instrument related variables
        instrument_vars = [
            "instrument_name",
            "instrument_model",
            "instrument_mfr",
            "instrument_serial_no",
        ]
        for var_name in instrument_vars:
            if var_name not in dataset.variables:
                continue
            raw = dataset.variables[var_name]
            text = self._decode_char_array(raw)
            if text:
                self.instrument_info[var_name] = text
                self.metadata[var_name] = text

        # Additional metadata of interest
        sample_attrs = [
            "sample_name",
            "experiment_title",
            "dataset_origin",
            "test_ionization_polarity",
        ]
        for attr in sample_attrs:
            if hasattr(dataset, attr):
                value = getattr(dataset, attr)
                if isinstance(value, bytes):
                    value = value.decode("utf-8", "ignore").strip()
                self.metadata[attr] = value

    def _detect_ionization_mode(self, dataset: nc.Dataset) -> None:
        """Infer positive/negative ionisation mode from metadata/filename."""
        polarity = None
        if hasattr(dataset, "test_ionization_polarity"):
            raw = getattr(dataset, "test_ionization_polarity")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            if isinstance(raw, str):
                raw_lower = raw.lower()
                if "positive" in raw_lower:
                    polarity = "positive"
                elif "negative" in raw_lower:
                    polarity = "negative"

        filename_lower = (self.file_name or "").lower()
        if " +tic" in filename_lower or "_pos" in filename_lower or "+" in filename_lower:
            polarity = "positive"
        elif " -tic" in filename_lower or "_neg" in filename_lower or "-" in filename_lower:
            polarity = "negative"

        self.ionization_mode = polarity or "unknown"

    def _extract_tic_data(self, dataset: nc.Dataset) -> None:
        """Extract the Total Ion Chromatogram as a dataframe."""
        try:
            scan_times_var = dataset.variables["scan_acquisition_time"]
            signal_var = dataset.variables["total_intensity"]

            scan_times = np.asarray(scan_times_var[:], dtype=float)
            signal = np.asarray(signal_var[:], dtype=float)
        except KeyError as exc:
            raise KeyError(f"Missing TIC variable in CDF: {exc}") from exc

        if scan_times.size > 0 and np.all(scan_times == 0):
            delay = float(dataset.variables.get("actual_delay_time", [0.0])[:].flat[0])
            interval = float(dataset.variables.get("actual_sampling_interval", [1.0])[:].flat[0])
            scan_times = delay + np.arange(len(signal)) * interval

        # Convert to minutes
        scan_times_min = scan_times / 60.0
        self.tic_data = pd.DataFrame(
            {
                "Time (min)": scan_times_min,
                "Intensity": signal,
            }
        )
        self.scan_count = len(self.tic_data)

        # Determine overall mass range if available
        min_range = dataset.variables.get("mass_range_min")
        max_range = dataset.variables.get("mass_range_max")
        if min_range is not None and max_range is not None:
            self.mass_range = (
                float(np.min(min_range[:])),
                float(np.max(max_range[:])),
            )

        self.metadata.update(
            {
                "scan_count": self.scan_count,
                "retention_time_min": float(scan_times_min.min()) if scan_times_min.size else 0.0,
                "retention_time_max": float(scan_times_min.max()) if scan_times_min.size else 0.0,
                "retention_time_range": self._format_time_range(scan_times_min),
                "max_intensity": float(signal.max()) if signal.size else 0.0,
            }
        )

    def _extract_mass_spectral_data(self, dataset: nc.Dataset) -> None:
        """Extract per-scan mass spectral arrays when available."""
        needed = ("mass_values", "intensity_values", "scan_index")
        if not all(v in dataset.variables for v in needed):
            return

        self.mass_spectral_data = {
            "mass_values": np.asarray(dataset.variables["mass_values"][:], dtype=np.float32),
            "intensity_values": np.asarray(dataset.variables["intensity_values"][:], dtype=np.float32),
            "scan_index": np.asarray(dataset.variables["scan_index"][:], dtype=np.int32),
        }
        if "point_count" in dataset.variables:
            self.mass_spectral_data["point_count"] = np.asarray(
                dataset.variables["point_count"][:], dtype=np.int32
            )

    # ------------------------------------------------------------------
    # Public API helpers
    # ------------------------------------------------------------------
    def get_metadata(self) -> Dict[str, Any]:
        """Return processed metadata for downstream consumers."""
        meta = self.metadata.copy()
        meta.update(
            {
                "ionization_mode": self.ionization_mode,
                "mass_range": self.mass_range,
                "mass_range_str": self._format_mass_range(),
                "instrument_info": self.instrument_info.copy(),
                "data_points": len(self.tic_data) if self.tic_data is not None else 0,
            }
        )
        return meta

    def get_raw_metadata(self) -> Dict[str, Any]:
        """Return the raw metadata dictionary (for debugging/UI drill-down)."""
        return self.metadata.copy()

    def get_data(self) -> Optional[pd.DataFrame]:
        return self.tic_data

    def get_ionization_mode(self) -> str:
        return self.ionization_mode or "unknown"

    def get_scan_count(self) -> int:
        return self.scan_count

    def get_retention_time_range(self) -> Tuple[float, float]:
        if self.tic_data is None or self.tic_data.empty:
            return (0.0, 0.0)
        return (
            float(self.tic_data["Time (min)"].min()),
            float(self.tic_data["Time (min)"].max()),
        )

    def get_mass_range(self) -> Tuple[float, float]:
        return self.mass_range

    def print_full_analysis(self) -> None:
        """Log a summary of the CDF analysis (useful for debugging)."""
        log.debug("LC-MS CDF ANALYSIS SUMMARY")
        log.debug("=" * 60)
        log.debug(f"File: {self.get_file_name()}")
        log.debug(f"Mode: {self.get_ionization_mode().upper()}")
        log.debug(f"Instrument: {self.instrument_info.get('instrument_name', 'Unknown')}")
        rt_min, rt_max = self.get_retention_time_range()
        log.debug(f"Retention Time: {rt_min:.2f} - {rt_max:.2f} min")
        low_mz, high_mz = self.mass_range
        if low_mz or high_mz:
            log.debug(f"Mass Range: {low_mz:.1f} - {high_mz:.1f} m/z")
        if self.tic_data is not None and not self.tic_data.empty:
            log.debug(f"TIC points: {len(self.tic_data)}")
            log.debug(f"Max Intensity: {float(self.tic_data['Intensity'].max()):,.0f}")
        log.debug("=" * 60)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_char_array(array: nc.Variable) -> str:
        """Convert an NC char array to a Python string."""
        values = array[:]
        if values.dtype.kind == "S":  # already bytes
            if values.ndim == 1:
                return values.tobytes().decode("utf-8", "ignore").strip("\x00")
            if values.ndim == 2 and len(values) > 0:
                return bytes(values[0]).decode("utf-8", "ignore").strip("\x00")
        if values.dtype.kind in {"U", "O"}:
            # numpy already decoded to str
            return str(values[0]).strip()
        return ""

    @staticmethod
    def _format_time_range(times: np.ndarray) -> str:
        if times.size == 0:
            return "Unknown"
        return f"{times.min() / 60.0:.2f}-{times.max() / 60.0:.2f} min" if times.max() > 60 else f"{times.min():.2f}-{times.max():.2f} min"

    def _format_mass_range(self) -> str:
        low, high = self.mass_range
        if not low and not high:
            return "Unknown"
        return f"{low:.0f}-{high:.0f} m/z"
