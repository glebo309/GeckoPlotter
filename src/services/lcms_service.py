"""LC-MS analysis service for GeckoPlotter V2.

Provides higher-level operations on parsed LC-MS CDF data: TIC/EIC
extraction, mass spectrum retrieval, background subtraction, and
ready-made Plotly figures.

The *data* parameter throughout this module is the parsed dictionary
returned by :class:`DataManager`, whose ``data['data']`` holds the raw
arrays/DataFrame and ``data['metadata']`` holds scan/file metadata.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go


class LCMSService:
    """Stateless service for LC-MS data manipulation and visualisation."""

    # ------------------------------------------------------------------
    # Internal helpers for navigating the parsed data dict
    # ------------------------------------------------------------------

    @staticmethod
    def _get_raw(data: dict) -> dict:
        """Return the inner raw-data mapping (arrays / DataFrame)."""
        raw = data.get("data", data)
        if isinstance(raw, pd.DataFrame):
            return {"dataframe": raw}
        return raw

    @staticmethod
    def _get_metadata(data: dict) -> dict:
        return data.get("metadata", {})

    # ------------------------------------------------------------------
    # Chromatogram extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_tic(data: dict) -> Tuple[np.ndarray, np.ndarray]:
        """Extract TIC arrays (time in minutes, intensity) from parsed data.

        Falls back to ``scan_acquisition_time`` / ``total_intensity`` keys
        when the data is not already a DataFrame with standard columns.
        """
        raw = data.get("data", data)

        # DataFrame path (produced by LCMSCDFReader)
        if isinstance(raw, pd.DataFrame):
            time = np.asarray(raw["Time (min)"], dtype=float)
            intensity = np.asarray(raw["Intensity"], dtype=float)
            return time, intensity

        # Dict-of-arrays path
        if isinstance(raw, dict):
            if "Time (min)" in raw and "Intensity" in raw:
                return (
                    np.asarray(raw["Time (min)"], dtype=float),
                    np.asarray(raw["Intensity"], dtype=float),
                )
            if "scan_acquisition_time" in raw and "total_intensity" in raw:
                time = np.asarray(raw["scan_acquisition_time"], dtype=float) / 60.0
                intensity = np.asarray(raw["total_intensity"], dtype=float)
                return time, intensity

        raise ValueError("Cannot extract TIC: unrecognised data structure.")

    @staticmethod
    def extract_uv_channel(
        data: dict, channel: str = "A"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Extract a UV detector channel (time, intensity).

        Channel is typically ``'A'`` or ``'B'``.  The method looks for
        keys like ``ordinate_values_A`` or a ``uv_channels`` sub-dict.
        """
        raw = data.get("data", data)
        if isinstance(raw, pd.DataFrame):
            col = f"Channel {channel}"
            if col in raw.columns:
                time = np.asarray(raw["Time (min)"], dtype=float)
                intensity = np.asarray(raw[col], dtype=float)
                return time, intensity
            raise KeyError(f"UV channel '{channel}' not found in DataFrame columns.")

        if isinstance(raw, dict):
            key = f"ordinate_values_{channel}"
            if key in raw:
                time_key = "scan_acquisition_time"
                if time_key not in raw:
                    raise KeyError("Missing scan_acquisition_time for UV channel.")
                time = np.asarray(raw[time_key], dtype=float) / 60.0
                intensity = np.asarray(raw[key], dtype=float)
                return time, intensity

            uv = raw.get("uv_channels", {})
            if channel in uv:
                ch = uv[channel]
                return (
                    np.asarray(ch["time"], dtype=float),
                    np.asarray(ch["intensity"], dtype=float),
                )

        raise KeyError(f"UV channel '{channel}' not found in data.")

    # ------------------------------------------------------------------
    # Mass spectrum access
    # ------------------------------------------------------------------

    @staticmethod
    def get_mass_spectrum(
        data: dict, scan_index: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (m/z, intensity) arrays for a single scan by index."""
        raw = data.get("data", data)
        if not isinstance(raw, dict):
            raise ValueError("Raw data is not a dict; cannot extract scan.")

        mass_values = np.asarray(raw.get("mass_values", []), dtype=float)
        intensity_values = np.asarray(raw.get("intensity_values", []), dtype=float)
        scan_index_arr = np.asarray(raw.get("scan_index", []), dtype=int)

        if mass_values.size == 0 or intensity_values.size == 0:
            raise ValueError("No mass/intensity data available.")

        n_scans = scan_index_arr.size
        if scan_index < 0 or scan_index >= n_scans:
            raise IndexError(
                f"scan_index {scan_index} out of range (0..{n_scans - 1})."
            )

        start = int(scan_index_arr[scan_index])
        end = (
            int(scan_index_arr[scan_index + 1])
            if scan_index + 1 < n_scans
            else mass_values.size
        )

        return mass_values[start:end], intensity_values[start:end]

    def get_mass_spectrum_at_time(
        self, data: dict, time_minutes: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return the mass spectrum closest to *time_minutes*."""
        time_arr, _ = self.extract_tic(data)
        if time_arr.size == 0:
            raise ValueError("No scan times available.")
        idx = int(np.argmin(np.abs(time_arr - time_minutes)))
        return self.get_mass_spectrum(data, idx)

    # ------------------------------------------------------------------
    # Extracted-ion chromatogram (EIC)
    # ------------------------------------------------------------------

    def extract_eic(
        self,
        data: dict,
        target_mz: float,
        tolerance: float = 0.5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an extracted-ion chromatogram for *target_mz +/- tolerance*.

        Returns (time, intensity) arrays where each intensity value is the
        summed signal within the m/z window for that scan.
        """
        time_arr, _ = self.extract_tic(data)
        raw = data.get("data", data)
        if not isinstance(raw, dict):
            raise ValueError("Raw data is not a dict; cannot build EIC.")

        mass_values = np.asarray(raw.get("mass_values", []), dtype=float)
        intensity_values = np.asarray(raw.get("intensity_values", []), dtype=float)
        scan_index_arr = np.asarray(raw.get("scan_index", []), dtype=int)

        if mass_values.size == 0:
            raise ValueError("No mass data available for EIC.")

        n_scans = scan_index_arr.size
        eic_intensities = np.zeros(n_scans, dtype=float)

        lo = target_mz - tolerance
        hi = target_mz + tolerance

        for i in range(n_scans):
            start = int(scan_index_arr[i])
            end = (
                int(scan_index_arr[i + 1]) if i + 1 < n_scans else mass_values.size
            )
            mz_slice = mass_values[start:end]
            int_slice = intensity_values[start:end]
            mask = (mz_slice >= lo) & (mz_slice <= hi)
            eic_intensities[i] = float(int_slice[mask].sum()) if mask.any() else 0.0

        return time_arr[:n_scans], eic_intensities

    # ------------------------------------------------------------------
    # Averaged / background-subtracted spectra
    # ------------------------------------------------------------------

    def get_averaged_spectrum(
        self,
        data: dict,
        time_start: float,
        time_end: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Average all mass spectra within [time_start, time_end] minutes.

        Returns (m/z, averaged_intensity).  The m/z axis is built by
        combining all unique values across the selected scans.
        """
        time_arr, _ = self.extract_tic(data)
        indices = np.where((time_arr >= time_start) & (time_arr <= time_end))[0]

        if indices.size == 0:
            return np.array([]), np.array([])

        # Collect all scans into a common m/z grid
        all_mz: List[np.ndarray] = []
        all_int: List[np.ndarray] = []
        for idx in indices:
            mz, ints = self.get_mass_spectrum(data, int(idx))
            all_mz.append(mz)
            all_int.append(ints)

        # Build union m/z axis (rounded to 1 decimal for binning)
        combined_mz = np.unique(np.round(np.concatenate(all_mz), decimals=1))
        averaged = np.zeros_like(combined_mz)

        for mz, ints in zip(all_mz, all_int):
            rounded = np.round(mz, decimals=1)
            for m, intensity in zip(rounded, ints):
                pos = np.searchsorted(combined_mz, m)
                if pos < combined_mz.size and combined_mz[pos] == m:
                    averaged[pos] += intensity

        averaged /= max(len(indices), 1)
        return combined_mz, averaged

    @staticmethod
    def subtract_background(
        spectrum: Tuple[np.ndarray, np.ndarray],
        background: Tuple[np.ndarray, np.ndarray],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Subtract *background* from *spectrum* on a common m/z axis.

        The m/z axes are aligned by rounding to 1 decimal place.  Negative
        intensities are clipped to zero.
        """
        mz_spec, int_spec = spectrum
        mz_bg, int_bg = background

        if mz_spec.size == 0:
            return np.array([]), np.array([])

        rounded_spec = np.round(mz_spec, decimals=1)
        rounded_bg = np.round(mz_bg, decimals=1)

        bg_map: Dict[float, float] = dict(zip(rounded_bg.tolist(), int_bg.tolist()))

        result_int = np.array(
            [
                max(0.0, val - bg_map.get(m, 0.0))
                for m, val in zip(rounded_spec.tolist(), int_spec.tolist())
            ]
        )

        return mz_spec, result_int

    # ------------------------------------------------------------------
    # Figure builders
    # ------------------------------------------------------------------

    def create_tic_figure(self, data: dict) -> go.Figure:
        """Create a TIC chromatogram figure."""
        time, intensity = self.extract_tic(data)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=time,
                y=intensity,
                mode="lines",
                name="TIC",
                line=dict(width=1.2),
            )
        )
        fig.update_layout(
            title="Total Ion Chromatogram",
            xaxis_title="Time (min)",
            yaxis_title="Intensity",
            template="plotly_white",
            hovermode="x unified",
        )
        return fig

    @staticmethod
    def create_spectrum_figure(
        mz: np.ndarray,
        intensity: np.ndarray,
        title: str = "",
    ) -> go.Figure:
        """Create a mass spectrum bar-plot figure."""
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=mz,
                y=intensity,
                width=0.4,
                name="Spectrum",
                marker_color="steelblue",
            )
        )
        fig.update_layout(
            title=title or "Mass Spectrum",
            xaxis_title="m/z",
            yaxis_title="Intensity",
            template="plotly_white",
            bargap=0,
        )
        return fig

    def create_eic_figure(
        self,
        data: dict,
        target_mz: float,
        tolerance: float = 0.5,
    ) -> go.Figure:
        """Create an EIC chromatogram figure."""
        time, intensity = self.extract_eic(data, target_mz, tolerance)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=time,
                y=intensity,
                mode="lines",
                name=f"EIC m/z {target_mz:.1f}",
                line=dict(width=1.2),
            )
        )
        fig.update_layout(
            title=f"Extracted Ion Chromatogram (m/z {target_mz:.1f} +/- {tolerance})",
            xaxis_title="Time (min)",
            yaxis_title="Intensity",
            template="plotly_white",
            hovermode="x unified",
        )
        return fig

    # ------------------------------------------------------------------
    # Quick metadata accessors
    # ------------------------------------------------------------------

    def get_scan_count(self, data: dict) -> int:
        """Return the number of scans in the dataset."""
        meta = self._get_metadata(data)
        if "scan_count" in meta:
            return int(meta["scan_count"])
        raw = data.get("data", data)
        if isinstance(raw, dict) and "scan_index" in raw:
            return len(raw["scan_index"])
        time, _ = self.extract_tic(data)
        return int(time.size)

    def get_time_range(self, data: dict) -> Tuple[float, float]:
        """Return (min_time, max_time) in minutes."""
        time, _ = self.extract_tic(data)
        if time.size == 0:
            return (0.0, 0.0)
        return (float(time.min()), float(time.max()))

    def get_mz_range(self, data: dict) -> Tuple[float, float]:
        """Return the overall (min_mz, max_mz) across the dataset."""
        meta = self._get_metadata(data)
        if "mass_range" in meta:
            mr = meta["mass_range"]
            if isinstance(mr, (list, tuple)) and len(mr) == 2:
                return (float(mr[0]), float(mr[1]))

        raw = data.get("data", data)
        if isinstance(raw, dict) and "mass_values" in raw:
            mv = np.asarray(raw["mass_values"], dtype=float)
            if mv.size:
                return (float(mv.min()), float(mv.max()))

        return (0.0, 0.0)
