# =============================================================================
# File: callbacks/deconvolution_callbacks.py
# =============================================================================
"""One-click peak deconvolution callbacks.

Select a peak → press Deconvolute → auto-detect + fit → preview → accept/cancel.
Marker clicks during preview add/remove centers and auto-refit.
"""

import logging
import sys

import dash
from dash import Input, Output, State, html
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

_SNAP_FRAC = 0.02
_DEFAULT_PROMINENCE = 0.05

_BTN_SHOW = {'padding': '4px 10px', 'fontSize': '12px', 'display': 'inline-block'}
_BTN_HIDE = {'padding': '4px 10px', 'fontSize': '12px', 'display': 'none'}


def _snap_to_local_max(x, y, clicked_x):
    """Return (apex_x, apex_y) at the nearest local maximum to clicked_x."""
    idx = int(np.argmin(np.abs(x - clicked_x)))
    window = max(5, int(0.01 * len(x)))
    lo = max(0, idx - window)
    hi = min(len(x), idx + window + 1)
    local = lo + int(np.argmax(y[lo:hi]))
    return float(x[local]), float(y[local])


def _find_peak(data_manager, file_id, peak_id):
    """Look up a Peak by ID. Searches all files so subplot mode works."""
    for fid, peaks in data_manager.peak_service.get_all_peaks().items():
        for p in peaks:
            if p.peak_id == peak_id:
                return fid, p
    return None, None


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
        html.Span(f'{len(payload["components"])} components',
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


def _extract_peak_region(data_manager, file_id, peak):
    """Get (x_region, y_region) arrays clipped to the selected peak's range."""
    x, y = get_xy_arrays(data_manager, file_id)
    if x is None:
        return None, None
    mask = (x >= peak.rt_start) & (x <= peak.rt_end)
    return x[mask], y[mask]


def _run_detect_and_fit(x_region, y_region):
    """Auto-detect centers and fit EMG model. Returns (markers, payload) or (None, None) if detection/fit fails."""
    centers = _svc.auto_detect_centers(x_region, y_region, prominence=_DEFAULT_PROMINENCE)
    if len(centers) < 2:
        return None, None
    result = _svc.fit_peaks(x_region, y_region, centers)
    if result is None:
        return None, None
    markers = [{'x': cx, 'y': cy} for cx, cy in centers]
    payload = serialize_result(result)
    return markers, payload


def _apply_deconv(data_manager, result, active_file, selected_peak_id):
    """Replace the selected peak with the fitted sub-peaks. Returns the count."""
    region_rt = float(np.mean([c.center for c in result.components]))
    new_peaks = _svc.result_to_peaks(result, active_file, region_rt)
    if not new_peaks:
        return 0
    data_manager.peak_service.save_undo()
    if selected_peak_id:
        data_manager.peak_service.remove_peak(active_file, selected_peak_id)
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
    return len(new_peaks)


def register_deconvolution_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all deconvolution callbacks."""

    # ── Deconvolute: toolbox button (preview) or right-click (auto-accept)
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('deconv-accept-btn', 'style', allow_duplicate=True),
         Output('deconv-cancel-btn', 'style', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('context-menu', 'opened', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True)],
        [Input('deconv-btn', 'n_clicks'),
         Input('ctx-deconvolve-item', 'n_clicks')],
        [State('selected-peak-idx', 'data'),
         State('active-file', 'data'),
         State('context-menu-store', 'data'),
         State('render-trigger', 'data'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def deconvolute(button_clicks, context_clicks, selected_peak_id, active_file,
                    context_store, render_counter, peak_counter):
        triggered = dash.callback_context.triggered_id
        from_context = triggered == 'ctx-deconvolve-item'
        if from_context:
            if not context_clicks or not context_store or not context_store.get('peak_id'):
                raise PreventUpdate
            selected_peak_id = context_store['peak_id']
        else:
            if not button_clicks:
                raise PreventUpdate

        peak_fid, peak = _find_peak(data_manager, active_file, selected_peak_id) if selected_peak_id else (None, None)

        close_menu = False if from_context else dash.no_update
        no = dash.no_update

        def fail(text, color='#c62828'):
            msg = html.Div(text, style={'fontSize': '11px', 'color': color})
            return no, no, no, msg, _BTN_HIDE, _BTN_HIDE, no, close_menu, no, no

        if not selected_peak_id:
            return fail('Select a peak first.', '#888')
        if peak is None:
            return fail('Peak not found. Select a peak first.')

        x_region, y_region = _extract_peak_region(data_manager, peak_fid, peak)
        if x_region is None or len(x_region) < 10:
            return fail('Peak region too narrow for deconvolution.')

        try:
            markers, payload = _run_detect_and_fit(x_region, y_region)
        except Exception:
            log.exception("Deconvolution fit failed")
            return fail('Fit failed — try a wider peak region.')

        if markers is None:
            return fail('Could not detect multiple peaks in this region.')

        # Right-click: auto-accept immediately, no preview step.
        if from_context:
            result = deserialize_result(payload)
            n = _apply_deconv(data_manager, result, peak_fid, selected_peak_id)
            if not n:
                return fail('Deconvolution produced no peaks.')
            log.debug(f"deconvolute (auto, right-click): {n} sub-peaks")
            return ('navigate', [], None, html.Div(), _BTN_HIDE, _BTN_HIDE,
                    None, close_menu, (render_counter or 0) + 1, (peak_counter or 0) + 1)

        # Toolbox button: show preview (table + on-plot markers), user clicks Accept.
        log.debug(f"deconvolute (preview): {len(markers)} components, R²={payload['r_squared']:.4f}")
        return ('deconvolve', markers, payload, _build_results_display(payload),
                _BTN_SHOW, _BTN_SHOW, selected_peak_id, close_menu,
                (render_counter or 0) + 1, no)

    # ── Marker add/remove + auto-refit ───────────────────────────────
    @app.callback(
        [Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-marker-click-store', 'data'),
        [State('deconv-markers', 'data'),
         State('active-file', 'data'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def marker_click_and_refit(click, markers, active_file, selected_peak_id, mode, render_counter):
        if mode != 'deconvolve' or not click or not selected_peak_id:
            raise PreventUpdate
        clicked_x = click.get('x')
        if clicked_x is None:
            raise PreventUpdate

        peak_fid, peak = _find_peak(data_manager, active_file, selected_peak_id)
        if peak is None:
            raise PreventUpdate

        x_region, y_region = _extract_peak_region(data_manager, peak_fid, peak)
        if x_region is None:
            raise PreventUpdate

        markers = list(markers or [])
        tol = float(np.ptp(x_region)) * _SNAP_FRAC

        # Click near existing marker → remove it
        for i, m in enumerate(markers):
            if abs(m['x'] - clicked_x) <= tol:
                markers.pop(i)
                break
        else:
            # Snap to nearest local max and add
            apex_x, apex_y = _snap_to_local_max(x_region, y_region, clicked_x)
            markers.append({'x': apex_x, 'y': apex_y})

        # Auto-refit with updated markers
        if len(markers) < 1:
            return markers, None, html.Div('Place at least one marker.',
                   style={'fontSize': '11px', 'color': '#888'}), (render_counter or 0) + 1

        centers = [(m['x'], m['y']) for m in markers]
        try:
            result = _svc.fit_peaks(x_region, y_region, centers)
        except Exception:
            log.exception("Refit failed after marker adjustment")
            return markers, None, html.Div('Fit failed — try different markers.',
                   style={'fontSize': '11px', 'color': '#c62828'}), (render_counter or 0) + 1

        if result is None:
            return markers, None, html.Div('Fit did not converge.',
                   style={'fontSize': '11px', 'color': '#c62828'}), (render_counter or 0) + 1

        payload = serialize_result(result)
        return markers, payload, _build_results_display(payload), (render_counter or 0) + 1

    # ── Accept: replace original peak with sub-peaks ─────────────────
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('deconv-accept-btn', 'style', allow_duplicate=True),
         Output('deconv-cancel-btn', 'style', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-accept-btn', 'n_clicks'),
        [State('deconv-result', 'data'),
         State('active-file', 'data'),
         State('selected-peak-idx', 'data'),
         State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def accept(n_clicks, result_payload, active_file, selected_peak_id, peak_counter, render_counter):
        if not n_clicks or not result_payload:
            raise PreventUpdate

        peak_fid, _ = _find_peak(data_manager, active_file, selected_peak_id) if selected_peak_id else (active_file, None)
        result = deserialize_result(result_payload)
        n = _apply_deconv(data_manager, result, peak_fid or active_file, selected_peak_id)
        if not n:
            raise PreventUpdate
        log.debug(f"accept: replaced peak {selected_peak_id} with {n} sub-peaks")

        status = html.Div('Select a peak first.',
                          style={'fontSize': '11px', 'color': '#888'})
        return ('navigate', [], None, status, _BTN_HIDE, _BTN_HIDE, None,
                (peak_counter or 0) + 1, (render_counter or 0) + 1)

    # ── Cancel ────────────────────────────────────────────────────────
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('deconv-accept-btn', 'style', allow_duplicate=True),
         Output('deconv-cancel-btn', 'style', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('deconv-cancel-btn', 'n_clicks'),
        State('render-trigger', 'data'),
        prevent_initial_call=True,
    )
    def cancel(n_clicks, render_counter):
        if not n_clicks:
            raise PreventUpdate
        status = html.Div('Select a peak first.',
                          style={'fontSize': '11px', 'color': '#888'})
        return ('navigate', [], None, status, _BTN_HIDE, _BTN_HIDE,
                (render_counter or 0) + 1)
