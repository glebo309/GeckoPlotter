"""
Peak detection, storage, and manipulation service for GeckoPlotter V2.

Provides automated peak detection via scipy.signal, manual peak addition,
cross-sample grouping, and integration with calibration models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# Okabe-Ito colorblind-friendly palette
OKABE_ITO_PALETTE = [
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
]


@dataclass
class Peak:
    """A single detected or manually placed chromatographic peak."""

    peak_id: str
    file_id: str
    name: str
    rt: float
    rt_start: float
    rt_end: float
    area: float
    height: float
    width: float
    width_half_height: Optional[float] = None
    color: str = OKABE_ITO_PALETTE[0]
    opacity: float = 0.3
    group_id: Optional[str] = None
    calibration_id: Optional[str] = None
    concentration: Optional[float] = None
    source: str = 'detected'  # 'imported' | 'manual' | 'detected'
    # Manual baseline integration fields (p-line)
    poly_x: Optional[List[float]] = None  # Filled polygon x-coords
    poly_y: Optional[List[float]] = None  # Filled polygon y-coords
    p_line: Optional[List[Tuple[float, float]]] = None  # User-drawn baseline [(x0,y0),(x1,y1)]
    q1: Optional[Tuple[float, float]] = None  # Constraint point 1
    q2: Optional[Tuple[float, float]] = None  # Constraint point 2


class PeakService:
    """Domain service for peak detection, storage, and cross-sample analysis."""

    def __init__(self) -> None:
        # file_id -> list of Peak objects
        self._peaks: Dict[str, List[Peak]] = {}
        self._color_index: int = 0

    # ------------------------------------------------------------------
    # Color cycling
    # ------------------------------------------------------------------

    def _next_color(self) -> str:
        color = OKABE_ITO_PALETTE[self._color_index % len(OKABE_ITO_PALETTE)]
        self._color_index += 1
        return color

    @staticmethod
    def _is_same_peak(existing: Peak, rt: float, rt_start: float, rt_end: float, rt_tol: float = 0.08) -> bool:
        """Return True if a candidate peak likely represents an existing peak."""
        if abs(existing.rt - rt) <= rt_tol:
            return True
        if existing.rt_start and existing.rt_end:
            overlap_start = max(existing.rt_start, rt_start)
            overlap_end = min(existing.rt_end, rt_end)
            if overlap_end >= overlap_start:
                return True
        return False

    # ------------------------------------------------------------------
    # Peak detection
    # ------------------------------------------------------------------

    def detect_peaks(
        self,
        file_id: str,
        signal: np.ndarray,
        time_axis: np.ndarray,
        threshold: float = 0.05,
        slope_threshold: float = 0.001,
        extension_factor: float = 1.1,
        min_prominence: Optional[float] = None,
    ) -> List[Peak]:
        """
        Auto-detect peaks in a chromatographic signal.

        Parameters
        ----------
        file_id : str
            Identifier for the source file.
        signal : np.ndarray
            Intensity values (1-D).
        time_axis : np.ndarray
            Retention time values (1-D, same length as signal).
        threshold : float
            Minimum peak height as a fraction of the signal range.
        slope_threshold : float
            Absolute slope value below which a peak boundary is placed.
        extension_factor : float
            Multiplicative factor to widen detected boundaries slightly.
        min_prominence : float, optional
            Minimum prominence for scipy.signal.find_peaks. If None, derived
            from threshold and signal range.

        Returns
        -------
        List[Peak]
            Detected peaks, stored internally and returned.
        """
        signal = np.asarray(signal, dtype=float)
        time_axis = np.asarray(time_axis, dtype=float)

        if signal.size < 3:
            return []

        sig_range = np.ptp(signal)
        if sig_range == 0:
            return []

        height_cutoff = np.min(signal) + threshold * sig_range
        prominence = min_prominence if min_prominence is not None else threshold * sig_range * 0.5

        indices, properties = find_peaks(
            signal,
            height=height_cutoff,
            prominence=prominence,
            distance=3,
        )

        peaks: List[Peak] = []
        existing_non_detected = [p for p in self._peaks.get(file_id, []) if p.source != 'detected']
        dt = np.median(np.diff(time_axis)) if time_axis.size > 1 else 1.0
        slope = np.gradient(signal, dt)

        for idx in indices:
            rt = float(time_axis[idx])
            apex_height = float(signal[idx])

            # Walk left to find start boundary
            left = idx
            while left > 0:
                if abs(slope[left]) < slope_threshold:
                    break
                if signal[left] < height_cutoff * 0.1:
                    break
                left -= 1

            # Walk right to find end boundary
            right = idx
            while right < len(signal) - 1:
                if abs(slope[right]) < slope_threshold:
                    break
                if signal[right] < height_cutoff * 0.1:
                    break
                right += 1

            # Apply extension factor around the apex
            half_width = max(idx - left, right - idx)
            extended_half = int(half_width * extension_factor)
            left_ext = max(0, idx - extended_half)
            right_ext = min(len(signal) - 1, idx + extended_half)

            rt_start = float(time_axis[left_ext])
            rt_end = float(time_axis[right_ext])

            area = self.calculate_peak_area(signal, time_axis, rt_start, rt_end)
            width = rt_end - rt_start

            if any(self._is_same_peak(p, rt, rt_start, rt_end) for p in existing_non_detected):
                continue

            peak = Peak(
                peak_id=str(uuid.uuid4()),
                file_id=file_id,
                name=f"Peak {len(peaks) + 1}",
                rt=rt,
                rt_start=rt_start,
                rt_end=rt_end,
                area=area,
                height=apex_height,
                width=width,
                color=self._next_color(),
                source='detected',
            )
            peak.width_half_height = self.calculate_width_at_half_height(
                signal, time_axis, peak
            )
            peaks.append(peak)

        # Sort by retention time
        peaks.sort(key=lambda p: p.rt)
        # Rename after sorting
        for i, p in enumerate(peaks, start=1):
            p.name = f"Peak {i}"

        # Append to existing peaks (don't overwrite imported/manual)
        self._peaks[file_id] = existing_non_detected + peaks
        return peaks

    # ------------------------------------------------------------------
    # Instrument peak import
    # ------------------------------------------------------------------

    def import_instrument_peaks(
        self, file_id: str, parsed_results: List[dict],
        sample_name: str = "",
    ) -> List[Peak]:
        """Import peaks parsed from instrument integration results.

        Parameters
        ----------
        file_id : str
            Identifier for the source file/bundle.
        parsed_results : list of dict
            Each dict has keys like 'peak_number', 'peak_name',
            'retention_time', 'area', 'height', 'relative_area',
            'relative_height'.
        sample_name : str
            Human-readable sample label.

        Returns
        -------
        List[Peak]
            Stored peaks.
        """
        peaks: List[Peak] = []
        for r in parsed_results:
            rt = r.get('retention_time', 0.0)
            peak = Peak(
                peak_id=str(uuid.uuid4()),
                file_id=file_id,
                name=r.get('peak_name', '') or f"Peak {r.get('peak_number', len(peaks)+1)}",
                rt=rt,
                rt_start=rt,       # instrument results don't give boundaries
                rt_end=rt,
                area=r.get('area', 0.0),
                height=r.get('height', 0.0),
                width=0.0,
                color=self._next_color(),
                source='imported',
            )
            peaks.append(peak)
        # Replace only imported peaks, keep manual/detected
        existing = [p for p in self._peaks.get(file_id, []) if p.source != 'imported']
        self._peaks[file_id] = peaks + existing
        return peaks

    # ------------------------------------------------------------------
    # Manual peak addition
    # ------------------------------------------------------------------

    def add_peak_manual(
        self,
        file_id: str,
        rt: float,
        signal: np.ndarray,
        time_axis: np.ndarray,
        threshold: float = 0.05,
        extension_factor: float = 1.1,
        slope_threshold: float = 0.001,
    ) -> Peak:
        """
        Add a peak manually by specifying a retention time near the apex.

        A local maximum is searched within a small window around *rt*.
        Boundaries are then estimated using slope analysis.

        Returns
        -------
        Peak
            The newly created Peak object.

        Raises
        ------
        ValueError
            If the retention time is outside the time axis range or no local
            maximum can be found.
        """
        signal = np.asarray(signal, dtype=float)
        time_axis = np.asarray(time_axis, dtype=float)

        if rt < time_axis[0] or rt > time_axis[-1]:
            raise ValueError(
                f"Retention time {rt:.3f} is outside the data range "
                f"[{time_axis[0]:.3f}, {time_axis[-1]:.3f}]."
            )

        # Find the closest index and search for a local max in a window
        closest_idx = int(np.argmin(np.abs(time_axis - rt)))
        window = max(5, int(0.02 * len(signal)))  # ~2 % of total points
        lo = max(0, closest_idx - window)
        hi = min(len(signal), closest_idx + window + 1)
        local_apex = lo + int(np.argmax(signal[lo:hi]))

        apex_rt = float(time_axis[local_apex])
        apex_height = float(signal[local_apex])

        dt = np.median(np.diff(time_axis)) if time_axis.size > 1 else 1.0
        slope = np.gradient(signal, dt)

        # Walk left
        left = local_apex
        while left > 0:
            if abs(slope[left]) < slope_threshold:
                break
            left -= 1

        # Walk right
        right = local_apex
        while right < len(signal) - 1:
            if abs(slope[right]) < slope_threshold:
                break
            right += 1

        half_width = max(local_apex - left, right - local_apex)
        extended_half = int(half_width * extension_factor)
        left_ext = max(0, local_apex - extended_half)
        right_ext = min(len(signal) - 1, local_apex + extended_half)

        rt_start = float(time_axis[left_ext])
        rt_end = float(time_axis[right_ext])
        area = self.calculate_peak_area(signal, time_axis, rt_start, rt_end)
        width = rt_end - rt_start

        existing = self._peaks.get(file_id, [])
        peak_number = len(existing) + 1

        peak = Peak(
            peak_id=str(uuid.uuid4()),
            file_id=file_id,
            name=f"Peak {peak_number}",
            rt=apex_rt,
            rt_start=rt_start,
            rt_end=rt_end,
            area=area,
            height=apex_height,
            width=width,
            color=self._next_color(),
        )
        peak.width_half_height = self.calculate_width_at_half_height(
            signal, time_axis, peak
        )

        self._peaks.setdefault(file_id, []).append(peak)
        return peak

    # ------------------------------------------------------------------
    # Manual baseline integration (p-line)
    # ------------------------------------------------------------------

    def add_baseline_peak(
        self,
        file_id: str,
        area: float,
        height: float,
        apex_x: float,
        poly_x: List[float],
        poly_y: List[float],
        p_line: List[Tuple[float, float]],
        q1: Tuple[float, float],
        q2: Tuple[float, float],
    ) -> Peak:
        """Add a manually integrated peak from baseline drawing (p-line).

        If a manual peak with a very close apex already exists, it is updated
        instead of creating a duplicate.
        """
        existing = self._peaks.get(file_id, [])

        # Check for duplicate editable peak (same apex within 0.05 min)
        for p in existing:
            if p.source in ('manual', 'detected') and abs(p.rt - apex_x) < 0.05:
                p.area = area
                p.height = height
                p.rt = apex_x
                p.poly_x = poly_x
                p.poly_y = poly_y
                p.p_line = p_line
                p.q1 = q1
                p.q2 = q2
                p.rt_start = min(p_line[0][0], p_line[1][0])
                p.rt_end = max(p_line[0][0], p_line[1][0])
                p.width = p.rt_end - p.rt_start
                p.source = 'manual'
                return p

        peak_number = len(existing) + 1
        peak = Peak(
            peak_id=str(uuid.uuid4()),
            file_id=file_id,
            name=f"Peak {peak_number}",
            rt=apex_x,
            rt_start=min(p_line[0][0], p_line[1][0]),
            rt_end=max(p_line[0][0], p_line[1][0]),
            area=area,
            height=height,
            width=abs(p_line[1][0] - p_line[0][0]),
            color=self._next_color(),
            source='manual',
            poly_x=poly_x,
            poly_y=poly_y,
            p_line=p_line,
            q1=q1,
            q2=q2,
        )
        self._peaks.setdefault(file_id, []).append(peak)
        return peak

    def clear_manual_peaks(self, file_id: str) -> None:
        """Remove all manual baseline peaks for a file."""
        if file_id in self._peaks:
            self._peaks[file_id] = [p for p in self._peaks[file_id] if p.source != 'manual']

    def clear_detected_peaks(self, file_id: str) -> None:
        """Remove all auto-detected peaks for a file."""
        if file_id in self._peaks:
            self._peaks[file_id] = [p for p in self._peaks[file_id] if p.source != 'detected']

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def remove_peak(self, file_id: str, peak_id: str) -> bool:
        """Remove a peak by ID. Returns True if found and removed."""
        peaks = self._peaks.get(file_id)
        if peaks is None:
            return False
        before = len(peaks)
        self._peaks[file_id] = [p for p in peaks if p.peak_id != peak_id]
        return len(self._peaks[file_id]) < before

    def rename_peak(self, file_id: str, peak_id: str, new_name: str) -> bool:
        """Rename a peak. Returns True if found."""
        for p in self._peaks.get(file_id, []):
            if p.peak_id == peak_id:
                p.name = new_name
                return True
        return False

    def set_peak_color(
        self,
        file_id: str,
        peak_id: str,
        color: str,
        opacity: Optional[float] = None,
    ) -> bool:
        """Update the display color (and optionally opacity) of a peak."""
        for p in self._peaks.get(file_id, []):
            if p.peak_id == peak_id:
                p.color = color
                if opacity is not None:
                    p.opacity = opacity
                return True
        return False

    def get_peaks(self, file_id: str) -> List[Peak]:
        """Return all peaks for a given file."""
        return list(self._peaks.get(file_id, []))

    def get_all_peaks(self) -> Dict[str, List[Peak]]:
        """Return all peaks keyed by file_id."""
        return {fid: list(pks) for fid, pks in self._peaks.items()}

    # ------------------------------------------------------------------
    # Cross-sample grouping
    # ------------------------------------------------------------------

    def group_peaks_across_samples(
        self, rt_window: float = 0.2
    ) -> Dict[str, List[Peak]]:
        """
        Group peaks from all loaded files by retention time proximity.

        Peaks whose apex RTs fall within *rt_window* minutes of each other
        are considered the same compound across samples. Each group receives
        a shared ``group_id`` and a consistent color.

        Returns
        -------
        Dict[str, List[Peak]]
            group_id -> list of peaks in that group.
        """
        all_peaks: List[Peak] = []
        for pks in self._peaks.values():
            all_peaks.extend(pks)

        if not all_peaks:
            return {}

        all_peaks.sort(key=lambda p: p.rt)

        groups: List[List[Peak]] = []
        current_group: List[Peak] = [all_peaks[0]]

        for peak in all_peaks[1:]:
            # Compare to the mean RT of the current group
            group_mean_rt = np.mean([p.rt for p in current_group])
            if abs(peak.rt - group_mean_rt) <= rt_window:
                current_group.append(peak)
            else:
                groups.append(current_group)
                current_group = [peak]
        groups.append(current_group)

        result: Dict[str, List[Peak]] = {}
        for i, group in enumerate(groups):
            gid = f"group_{i + 1}"
            color = OKABE_ITO_PALETTE[i % len(OKABE_ITO_PALETTE)]
            for peak in group:
                peak.group_id = gid
                peak.color = color
            result[gid] = group

        return result

    # ------------------------------------------------------------------
    # Integration and measurement
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_peak_area(
        signal: np.ndarray,
        time_axis: np.ndarray,
        rt_start: float,
        rt_end: float,
        baseline: Optional[np.ndarray] = None,
    ) -> float:
        """
        Trapezoidal integration of signal between rt_start and rt_end.

        Parameters
        ----------
        signal : np.ndarray
            Intensity values.
        time_axis : np.ndarray
            Retention time values.
        rt_start, rt_end : float
            Integration boundaries.
        baseline : np.ndarray, optional
            If provided, subtracted from signal before integration.
            Must be the same length as signal.

        Returns
        -------
        float
            Integrated area (always >= 0).
        """
        mask = (time_axis >= rt_start) & (time_axis <= rt_end)
        t_seg = time_axis[mask]
        s_seg = signal[mask].copy()

        if t_seg.size < 2:
            return 0.0

        if baseline is not None:
            s_seg = s_seg - baseline[mask]

        area = float(np.trapz(s_seg, t_seg))
        return max(area, 0.0)

    @staticmethod
    def calculate_width_at_half_height(
        signal: np.ndarray,
        time_axis: np.ndarray,
        peak: Peak,
    ) -> float:
        """
        Calculate peak width at half the apex height.

        Uses linear interpolation to find the retention times where the
        signal crosses half-height on each side of the apex.

        Returns
        -------
        float
            Width at half height in minutes. Returns peak.width if the
            interpolation fails.
        """
        signal = np.asarray(signal, dtype=float)
        time_axis = np.asarray(time_axis, dtype=float)

        mask = (time_axis >= peak.rt_start) & (time_axis <= peak.rt_end)
        t_seg = time_axis[mask]
        s_seg = signal[mask]

        if t_seg.size < 3:
            return peak.width

        # Find the apex index within the segment
        apex_local = int(np.argmax(s_seg))
        half_h = s_seg[apex_local] / 2.0

        # Interpolate left crossing
        left_rt = t_seg[0]
        for i in range(apex_local, 0, -1):
            if s_seg[i - 1] <= half_h <= s_seg[i]:
                frac = (half_h - s_seg[i - 1]) / (s_seg[i] - s_seg[i - 1] + 1e-15)
                left_rt = t_seg[i - 1] + frac * (t_seg[i] - t_seg[i - 1])
                break

        # Interpolate right crossing
        right_rt = t_seg[-1]
        for i in range(apex_local, len(s_seg) - 1):
            if s_seg[i] >= half_h >= s_seg[i + 1]:
                frac = (s_seg[i] - half_h) / (s_seg[i] - s_seg[i + 1] + 1e-15)
                right_rt = t_seg[i] + frac * (t_seg[i + 1] - t_seg[i])
                break

        w = right_rt - left_rt
        return float(w) if w > 0 else peak.width

    # ------------------------------------------------------------------
    # Export to DataFrames
    # ------------------------------------------------------------------

    def peaks_to_table(self, file_id: str) -> pd.DataFrame:
        """Return a user-facing peak table for a file (combined sources)."""
        peaks = self._peaks.get(file_id, [])
        if not peaks:
            return pd.DataFrame()
        total_area = sum(max(float(p.area or 0.0), 0.0) for p in peaks)
        total_height = sum(max(float(p.height or 0.0), 0.0) for p in peaks)
        rows = []
        for i, p in enumerate(sorted(peaks, key=lambda pk: pk.rt), start=1):
            rows.append({
                'No.': i,
                'Peak Name': p.name,
                'RT (min)': round(p.rt, 3),
                'Area': round(p.area, 1),
                'Height': round(p.height, 1),
                'Relative Area (%)': round((p.area / total_area * 100.0), 2) if total_area > 0 else 0.0,
                'Relative Height (%)': round((p.height / total_height * 100.0), 2) if total_height > 0 else 0.0,
                'Width (min)': round(p.width, 3) if p.width else '',
                'Source': p.source,
            })
        return pd.DataFrame(rows)

    def to_dataframe(self, file_id: str) -> pd.DataFrame:
        """Return peaks for a single file as a DataFrame."""
        peaks = self._peaks.get(file_id, [])
        if not peaks:
            return pd.DataFrame(columns=[
                "peak_id", "file_id", "name", "rt", "rt_start", "rt_end",
                "area", "height", "width", "width_half_height", "color",
                "opacity", "group_id", "calibration_id", "concentration",
                "source",
            ])
        return pd.DataFrame([asdict(p) for p in peaks])

    def to_comparison_dataframe(
        self, group_id: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Build a cross-sample comparison table.

        If *group_id* is provided, only peaks in that group are included.
        Otherwise all grouped peaks are returned.

        Columns: group_id, file_id, name, rt, area, height, width,
        width_half_height, concentration.
        """
        rows = []
        cols = [
            "group_id", "file_id", "name", "rt", "area", "height",
            "width", "width_half_height", "concentration",
        ]
        for pks in self._peaks.values():
            for p in pks:
                if p.group_id is None:
                    continue
                if group_id is not None and p.group_id != group_id:
                    continue
                rows.append({
                    "group_id": p.group_id,
                    "file_id": p.file_id,
                    "name": p.name,
                    "rt": p.rt,
                    "area": p.area,
                    "height": p.height,
                    "width": p.width,
                    "width_half_height": p.width_half_height,
                    "concentration": p.concentration,
                })
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)

    # ------------------------------------------------------------------
    # Serialization / deserialization
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        """Serialize all peak data for persistence (JSON-compatible)."""
        return {
            "color_index": self._color_index,
            "peaks": {
                fid: [asdict(p) for p in pks]
                for fid, pks in self._peaks.items()
            },
        }

    def deserialize(self, data: dict) -> None:
        """Restore peak data from a previously serialized dict."""
        self._color_index = data.get("color_index", 0)
        self._peaks.clear()
        for fid, peak_dicts in data.get("peaks", {}).items():
            self._peaks[fid] = [Peak(**d) for d in peak_dicts]
