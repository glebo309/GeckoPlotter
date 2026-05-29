# =============================================================================
# File: callbacks/deconvolution_callbacks.py
# =============================================================================
"""Peak deconvolution callbacks for GeckoPlotter V2.

Wires the Integration-panel deconvolution controls to DeconvolutionService:

- Toggle Deconvolve mode (stored as 'deconvolve' in baseline-mode).
- Auto-detect / manually place / remove peak-center markers.
- Fit a composite EMG model and preview the result.
- Accept (convert fitted components to standard Peak objects) or Cancel.

Preview rendering (markers + fitted curves) is owned by master_render in
viz_callbacks.py; these callbacks only mutate the deconv-* stores and bump
render-trigger.
"""

import logging
import sys

import dash
from dash import Input, Output, State, html, callback_context
from dash.exceptions import PreventUpdate
import numpy as np

from callbacks.baseline_callbacks import get_xy_arrays
from services.deconvolution_service import (
    DeconvolutionService,
    serialize_result,
    deserialize_result,
)

log = logging.getLogger('geckoplotter.deconvolution')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

_svc = DeconvolutionService()

# Marker placement / removal tolerance, as a fraction of the x-range.
_SNAP_FRAC = 0.02


def _snap_to_local_max(x, y, clicked_x):
    """Return (apex_x, apex_y) at the nearest local maximum to clicked_x."""
    idx = int(np.argmin(np.abs(x - clicked_x)))
    window = max(5, int(0.01 * len(x)))
    lo = max(0, idx - window)
    hi = min(len(x), idx + window + 1)
    local = lo + int(np.argmax(y[lo:hi]))
    return float(x[local]), float(y[local])


def _build_results_display(payload):
    """R² badge + per-component table for the Integration panel."""
    if not payload:
        return html.Div()

    r2 = payload['r_squared']
    color = '#2e7d32' if r2 > 0.99 else '#ef6c00' if r2 > 0.95 else '#c62828'
    badge_style = {
        'display': 'inline-block', 'padding': '2px 10px', 'borderRadius': '10px',
        'fontSize': '11px', 'fontWeight': '600', 'color': 'white',
        'backgroundColor': color, 'marginRight': '6px',
    }

    header = html.Div([
        html.Span(f'R² = {r2:.4f}', style=badge_style),
        html.Span(f'{len(payload["components"])} peaks',
                  style={**badge_style, 'backgroundColor': '#607d8b'}),
    ], style={'marginBottom': '6px'})

    th = {'textAlign': 'left', 'padding': '3px 6px', 'borderBottom': '1px solid #ccc',
          'fontSize': '11px'}
    td = {'padding': '2px 6px', 'borderBottom': '1px solid #eee', 'fontSize': '11px'}
    rows = [html.Tr([
        html.Td(str(c['index'] + 1), style=td),
        html.Td(f'{c["center"]:.3f}', style=td),
        html.Td(f'{c["area"]:.1f}', style=td),
        html.Td(f'{c["sigma"]:.4f}', style=td),
        html.Td(f'{c["gamma"]:.4f}', style=td),
    ]) for c in payload['components']]

    table = html.Table([
        html.Thead(html.Tr([
            html.Th('#', style=th), html.Th('Center', style=th),
            html.Th('Area', style=th), html.Th('σ', style=th), html.Th('γ', style=th),
        ])),
        html.Tbody(rows),
    ], style={'width': '100%', 'borderCollapse': 'collapse'})

    return html.Div([header, table])


