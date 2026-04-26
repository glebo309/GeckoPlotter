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


def register_export_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Export toolbox callbacks."""

    export_svc = data_manager.export_service

    # ── Export Figure ─────────────────────────────────────────────────

    @app.callback(
        Output('exp-fig-download', 'data'),
        Input('exp-fig-btn', 'n_clicks'),
        [State('pub-plot-figure', 'data'),
         State('exp-fig-format', 'value'),
         State('exp-width', 'value'),
         State('exp-height', 'value'),
         State('exp-dpi', 'value')],
        prevent_initial_call=True,
    )
    def export_figure(n_clicks, fig_data, fmt, width, height, dpi):
        if not n_clicks or not fig_data:
            return dash.no_update

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
                # kaleido supports pdf
                pdf_bytes = fig.to_image(format='pdf', width=width, height=height,
                                         scale=scale, engine='kaleido')
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
         State('exp-data-format', 'value')],
        prevent_initial_call=True,
    )
    def export_table_data(n_clicks, data_json, fmt):
        if not n_clicks or not data_json:
            return dash.no_update

        try:
            df = pd.read_json(io.StringIO(data_json), orient='split')
            # Drop internal columns
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

        # Collect peaks from PeakService
        all_peaks = data_manager.peak_service.get_all_peaks()
        if not all_peaks:
            return dash.no_update

        # Build a combined DataFrame
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
        Output('exp-session-download', 'data'),
        Input('exp-session-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def save_session(n_clicks):
        if not n_clicks:
            return dash.no_update

        try:
            # Persist services to project file first
            data_manager.persist_services()

            session_json = export_svc.export_session(
                data_manager,
                peak_service=data_manager.peak_service,
                calibration_service=data_manager.calibration_service,
            )
            return dict(content=session_json, filename='geckoplotter_session.json')
        except Exception as e:
            log.exception(f"Session save failed: {e}")
            return dash.no_update

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
