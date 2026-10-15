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

# Names and physical sizes match the publication presets.
PRESETS = {
    'single-col': {'w': 84, 'h': 63, 'label': '84 × 63 mm · single-column'},
    'full-width': {'w': 174, 'h': 104, 'label': '174 × 104 mm · full-width'},
    'presentation': {'w': 254, 'h': 143, 'label': '254 × 143 mm · presentation'},
}


def register_export_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Export toolbox callbacks."""

    from services.workspaces import service_of
    export_svc = service_of(data_manager, 'export_service')

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
            return (dash.no_update, dash.no_update,
                    {'display': 'block' if preset == 'custom' else 'none'},
                    'Custom size in millimetres' if preset == 'custom' else 'Keeps the displayed figure, styling and zoom')
        return p['w'], p['h'], {'display': 'none'}, p['label']

    # ── Export Figure ─────────────────────────────────────────────────

    app.clientside_callback(
        dash.ClientsideFunction(namespace='geckoFigureActions', function_name='exportRequest'),
        Output('figure-export-request', 'data'),
        [Input('exp-fig-btn', 'n_clicks'), Input('pub-export-btn', 'n_clicks')],
        [State('exp-fig-format', 'value'), State('exp-preset', 'value'),
         State('exp-width', 'value'), State('exp-height', 'value'), State('exp-dpi', 'value'),
         State('pub-export-format', 'value'), State('pub-fig-width-mm', 'value'),
         State('pub-fig-height-mm', 'value'), State('pub-dpi', 'value')],
        prevent_initial_call=True,
    )

    @app.callback(
        [Output('exp-fig-download', 'data'), Output('exp-fig-status', 'children'),
         Output('pub-export-status', 'children'),
         Output('figure-action-status', 'children', allow_duplicate=True)],
        Input('figure-export-request', 'data'),
        prevent_initial_call=True,
        running=[(Output('exp-fig-btn', 'loading'), True, False),
                 (Output('pub-export-btn', 'loading'), True, False)],
    )
    def export_figure(request):
        if not request:
            return (dash.no_update,) * 4
        from services.figure_export import export_displayed_figure
        try:
            if request.get('error'):
                raise ValueError(request['error'])
            result = export_displayed_figure(
                request['figure'], request.get('format'), request['width_mm'],
                request['height_mm'], request.get('dpi'), request.get('render_width'),
                request.get('label'))
            message = f"Download ready: {result['filename']}"
            return result, message, message, message
        except Exception:
            log.exception('Displayed figure export failed')
            message = request.get('error') or 'Export failed. Try another format or a lower resolution.'
            return dash.no_update, message, message, message

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
                from services import table_store
                df = table_store.frame(data_json)
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
        [Output('exp-data-download', 'data', allow_duplicate=True),
         Output('status-text', 'children', allow_duplicate=True)],
        Input('exp-results-btn', 'n_clicks'),
        State('plot-tabs', 'data'),
        prevent_initial_call=True,
    )
    def export_results_workbook(n_clicks, tabs=None):
        """Every result of the workspace in one Excel workbook (services/results_workbook)."""
        if not n_clicks:
            return dash.no_update, dash.no_update
        if not any(True for _ in data_manager.iter_bundles()):
            return dash.no_update, 'Load data first: there is nothing to export yet.'
        from datetime import date
        from services.results_workbook import build_results_workbook
        name = (getattr(data_manager, 'session_meta', {}) or {}).get('project_name') or 'GeckoPlotter results'
        labels = {t.get('id'): t.get('label') for t in (tabs or []) if t.get('type', 'raw') == 'raw'}
        content = build_results_workbook(data_manager, name, tab_labels=labels)
        filename = f"{name} {date.today().isoformat()}.xlsx".replace('/', '-')
        return (dict(content=base64.b64encode(content).decode(), filename=filename, base64=True),
                f'Exported {filename}')

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