def register_deconvolution_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all deconvolution-mode callbacks."""

    def _xy(file_id):
        return get_xy_arrays(data_manager, file_id)

    # ── Toggle Deconvolve mode ────────────────────────────────────────
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-toggle-btn', 'n_clicks'),
        [State('baseline-mode', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def toggle_deconv_mode(n_clicks, current_mode, render_counter):
        if not n_clicks:
            raise PreventUpdate
        mode = 'navigate' if current_mode == 'deconvolve' else 'deconvolve'
        # Entering or leaving always starts from a clean slate.
        return mode, None, [], None, html.Div(), (render_counter or 0) + 1

    # ── Button active-state styling ──────────────────────────────────
    @app.callback(
        Output('deconv-toggle-btn', 'className'),
        Input('baseline-mode', 'data'),
        prevent_initial_call=True,
    )
    def sync_deconv_button(mode):
        return 'btn btn-primary active' if mode == 'deconvolve' else 'btn btn-secondary'

    # ── Auto-detect centers ───────────────────────────────────────────
    @app.callback(
        [Output('deconv-markers', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-detect-btn', 'n_clicks'),
        [State('deconv-prominence', 'value'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def detect_centers(n_clicks, prominence_pct, active_file, render_counter):
        if not n_clicks or not active_file:
            raise PreventUpdate
        x, y = _xy(active_file)
        if x is None:
            raise PreventUpdate
        prominence = (prominence_pct or 5) / 100.0
        centers = _svc.auto_detect_centers(x, y, prominence=prominence)
        markers = [{'x': cx, 'y': cy} for cx, cy in centers]
        log.debug(f"detect_centers: {len(markers)} centers @ prominence {prominence}")
        return markers, (render_counter or 0) + 1

    # ── Manual marker add / remove (click on plot) ────────────────────
    @app.callback(
        [Output('deconv-markers', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-marker-click-store', 'data'),
        [State('deconv-markers', 'data'),
         State('active-file', 'data'),
         State('baseline-mode', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def place_or_remove_marker(click, markers, active_file, mode, render_counter):
        if mode != 'deconvolve' or not click or not active_file:
            raise PreventUpdate
        clicked_x = click.get('x')
        if clicked_x is None:
            raise PreventUpdate
        x, y = _xy(active_file)
        if x is None:
            raise PreventUpdate

        markers = list(markers or [])
        tol = float(np.ptp(x)) * _SNAP_FRAC
        # Click near an existing marker → remove it.
        for i, m in enumerate(markers):
            if abs(m['x'] - clicked_x) <= tol:
                markers.pop(i)
                return markers, (render_counter or 0) + 1
        # Otherwise snap to nearest local max and add.
        apex_x, apex_y = _snap_to_local_max(x, y, clicked_x)
        markers.append({'x': apex_x, 'y': apex_y})
        return markers, (render_counter or 0) + 1

    # ── Fit composite EMG ─────────────────────────────────────────────
    @app.callback(
        [Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-fit-btn', 'n_clicks'),
        [State('deconv-markers', 'data'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def fit(n_clicks, markers, active_file, render_counter):
        if not n_clicks or not active_file:
            raise PreventUpdate
        if not markers:
            return None, html.Div('Place at least one peak marker first.',
                                   style={'fontSize': '11px', 'color': '#c62828'}), dash.no_update
        x, y = _xy(active_file)
        if x is None:
            raise PreventUpdate
        centers = [(m['x'], m['y']) for m in markers]
        try:
            result = _svc.fit_peaks(x, y, centers)
        except Exception:
            log.exception("Deconvolution fit failed")
            return None, html.Div('Fit failed — try adjusting markers.',
                                   style={'fontSize': '11px', 'color': '#c62828'}), dash.no_update
        if result is None:
            raise PreventUpdate
        payload = serialize_result(result)
        return payload, _build_results_display(payload), (render_counter or 0) + 1

    # ── Accept: convert components to Peak objects ────────────────────
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-accept-btn', 'n_clicks'),
        [State('deconv-result', 'data'),
         State('active-file', 'data'),
         State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def accept(n_clicks, result_payload, active_file, peak_counter, render_counter):
        if not n_clicks or not result_payload or not active_file:
            raise PreventUpdate

        result = deserialize_result(result_payload)
        region_rt = float(np.mean([c.center for c in result.components]))
        new_peaks = _svc.result_to_peaks(result, active_file, region_rt)
        if not new_peaks:
            raise PreventUpdate

        # Remove pre-existing peaks overlapping the deconvolved region (>50%).
        region_lo = min(p.rt_start for p in new_peaks)
        region_hi = max(p.rt_end for p in new_peaks)
        data_manager.peak_service.clear_region(active_file, region_lo, region_hi)

        for p in new_peaks:
            data_manager.peak_service.add_baseline_peak(
                file_id=active_file,
                area=p.area, height=p.height, apex_x=p.rt,
                poly_x=p.poly_x, poly_y=p.poly_y,
                p_line=p.p_line, q1=p.q1, q2=p.q2,
                source='deconvolved',
                deconv_group=p.deconv_group,
                fit_params=p.fit_params,
            )

        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"accept: added {len(new_peaks)} deconvolved peaks to {active_file}")

        return ('navigate', [], None, html.Div(), None,
                (peak_counter or 0) + 1, (render_counter or 0) + 1)

    # ── Cancel ─────────────────────────────────────────────────────────
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-cancel-btn', 'n_clicks'),
        State('render-trigger', 'data'),
        prevent_initial_call=True,
    )
    def cancel(n_clicks, render_counter):
        if not n_clicks:
            raise PreventUpdate
        return 'navigate', [], None, html.Div(), (render_counter or 0) + 1
