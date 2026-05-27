# =============================================================================
# File: callbacks/integration_callbacks.py
# =============================================================================
"""
Integration toolbox callbacks for GeckoPlotter V2.

Wires the Integration tab controls (smoothing, baseline, peak detection)
to IntegrationService + PeakService, and overlays results on main-plot.
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

    def _get_chromatogram_arrays(file_id):
        """Extract time and signal arrays from the active chromatogram.

        Returns (time, signal) numpy arrays or (None, None) if the active
        file is not a chromatogram.
        """
        file_data = data_manager.get_data_by_id(file_id)
        if file_data is None:
            bundle = data_manager.get_bundle_by_id(file_id)
            if bundle and bundle.main_file:
                file_data = data_manager.get_data_by_id(bundle.main_file.get('id'))

        if file_data is None:
            return None, None

        df = file_data.get('data')
        if df is None:
            return None, None

        # Chromatogram columns: 'Time (min)' / 'Value (mAU)'
        time_col = signal_col = None
        for c in df.columns:
            cl = c.lower()
            if 'time' in cl:
                time_col = c
            elif 'value' in cl or 'intensity' in cl or 'mau' in cl:
                signal_col = c

        if time_col is None or signal_col is None:
            return None, None

        return (
            df[time_col].to_numpy(dtype=float),
            df[signal_col].to_numpy(dtype=float),
        )

    # ── Detect Peaks ──────────────────────────────────────────────────

    @app.callback(
        Output('peak-change-trigger', 'data', allow_duplicate=True),
        Input('int-detect-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('int-smooth-window', 'value'),
         State('int-smooth-poly', 'value'),
         State('int-baseline-method', 'value'),
         State('int-baseline-iter', 'value'),
         State('int-baseline-poly', 'value'),
         State('int-peak-threshold', 'value'),
         State('int-slope-threshold', 'value'),
         State('int-extension', 'value'),
         State('int-min-width', 'value'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def detect_peaks(
        n_clicks, active_file,
        smooth_window, smooth_poly,
        baseline_method, baseline_iter, baseline_poly,
        peak_threshold, slope_threshold, extension_factor, min_width,
        trigger_counter,
    ):
        if not n_clicks or not active_file:
            return dash.no_update

        time_arr, signal_arr = _get_chromatogram_arrays(active_file)
        if time_arr is None:
            log.debug("No chromatogram data for integration")
            return dash.no_update

        # Update IntegrationService settings
        data_manager.integration_service.update_settings(
            active_file,
            smooth_window=int(smooth_window or 11),
            smooth_poly_order=int(smooth_poly or 3),
            baseline_method=baseline_method or 'snip',
            baseline_iterations=int(baseline_iter or 40),
            baseline_poly_order=int(baseline_poly or 5),
            peak_threshold=float(peak_threshold or 0.01),
            slope_threshold=float(slope_threshold or 0.001),
            extension_factor=float(extension_factor or 1.1),
            min_peak_width=int(min_width or 3),
        )

        # Process signal
        processed = data_manager.integration_service.process_signal(
            active_file, time_arr, signal_arr,
        )

        # Detect peaks on the corrected signal
        settings = data_manager.integration_service.get_settings(active_file)
        peaks = data_manager.peak_service.detect_peaks(
            file_id=active_file,
            signal=processed.corrected,
            time_axis=processed.time,
            threshold=settings.peak_threshold,
            slope_threshold=settings.slope_threshold,
            extension_factor=settings.extension_factor,
        )

        data_manager.peak_service.group_peaks_across_samples()
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
        data_manager.peak_service.group_peaks_across_samples()
        log.debug(f"Cleared peaks for {active_file}")
        return (trigger_counter or 0) + 1
