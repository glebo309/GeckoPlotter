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


def sensitivity_threshold(value):
    """Map a left-to-right sensitivity fader to a minimum height fraction."""
    sensitivity = 50 if value is None else min(100, max(0, float(value)))
    return max(.001, (100-sensitivity)/100)


def register_integration_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Integration toolbox callbacks."""

    from callbacks.baseline_callbacks import get_xy_arrays

    def _get_xy(file_id):
        return get_xy_arrays(data_manager, file_id)

    def target(active_file):
        bundle = data_manager.get_bundle(active_file)
        if bundle and bundle.primary:
            active_file = bundle.primary.component_id
        entry = data_manager.get_data_by_id(active_file) if active_file else None
        name = (entry or {}).get('record', {}).get('name', '')
        return active_file, name

    @app.callback(
        [Output('int-detection-target', 'children'),
         Output('int-detect-btn', 'disabled'), Output('int-clear-btn', 'disabled')],
        [Input('active-file', 'data'), Input('loaded-files', 'data'), Input('pda-preview', 'data')],
    )
    def detection_target(active_file, _, preview=None):
        file_id, name = target(active_file)
        x, y = _get_xy(file_id) if file_id else (None, None)
        unavailable = bool(preview) or x is None or y is None or len(x) < 3
        return ('Select a signal in Files' if unavailable else f'Signal: {name}'), unavailable, unavailable

    @app.callback(
        Output('render-trigger', 'data', allow_duplicate=True),
        Input('int-display-opts', 'value'),
        State('render-trigger', 'data'),
        prevent_initial_call=True,
    )
    def update_peak_visibility(_options, counter):
        return (counter or 0) + 1

    @app.callback(
        Output('int-sensitivity-help', 'children'),
        Input('int-detection-sensitivity', 'value'),
    )
    def explain_sensitivity(value):
        percent = sensitivity_threshold(value) * 100
        return f'Minimum height: {percent:g}%'

    # ── Detect Peaks ──────────────────────────────────────────────────

    @app.callback(
        [Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('status-text', 'children', allow_duplicate=True),
         Output('current-plot-settings', 'data', allow_duplicate=True)],
        [Input('int-detect-btn', 'n_clicks'),
         Input('int-detection-sensitivity', 'value')],
        [State('active-file', 'data'),
         State('current-plot-settings', 'data'),
         State('peak-change-trigger', 'data'),
         State('integration-baseline', 'value'), State('pda-preview', 'data')],
        prevent_initial_call=True,
    )
    def detect_peaks(n_clicks, sensitivity, active_file, plot_settings, trigger_counter, baseline_mode='linear', preview=None):
        if preview:
            return dash.no_update, 'Set the wavelength before integrating the preview.', dash.no_update
        if not n_clicks or not active_file:
            return dash.no_update, dash.no_update, dash.no_update

        active_file, target_name = target(active_file)
        try:
            slider_changed = dash.ctx.triggered_id == 'int-detection-sensitivity'
        except dash.exceptions.MissingCallbackContextException:
            slider_changed = False
        if slider_changed and data_manager.integration_service.get_processed_signal(active_file) is None:
            return dash.no_update, dash.no_update, dash.no_update
        time_arr, signal_arr = _get_xy(active_file)
        if time_arr is None:
            log.debug("No plottable X/Y data for integration")
            return dash.no_update, "Select a signal with numeric X/Y data to detect peaks.", dash.no_update

        smooth_window = (plot_settings or {}).get('smooth_window', 0)
        effective_window = max(3, smooth_window) if smooth_window > 0 else 11

        data_manager.integration_service.update_settings(
            active_file,
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
            display_signal=processed.raw,
            integration_baseline=baseline_mode or 'linear',
        )

        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"Detected {len(peaks)} peaks for {active_file}")
        from services.ms_polarity import entry_polarity
        polarity = entry_polarity(data_manager.get_data_by_id(active_file) or {})
        shown = (plot_settings or {}).get('ms_polarity', 'both')
        settings_update = dash.no_update
        if polarity and shown not in ('both', polarity):
            settings_update = {**(plot_settings or {}), 'ms_polarity': polarity}
        return ((trigger_counter or 0) + 1,
                f"Detected {len(peaks)} new peaks in {target_name}. Existing integrated peaks are kept.",
                settings_update)

    # ── Clear Peaks ───────────────────────────────────────────────────

    @app.callback(
        [Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('status-text', 'children', allow_duplicate=True)],
        Input('int-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_peaks(n_clicks, active_file, trigger_counter):
        if not n_clicks or not active_file:
            return dash.no_update, dash.no_update

        active_file, target_name = target(active_file)
        data_manager.peak_service.clear_detected_peaks(active_file)
        data_manager.integration_service.clear_processed_signal(active_file)
        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"Cleared peaks for {active_file}")
        return (trigger_counter or 0) + 1, f"Cleared detected peaks in {target_name}."
