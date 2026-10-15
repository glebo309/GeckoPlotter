"""
Peak detection, storage, and manipulation service for GeckoPlotter V2.

Provides automated peak detection via scipy.signal, manual peak addition,
cross-sample grouping, and integration with calibration models.
"""

from __future__ import annotations

import copy
import re
import uuid
from dataclasses import dataclass, field, asdict, replace
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths

# NumPy 2 renamed trapz to trapezoid and later removed the old name; a clean install gets the new NumPy.
_trapezoid = getattr(np, 'trapezoid', None) or np.trapz

# Okabe-Ito colorblind-friendly palette
OKABE_ITO_PALETTE = [
    "#E69F00",  # orange
    "#0072B2",  # blue
    "#009E73",  # bluish green
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#F0E442",  # yellow
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
    source: str = 'detected'  # 'imported' | 'manual' | 'detected' | 'deconvolved'
    label: str = ''  # User-assigned compound/label shown above peak on plot
    # Deconvolution fields (EMG fit)
    deconv_group: Optional[str] = None  # e.g. "deconv_5.2_c1" — cross-sample matching tag
    fit_params: Optional[Dict] = None  # {sigma, gamma, amplitude} from the EMG fit
    # Manual baseline integration fields (p-line)
    poly_x: Optional[List[float]] = None  # Filled polygon x-coords
    poly_y: Optional[List[float]] = None  # Filled polygon y-coords
    p_line: Optional[List[Tuple[float, float]]] = None  # User-drawn baseline [(x0,y0),(x1,y1)]
    q1: Optional[Tuple[float, float]] = None  # Constraint point 1
    q2: Optional[Tuple[float, float]] = None  # Constraint point 2
    # Name label dragged away from its place above the peak: [dx, dy] (dy up), and whether a line leads from the peak's
    # top to it. In the plot's own units (minutes, signal) when label_in_data, so it keeps its place in a subplot of any
    # size; older projects have screen pixels. None: centred above the peak.
    label_offset: Optional[List[float]] = None
    label_leader: bool = False
    label_in_data: bool = False


class PeakService:
    """Domain service for peak detection, storage, and cross-sample analysis."""

    MAX_UNDO = 50

    def __init__(self, file_id_resolver=None, color_scope_resolver=None) -> None:
        self._file_id_resolver = file_id_resolver
        self._color_scope_resolver = color_scope_resolver
        self._grouping_window = None
        self._peaks: Dict[str, List[Peak]] = {}
        self._color_index: int = 0
        self._file_color_index: Dict[str, int] = {}
        self._imported_files: set = set()
        # Nested: overlay_group -> compound_gid -> color
        self._group_colors: Dict[str, Dict[str, str]] = {}
        self._undo_stack: List[Dict[str, List[Peak]]] = []
        self._redo_stack: List[Dict[str, List[Peak]]] = []
        # Palette and its name must agree from the start (the name is what the plot settings show).
        self._palette_name: str = 'muted'
        self._palette: List[str] = self._named_palette(self._palette_name)

    @staticmethod
    def _named_palette(name: str) -> List[str]:
        """Colours of the plot-settings palette *name* (imported lazily; Okabe-Ito if unknown)."""
        try:
            from .plot_settings_service import COLOR_PALETTES
            colors = COLOR_PALETTES.get(name)
        except ImportError:
            colors = None
        return list(colors or OKABE_ITO_PALETTE)

    def _resolve_file_id(self, file_id):
        """Use one peak owner for equivalent bundle/primary-component selections."""
        if self._file_id_resolver is None:
            return file_id
        owner = self._file_id_resolver(file_id)
        # Older workspaces may contain peaks under either spelling. Migrate on
        # access so undo/restore also stays compatible without losing peak IDs.
        for old_id in list(self._peaks):
            if old_id == owner or self._file_id_resolver(old_id) != owner:
                continue
            existing = self._peaks.setdefault(owner, [])
            ids = {peak.peak_id for peak in existing}
            for peak in self._peaks.pop(old_id):
                peak.file_id = owner
                if peak.peak_id not in ids:
                    existing.append(peak)
                    ids.add(peak.peak_id)
            if old_id in self._imported_files:
                self._imported_files.discard(old_id)
                self._imported_files.add(owner)
            if old_id in self._file_color_index:
                self._file_color_index[owner] = max(self._file_color_index.get(owner, 0), self._file_color_index.pop(old_id))
        return owner

    def set_palette(self, name: str, colors: List[str]) -> None:
        """Update the color palette used for peak groups.

        Clears cached group colors so they are reassigned on the next
        ``group_peaks_across_samples`` call.
        """
        self._palette_name = name
        self._palette = list(colors)
        self._group_colors.clear()

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def _snapshot(self) -> Dict[str, List[Peak]]:
        return {fid: [replace(p) for p in peaks] for fid, peaks in self._peaks.items()}

    def save_undo(self) -> None:
        """Push current peak state onto the undo stack. Call before any mutation."""
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Restore previous peak state. Returns True if anything changed."""
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        self._peaks = self._undo_stack.pop()
        return True

    def redo(self) -> bool:
        """Re-apply last undone action. Returns True if anything changed."""
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        self._peaks = self._redo_stack.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    # ------------------------------------------------------------------
    # Color cycling
    # ------------------------------------------------------------------

    def _next_color(self, file_id: str = '') -> str:
        """Return next color for a file. Each file starts from color[0]."""
        idx = self._file_color_index.get(file_id, 0)
        pal = self._palette or OKABE_ITO_PALETTE
        color = pal[idx % len(pal)]
        self._file_color_index[file_id] = idx + 1
        return color

    @staticmethod
    def _is_same_peak(existing: Peak, rt: float, rt_start: float, rt_end: float, rt_tol: float = 0.08) -> bool:
        """Keep existing integrations without suppressing neighbouring apices.

        Detected tails can overlap a manually drawn baseline even when the
        candidate apex lies outside it. Only an apex inside that integration
        is already accounted for; touching/overlapping tails are not enough.
        """
        if existing.rt_end > existing.rt_start:
            return existing.rt_start <= rt <= existing.rt_end
        return abs(existing.rt - rt) <= rt_tol

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
        display_signal: Optional[np.ndarray] = None,
        baseline: Optional[np.ndarray] = None,
        integration_baseline: Optional[str] = None,
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
            Retained for compatibility; boundaries use relative prominence.
        extension_factor : float
            Multiplicative factor to widen detected boundaries slightly.
        min_prominence : float, optional
            Minimum prominence for scipy.signal.find_peaks. If None, derived
            from threshold and signal range.
        integration_baseline : {'linear', 'zero'}, optional
            Baseline for quantitation and fill on display_signal. Detection
            still uses signal (the processed trace). None preserves the
            supplied estimated baseline and corrected-signal quantitation.

        Returns
        -------
        List[Peak]
            Detected peaks, stored internally and returned.
        """
        if integration_baseline not in (None, 'linear', 'zero'):
            raise ValueError('Unknown integration baseline')
        file_id = self._resolve_file_id(file_id)
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
        previous_names = [p for p in self._peaks.get(file_id, []) if p.source == 'detected' and self.has_custom_name(p)]
        # Prominence-relative widths are independent of detector units. Bound
        # each integration by neighbouring valleys so large ion counts cannot
        # make every peak extend over the entire chromatogram.
        _, _, left_ips, right_ips = peak_widths(
            signal, indices, rel_height=0.99,
            prominence_data=(properties['prominences'], properties['left_bases'], properties['right_bases']),
        )
        valleys = [int(a + np.argmin(signal[a:b+1])) for a, b in zip(indices[:-1], indices[1:])]
        # Unresolved neighbours share the outer baseline. A valley partitions
        # their areas vertically; it must not pull the baseline up into a peak.
        # Resolved peaks retain their own baseline. The 1% return criterion is
        # relative to the smaller adjacent peak on the corrected signal.
        cluster_geometry = {}
        if integration_baseline in ('linear', 'zero') and len(indices):
            raw = signal if display_signal is None else np.asarray(display_signal)
            groups = [[0]]
            for number, valley in enumerate(valleys):
                return_level = .01 * min(signal[indices[number]], signal[indices[number+1]])
                if signal[valley] > max(return_level, 0):
                    groups[-1].append(number+1)
                else:
                    groups.append([number+1])
            for group in groups:
                first, last = group[0], group[-1]
                lower = valleys[first-1] if first else 0
                upper = valleys[last] if last < len(valleys) else len(signal)-1
                left, right = int(indices[first]), int(indices[last])
                # Use the outer peaks' own heights, so a tall neighbour cannot
                # truncate the tail of a smaller peak in the same cluster.
                left_floor = max(0, .01 * signal[left])
                right_floor = max(0, .01 * signal[right])
                while left > lower and signal[left] > left_floor:
                    left -= 1
                while right < upper and signal[right] > right_floor:
                    right += 1
                extended_left = max(lower, int(np.floor(indices[first] - (indices[first]-left)*extension_factor)))
                extended_right = min(upper, int(np.ceil(indices[last] + (right-indices[last])*extension_factor)))
                # Extension can cross a small, below-threshold neighbour. Stop
                # at the lowest point instead of anchoring on its rising flank.
                left = int(extended_left + np.argmin(raw[extended_left:left+1]))
                right = int(right + np.argmin(raw[right:extended_right+1]))
                splits = [int(a + np.argmin(raw[a:b+1]))
                          for a, b in zip(indices[first:last], indices[first+1:last+1])]
                bounds = [left, *splits, right]
                for offset, number in enumerate(group):
                    cluster_geometry[number] = (bounds[offset], bounds[offset+1], left, right)
        for number, idx in enumerate(indices):
            rt = float(time_axis[idx])
            apex_height = float(signal[idx])
            lower = valleys[number-1] if number else int(properties['left_bases'][number])
            upper = valleys[number] if number < len(valleys) else int(properties['right_bases'][number])
            left_ext = max(lower, int(np.floor(idx - (idx-left_ips[number])*extension_factor)))
            right_ext = min(upper, int(np.ceil(idx + (right_ips[number]-idx)*extension_factor)))

            if number in cluster_geometry:
                left_ext, right_ext, baseline_left, baseline_right = cluster_geometry[number]
            if right_ext <= left_ext:
                continue
            rt_start = float(time_axis[left_ext])
            rt_end = float(time_axis[right_ext])

            segment = slice(left_ext, right_ext + 1)
            xs = time_axis[segment]
            top = (signal if display_signal is None else np.asarray(display_signal))[segment]
            if integration_baseline == 'linear':
                bottom = np.interp(xs, time_axis[[baseline_left, baseline_right]],
                                   raw[[baseline_left, baseline_right]])
            elif integration_baseline == 'zero':
                bottom = np.zeros_like(xs)
            else:
                bottom = np.zeros_like(xs) if baseline is None else np.asarray(baseline)[segment]
            if integration_baseline is not None:
                response = np.maximum(top - bottom, 0)
                area = float(np.trapezoid(response, xs))
                apex_height = float(response[idx-left_ext])
            else:
                area = self.calculate_peak_area(signal, time_axis, rt_start, rt_end)
            width = rt_end - rt_start
            if area <= 0 or apex_height <= 0:
                continue

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
                color=self._next_color(file_id),
                source='detected',
            )
            # Display the same baseline used for quantitation.
            peak.poly_x = np.r_[xs, xs[::-1]].tolist()
            peak.poly_y = np.r_[top, bottom[::-1]].tolist()
            peak.q1 = (float(xs[0]), float(bottom[0]))
            peak.q2 = (float(xs[-1]), float(bottom[-1]))
            peak.p_line = [peak.q1, peak.q2]
            peak.width_half_height = self.calculate_width_at_half_height(
                response if integration_baseline is not None else signal,
                xs if integration_baseline is not None else time_axis, peak
            )
            peaks.append(peak)

        # Sort by retention time
        peaks.sort(key=lambda p: p.rt)
        # Rename after sorting
        for i, p in enumerate(peaks, start=1):
            p.name = f"Peak {i}"
        # Detection runs again whenever a setting changes: peaks the user has named keep their name.
        for old in previous_names:
            nearest = min(peaks, key=lambda p: abs(p.rt - old.rt), default=None)
            if nearest is not None and abs(nearest.rt - old.rt) <= max(0.05, 0.5 * (old.rt_end - old.rt_start)) \
                    and not self.has_custom_name(nearest):
                nearest.name = old.name
                nearest.label = old.label or old.name

        # Append to existing peaks (don't overwrite imported/manual)
        self._peaks[file_id] = existing_non_detected + peaks
        return peaks

    # ------------------------------------------------------------------
    # Boundary estimation from chromatogram signal
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_peak_shape(
        time_axis: np.ndarray,
        signal: np.ndarray,
        rt: float,
    ) -> Optional[dict]:
        """Estimate peak boundaries and polygon from chromatogram data.

        Walks left/right from the apex until the signal drops below 1% of
        peak height, then builds a filled polygon with a y=0 baseline.

        Returns None if the RT is out of range or no valid peak shape found.
        """
        if rt < time_axis[0] or rt > time_axis[-1]:
            return None

        local_apex = int(np.argmin(np.abs(time_axis - rt)))
        apex_rt = float(time_axis[local_apex])
        apex_height = float(signal[local_apex])
        if apex_height <= 0:
            return None

        floor = apex_height * 0.05

        # Walk left: stop at valley (signal starts rising) or floor
        left = local_apex
        while left > 1:
            if signal[left - 1] > signal[left]:
                break
            if signal[left] < floor:
                break
            left -= 1

        # Walk right: stop at valley (signal starts rising) or floor
        right = local_apex
        while right < len(signal) - 2:
            if signal[right + 1] > signal[right]:
                break
            if signal[right] < floor:
                break
            right += 1

        rt_start = float(time_axis[left])
        rt_end = float(time_axis[right])

        mask = (time_axis >= rt_start) & (time_axis <= rt_end)
        xs = time_axis[mask]
        ys = signal[mask]
        if len(xs) < 2:
            return None

        y_left = float(ys[0])
        y_right = float(ys[-1])
        baseline = y_left + (y_right - y_left) * (xs - xs[0]) / (xs[-1] - xs[0])
        diff = ys - baseline
        area = float(_trapezoid(np.maximum(diff, 0), xs))
        height = float(diff.max())

        baseline_clamped = np.minimum(baseline, ys)
        poly_x = np.concatenate([xs, xs[::-1]]).tolist()
        poly_y = np.concatenate([ys, baseline_clamped[::-1]]).tolist()
        p_line = [(rt_start, y_left), (rt_end, y_right)]

        return dict(
            apex_rt=apex_rt,
            apex_height=apex_height,
            rt_start=rt_start,
            rt_end=rt_end,
            area=area,
            height=height,
            width=rt_end - rt_start,
            poly_x=poly_x,
            poly_y=poly_y,
            p_line=p_line,
            q1=(rt_start, y_left),
            q2=(rt_end, y_right),
        )

    # ------------------------------------------------------------------
    # Instrument peak import
    # ------------------------------------------------------------------

    def import_instrument_peaks(
        self, file_id: str, parsed_results: List[dict],
        sample_name: str = "",
        time_axis: Optional[np.ndarray] = None,
        signal: Optional[np.ndarray] = None,
    ) -> List[Peak]:
        """Import peaks parsed from instrument integration results.

        When time_axis and signal are provided, boundaries and polygons are
        estimated from the chromatogram so imported peaks are fully editable
        — identical to manually drawn peaks.

        Parameters
        ----------
        file_id : str
            Identifier for the source file/bundle.
        parsed_results : list of dict
            Each dict has keys like 'peak_number', 'peak_name',
            'retention_time', 'area', 'height'.
        sample_name : str
            Human-readable sample label.
        time_axis, signal : ndarray, optional
            Chromatogram arrays for boundary estimation.
        """
        file_id = self._resolve_file_id(file_id)
        fid = file_id

        if fid in self._imported_files:
            return self._peaks.get(fid, [])
        self._imported_files.add(fid)

        has_signal = time_axis is not None and signal is not None
        if has_signal:
            time_axis = np.asarray(time_axis, dtype=float)
            signal = np.asarray(signal, dtype=float)

        peaks: List[Peak] = []
        for r in parsed_results:
            rt = r.get('retention_time', 0.0)
            name = r.get('peak_name', '') or f"Peak {r.get('peak_number', len(peaks)+1)}"

            shape = self._estimate_peak_shape(time_axis, signal, rt) if has_signal else None

            if shape:
                peak = Peak(
                    peak_id=str(uuid.uuid4()),
                    file_id=fid,
                    name=name,
                    rt=shape['apex_rt'],
                    rt_start=shape['rt_start'],
                    rt_end=shape['rt_end'],
                    area=r.get('area', shape['area']),
                    height=r.get('height', shape['height']),
                    width=shape['width'],
                    color=self._next_color(file_id),
                    source='imported',
                    poly_x=shape['poly_x'],
                    poly_y=shape['poly_y'],
                    p_line=shape['p_line'],
                    q1=shape['q1'],
                    q2=shape['q2'],
                )
            else:
                peak = Peak(
                    peak_id=str(uuid.uuid4()),
                    file_id=fid,
                    name=name,
                    rt=rt,
                    rt_start=rt,
                    rt_end=rt,
                    area=r.get('area', 0.0),
                    height=r.get('height', 0.0),
                    width=0.0,
                    color=self._next_color(file_id),
                    source='imported',
                )
            peaks.append(peak)

        self._peaks[fid] = peaks
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
        file_id = self._resolve_file_id(file_id)
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
            color=self._next_color(file_id),
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
        source: str = 'manual',
        name: Optional[str] = None,
        label: Optional[str] = None,
        deconv_group: Optional[str] = None,
        fit_params: Optional[Dict] = None,
    ) -> Peak:
        """Add a manually integrated peak from baseline drawing (p-line).

        If a manual peak with a very close apex already exists, it is updated
        instead of creating a duplicate.

        ``source`` tags the peak's origin ('manual' by default; 'cross_integrated'
        when dropped in by the cross-file integration tool). ``name``/``label``
        let cross-file integration inherit the source peak's compound name.

        Deconvolved peaks (``source='deconvolved'``) are always appended fresh
        and carry their ``deconv_group``/``fit_params`` tags — the overlap
        replacement is skipped so sibling components (which overlap by nature)
        never clobber one another. Clearing pre-existing peaks in the region is
        the caller's responsibility for deconvolution.
        """
        file_id = self._resolve_file_id(file_id)
        existing = self._peaks.get(file_id, [])

        if source == 'deconvolved':
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
                color=self._next_color(file_id),
                source='deconvolved',
                poly_x=poly_x,
                poly_y=poly_y,
                p_line=p_line,
                q1=q1,
                q2=q2,
                deconv_group=deconv_group,
                fit_params=fit_params,
            )
            self._peaks.setdefault(file_id, []).append(peak)
            return peak

        line_x_min = min(p_line[0][0], p_line[1][0])
        line_x_max = max(p_line[0][0], p_line[1][0])
        for p in existing:
            p_width = p.rt_end - p.rt_start
            overlap = max(0, min(line_x_max, p.rt_end) - max(line_x_min, p.rt_start))
            if (p_width > 0 and overlap / p_width > 0.5) or abs(p.rt - apex_x) < 0.05:
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
                p.source = source
                if name is not None:
                    p.name = name
                if label is not None:
                    p.label = label
                return p

        peak_number = len(existing) + 1
        peak = Peak(
            peak_id=str(uuid.uuid4()),
            file_id=file_id,
            name=name if name is not None else f"Peak {peak_number}",
            rt=apex_x,
            rt_start=min(p_line[0][0], p_line[1][0]),
            rt_end=max(p_line[0][0], p_line[1][0]),
            area=area,
            height=height,
            width=abs(p_line[1][0] - p_line[0][0]),
            color=self._next_color(file_id),
            source=source,
            label=label if label is not None else '',
            poly_x=poly_x,
            poly_y=poly_y,
            p_line=p_line,
            q1=q1,
            q2=q2,
        )
        self._peaks.setdefault(file_id, []).append(peak)
        return peak

    def find_matching_peak(
        self,
        file_id: str,
        target_rt: float,
        tolerance: float,
        signal: np.ndarray,
        time: np.ndarray,
        prominence_frac: float = 0.01,
    ) -> Optional[dict]:
        """Find and integrate the peak nearest to *target_rt* within a window.

        Searches ``[target_rt - tolerance, target_rt + tolerance]`` for the
        local maximum **closest to target_rt** (not the tallest). This ensures
        cross-file integration matches the same compound, even when a taller
        neighbour sits inside the tolerance window.

        Walks the flanks down to the peak foot (valley or 1 % of apex height),
        integrates against a straight baseline, and returns geometry ready for
        ``add_baseline_peak``.

        Returns a dict with apex_x, height, area, rt_start, rt_end, poly_x,
        poly_y, p_line, q1, q2 — or ``None``.
        """
        signal = np.asarray(signal, dtype=float)
        time = np.asarray(time, dtype=float)
        if signal.size < 3:
            return None

        sig_range = float(np.ptp(signal))
        if sig_range == 0:
            return None

        lo = target_rt - tolerance
        hi = target_rt + tolerance
        win_idx = np.where((time >= lo) & (time <= hi))[0]
        if win_idx.size < 3:
            return None

        win_sig = signal[win_idx]
        rel_peaks, _ = find_peaks(win_sig)
        if rel_peaks.size > 0:
            rel_rts = time[win_idx[0] + rel_peaks]
            nearest = int(np.argmin(np.abs(rel_rts - target_rt)))
            apex_idx = int(win_idx[0] + rel_peaks[nearest])
        else:
            apex_idx = int(win_idx[0] + int(np.argmax(win_sig)))

        apex_h = float(signal[apex_idx])
        if apex_h <= 0:
            return None

        base_floor = apex_h * 0.01
        n = signal.size

        left = apex_idx
        while left > 0:
            if signal[left] <= base_floor:
                break
            if signal[left - 1] > signal[left]:
                break
            left -= 1

        right = apex_idx
        while right < n - 1:
            if signal[right] <= base_floor:
                break
            if signal[right + 1] > signal[right]:
                break
            right += 1

        if right <= left:
            return None

        xs = time[left:right + 1]
        ys = signal[left:right + 1]
        y_left = float(signal[left])
        y_right = float(signal[right])
        baseline = y_left + (y_right - y_left) * (xs - xs[0]) / (xs[-1] - xs[0])
        diff = ys - baseline
        area = float(_trapezoid(np.maximum(diff, 0), xs))
        if area <= 0:
            return None

        rt_start = float(time[left])
        rt_end = float(time[right])
        baseline_clamped = np.minimum(baseline, ys)
        return dict(
            apex_x=float(time[apex_idx]),
            height=float(diff.max()),
            area=area,
            rt_start=rt_start,
            rt_end=rt_end,
            poly_x=np.concatenate([xs, xs[::-1]]).tolist(),
            poly_y=np.concatenate([ys, baseline_clamped[::-1]]).tolist(),
            p_line=[(rt_start, y_left), (rt_end, y_right)],
            q1=(rt_start, y_left),
            q2=(rt_end, y_right),
        )

    def clear_region(
        self, file_id: str, rt_lo: float, rt_hi: float, min_overlap: float = 0.5
    ) -> int:
        """Remove peaks overlapping ``[rt_lo, rt_hi]`` by more than
        ``min_overlap`` of their own width. Returns the number removed.

        Used by deconvolution accept to clear pre-existing peaks in a region
        before dropping in the fitted components.
        """
        file_id = self._resolve_file_id(file_id)
        peaks = self._peaks.get(file_id)
        if not peaks:
            return 0
        kept: List[Peak] = []
        removed = 0
        for p in peaks:
            width = p.rt_end - p.rt_start
            overlap = max(0.0, min(rt_hi, p.rt_end) - max(rt_lo, p.rt_start))
            if width > 0 and overlap / width > min_overlap:
                removed += 1
            else:
                kept.append(p)
        self._peaks[file_id] = kept
        return removed

    def clear_peaks(self, file_id: str) -> None:
        """Remove all peaks for a bundle."""
        file_id = self._resolve_file_id(file_id)
        self._peaks.pop(file_id, None)
        self._imported_files.discard(file_id)
        self._file_color_index.pop(file_id, None)

    def clear_all_peaks(self) -> None:
        """Remove every peak. Used when all files are deleted."""
        self._peaks.clear()
        self._imported_files.clear()
        self._color_index = 0
        self._file_color_index.clear()
        self._group_colors.clear()  # clears entire nested dict
        self._grouping_window = None

    def clear_manual_peaks(self, file_id: str) -> None:
        """Remove all manual baseline peaks for a file."""
        file_id = self._resolve_file_id(file_id)
        fid = file_id
        if fid in self._peaks:
            self._peaks[fid] = [p for p in self._peaks[fid] if p.source != 'manual']

    def clear_detected_peaks(self, file_id: str) -> None:
        """Remove all auto-detected peaks for a file."""
        file_id = self._resolve_file_id(file_id)
        fid = file_id
        if fid in self._peaks:
            self._peaks[fid] = [p for p in self._peaks[fid] if p.source != 'detected']

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def remove_peak(self, file_id: str, peak_id: str) -> bool:
        """Remove a peak by ID. Returns True if found and removed."""
        file_id = self._resolve_file_id(file_id)
        fid = file_id
        peaks = self._peaks.get(fid)
        if peaks is None:
            return False
        before = len(peaks)
        self._peaks[fid] = [p for p in peaks if p.peak_id != peak_id]
        return len(self._peaks[fid]) < before

    def delete_peaks(self, targets, file_overlay_map: Optional[Dict[str, str]] = None) -> List[Peak]:
        """Delete peaks from every UI path (tables, context menu, keyboard).

        ``targets`` is an iterable of ``(file_id, peak_id)``. One undo snapshot
        covers the whole batch. Unknown targets are ignored; nothing is saved
        and nothing is regrouped when no peak was actually found. Surviving
        siblings (e.g. the other components of a deconvolution) keep their tags
        and colours. Returns the removed peaks.
        """
        found = []
        for file_id, peak_id in dict.fromkeys((f, p) for f, p in targets if f and p):
            peak = next((p for p in self._peaks.get(self._resolve_file_id(file_id), [])
                         if p.peak_id == peak_id), None)
            if peak is not None:
                found.append((file_id, peak))
        if not found:
            return []
        self.save_undo()
        for file_id, peak in found:
            self.remove_peak(file_id, peak.peak_id)
        self.group_peaks_across_samples(file_overlay_map=file_overlay_map)
        return [peak for _, peak in found]

    def set_label_position(self, file_id: str, peak_id: str, offset, leader: bool = False, in_data: bool = False) -> bool:
        """Place a peak's name label ``offset`` = (dx, dy) from its spot above the peak (dy up), in screen pixels or, with
        ``in_data``, in the plot's units (minutes, signal); with or without a leader line. None puts it back."""
        file_id = self._resolve_file_id(file_id)
        for peak in self._peaks.get(file_id, []):
            if peak.peak_id == peak_id:
                if offset is None:
                    peak.label_offset, peak.label_leader, peak.label_in_data = None, False, False
                elif in_data:
                    peak.label_offset = [float(f'{float(offset[0]):.6g}'), float(f'{float(offset[1]):.6g}')]
                    peak.label_leader, peak.label_in_data = bool(leader), True
                else:
                    peak.label_offset = [round(float(offset[0]), 1), round(float(offset[1]), 1)]
                    peak.label_leader, peak.label_in_data = bool(leader), False
                return True
        return False

    def rename_peak(self, file_id: str, peak_id: str, new_name: str) -> bool:
        """Rename a peak and propagate to all peaks in the same group."""
        file_id = self._resolve_file_id(file_id)
        fid = file_id
        target = None
        for p in self._peaks.get(fid, []):
            if p.peak_id == peak_id:
                p.name = new_name
                p.label = new_name                      # the plot shows the label; one name everywhere
                target = p
                break
        if target is None:
            return False
        if target.group_id:
            for pks in self._peaks.values():
                for p in pks:
                    if p.group_id == target.group_id:
                        p.name = new_name
                        p.label = new_name
        return True

    @staticmethod
    def has_custom_name(peak: "Peak") -> bool:
        """True when the user (or a calibration) named the peak, i.e. it is not the automatic "Peak 3"."""
        return re.fullmatch(r'Peak \d+', peak.name or '') is None and bool(peak.name or peak.label)

    def set_peak_color(
        self,
        file_id: str,
        peak_id: str,
        color: str,
        opacity: Optional[float] = None,
    ) -> bool:
        """Update the display color (and optionally opacity) of a peak."""
        file_id = self._resolve_file_id(file_id)
        fid = file_id
        for p in self._peaks.get(fid, []):
            if p.peak_id == peak_id:
                p.color = color
                if opacity is not None:
                    p.opacity = opacity
                return True
        return False

    def has_peak_history(self, file_id: str) -> bool:
        """An empty edited peak list must not trigger another instrument import."""
        return self._resolve_file_id(file_id) in self._peaks

    def get_peaks(self, file_id: str) -> List[Peak]:
        """Return all peaks for a given file."""
        file_id = self._resolve_file_id(file_id)
        return list(self._peaks.get(file_id, []))

    def get_all_peaks(self) -> Dict[str, List[Peak]]:
        """Return all peaks keyed by file_id."""
        for fid in list(self._peaks):
            self._resolve_file_id(fid)
        return {fid: list(pks) for fid, pks in self._peaks.items()}

    # ------------------------------------------------------------------
    # Cross-sample grouping
    # ------------------------------------------------------------------

    def group_peaks_across_samples(
        self,
        rt_window: float = 0.2,
        file_overlay_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, List[Peak]]:
        """
        Group peaks from all loaded files by retention time proximity.

        Peaks whose apex RTs fall within *rt_window* minutes of each other
        are considered the same compound across samples. Each group receives
        a shared ``group_id`` and a consistent color.

        Existing identities and colours survive additions and removals. New
        peaks use the nearest available match, with one peak per file in each
        group. A scope resolver can match comparable signals across plot tabs.

        Parameters
        ----------
        rt_window : float
            Maximum RT difference (minutes) to merge peaks into a group.
        file_overlay_map : dict, optional
            Maps file_id -> overlay group key string. Files that share an
            overlay group (i.e. the same plot tab) get independent color
            cycling.  When *None*, all files share a single color scope
            (legacy behaviour).

        Returns
        -------
        Dict[str, List[Peak]]
            group_id -> list of peaks in that group.
        """
        # Keep established identities instead of reclustering from the leftmost
        # peak on every edit. Otherwise removing a neighbour can change a
        # surviving peak's group (and its colour).
        regroup = self._grouping_window is not None and rt_window != self._grouping_window
        self._grouping_window = rt_window
        buckets: Dict[str, List[Peak]] = {}
        for fid, peaks in self.get_all_peaks().items():
            scope = (self._color_scope_resolver(fid) if self._color_scope_resolver
                     else (file_overlay_map or {}).get(fid, ''))
            buckets.setdefault(scope, []).extend(peaks)
        result: Dict[str, List[Peak]] = {}
        pal = self._palette or OKABE_ITO_PALETTE

        def anchor(gid):
            try:
                return float(gid.removeprefix('compound_rt').split('_')[0])
            except (ValueError, AttributeError):
                return None

        for scope, peaks in buckets.items():
            colors = self._group_colors.setdefault(scope, {})
            groups: Dict[str, List[Peak]] = {}
            pending = []
            for peak in peaks:
                if peak.source == 'deconvolved' and peak.deconv_group:
                    groups.setdefault(peak.deconv_group, []).append(peak)
                elif peak.group_id and not regroup:
                    groups.setdefault(peak.group_id, []).append(peak)
                else:
                    pending.append(peak)

            # Assign closest pairs first. A broad tolerance must not let an
            # earlier, weaker match steal the exact RT match in another file.
            while pending:
                candidates = []
                for i, peak in enumerate(pending):
                    for gid in dict.fromkeys([*groups, *([] if regroup else colors)]):
                        rt = anchor(gid)
                        if rt is None:
                            continue  # deconvolution components retain their tags
                        members = groups.get(gid, [])
                        if any(p.file_id == peak.file_id for p in members):
                            continue
                        distance = min((abs(peak.rt-p.rt) for p in members),
                                       default=abs(peak.rt-rt))
                        if distance <= rt_window:
                            candidates.append((distance, i, gid))
                if candidates:
                    _, index, gid = min(candidates)
                    peak = pending.pop(index)
                else:
                    peak = pending.pop(0)
                    base = (peak.group_id if regroup and peak.group_id else f'compound_rt{peak.rt:.3f}')
                    gid = base
                    suffix = 2
                    while gid in groups or (gid in colors and not regroup):
                        gid = f'{base}_{suffix}'
                        suffix += 1
                groups.setdefault(gid, []).append(peak)

            for gid, members in groups.items():
                if gid not in colors:
                    # Preserve imported colours when available, but don't restart
                    # the palette for each sample. Deleted identities stay reserved.
                    preferred = members[0].color
                    free = [c for c in pal if c not in colors.values()]
                    colors[gid] = (preferred if preferred in free and not members[0].group_id
                                   else free[0] if free else pal[len(colors) % len(pal)])
                for peak in members:
                    peak.group_id = gid
                    peak.color = colors[gid]
                result.setdefault(gid, []).extend(members)
            self._name_groups(groups)

        return result

    def _name_groups(self, groups: Dict[str, List[Peak]]) -> None:
        """One name per group: the same compound has the same name in every sample.

        A group with a name the user gave (or a calibration) gives it to all its members; groups that only have
        automatic names are numbered across the samples by retention time (Peak 1, Peak 2 ...) instead of within each
        sample, where one compound could be "Peak 1" in one run and "Peak 2" in the next.
        """
        named = {}
        for gid, members in groups.items():
            custom = [p.label or p.name for p in members if self.has_custom_name(p)]
            if custom:
                named[gid] = max(dict.fromkeys(custom), key=custom.count)       # most used; first one on a tie
        automatic = [gid for gid, members in groups.items()
                     if gid not in named and members and not any(p.source == 'deconvolved' for p in members)]
        automatic.sort(key=lambda gid: float(np.median([p.rt for p in groups[gid]])))
        for number, gid in enumerate(automatic, start=1):
            named[gid] = f'Peak {number}'
        for gid, name in named.items():
            for peak in groups[gid]:
                if peak.source == 'deconvolved':
                    continue
                peak.name = name
                peak.label = name

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

        area = float(_trapezoid(s_seg, t_seg))
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
        file_id = self._resolve_file_id(file_id)
        peaks = self._peaks.get(file_id, [])
        if not peaks:
            return pd.DataFrame()
        total_area = sum(max(float(p.area or 0.0), 0.0) for p in peaks)
        total_height = sum(max(float(p.height or 0.0), 0.0) for p in peaks)
        rows = []
        for i, p in enumerate(sorted(peaks, key=lambda pk: pk.rt), start=1):
            rows.append({
                'No.': i,
                'peak_id': p.peak_id,
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
        file_id = self._resolve_file_id(file_id)
        peaks = self._peaks.get(file_id, [])
        if not peaks:
            return pd.DataFrame(columns=[
                "peak_id", "file_id", "name", "rt", "rt_start", "rt_end",
                "area", "height", "width", "width_half_height", "color",
                "opacity", "group_id", "calibration_id", "concentration",
                "source", "deconv_group", "fit_params",
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
        """Serialize all peak data for persistence (JSON-compatible).

        Complete: besides the peaks (incl. deconvolution fields) this carries
        the colour bookkeeping, the palette and the set of files whose
        instrument peaks were already imported, so a restored workspace never
        re-imports them over the saved peaks.
        """
        return {
            "grouping_window": self._grouping_window,
            "color_index": self._color_index,
            "file_color_index": self._file_color_index,
            "group_colors": self._group_colors,  # nested dict, JSON-safe
            "imported_files": sorted(self._imported_files),
            "palette": list(self._palette),
            "palette_name": self._palette_name,
            "peaks": {
                fid: [asdict(p) for p in pks]
                for fid, pks in self._peaks.items()
            },
        }

    _PEAK_TUPLE_FIELDS = ("q1", "q2")

    @classmethod
    def _peak_from_dict(cls, d: dict, file_id: Optional[str] = None) -> "Peak":
        if not isinstance(d, dict):
            raise ValueError(f'a saved peak must be an object, not {type(d).__name__}')
        values = {k: v for k, v in d.items() if k in Peak.__dataclass_fields__}
        # Tolerate older / hand-edited files: identity fields are filled in. The measured values
        # (rt, rt_start, rt_end, area, height, width) are never invented: a peak without them is
        # rejected (TypeError), which restore_session catches in its dry run before touching the workspace.
        values.setdefault('peak_id', str(uuid.uuid4()))
        values.setdefault('file_id', file_id or '')
        values.setdefault('name', '')
        # JSON turns tuples into lists; the in-memory model uses tuples.
        for key in cls._PEAK_TUPLE_FIELDS:
            if isinstance(values.get(key), list):
                values[key] = tuple(values[key])
        if isinstance(values.get("p_line"), list):
            values["p_line"] = [tuple(point) for point in values["p_line"]]
        return Peak(**values)

    def deserialize(self, data: dict) -> None:
        """Restore peak data from a previously serialized dict.

        All peaks are parsed first, so malformed data raises before this service is modified.
        """
        peaks = {fid: [self._peak_from_dict(d, fid) for d in peak_dicts]
                 for fid, peak_dicts in data.get("peaks", {}).items()}
        self._grouping_window = data.get("grouping_window")
        self._color_index = data.get("color_index", 0)
        self._file_color_index = data.get("file_color_index", {})
        # Support both old flat format and new nested format
        raw_gc = data.get("group_colors", {})
        if raw_gc and isinstance(next(iter(raw_gc.values()), None), str):
            # Old flat format {gid: color} -> migrate to nested under ''
            self._group_colors = {'': raw_gc}
        else:
            self._group_colors = raw_gc
        # Absent in data written before these fields existed: keep defaults.
        if "imported_files" in data:
            self._imported_files = set(data["imported_files"])
        if data.get("palette"):
            self._palette = list(data["palette"])
        if data.get("palette_name"):
            self._palette_name = data["palette_name"]
            if not data.get("palette"):
                self._palette = self._named_palette(self._palette_name)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._peaks.clear()
        self._peaks.update(peaks)

    def rekey_files(self, mapping: Dict[str, str]) -> None:
        """Move peaks and per-file bookkeeping to new file ids ({old: new})."""
        if not mapping:
            return
        def key(value):
            return mapping.get(value, value)
        self._peaks = {key(fid): peaks for fid, peaks in self._peaks.items()}
        for fid, peaks in self._peaks.items():
            for peak in peaks:
                peak.file_id = fid
        self._imported_files = {key(fid) for fid in self._imported_files}
        self._file_color_index = {key(fid): index for fid, index in self._file_color_index.items()}
        self._undo_stack.clear()
        self._redo_stack.clear()
