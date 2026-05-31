# =============================================================================
# File: callbacks/export_callbacks.py
# =============================================================================
"""
Export toolbox callbacks for GeckoPlotter V2.

Wires the Export tab buttons to ExportService for figure, data, peak,
calibration, and session export/import.
"""

import base64
import io
import json
import logging
import sys

import dash
from dash import Input, Output, State
import pandas as pd
import plotly.graph_objects as go

log = logging.getLogger('geckoplotter.export')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

# Publication preset dimensions (px at 300 DPI)
# Journal: 84mm single col, 114mm 1.5 col, 174mm full width
PRESETS = {
    'two-col':  {'w': 992,  'h': 744,  'label': '84 × 63 mm (two-column)'},
    'one-col':  {'w': 2055, 'h': 1541, 'label': '174 × 131 mm (full width)'},
    '1.5-col':  {'w': 1346, 'h': 1009, 'label': '114 × 86 mm (1.5 column)'},
    'ppt':      {'w': 1920, 'h': 1080, 'label': '16:9 PowerPoint slide'},
    'custom':   None,
}


def register_export_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Export toolbox callbacks."""

    export_svc = data_manager.export_service

    # ── Preset selector ──────────────────────────────────────────────

    @app.callback(
        [Output('exp-width', 'value'),
         Output('exp-height', 'value'),
         Output('exp-custom-dims', 'style'),
         Output('exp-preset-info', 'children')],
        Input('exp-preset', 'value'),
        prevent_initial_call=True,
    )
    def apply_preset(preset):
        p = PRESETS.get(preset)
        if p is None:
            return dash.no_update, dash.no_update, {'display': 'block'}, 'Custom dimensions'
        return p['w'], p['h'], {'display': 'none'}, p['label']

    # ── Export Figure ─────────────────────────────────────────────────

    @app.callback(
        Output('exp-fig-download', 'data'),
        Input('exp-fig-btn', 'n_clicks'),
        [State('main-plot', 'figure'),
         State('exp-fig-format', 'value'),
         State('exp-preset', 'value'),
         State('exp-width', 'value'),
         State('exp-height', 'value'),
         State('exp-dpi', 'value')],
        prevent_initial_call=True,
    )
    def export_figure(n_clicks, fig_data, fmt, preset, width, height, dpi):
        if not n_clicks or not fig_data:
            log.debug("Export figure: no figure data available")
            return dash.no_update

        p = PRESETS.get(preset)
        if p is not None:
            width = p['w']
            height = p['h']

        fig = go.Figure(fig_data)
        width = int(width or 800)
        height = int(height or 500)
        scale = int(dpi or 3)

        try:
            if fmt == 'html':
                html_str = export_svc.export_figure_html(fig)
                return dict(content=html_str, filename='figure.html')
            elif fmt == 'svg':
                svg_bytes = export_svc.export_figure_svg(fig, width=width, height=height)
                return dict(
                    content=base64.b64encode(svg_bytes).decode(),
                    filename='figure.svg',
                    base64=True,
                )
            elif fmt == 'pdf':
                fig = export_svc.prepare_figure_for_static_export(fig, width, height)
                pdf_bytes = fig.to_image(format='pdf', width=width, height=height,
                                         scale=scale)
                return dict(
                    content=base64.b64encode(pdf_bytes).decode(),
                    filename='figure.pdf',
                    base64=True,
                )
            else:  # png
                png_bytes = export_svc.export_figure_png(fig, width=width, height=height, scale=scale)
                return dict(
                    content=base64.b64encode(png_bytes).decode(),
                    filename='figure.png',
                    base64=True,
                )
        except Exception as e:
            log.exception(f"Figure export failed: {e}")
            return dash.no_update

    # ── Export Table Data ─────────────────────────────────────────────

    @app.callback(
        Output('exp-data-download', 'data', allow_duplicate=True),
        Input('exp-data-btn', 'n_clicks'),
        [State('pub-data-store', 'data'),
         State('active-file', 'data'),
         State('exp-data-format', 'value')],
        prevent_initial_call=True,
    )
    def export_table_data(n_clicks, data_json, active_file, fmt):
        if not n_clicks:
            return dash.no_update

        df = None
        if data_json:
            try:
                df = pd.read_json(io.StringIO(data_json), orient='split')
            except Exception:
                pass

        if df is None and active_file:
            file_data = data_manager.get_data_by_id(active_file)
            if file_data is not None:
                sr = file_data.get('standardized')
                if sr is not None and hasattr(sr, 'data') and sr.data is not None:
                    df = sr.data.copy()
                elif 'data' in file_data and isinstance(file_data['data'], pd.DataFrame):
                    df = file_data['data'].copy()

        if df is None:
            log.debug("Export table: no data available")
            return dash.no_update

        try:
            for col in ['_row_id']:
                if col in df.columns:
                    df = df.drop(columns=[col])

            if fmt == 'xlsx':
                content = export_svc.export_table_excel(df)
                return dict(
                    content=base64.b64encode(content).decode(),
                    filename='data.xlsx',
                    base64=True,
                )
            elif fmt == 'json':
                return dict(
                    content=df.to_json(orient='records', indent=2),
                    filename='data.json',
                )
            else:  # csv
                content = export_svc.export_table_csv(df)
                return dict(
                    content=base64.b64encode(content).decode(),
                    filename='data.csv',
                    base64=True,
                )
        except Exception as e:
            log.exception(f"Table data export failed: {e}")
            return dash.no_update

    # ── Export Peak Results ───────────────────────────────────────────

    @app.callback(
        Output('exp-data-download', 'data', allow_duplicate=True),
        Input('exp-peaks-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('exp-data-format', 'value')],
        prevent_initial_call=True,
    )
    def export_peak_results(n_clicks, active_file, fmt):
        if not n_clicks:
            return dash.no_update

        all_peaks = data_manager.peak_service.get_all_peaks()
        if not all_peaks:
            return dash.no_update

        rows = []
        for fid, peaks in all_peaks.items():
            for p in peaks:
                rows.append({
                    'file_id': p.file_id,
                    'name': p.name,
                    'retention_time': p.rt,
                    'area': p.area,
                    'height': p.height,
                    'width': p.width,
                    'start': p.rt_start,
                    'end': p.rt_end,
                })

        if not rows:
            return dash.no_update

        df = pd.DataFrame(rows)
        if fmt == 'xlsx':
            content = export_svc.export_table_excel(df, filename='peaks.xlsx')
            return dict(content=base64.b64encode(content).decode(), filename='peaks.xlsx', base64=True)
        else:
            content = export_svc.export_table_csv(df, filename='peaks.csv')
            return dict(content=base64.b64encode(content).decode(), filename='peaks.csv', base64=True)

    # ── Export Calibration ────────────────────────────────────────────

    @app.callback(
        Output('exp-data-download', 'data', allow_duplicate=True),
        Input('exp-cal-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def export_calibration(n_clicks):
        if not n_clicks:
            return dash.no_update

        cal_data = data_manager.calibration_service.serialize()
        if not cal_data:
            return dash.no_update

        content = json.dumps(cal_data, indent=2)
        return dict(content=content, filename='calibration.json')

    # ── Save Session ──────────────────────────────────────────────────

    @app.callback(
        [Output('exp-session-download', 'data'),
         Output('exp-session-status', 'children')],
        Input('exp-session-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def save_session(n_clicks):
        if not n_clicks:
            return dash.no_update, dash.no_update

        return (
            dash.no_update,
            "Session saving is not implemented yet. It will come in a future build.",
        )

    # ── Load Session ──────────────────────────────────────────────────

    @app.callback(
        Output('exp-session-download', 'data', allow_duplicate=True),
        Input('exp-session-upload', 'contents'),
        State('exp-session-upload', 'filename'),
        prevent_initial_call=True,
    )
    def load_session(contents, filename):
        if not contents:
            return dash.no_update

        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string).decode('utf-8')

            export_svc.import_session(
                decoded,
                data_manager,
                peak_service=data_manager.peak_service,
                calibration_service=data_manager.calibration_service,
            )
            log.debug(f"Session loaded from {filename}")
        except Exception as e:
            log.exception(f"Session load failed: {e}")

        return dash.no_update
