# =============================================================================
# File: callbacks/integration_callbacks.py
# =============================================================================
"""
Integration toolbox callbacks for GeckoPlotter V2.

Wires the Integration tab controls (peak detection, display options)
to IntegrationService + PeakService.
"""

import logging
import sys

import dash
from dash import Input, Output, State

log = logging.getLogger('geckoplotter.integration')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def register_integration_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Integration toolbox callbacks."""

    from callbacks.baseline_callbacks import get_xy_arrays

    def _get_xy(file_id):
        return get_xy_arrays(data_manager, file_id)

    # ── Detect Peaks ──────────────────────────────────────────────────

    @app.callback(
        Output('peak-change-trigger', 'data', allow_duplicate=True),
        Input('int-detect-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('int-peak-threshold', 'value'),
         State('current-plot-settings', 'data'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def detect_peaks(n_clicks, active_file, peak_threshold, plot_settings, trigger_counter):
        if not n_clicks or not active_file:
            return dash.no_update

        time_arr, signal_arr = _get_xy(active_file)
        if time_arr is None:
            log.debug("No plottable X/Y data for integration")
            return dash.no_update

        smooth_window = (plot_settings or {}).get('smooth_window', 0)
        effective_window = max(3, smooth_window) if smooth_window > 0 else 11

        data_manager.integration_service.update_settings(
            active_file,
            smooth_window=effective_window,
            smooth_poly_order=3,
            baseline_method='snip',
            baseline_iterations=40,
            baseline_poly_order=5,
            peak_threshold=float(peak_threshold or 0.01),
            slope_threshold=0.001,
            extension_factor=1.1,
            min_peak_width=3,
        )

        processed = data_manager.integration_service.process_signal(
            active_file, time_arr, signal_arr,
        )

        settings = data_manager.integration_service.get_settings(active_file)
        peaks = data_manager.peak_service.detect_peaks(
            file_id=active_file,
            signal=processed.corrected,
            time_axis=processed.time,
            threshold=settings.peak_threshold,
            slope_threshold=settings.slope_threshold,
            extension_factor=settings.extension_factor,
        )

        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"Detected {len(peaks)} peaks for {active_file}")
        return (trigger_counter or 0) + 1

    # ── Clear Peaks ───────────────────────────────────────────────────

    @app.callback(
        Output('peak-change-trigger', 'data', allow_duplicate=True),
        Input('int-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_peaks(n_clicks, active_file, trigger_counter):
        if not n_clicks or not active_file:
            return dash.no_update

        data_manager.peak_service.clear_detected_peaks(active_file)
        data_manager.integration_service.clear_processed_signal(active_file)
        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"Cleared peaks for {active_file}")
        return (trigger_counter or 0) + 1
