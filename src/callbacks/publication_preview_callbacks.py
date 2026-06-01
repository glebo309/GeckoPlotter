"""Publication preview callbacks — render figure in paper mock."""

import base64
import logging
import sys

import dash
from dash import Input, Output, State
import plotly.graph_objects as go

log = logging.getLogger('geckoplotter.pub_preview')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

MM_TO_PX_300DPI = 300 / 25.4  # ~11.81 px per mm

# Paper mock layout constants (must match paper_mock.py)
_PAGE_WIDTH = 680
_PAGE_PAD_H = 28 * 2  # left + right padding
_CONTENT_WIDTH = _PAGE_WIDTH - _PAGE_PAD_H  # 624
_COL_GAP = 10
_SINGLE_COL_WIDTH = (_CONTENT_WIDTH - _COL_GAP) / 2  # 307


def register_publication_preview_callbacks(app, data_manager):
    """Register all publication preview callbacks."""

    from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS
    from callbacks.viz_callbacks import _collect_visible_files
    from callbacks.peak_overlay import overlay_peaks_on_figure, add_peak_traces, cleanup_peak_traces
    from callbacks.baseline_callbacks import get_xy_arrays
    from services.plot_manager import PlotManager
    from services.plot_smoothing import smooth_plotly_traces
    from components.paper_mock import PUB_PRESETS

    plot_manager = PlotManager()

    def _build_pub_figure(plot_settings, active_file, sub_rows, sub_cols,
                          zoom_sync, selected_peak_id,
                          loaded_files, plot_tabs, file_order, display_opts,
                          source_group_key=None):
        """Build the publication figure. Shared by render and export."""
        from plotly.subplots import make_subplots

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        layout_mode = s.get('layout_mode', 'overlay')

        n_rows = max(1, int(sub_rows or 1))
        n_cols = max(1, int(sub_cols or 1))
        n_panels = n_rows * n_cols

        raw_tabs = [t for t in (plot_tabs or []) if t.get('type') == 'raw']
        if source_group_key is None and not raw_tabs:
            empty = go.Figure()
            empty.update_layout(
                xaxis={'visible': False}, yaxis={'visible': False},
                annotations=[dict(text='Load data to preview',
                                  xref='paper', yref='paper',
                                  x=0.5, y=0.5, showarrow=False,
                                  font=dict(size=14, color='#999'))],
            )
            return empty

        if source_group_key is None:
            source_tab = raw_tabs[0]
            group_key = tuple(source_tab.get('group_key', []))
        else:
            group_key = tuple(source_group_key)
        visible_files = _collect_visible_files(
            data_manager, active_file, loaded_files,
            target_group_override=group_key, file_order=file_order)

        if not visible_files:
            return go.Figure()

        subplot_spacing = s.get('subplot_spacing', 0.08)
        base_fig = plot_manager.create_multi_file_plot(visible_files, layout_mode, subplot_spacing=subplot_spacing)
        base_obj = go.Figure(base_fig) if isinstance(base_fig, dict) else base_fig
        all_traces = list(base_obj.data)

        # Smoothing
        smooth_window = s.get('smooth_window', 0)
        if smooth_window >= 3:
            smooth_plotly_traces(all_traces, smooth_window)

        if n_panels > 1:
            fig_obj = make_subplots(rows=n_rows, cols=n_cols,
                                    vertical_spacing=max(0.02, subplot_spacing),
                                    horizontal_spacing=0.08)
            for i, trace in enumerate(all_traces):
                panel_idx = i % n_panels
                r = panel_idx // n_cols + 1
                c = panel_idx % n_cols + 1
                trace.showlegend = (i < n_panels)
                fig_obj.add_trace(trace, row=r, col=c)

            if zoom_sync and n_panels > 1:
                for i in range(2, n_panels + 1):
                    fig_obj.update_layout(**{
                        f'xaxis{i}': {'matches': 'x'},
                        f'yaxis{i}': {'matches': 'y'},
                    })
        elif layout_mode == 'stacked':
            fig_obj = base_obj
        else:
            fig_obj = go.Figure(data=all_traces, layout=base_obj.layout)

        # Peak overlays
        show_peaks = 'peaks' in (display_opts or ['peaks'])
        if show_peaks:
            if layout_mode == 'stacked':
                flat_files = []
                for files in visible_files.values():
                    flat_files.extend(files)
                from callbacks.viz_callbacks import _find_file_id
                cleanup_peak_traces(fig_obj)
                for row_idx, (fname, fdata) in enumerate(flat_files, start=1):
                    fid = _find_file_id(data_manager, fdata)
                    if not fid:
                        continue
                    peaks = data_manager.peak_service.get_peaks(fid)
                    if not peaks:
                        continue
                    _ov_time, _ov_signal = get_xy_arrays(data_manager, fid)
                    if _ov_time is not None:
                        add_peak_traces(fig_obj, peaks, _ov_time, _ov_signal, selected_peak_id, row=row_idx)
            elif active_file:
                _ov_time, _ov_signal = get_xy_arrays(data_manager, active_file)
                if _ov_time is not None:
                    all_peaks = data_manager.peak_service.get_peaks(active_file)
                    if all_peaks:
                        fig_obj = overlay_peaks_on_figure(
                            all_peaks, fig_obj, _ov_time, _ov_signal, selected_peak_id)

        # Apply plot settings
        ps = PlotSettingsService.from_dict(dict(s, y_label=s.get('y1_label', 'Y1')))
        PlotSettingsService.apply_to_figure(fig_obj, ps)

        fig_obj.update_layout(autosize=True)

        return fig_obj

    def _active_publication_tab(active_tab_id, plot_tabs):
        return next(
            (t for t in (plot_tabs or [])
             if t.get('id') == active_tab_id and t.get('type') == 'publication'),
            None,
        )

    def _style_snapshot_figure(fig_data, plot_settings):
        fig_obj = go.Figure(fig_data)
        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        ps = PlotSettingsService.from_dict(dict(s, y_label=s.get('y1_label', 'Y1')))
        PlotSettingsService.apply_to_figure(fig_obj, ps)
        return fig_obj

    # ── Toggle paper mock visibility ─────────────────────────────────
    @app.callback(
        [Output('pub-preview-wrapper', 'style'),
         Output('main-plot', 'style')],
        Input('active-plot-tab', 'data'),
        State('plot-tabs', 'data'),
        prevent_initial_call=True,
    )
    def toggle_pub_preview(active_tab_id, plot_tabs):
        if _active_publication_tab(active_tab_id, plot_tabs):
            return (
                {'display': 'flex', 'flexDirection': 'column', 'height': '100%',
                 'width': '100%', 'position': 'absolute', 'top': '0', 'left': '0',
                 'zIndex': '10', 'background': '#e8e8e8'},
                {'width': '100%', 'height': '100%', 'display': 'none'},
            )
        return (
            {'display': 'none'},
            {'width': '100%', 'height': '100%'},
        )

    # ── Sync preset → figure size inputs (respecting custom dims) ────
    @app.callback(
        [Output('pub-fig-width-mm', 'value'),
         Output('pub-fig-height-mm', 'value')],
        Input('pub-preset', 'value'),
        State('pub-custom-dims', 'data'),
        prevent_initial_call=True,
    )
    def sync_preset_to_dims(preset, custom_dims):
        custom_dims = custom_dims or {}
        if preset in custom_dims:
            cd = custom_dims[preset]
            return cd.get('w', 84), cd.get('h', 63)
        p = PUB_PRESETS.get(preset)
        if p:
            return p['mm_w'], p['mm_h']
        return dash.no_update, dash.no_update

    # ── Toggle journal paper vs PowerPoint slide mock ───────────────────
    @app.callback(
        [Output('pub-paper-container', 'style'),
         Output('pub-slide-container', 'style')],
        Input('pub-preset', 'value'),
    )
    def toggle_mock_layout(preset):
        paper_style = {
            'flex': '1', 'overflow': 'auto', 'background': '#e8e8e8',
            'display': 'flex', 'justifyContent': 'center',
            'alignItems': 'flex-start', 'padding': '20px',
        }
        slide_style = {
            'flex': '1', 'overflow': 'auto', 'background': '#e8e8e8',
            'display': 'none', 'justifyContent': 'center',
            'alignItems': 'center', 'padding': '20px',
        }
        if preset == 'presentation':
            return {**paper_style, 'display': 'none'}, {**slide_style, 'display': 'flex'}
        return paper_style, slide_style

    @app.callback(
        Output('pub-slide-graph', 'figure'),
        [Input('pub-preview-graph', 'figure'),
         Input('pub-preset', 'value')],
    )
    def sync_slide_figure(fig, preset):
        if preset != 'presentation' or not fig:
            raise dash.exceptions.PreventUpdate
        return fig

    # ── Save custom dims per preset ──────────────────────────────────
    @app.callback(
        Output('pub-custom-dims', 'data'),
        [Input('pub-fig-width-mm', 'value'),
         Input('pub-fig-height-mm', 'value')],
        [State('pub-preset', 'value'),
         State('pub-custom-dims', 'data')],
        prevent_initial_call=True,
    )
    def save_custom_dims(w, h, preset, custom_dims):
        if w is None or h is None or not preset:
            return dash.no_update
        custom_dims = custom_dims or {}
        existing = custom_dims.get(preset, {})
        if existing.get('w') == w and existing.get('h') == h:
            return dash.no_update
        return {**custom_dims, preset: {'w': w, 'h': h}}

    # ── Sync subplot grid → layout mode ───────────────────────────────
    @app.callback(
        Output('pt-layout-mode', 'value', allow_duplicate=True),
        [Input('pub-subplot-rows', 'value'),
         Input('pub-subplot-cols', 'value')],
        prevent_initial_call=True,
    )
    def sync_grid_to_layout_mode(rows, cols):
        """Publication grid is preview-local; do not mutate the raw plot layout."""
        return dash.no_update

    # ── Render figure into pub-preview-graph ─────────────────────────
    # Display-only: peaks are shown but not interactive (no selection,
    # no integration drawing). Use the Chromatograms tab for analysis.
    @app.callback(
        Output('pub-preview-graph', 'figure'),
        [Input('active-plot-tab', 'data'),
         Input('current-plot-settings', 'data'),
         Input('pub-preset', 'value'),
         Input('render-trigger', 'data'),
         Input('active-file', 'data'),
         Input('pub-subplot-rows', 'value'),
         Input('pub-subplot-cols', 'value'),
         Input('pub-zoom-sync', 'checked'),
         Input('peak-change-trigger', 'data')],
        [State('loaded-files', 'data'),
         State('plot-tabs', 'data'),
         State('file-order', 'data'),
         State('int-display-opts', 'value'),
         State('custom-plot-figures', 'data')],
        prevent_initial_call=True,
    )
    def render_pub_figure(active_tab_id, plot_settings, preset, render_trigger,
                          active_file, sub_rows, sub_cols, zoom_sync, peak_trigger,
                          loaded_files, plot_tabs, file_order, display_opts,
                          custom_figures):
        pub_tab = _active_publication_tab(active_tab_id, plot_tabs)
        if not pub_tab:
            raise dash.exceptions.PreventUpdate

        entry = (custom_figures or {}).get(active_tab_id, {})
        source_group_key = entry.get('source_group_key')
        snapshot = entry.get('figure')

        if source_group_key:
            fig_obj = _build_pub_figure(
                plot_settings, active_file, sub_rows, sub_cols,
                zoom_sync, None,
                loaded_files, plot_tabs, file_order, display_opts,
                source_group_key=source_group_key)
        elif snapshot:
            fig_obj = _style_snapshot_figure(snapshot, plot_settings)
        else:
            fig_obj = go.Figure()

        fig_obj.update_layout(
            uirevision=active_tab_id,
            hovermode=False,
            dragmode='zoom',
        )

        return fig_obj

    # ── Update figure slot + readout based on size inputs ─────────────
    @app.callback(
        [Output('pub-figure-slot', 'style'),
         Output('pub-right-col', 'style'),
         Output('pub-dim-readout', 'children')],
        [Input('pub-fig-width-mm', 'value'),
         Input('pub-fig-height-mm', 'value'),
         Input('pub-dpi', 'value')],
        prevent_initial_call=True,
    )
    def update_figure_layout(w_mm, h_mm, dpi):
        w_mm = max(20, int(w_mm or 84))
        h_mm = max(15, int(h_mm or 63))
        dpi = max(72, int(dpi or 300))
        readout = f"{w_mm} × {h_mm} mm · {dpi} DPI"
        aspect = f"{w_mm} / {h_mm}"

        is_full = w_mm > 90

        base_slot_style = {
            'margin': '4px 0',
            'overflow': 'hidden',
            'aspectRatio': aspect,
        }

        if is_full:
            slot_style = {**base_slot_style, 'width': '100%'}
            right_style = {'display': 'none'}
        else:
            slot_style = {**base_slot_style, 'width': '100%'}
            right_style = {'flex': '1', 'minWidth': '0'}

        return slot_style, right_style, readout

    # ── Export from preview ─────────────────────────────────────────
    @app.callback(
        Output('pub-export-download', 'data'),
        Input('pub-export-btn', 'n_clicks'),
        [State('pub-export-format', 'value'),
         State('pub-fig-width-mm', 'value'),
         State('pub-fig-height-mm', 'value'),
         State('pub-dpi', 'value'),
         State('pub-preview-graph', 'figure')],
        prevent_initial_call=True,
    )
    def export_from_preview(n_clicks, fmt, w_mm, h_mm, dpi, fig_data):
        if not n_clicks or not fig_data:
            return dash.no_update

        w_mm = max(20, int(w_mm or 84))
        h_mm = max(15, int(h_mm or 63))
        dpi = max(72, int(dpi or 300))

        fig = go.Figure(fig_data)

        is_full = w_mm > 90
        preview_width = _CONTENT_WIDTH if is_full else _SINGLE_COL_WIDTH
        preview_height = preview_width * h_mm / w_mm

        width = int(round(preview_width))
        height = int(round(preview_height))

        mm_to_px = dpi / 25.4
        target_px = w_mm * mm_to_px
        scale = target_px / preview_width

        export_svc = data_manager.export_service

        try:
            if fmt == 'svg':
                svg_bytes = export_svc.export_figure_svg(fig, width=width, height=height)
                return dict(
                    content=base64.b64encode(svg_bytes).decode(),
                    filename='figure.svg', base64=True)
            elif fmt == 'pdf':
                fig = export_svc.prepare_figure_for_static_export(fig, width, height)
                pdf_bytes = fig.to_image(
                    format='pdf', width=width, height=height, scale=scale)
                return dict(
                    content=base64.b64encode(pdf_bytes).decode(),
                    filename='figure.pdf', base64=True)
            elif fmt == 'tiff':
                from PIL import Image
                import io as _io
                png_bytes = export_svc.export_figure_png(
                    fig, width=width, height=height, scale=scale)
                img = Image.open(_io.BytesIO(png_bytes))
                buf = _io.BytesIO()
                img.save(buf, format='TIFF', compression='tiff_lzw', dpi=(dpi, dpi))
                return dict(
                    content=base64.b64encode(buf.getvalue()).decode(),
                    filename='figure.tiff', base64=True)
            else:
                png_bytes = export_svc.export_figure_png(
                    fig, width=width, height=height, scale=scale)
                return dict(
                    content=base64.b64encode(png_bytes).decode(),
                    filename='figure.png', base64=True)
        except Exception as e:
            log.exception(f"Publication export failed: {e}")
            return dash.no_update
