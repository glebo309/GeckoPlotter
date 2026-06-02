"""LC-MS viewer callbacks.

Wires the MS Analysis bottom-panel tab:
  - Click on main-plot chromatogram → mass spectrum display
  - EIC extraction from m/z input → overlay on main plot
"""
from __future__ import annotations

import logging

import dash
from dash import Input, Output, State, html, dcc, callback_context
import plotly.graph_objects as go
import numpy as np

log = logging.getLogger(__name__)


def register_lcms_callbacks(app, data_manager):
    """Register LC-MS viewer callbacks against *app*."""
    from callbacks.viz_callbacks import _collect_visible_files

    lcms_svc = data_manager.lcms_service

    from services.data_store import BundleType, ComponentRole

    @app.callback(
        Output('pt-layout-mode', 'value', allow_duplicate=True),
        Input('active-file', 'data'),
        State('pt-layout-mode', 'value'),
        prevent_initial_call=True,
    )
    def auto_subplot_for_lcms(active_file, current_mode):
        if not active_file:
            raise dash.exceptions.PreventUpdate
        bundle = data_manager.get_bundle_for_component(active_file) if hasattr(data_manager, 'get_bundle_for_component') else None
        if not bundle:
            bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if bundle and bundle.bundle_type == BundleType.LCMS and len(bundle.component_list) > 1:
            if current_mode != 'stacked':
                return 'stacked'
        raise dash.exceptions.PreventUpdate

    # ------------------------------------------------------------------
    # 1. Click on main-plot → update mass spectrum figure
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ms-spectrum-graph', 'figure'),
         Output('ms-spectrum-info', 'children'),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True)],
        [Input('main-plot', 'clickData'),
         Input('eic-graph', 'clickData')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def update_mass_spectrum(main_click_data, eic_click_data, active_file):
        trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        click_data = eic_click_data if trigger_id == 'eic-graph' else main_click_data
        if not click_data or not active_file:
            return _empty_spectrum("Click on the chromatogram to view a mass spectrum"), "", dash.no_update, dash.no_update

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return _empty_spectrum("No mass spectral data for this file"), "", dash.no_update, dash.no_update

        point = click_data['points'][0]
        rt = point.get('x', 0)

        fig, status, scan_idx = _build_spectrum_at_time(lcms_svc, file_data, rt)
        return fig, _source_status(trigger_id, status), scan_idx, _scan_label(lcms_svc, file_data, scan_idx)

    @app.callback(
        [Output('ms-scan-slider', 'min'),
         Output('ms-scan-slider', 'max'),
         Output('ms-scan-slider', 'value'),
         Output('ms-scan-label', 'children'),
         Output('ms-active-subplot-idx', 'data')],
        [Input('active-file', 'data')],
        State('loaded-files', 'data'),
        prevent_initial_call=True,
    )
    def configure_scan_slider(active_file, loaded_files):
        subplot_idx = 0
        if active_file and loaded_files:
            visible = _collect_visible_files(
                data_manager, active_file, loaded_files)
            for files in visible.values():
                for i, (name, fdata) in enumerate(files):
                    fid = fdata.get('record', {}).get('id', '')
                    if fid == active_file:
                        subplot_idx = i
                        break

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return 0, 1, 0, 'No scan selected', subplot_idx

        n_scans = max(lcms_svc.get_scan_count(file_data), 1)
        time_arr, _ = lcms_svc.extract_tic(file_data)
        apex_idx = 0
        if time_arr.size:
            try:
                _, intensity = lcms_svc.extract_tic(file_data)
                apex_idx = int(np.argmax(intensity)) if intensity.size else 0
            except ValueError:
                apex_idx = 0
        apex_idx = min(max(apex_idx, 0), n_scans - 1)
        return 0, n_scans - 1, apex_idx, _scan_label(lcms_svc, file_data, apex_idx), subplot_idx

    # ------------------------------------------------------------------
    # Polarity toggle: sync both toggles from active-file selection
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ms-polarity-toggle', 'checked'),
         Output('ms-polarity-toggle-wrapper', 'style'),
         Output('ms-polarity-pos-label', 'style'),
         Output('ms-polarity-neg-label', 'style'),
         Output('eic-polarity-toggle', 'checked'),
         Output('eic-polarity-toggle-wrapper', 'style'),
         Output('eic-polarity-pos-label', 'style'),
         Output('eic-polarity-neg-label', 'style')],
        Input('active-file', 'data'),
        prevent_initial_call=True,
    )
    def sync_polarity_toggle(active_file):
        """Update both toggle positions and visibility when active file changes."""
        hidden = {'display': 'none', 'alignItems': 'center', 'gap': '2px'}
        visible = {'display': 'flex', 'alignItems': 'center', 'gap': '2px'}
        pos_active = {'fontSize': '12px', 'fontWeight': '600', 'color': '#333', 'cursor': 'default'}
        pos_dim = {'fontSize': '12px', 'fontWeight': '400', 'color': '#999', 'cursor': 'default'}
        neg_active = {'fontSize': '12px', 'fontWeight': '600', 'color': '#333', 'cursor': 'default'}
        neg_dim = {'fontSize': '12px', 'fontWeight': '400', 'color': '#999', 'cursor': 'default'}

        def _pack(checked, show, pos_s, neg_s):
            wrapper = visible if show else hidden
            return checked, wrapper, pos_s, neg_s, checked, wrapper, pos_s, neg_s

        if not active_file:
            return _pack(False, False, pos_active, neg_dim)

        bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file)
        if not bundle or bundle.bundle_type != BundleType.LCMS:
            return _pack(False, False, pos_active, neg_dim)

        has_pos = bundle.get_component(ComponentRole.MS_POSITIVE) is not None
        has_neg = bundle.get_component(ComponentRole.MS_NEGATIVE) is not None
        if not (has_pos and has_neg):
            return _pack(False, False, pos_active, neg_dim)

        current = next(
            (c for c in bundle.component_list if c.component_id == active_file), None)
        is_negative = current and current.role == ComponentRole.MS_NEGATIVE
        if not current or current.role not in (ComponentRole.MS_POSITIVE, ComponentRole.MS_NEGATIVE):
            entry = data_manager.get_data_by_id(active_file)
            if entry and lcms_svc.has_spectral_data(entry):
                is_negative = False
            else:
                resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
                if resolved:
                    resolved_id = resolved[0]
                    resolved_comp = next(
                        (c for c in bundle.component_list if c.component_id == resolved_id), None)
                    is_negative = resolved_comp and resolved_comp.role == ComponentRole.MS_NEGATIVE

        if is_negative:
            return _pack(True, True, pos_dim, neg_active)
        return _pack(False, True, pos_active, neg_dim)

    # ------------------------------------------------------------------
    # Polarity toggle: switch active file when either toggle is clicked
    # ------------------------------------------------------------------
    @app.callback(
        Output('active-file', 'data', allow_duplicate=True),
        [Input('ms-polarity-toggle', 'checked'),
         Input('eic-polarity-toggle', 'checked')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def polarity_toggle_switch(ms_checked, eic_checked, active_file):
        """Switch active MS component when either polarity toggle is clicked."""
        if active_file is None:
            raise dash.exceptions.PreventUpdate

        trigger = callback_context.triggered[0]['prop_id'] if callback_context.triggered else ''
        is_negative = eic_checked if 'eic-polarity' in trigger else ms_checked

        bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file)
        if not bundle or bundle.bundle_type != BundleType.LCMS:
            raise dash.exceptions.PreventUpdate

        target_role = ComponentRole.MS_NEGATIVE if is_negative else ComponentRole.MS_POSITIVE
        target = bundle.get_component(target_role)
        if not target or target.component_id == active_file:
            raise dash.exceptions.PreventUpdate
        return target.component_id

    @app.callback(
        [Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True)],
        Input('ms-scan-slider', 'value'),
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def scrub_mass_spectrum(scan_idx, active_file):
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if scan_idx is None or not file_data or not lcms_svc.has_spectral_data(file_data):
            return dash.no_update, dash.no_update, dash.no_update
        fig, status, resolved_idx = _build_spectrum_at_scan(lcms_svc, file_data, int(scan_idx))
        return fig, _source_status('slider', status), _scan_label(lcms_svc, file_data, resolved_idx)

    @app.callback(
        Output('ms-scan-slider', 'value', allow_duplicate=True),
        Input('ms-scan-client-input', 'value'),
        State('ms-scan-slider', 'value'),
        prevent_initial_call=True,
    )
    def sync_client_scan_event(input_scan_idx, current_scan_idx):
        """Bridge browser plot drag/click scan events back into the Dash slider."""
        if input_scan_idx is None:
            return dash.no_update
        try:
            scan_idx = int(input_scan_idx)
            current_idx = int(current_scan_idx) if current_scan_idx is not None else None
        except (TypeError, ValueError):
            return dash.no_update
        if current_idx == scan_idx:
            return dash.no_update
        return scan_idx

    app.clientside_callback(
        """
        function(scanIdx, activeTab, activeFile, subplotIdx, figure) {
            var hidden = {
                position: 'absolute',
                display: 'none',
                top: '0px',
                left: '0px',
                height: '0px',
                width: '18px',
                borderLeft: '2px dotted #111',
                zIndex: 30,
                pointerEvents: 'auto',
                cursor: 'col-resize'
            };

            function visibleStyle(left, top, height) {
                return {
                    position: 'absolute',
                    display: 'block',
                    top: top + 'px',
                    left: left + 'px',
                    height: Math.max(0, height) + 'px',
                    width: '18px',
                    borderLeft: '2px dotted #111',
                    zIndex: 30,
                    pointerEvents: 'auto',
                    cursor: 'col-resize'
                };
            }

            var sliderRoot = document.getElementById('ms-scan-slider');
            var active = !!(sliderRoot && sliderRoot.getClientRects && sliderRoot.getClientRects().length);
            var wrapper = document.getElementById('main-plot');
            var overlay = document.getElementById('lcms-scan-cursor-overlay');
            var host = overlay ? overlay.parentElement : null;
            var handle = sliderRoot ? sliderRoot.querySelector('[role="slider"]') : null;

            if (activeTab !== 'ms-viewer' || !active || scanIdx === null || scanIdx === undefined || !host || !handle) {
                return hidden;
            }

            var plotDrags = wrapper ? wrapper.querySelectorAll('.nsewdrag') : [];
            var spIdx = (typeof subplotIdx === 'number') ? subplotIdx : 0;
            var plotDrag = plotDrags[Math.min(spIdx, plotDrags.length - 1)] || null;

            if (!plotDrag) return hidden;

            var maxIdx = Number(handle.getAttribute('aria-valuemax'));
            if (!Number.isFinite(maxIdx) || maxIdx <= 0) {
                return hidden;
            }

            var idx = Math.max(0, Math.min(Math.round(Number(scanIdx)), Math.round(maxIdx)));
            var rect = plotDrag.getBoundingClientRect();
            var hostRect = host.getBoundingClientRect();
            var left = rect.left - hostRect.left + (idx / maxIdx) * rect.width;
            var top = rect.top - hostRect.top;
            var height = rect.height;

            var spIdx = plotDrag ? Array.prototype.indexOf.call(plotDrags, plotDrag) : 0;
            window.__geckoLcmsScanState = {idx: idx, left: left, active: active, maxIdx: maxIdx, subplotIdx: spIdx};
            return visibleStyle(left, top, height);
        }
        """,
        Output('lcms-scan-cursor-overlay', 'style'),
        [Input('ms-scan-slider', 'value'),
         Input('active-tab', 'data'),
         Input('active-file', 'data'),
         Input('ms-active-subplot-idx', 'data')],
        State('main-plot', 'figure'),
        prevent_initial_call=True,
    )

    # ------------------------------------------------------------------
    # 2. EIC extraction → overlay on main plot
    # ------------------------------------------------------------------
    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('eic-graph', 'figure', allow_duplicate=True),
         Output('eic-active-list', 'children', allow_duplicate=True),
         Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True)],
        Input('eic-extract-btn', 'n_clicks'),
        [State('eic-mz-input', 'value'),
         State('eic-tolerance-input', 'value'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def extract_eic_trigger(n_clicks, mz_value, tolerance, active_file, current_trigger):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if mz_value is None:
            return (
                dash.no_update,
                _empty_eic("Enter a target m/z"),
                dash.no_update,
                dash.no_update,
                dash.no_update,
                dash.no_update,
                "Enter a target m/z before extracting an EIC",
            )

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return (
                dash.no_update,
                _empty_eic("No LC-MS spectral data for this selection"),
                [],
                _empty_spectrum("No LC-MS spectral data for this selection"),
                dash.no_update,
                dash.no_update,
                "No LC-MS spectral data for this selection",
            )

        tolerance = tolerance or 0.5

        try:
            eic_time, eic_intensity = lcms_svc.extract_eic(
                file_data, float(mz_value), float(tolerance)
            )
        except (ValueError, KeyError) as exc:
            return dash.no_update, _empty_eic(str(exc)), dash.no_update, dash.no_update, dash.no_update, dash.no_update, str(exc)

        overlay = {
            'mz': float(mz_value),
            'tolerance': float(tolerance),
            'time': eic_time,
            'intensity': eic_intensity,
        }
        if hasattr(data_manager, 'add_lcms_eic_overlay'):
            data_manager.add_lcms_eic_overlay(file_id, overlay)
        else:
            file_data.setdefault('eic_overlays', []).append(overlay)

        _extract_eic_other_polarity(data_manager, lcms_svc, active_file, file_id, mz_value, tolerance)

        eic_list = _get_eic_list(data_manager, file_id, file_data)
        apex_idx = int(np.argmax(eic_intensity)) if eic_intensity.size else 0
        apex_rt = float(eic_time[apex_idx]) if eic_time.size else 0.0
        spectrum_fig, spectrum_status, scan_idx = _build_spectrum_at_time(lcms_svc, file_data, apex_rt)
        status = (
            f"Extracted EIC m/z {float(mz_value):.4g} +/- {float(tolerance):.3g} "
            f"| Spectrum source: EIC apex | {spectrum_status}"
        )
        return (
            (current_trigger or 0) + 1,
            _build_eic_figure(eic_list),
            _render_eic_list(eic_list),
            spectrum_fig,
            scan_idx,
            _scan_label(lcms_svc, file_data, scan_idx),
            status,
        )

    @app.callback(
        Output('eic-active-list', 'children'),
        [Input('render-trigger', 'data'),
         Input('active-file', 'data')],
    )
    def update_eic_list(_, active_file):
        if not active_file:
            return []
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data:
            return []
        return _render_eic_list(_get_eic_list(data_manager, file_id, file_data))

    @app.callback(
        Output('eic-graph', 'figure'),
        [Input('render-trigger', 'data'),
         Input('active-file', 'data')],
    )
    def update_eic_graph(_, active_file):
        if not active_file:
            return _empty_eic("Select an LC-MS file to extract an EIC")

        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if not file_data:
            return _empty_eic("No LC-MS spectral data for this selection")

        return _build_eic_figure(_get_eic_list(data_manager, file_id, file_data))

    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('eic-graph', 'figure', allow_duplicate=True),
         Output('eic-active-list', 'children', allow_duplicate=True),
         Output('ms-spectrum-graph', 'figure', allow_duplicate=True),
         Output('ms-scan-slider', 'value', allow_duplicate=True),
         Output('ms-scan-label', 'children', allow_duplicate=True),
         Output('ms-spectrum-info', 'children', allow_duplicate=True)],
        Input('eic-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_eic_overlays(n_clicks, active_file, current_trigger):
        if not n_clicks or not active_file:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        resolved = _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc)
        file_id, file_data = resolved if resolved else (None, None)
        if file_id and hasattr(data_manager, 'clear_lcms_eic_overlays'):
            data_manager.clear_lcms_eic_overlays(file_id)
        elif file_data:
            file_data.pop('eic_overlays', None)
        _clear_eic_other_polarity(data_manager, active_file, file_id)
        return (
            (current_trigger or 0) + 1,
            _empty_eic("Extract an EIC to view it here"),
            _render_eic_list([]),
            dash.no_update,
            dash.no_update,
            dash.no_update,
            "Cleared EICs",
        )


def _empty_spectrum(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=30, b=40),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, xref='paper', yref='paper',
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color='#999'),
        )],
    )
    return fig


