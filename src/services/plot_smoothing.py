"""Display-only smoothing helpers for rendered Plotly traces."""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np


def _coerce_window(requested_window) -> int:
    try:
        return int(round(float(requested_window or 0)))
    except (TypeError, ValueError):
        return 0


def normalize_smooth_window(requested_window, n_points: int) -> int:
    """Return an odd Savitzky-Golay window that fits the data, or 0 for off."""
    window = _coerce_window(requested_window)
    if window < 3 or n_points < 3:
        return 0

    window = min(window, int(n_points))
    if window % 2 == 0:
        window -= 1
    return window if window >= 3 else 0


def smooth_trace_y(y_values, requested_window):
    """Smooth one y-array without mutating source data.

    Returns ``None`` when smoothing should be skipped.
    """
    try:
        y = np.asarray(y_values, dtype=float)
    except (TypeError, ValueError):
        return None

    if y.ndim != 1 or y.size < 3 or not np.all(np.isfinite(y)):
        return None

    window = normalize_smooth_window(requested_window, y.size)
    if not window:
        return None

    try:
        from scipy.signal import savgol_filter
    except Exception:
        return None

    poly_order = min(3, window - 1)
    return savgol_filter(y, window, poly_order)


def smooth_plotly_traces(traces: Iterable, requested_window) -> None:
    """Apply display-only smoothing to line-like Plotly traces in-place."""
    window = normalize_smooth_window(requested_window, 10**9)
    if not window:
        return

    for trace in traces:
        if getattr(trace, "type", "") not in ("scatter", "scattergl"):
            continue
        mode = getattr(trace, "mode", None)
        if mode and "lines" not in str(mode):
            continue
        if getattr(trace, "y", None) is None:
            continue

        smoothed = smooth_trace_y(trace.y, window)
        if smoothed is not None:
            trace.y = tuple(smoothed)


def smoothing_fair_export_record(requested_window, n_points: Optional[int] = None) -> dict:
    """Describe the smoothing transform for future FAIR-style report export.

    The record is intentionally explicit about scope: smoothing is a visual
    processing step for plotted line traces and does not overwrite imported
    source data.
    """
    requested = _coerce_window(requested_window)
    effective = normalize_smooth_window(requested, n_points or 10**9)
    poly_order = min(3, effective - 1) if effective else None

    return {
        "processing_step": "display_smoothing",
        "applied": bool(effective),
        "algorithm": "Savitzky-Golay filter",
        "implementation": "scipy.signal.savgol_filter",
        "parameters": {
            "requested_window_points": requested,
            "effective_window_points": effective,
            "polynomial_order": poly_order,
            "edge_mode": "interp",
        },
        "scope": "Rendered line traces only; imported source data remains unchanged.",
        "input": "Trace y-values in plotted x-axis order",
        "output": "Smoothed y-values for visualization and publication preview",
    }
