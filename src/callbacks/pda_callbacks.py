"""PDA explorer links measured slices without changing the main plot's viewport."""
from __future__ import annotations

import math

import dash
from dash import Input, Output, State, callback_context
import plotly.graph_objects as go

from services.pda_service import display_matrix, preview_chromatograms
from services.themes import colorscale, DEFAULT_COLORMAP

from services.pda_service import resolve_pda_source, extract_pda_views, add_pda_chromatogram, add_pda_series


def _figure(source, kind, x_label, y_label, dragmode='zoom', hovermode='closest'):
    fig = go.Figure()
    fig.update_layout(template='plotly_white', margin=dict(l=56, r=18, t=24, b=45),
        font=dict(family='Arial, sans-serif', size=12, color='#454a4f'),
        xaxis_title=x_label, yaxis_title=y_label, showlegend=False,
        dragmode=dragmode, uirevision=f'pda-{source}-{kind}',
        paper_bgcolor='white', plot_bgcolor='white', hovermode=hovermode)
    fig.update_xaxes(showgrid=False, zeroline=False, showline=True, mirror=True,
                     linecolor='#555', linewidth=1, ticks='outside', automargin=True)
    fig.update_yaxes(showgrid=False, zeroline=False, showline=True, mirror=True,
                     linecolor='#555', linewidth=1, ticks='outside', automargin=True)
    return fig


def build_pda_figures(source_id, view, patch_heatmap=False, colormap=DEFAULT_COLORMAP):
    """Display heatmap and exact measured spectrum, retaining zoom between selections."""
    if patch_heatmap:
        heat = dash.no_update  # the selection cross is a client-side overlay; the matrix is never resent
    else:
        heat = _figure(source_id, 'heatmap', 'Time (min)', 'Wavelength (nm)',
                       dragmode='pan',  # Plotly turns Shift + drag into box zoom only from pan; plain drag is taken by the cross
                       hovermode=False)  # the readout is plain JS (pda-heatmap-cursor.js); Plotly hover events cost a Dash round trip each
        times, wavelengths, z = display_matrix(view['times'], view['wavelengths'], view['intensity'])
        heat.add_trace(go.Heatmap(x=times, y=wavelengths,
            z=z.T, colorscale=colorscale(colormap),
            colorbar=dict(title=dict(text='mAU'), thickness=10, len=.9),
            hoverinfo='none'))
    spectrum = _figure(source_id, 'spectrum', 'Wavelength (nm)', 'Absorbance (mAU)')
    spectrum.add_trace(go.Scatter(x=view['wavelengths'].tolist(), y=view['spectrum'].tolist(),
        mode='lines', line=dict(color='#60a5df', width=1.6),
        hovertemplate='%{x:.0f} nm<br>%{y:.5g} mAU<extra></extra>'))
    spectrum.add_vline(x=view['wavelength_nm'], line_width=1, line_dash='dash', line_color='#777')
    spectrum.update_layout(title=dict(text=f"{view['time_min']:.4g} min", font=dict(size=12), x=.12))
    return heat, spectrum


def _point(click):
    return (click or {}).get('points', [{}])[0] if (click or {}).get('points') else {}