def _empty_eic(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=28, b=36),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[dict(
            text=message, xref='paper', yref='paper',
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=13, color='#999'),
        )],
    )
    return fig


def _source_status(source, status):
    labels = {
        'main-plot': 'Spectrum source: TIC click',
        'eic-graph': 'Spectrum source: EIC click',
        'slider': 'Spectrum source: scan scrubber',
    }
    prefix = labels.get(source)
    return f"{prefix} | {status}" if prefix else status


def _scan_label(lcms_svc, file_data, scan_idx):
    try:
        time_arr, _ = lcms_svc.extract_tic(file_data)
        rt = float(time_arr[int(scan_idx)]) if len(time_arr) > int(scan_idx) else 0.0
        total = max(lcms_svc.get_scan_count(file_data), 1)
        return f"Scan {int(scan_idx)} / {total - 1} | RT {rt:.3f} min"
    except (ValueError, IndexError, TypeError):
        return f"Scan {int(scan_idx)}"


def _main_figure_without_scan_line(current_figure):
    if not current_figure:
        return dash.no_update

    figure = {
        'data': list(current_figure.get('data', [])),
        'layout': dict(current_figure.get('layout', {})),
    }
    shapes = [
        shape for shape in figure['layout'].get('shapes', [])
        if shape.get('name') != 'lcms-scan-line'
    ]
    if shapes:
        figure['layout']['shapes'] = shapes
    else:
        figure['layout'].pop('shapes', None)
    return figure


