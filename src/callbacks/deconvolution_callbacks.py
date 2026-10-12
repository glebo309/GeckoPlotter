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
from dash import Input, Output, State, html, ALL
import dash_mantine_components as dmc
import re
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


def _component_apex(payload, component):
    x = payload.get('render_x') or payload['x']
    curve = component.get('render_curve') or component['curve']
    return float(x[int(np.argmax(curve))])


def _fitted_markers(payload, previous=()):
    return [{'x': (previous[i]['x'] if i < len(previous) and previous[i].get('fixed')
                   else _component_apex(payload, c)),
             'y': float(np.interp(_component_apex(payload, c), payload['x'], payload['best_fit'])),
             'fixed': bool(i < len(previous) and previous[i].get('fixed'))}
            for i, c in enumerate(payload['components'])]


def _build_results_display(payload):
    """Compact fit summary and component table for the Integration panel."""
    if not payload:
        return html.Div()

    r2 = payload['r_squared']
    header = html.Div(f"R² = {r2:.4f} · {len(payload['components'])} components",
                      style={'fontSize': '12px', 'color': '#60666d', 'marginBottom': '6px'})

    th = {'textAlign': 'left', 'padding': '3px 6px', 'borderBottom': '1px solid #ccc',
          'fontSize': '11px'}
    td = {'padding': '2px 6px', 'borderBottom': '1px solid #eee', 'fontSize': '11px'}
    rows = [html.Tr([
        html.Td(str(c['index'] + 1), style=td),
        html.Td(f'{_component_apex(payload, c):.3f}', style=td),
        html.Td(f'{c["area"]:.1f}', style=td),
        html.Td(f'{c["sigma"]:.4f}', style=td),
        html.Td(f'{c["gamma"]:.4f}', style=td),
        html.Td(dmc.ActionIcon('×', id={'type': 'deconv-remove', 'index': c['index']},
            size='xs', variant='subtle', color='gray', disabled=len(payload['components']) <= 1,
            **{'aria-label': f"Remove component {c['index'] + 1}"}), style=td),
    ]) for c in payload['components']]

    table = html.Table([
        html.Thead(html.Tr([
            html.Th('#', style=th), html.Th('Apex', style=th),
            html.Th('Area', style=th), html.Th('σ', style=th), html.Th('γ', style=th), html.Th('', style=th),
        ])),
        html.Tbody(rows),
    ], style={'width': '100%', 'borderCollapse': 'collapse'})

    return html.Div([header, table, html.Div('Shift-click to add · Drag lines to adjust',
        style={'fontSize': '11px', 'color': '#60666d', 'marginTop': '4px'})])


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
    payload = serialize_result(result)
    markers = _fitted_markers(payload)
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

    @app.callback(Output('deconv-btn', 'disabled'), [Input('baseline-mode', 'data'), Input('pda-preview', 'data')])
    def deconv_editor_active(mode, preview=None):
        return mode == 'deconvolve' or bool(preview)

    # ── Deconvolute: toolbox button (preview) or right-click (auto-accept)
    @app.callback(
        [Output('baseline-mode', 'data', allow_duplicate=True),
         Output('deconv-markers', 'data', allow_duplicate=True),
         Output('deconv-result', 'data', allow_duplicate=True),
         Output('deconv-results-container', 'children', allow_duplicate=True),
         Output('deconv-accept-btn', 'style', allow_duplicate=True),
         Output('deconv-cancel-btn', 'style', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('context-menu', 'hidden', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True)],
        [Input('deconv-btn', 'n_clicks'),
         Input('ctx-deconvolve-item', 'n_clicks')],
        [State('selected-peak-idx', 'data'),
         State('active-file', 'data'),
         State('context-menu-store', 'data'),
         State('render-trigger', 'data'),
         State('peak-change-trigger', 'data'), State('pda-preview', 'data')],
        prevent_initial_call=True,
    )
    def deconvolute(button_clicks, context_clicks, selected_peak_id, active_file,
                    context_store, render_counter, peak_counter, preview=None):
        if preview:
            raise PreventUpdate
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

        close_menu = True if from_context else dash.no_update  # hide the popup
        no = dash.no_update

        def fail(text, color='#c62828'):
            tone = 'integration-note-muted' if color == '#888' else 'integration-note-warn'
            msg = html.Div([html.Span('!' if tone == 'integration-note-warn' else 'i', className='integration-note-icon', **{'aria-hidden': 'true'}),
                            html.Span(text)], className=f'integration-note {tone}')
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
            return fail('Region looks like a single peak: no second maximum or shoulder found. Widen the selection if the overlap extends beyond it.', '#888')

        payload.update(file_id=peak_fid, peak_id=selected_peak_id)

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
        [Input('deconv-marker-click-store', 'data'),
         Input('main-shape-relayout', 'data'),
         Input({'type': 'deconv-remove', 'index': ALL}, 'n_clicks')],
        [State('deconv-markers', 'data'),
         State('active-file', 'data'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data'),
         State('render-trigger', 'data'),
         State('deconv-result', 'data'),
         State('main-plot', 'figure')],
        prevent_initial_call=True,
        running=[(Output('deconv-accept-btn', 'disabled'), True, False),
                 (Output('deconv-cancel-btn', 'disabled'), True, False)],
    )
    def marker_click_and_refit(click, relayout, remove_clicks, markers, active_file,
                               selected_peak_id, mode, render_counter, payload, figure):
        if mode != 'deconvolve' or not payload:
            raise PreventUpdate
        peak_fid, peak = _find_peak(data_manager, payload.get('file_id', active_file),
                                   payload.get('peak_id', selected_peak_id))
        if peak is None:
            raise PreventUpdate
        x_region, y_region = _extract_peak_region(data_manager, peak_fid, peak)
        if x_region is None:
            raise PreventUpdate
        markers = [dict(m) for m in (markers or [])]
        trigger = dash.callback_context.triggered_id
        if isinstance(trigger, dict) and trigger.get('type') == 'deconv-remove':
            index = trigger['index']
            if len(markers) <= 1 or index >= len(markers) or not remove_clicks[index]:
                raise PreventUpdate
            markers.pop(index)
        elif trigger == 'main-shape-relayout':
            shapes = (figure or {}).get('layout', {}).get('shapes', [])
            changes = {}
            for key, value in (relayout or {}).items():
                match = re.fullmatch(r'shapes\[(\d+)\]\.x[01]', key)
                if not match:
                    continue
                shape_index = int(match.group(1))
                if shape_index >= len(shapes):
                    continue
                name = shapes[shape_index].get('name', '')
                if name.startswith('deconv:'):
                    changes.setdefault(int(name.split(':')[1]), []).append(float(value))
            if not changes:
                raise PreventUpdate
            for index, values in changes.items():
                if index >= len(markers):
                    continue
                position = float(np.clip(np.mean(values), x_region[0], x_region[-1]))
                markers[index] = {'x': position, 'y': float(np.interp(position, x_region, y_region)), 'fixed': True}
        elif trigger == 'deconv-marker-click-store':
            if not click or click.get('x') is None:
                raise PreventUpdate
            # Only explicit Shift-clicks are published by the browser.
            if click['x'] < x_region[0] or click['x'] > x_region[-1]:
                raise PreventUpdate
            apex_x, apex_y = _snap_to_local_max(x_region, y_region, click['x'])
            if any(abs(m['x'] - apex_x) <= np.ptp(x_region) * _SNAP_FRAC for m in markers):
                raise PreventUpdate
            markers.append({'x': apex_x, 'y': apex_y})
        else:
            raise PreventUpdate

        # Auto-refit with updated markers
        if len(markers) < 1:
            return markers, None, html.Div('Place at least one marker.',
                   style={'fontSize': '11px', 'color': '#888'}), (render_counter or 0) + 1

        centers = [(m['x'], m['y']) for m in markers]
        try:
            result = _svc.fit_peaks(x_region, y_region, centers,
                fixed_apices={i: m['x'] for i, m in enumerate(markers) if m.get('fixed')})
        except Exception:
            log.exception("Refit failed after marker adjustment")
            return dash.no_update, dash.no_update, html.Div([_build_results_display(payload),
                html.Small('Adjustment failed. Previous fit retained.')]), (render_counter or 0) + 1

        if result is None:
            return dash.no_update, dash.no_update, html.Div([_build_results_display(payload),
                html.Small('Adjustment failed. Previous fit retained.')]), (render_counter or 0) + 1

        payload = dict(serialize_result(result), file_id=peak_fid, peak_id=peak.peak_id)
        markers = _fitted_markers(payload, markers)
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

        selected_peak_id = result_payload.get('peak_id', selected_peak_id)
        active_file = result_payload.get('file_id', active_file)
        peak_fid, peak = _find_peak(data_manager, active_file, selected_peak_id)
        if peak is None:
            raise PreventUpdate
        result = deserialize_result(result_payload)
        n = _apply_deconv(data_manager, result, peak_fid or active_file, selected_peak_id)
        if not n:
            raise PreventUpdate
        log.debug(f"accept: replaced peak {selected_peak_id} with {n} sub-peaks")

        status = html.Div()
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
        status = html.Div()
        return ('navigate', [], None, status, _BTN_HIDE, _BTN_HIDE,
                (render_counter or 0) + 1)
