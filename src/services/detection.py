"""Automatic peak detection on one signal, as the Integration inspector's Detect button runs it.

Shared by the button (callbacks/integration_callbacks.py) and the agent interface (gecko_api.py), so both give the same
peaks for the same signal and sensitivity.
"""
from __future__ import annotations


def sensitivity_threshold(value) -> float:
    """Map a left-to-right sensitivity fader (0-100) to a minimum height fraction."""
    sensitivity = 50 if value is None else min(100, max(0, float(value)))
    return max(.001, (100 - sensitivity) / 100)


def detect(store, file_id, time_arr, signal_arr, sensitivity=50, smooth_window=0, baseline_mode='linear'):
    """Smooth, correct the baseline and detect the peaks of one signal; they replace its earlier detected peaks
    (manual ones stay) and are grouped across samples. Returns the new peaks."""
    effective_window = max(3, smooth_window) if smooth_window and smooth_window > 0 else 11
    service = store.integration_service
    service.update_settings(
        file_id,
        smooth_window=effective_window,
        smooth_poly_order=3,
        baseline_method='snip',
        baseline_iterations=40,
        baseline_poly_order=5,
        peak_threshold=sensitivity_threshold(sensitivity),
        slope_threshold=0.001,
        extension_factor=1.1,
        min_peak_width=3,
    )
    processed = service.process_signal(file_id, time_arr, signal_arr)
    settings = service.get_settings(file_id)
    store.peak_service.save_undo()                      # Cmd/Ctrl-Z brings the previous peaks back
    peaks = store.peak_service.detect_peaks(
        file_id=file_id,
        signal=processed.corrected,
        time_axis=processed.time,
        threshold=settings.peak_threshold,
        slope_threshold=settings.slope_threshold,
        extension_factor=settings.extension_factor,
        display_signal=processed.raw,
        integration_baseline=baseline_mode or 'linear',
    )
    store.peak_service.group_peaks_across_samples(file_overlay_map=store.build_file_overlay_map())
    return peaks