def register_pda_callbacks(app, data_manager):
    from flask import jsonify, request

    def pda_chromatograms():
        """Small JSON for the live preview while the heatmap cross is dragged (no Dash round trip)."""
        owner = request.args.get('owner')
        wavelength = request.args.get('wavelength', type=float)
        if not owner or wavelength is None or not math.isfinite(wavelength):   # also 'inf' / 'nan'
            return jsonify({'samples': []}), 400
        return jsonify({'samples': preview_chromatograms(data_manager, owner, wavelength)})

    if getattr(app, 'server', None) is not None:
        app.server.add_url_rule('/_pda/chromatograms', 'pda_chromatograms', pda_chromatograms)

    @app.callback(
        [Output('analysis-nav-pda', 'style'), Output('analysis-tabs', 'value', allow_duplicate=True)],
        [Input('active-file', 'data'), Input('loaded-files', 'data')],
        State('analysis-tabs', 'value'), prevent_initial_call=True)
    def show_pda_tab(active_file, loaded_files, analysis_tab):
        available = resolve_pda_source(data_manager, active_file) is not None
        style = {'flexShrink': 0, 'whiteSpace': 'nowrap', 'display': '' if available else 'none'}
        return style, 'data-overview' if not available and analysis_tab == 'pda' else dash.no_update

    @app.callback(
        [Output('pda-heatmap', 'figure'),
         Output('pda-spectrum', 'figure'), Output('pda-wavelength', 'value'), Output('pda-time', 'value'),
         Output('pda-wavelength', 'min'), Output('pda-wavelength', 'max'),
         Output('pda-time', 'min'), Output('pda-time', 'max'), Output('pda-context', 'data'),
         Output('pda-selection-info', 'children'), Output('pda-add-chromatogram', 'disabled'), Output('pda-add-chromatogram', 'children')],
        [Input('active-file', 'data'), Input('pda-wavelength', 'value'), Input('pda-time', 'value'),
         Input('pda-heatmap', 'clickData'), Input('pda-spectrum', 'clickData'),
         Input('main-plot', 'clickData'),
         Input('selected-peak-idx', 'data'), Input('analysis-tabs', 'value'), Input('pda-colormap', 'data')],
        [State('pda-context', 'data'), State('main-inspector-context', 'data'), State('view-mode', 'data'), Input('pda-cursor-event', 'data'),
         Input('pda-heatmap-event', 'data')],
        prevent_initial_call=True)
    def update_pda_views(active_file, wavelength, time, heat_click, spectrum_click,
                         main_click, selected_peak, analysis_tab, colormap,
                         context, main_figure, view_mode, cursor_event=None, heat_event=None):
        source = resolve_pda_source(data_manager, active_file)
        if not source:
            raise dash.exceptions.PreventUpdate
        source_id, payload = source
        trigger = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        # Selection echoes when another analysis view is in use do not resend
        # a matrix. Opening PDA synchronizes the current peak below.
        if analysis_tab != 'pda':
            raise dash.exceptions.PreventUpdate
        if (context or {}).get('source_id') != source_id:
            entry = data_manager.get_data_by_id(active_file)
            metadata = entry.get('metadata') or {}
            wavelength = metadata.get('wavelength_nm', metadata.get('wavelength', 254.))
            time = None
        elif trigger == 'active-file':
            wavelength = (context or {}).get('wavelength_nm', wavelength)
            time = (context or {}).get('time_min', time)
        if trigger == 'pda-heatmap':
            point = _point(heat_click)
            time, wavelength = point.get('x', time), point.get('y', wavelength)
        elif trigger == 'pda-spectrum':
            wavelength = _point(spectrum_click).get('x', wavelength)
        elif trigger == 'pda-heatmap-event':
            if not heat_event:
                raise dash.exceptions.PreventUpdate
            time = heat_event.get('time_min', time)
            wavelength = heat_event.get('wavelength_nm', wavelength)
        elif trigger == 'pda-cursor-event':
            if not cursor_event or cursor_event.get('source_id') != source_id or view_mode != 'raw':
                raise dash.exceptions.PreventUpdate
            time = cursor_event.get('time_min', time)
        elif trigger == 'main-plot':
            if view_mode != 'raw':
                raise dash.exceptions.PreventUpdate
            point = _point(main_click)
            traces = (main_figure or {}).get('data', [])
            curve = point.get('curveNumber')
            owner = None
            if isinstance(curve, int) and 0 <= curve < len(traces):
                meta = traces[curve].get('meta') or {}
                owner = (meta.get('file_id') or meta.get('pda_source_id')) if isinstance(meta, dict) else None
            clicked_source = resolve_pda_source(data_manager, owner or active_file)
            if not clicked_source or clicked_source[0] != source_id:
                raise dash.exceptions.PreventUpdate
            time = point.get('x', time)
        if trigger in ('selected-peak-idx', 'analysis-tabs', 'active-file') and selected_peak:
            bundle = data_manager.get_bundle_for_component(source_id)
            owners = [bundle.bundle_id] + [component.component_id for component in bundle.component_list] if bundle else [source_id]
            peak = next((peak for owner in owners for peak in data_manager.peak_service.get_peaks(owner)
                         if peak.peak_id == selected_peak), None)
            if peak:
                time = peak.rt
        try:
            view = extract_pda_views(payload, wavelength, time)
        except (ValueError, TypeError) as exc:
            return (dash.no_update,) * 9 + (str(exc), True, 'Add wavelength channel')
        colormap = colormap or DEFAULT_COLORMAP
        patch_heatmap = ((context or {}).get('source_id') == source_id
                         and (context or {}).get('heatmap_ready') is True
                         and (context or {}).get('colormap') == colormap)
        figures = build_pda_figures(source_id, view, patch_heatmap=patch_heatmap, colormap=colormap)
        context = {key: view[key] for key in ('wavelength_nm', 'time_min')}
        context['source_id'] = source_id
        context['heatmap_ready'] = True
        context['colormap'] = colormap
        info = f"Measured: {view['wavelength_nm']:.0f} nm · {view['time_min']:.4g} min"
        return (*figures, view['wavelength_nm'], view['time_min'],
            float(round(min(view['wavelengths']))), float(round(max(view['wavelengths']))),
            float(min(view['times'])), float(max(view['times'])), context, info, False, f"Add {view['wavelength_nm']:.0f} nm channel")

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True), Output('active-file', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True), Output('status-text', 'children', allow_duplicate=True),
         Output('pda-live', 'checked')],
        Input('pda-add-chromatogram', 'n_clicks'),
        [State('active-file', 'data'), State('pda-wavelength', 'value'), State('render-trigger', 'data')],
        prevent_initial_call=True)
    def add_pda_trace(n_clicks, active_file, wavelength, render_trigger):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        try:
            added = add_pda_series(data_manager, active_file, wavelength)
            component_id = next(iter(added.values()))
        except (ValueError, TypeError) as exc:
            return dash.no_update, dash.no_update, dash.no_update, str(exc), dash.no_update
        entry = data_manager.get_data_by_id(component_id)
        return data_manager.get_loaded_files_list(), component_id, (render_trigger or 0) + 1, f"Added {entry['metadata']['wavelength_nm']:.0f} nm channel to {len(added)} sample" + ("s." if len(added) != 1 else "."), False

    @app.callback(
        [Output('pda-preview', 'data'), Output('pda-main-cursor', 'data')],
        [Input('pda-context', 'data'), Input('pda-live', 'checked'),
         Input('analysis-tabs', 'value'), Input('active-file', 'data'), Input('baseline-mode', 'data')])
    def sync_pda_main_view(context, live, analysis_tab, active_file, mode):
        source = resolve_pda_source(data_manager, active_file)
        if (analysis_tab != 'pda' or not context or not source
                or context.get('source_id') != source[0]):
            return None, None
        bundle = data_manager.get_bundle(active_file)
        owner = bundle.primary.component_id if bundle and bundle.primary else active_file
        times = source[1]['time_min']
        state = {**context, 'owner_id': owner, 'time_minimum':float(times[0]), 'time_maximum':float(times[-1])}
        preview = {key:state[key] for key in ('source_id','owner_id','wavelength_nm')}
        return (preview if live and mode != 'deconvolve' else None), state

    @app.callback(
        Output('baseline-draw-btn', 'disabled'),
        Input('pda-preview', 'data'))
    def preview_integration_controls(preview):
        return False  # drawing on a preview keeps its wavelength as real channels (see handle_relayout)

    app.clientside_callback(
        """function(context) {
            if (window.GeckoPdaHeatmapCursor) window.GeckoPdaHeatmapCursor.setSelection(context);
            return context;
        }""",
        Output('pda-cross-sync', 'data'), Input('pda-context', 'data'))

    app.clientside_callback(
        """function(cursor) {
            if (window.GeckoPdaScanCursor) window.GeckoPdaScanCursor.setState(cursor);
            return cursor;
        }""",
        Output('pda-cursor-sync', 'data'), Input('pda-main-cursor', 'data'))