def _main_figure_with_scan_line(current_figure, rt):
    figure = _main_figure_without_scan_line(current_figure)
    if figure is dash.no_update:
        return dash.no_update

    layout = figure.setdefault('layout', {})
    shapes = list(layout.get('shapes', []))
    shapes.append({
        'type': 'line',
        'name': 'lcms-scan-line',
        'xref': 'x',
        'yref': 'paper',
        'x0': rt,
        'x1': rt,
        'y0': 0,
        'y1': 1,
        'layer': 'above',
        'editable': False,
        'line': {
            'color': '#111111',
            'width': 1.5,
            'dash': 'dot',
        },
    })
    layout['shapes'] = shapes
    layout['uirevision'] = layout.get('uirevision', 'main-plot')
    return figure


def _build_spectrum_at_time(lcms_svc, file_data, rt):
    try:
        scan_idx = lcms_svc.get_scan_index_at_time(file_data, rt)
    except (ValueError, IndexError) as exc:
        return _empty_spectrum(str(exc)), str(exc), 0
    return _build_spectrum_at_scan(lcms_svc, file_data, scan_idx)


def _build_spectrum_at_scan(lcms_svc, file_data, scan_idx):
    try:
        n_scans = max(lcms_svc.get_scan_count(file_data), 1)
        scan_idx = min(max(int(scan_idx), 0), n_scans - 1)
        mz, intensity = lcms_svc.get_mass_spectrum(file_data, scan_idx)
        time_arr, _ = lcms_svc.extract_tic(file_data)
        rt = float(time_arr[scan_idx]) if time_arr.size > scan_idx else 0.0
    except (ValueError, IndexError) as exc:
        return _empty_spectrum(str(exc)), str(exc), 0

    display_intensity = np.asarray(intensity, dtype=float)
    if display_intensity.size:
        display_intensity = display_intensity - np.nanmin(display_intensity)
    max_int = np.nanmax(display_intensity) if display_intensity.size else 1.0
    rel_intensity = display_intensity / max_int * 100 if max_int > 0 else display_intensity

    fig = go.Figure()
    TraceType = go.Scattergl if mz.size > 1200 else go.Scatter

    xs = []
    ys = []
    cd = []
    for x_val, y_val, i_val in zip(mz, rel_intensity, intensity):
        xs.extend([x_val, x_val, None])
        ys.extend([0, y_val, None])
        cd.extend([i_val, i_val, None])

    fig.add_trace(TraceType(
        x=xs,
        y=ys,
        mode='lines',
        line=dict(color='#2B6CB0', width=1),
        hoverinfo='skip',
        showlegend=False,
    ))
    fig.add_trace(TraceType(
        x=mz,
        y=rel_intensity,
        mode='markers',
        marker=dict(color='#2B6CB0', size=3, opacity=0.45),
        customdata=intensity,
        hovertemplate=(
            'm/z: %{x:.4g}<br>'
            'Intensity: %{customdata:.4g}<br>'
            'Relative: %{y:.1f}%<extra></extra>'
        ),
        showlegend=False,
    ))
    fig.update_layout(
        template='plotly_white',
        margin=dict(l=48, r=16, t=20, b=38),
        xaxis_title='m/z',
        yaxis_title='Relative Intensity (%)',
        hovermode='closest',
        yaxis=dict(range=[0, 105], showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        xaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        uirevision='ms-spectrum',
    )

    if mz.size > 0:
        top_n = min(5, mz.size)
        top_idx = np.argsort(intensity)[-top_n:][::-1]
        top_peaks = ", ".join(f"{mz[i]:.1f}" for i in top_idx)
        return fig, f"Scan {scan_idx} at {rt:.3f} min | Top m/z: {top_peaks}", scan_idx

    return fig, f"Scan {scan_idx} at {rt:.3f} min | no peaks", scan_idx


def _get_eic_list(data_manager, file_id, file_data):
    if not file_id or not file_data:
        return []
    if hasattr(data_manager, 'get_lcms_eic_overlays'):
        return data_manager.get_lcms_eic_overlays(file_id)
    return file_data.get('eic_overlays', [])


def _opposite_polarity_component(data_manager, active_file, current_file_id):
    """Return (component_id, file_data) for the opposite polarity, or (None, None)."""
    from services.data_store import BundleType, ComponentRole
    bundle = None
    if hasattr(data_manager, 'get_bundle'):
        bundle = data_manager.get_bundle(active_file)
    if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
        bundle = data_manager.get_bundle_for_component(active_file)
    if not bundle or bundle.bundle_type != BundleType.LCMS:
        return None, None

    lookup_id = current_file_id or active_file
    current = next((c for c in bundle.component_list if c.component_id == lookup_id), None)
    if not current:
        return None, None

    if current.role == ComponentRole.MS_POSITIVE:
        other = bundle.get_component(ComponentRole.MS_NEGATIVE)
    elif current.role == ComponentRole.MS_NEGATIVE:
        other = bundle.get_component(ComponentRole.MS_POSITIVE)
    else:
        return None, None

    if not other:
        return None, None
    other_data = data_manager.get_data_by_id(other.component_id)
    return other.component_id, other_data


def _extract_eic_other_polarity(data_manager, lcms_svc, active_file, current_file_id, mz_value, tolerance):
    """Silently extract the same EIC from the opposite polarity component."""
    other_id, other_data = _opposite_polarity_component(data_manager, active_file, current_file_id)
    if not other_data or not lcms_svc.has_spectral_data(other_data):
        return
    try:
        eic_time, eic_intensity = lcms_svc.extract_eic(other_data, float(mz_value), float(tolerance))
    except (ValueError, KeyError):
        return
    overlay = {'mz': float(mz_value), 'tolerance': float(tolerance), 'time': eic_time, 'intensity': eic_intensity}
    if hasattr(data_manager, 'add_lcms_eic_overlay'):
        data_manager.add_lcms_eic_overlay(other_id, overlay)
    else:
        other_data.setdefault('eic_overlays', []).append(overlay)


def _clear_eic_other_polarity(data_manager, active_file, current_file_id):
    """Clear EIC overlays from the opposite polarity component."""
    other_id, other_data = _opposite_polarity_component(data_manager, active_file, current_file_id)
    if not other_id:
        return
    if hasattr(data_manager, 'clear_lcms_eic_overlays'):
        data_manager.clear_lcms_eic_overlays(other_id)
    elif other_data:
        other_data.pop('eic_overlays', None)


def _render_eic_list(eic_list):
    if not eic_list:
        return [html.Span("No EICs extracted", style={'color': '#999', 'fontSize': '12px'})]
    return [
        html.Span(
            f"m/z {e['mz']:.1f} ±{e['tolerance']}",
            style={
                'display': 'inline-block', 'padding': '2px 8px',
                'backgroundColor': '#f0f0f0', 'borderRadius': '12px',
                'fontSize': '11px', 'marginRight': '4px', 'marginBottom': '4px',
            },
        )
        for e in eic_list
    ]


def _build_eic_figure(eic_list):
    if not eic_list:
        return _empty_eic("Extract an EIC to view it here")

    fig = go.Figure()
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9']
    for idx, eic in enumerate(eic_list[-6:]):
        time = np.asarray(eic.get('time', []), dtype=float)
        intensity = np.asarray(eic.get('intensity', []), dtype=float)
        if time.size == 0 or intensity.size == 0:
            continue

        mz = float(eic.get('mz', 0.0))
        tolerance = float(eic.get('tolerance', 0.0))
        label = f"m/z {mz:.4g} +/- {tolerance:.3g}"
        color = colors[idx % len(colors)]
        fig.add_trace(go.Scatter(
            x=time,
            y=intensity,
            mode='lines',
            name=label,
            line=dict(color=color, width=1.6),
            hovertemplate=(
                f"{label}<br>Time: %{{x:.3f}} min"
                "<br>Intensity: %{y:.4g}<extra></extra>"
            ),
        ))

        apex_idx = int(np.argmax(intensity)) if intensity.size else 0
        if intensity.size and intensity[apex_idx] > 0:
            fig.add_trace(go.Scatter(
                x=[time[apex_idx]],
                y=[intensity[apex_idx]],
                mode='markers',
                name=f"{label} apex",
                marker=dict(color=color, size=7, symbol='x'),
                showlegend=False,
                hovertemplate=(
                    f"{label} apex<br>Time: %{{x:.3f}} min"
                    "<br>Intensity: %{y:.4g}<extra></extra>"
                ),
            ))

    if not fig.data:
        return _empty_eic("No EIC signal in the selected m/z window")

    fig.update_layout(
        template='plotly_white',
        margin=dict(l=50, r=20, t=28, b=36),
        xaxis_title='Retention Time (min)',
        yaxis_title='EIC Intensity',
        hovermode='closest',
        xaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        yaxis=dict(showgrid=False, showline=True, mirror=True, linecolor='#ccc', linewidth=1),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0,
            font=dict(size=10),
        ),
        uirevision='lcms-eic',
    )
    return fig


def _resolve_lcms_spectral_entry(data_manager, active_file, lcms_svc):
    """Resolve bundle or component selection to a spectral LC-MS component."""
    if active_file:
        entry = data_manager.get_data_by_id(active_file)
        if entry and lcms_svc.has_spectral_data(entry):
            record = entry.get('record') or {}
            return record.get('id', active_file), entry

        bundle = data_manager.get_bundle(active_file) if hasattr(data_manager, 'get_bundle') else None
        if not bundle and hasattr(data_manager, 'get_bundle_for_component'):
            bundle = data_manager.get_bundle_for_component(active_file)

        if bundle:
            for component in bundle.component_list:
                entry = data_manager.get_data_by_id(component.component_id)
                if entry and lcms_svc.has_spectral_data(entry):
                    return component.component_id, entry

    for candidate_id, candidate in data_manager.loaded_data.items():
        if candidate and lcms_svc.has_spectral_data(candidate):
            record = candidate.get('record') or {}
            return record.get('id', candidate_id), candidate

    return None
