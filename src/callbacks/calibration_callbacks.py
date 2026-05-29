# =============================================================================
# File: callbacks/calibration_callbacks.py
# =============================================================================
"""
Calibration tab callbacks for GeckoPlotter V2.

Wires the Calibration UI to CalibrationService for creating models,
adding standards, fitting curves, and predicting concentrations.
"""

import logging
import sys

import dash
from dash import Input, Output, State, html, dcc
import plotly.graph_objects as go

log = logging.getLogger('geckoplotter.calibration')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def register_calibration_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all Calibration tab callbacks."""

    cal_svc = data_manager.calibration_service

    def _model_options():
        """Build dropdown options from existing models."""
        opts = []
        for mid, m in cal_svc.get_all_models().items():
            label = f"{m.analyte_name} ({m.fit_type})"
            if m.r_squared is not None:
                label += f" — R²={m.r_squared:.5f}"
            opts.append({'label': label, 'value': mid})
        return opts

    def _standards_table(model_id):
        """Build an HTML table showing standards for a model."""
        model = cal_svc.get_model(model_id)
        if model is None or not model.standards:
            return html.P("No standards added yet",
                          style={'color': '#999', 'fontSize': '12px'})

        header = html.Tr([
            html.Th("Sample", style={'padding': '4px 8px', 'fontSize': '12px', 'backgroundColor': '#f0f0f0', 'border': '1px solid #ddd'}),
            html.Th("Conc.", style={'padding': '4px 8px', 'fontSize': '12px', 'backgroundColor': '#f0f0f0', 'border': '1px solid #ddd', 'textAlign': 'right'}),
            html.Th("Area", style={'padding': '4px 8px', 'fontSize': '12px', 'backgroundColor': '#f0f0f0', 'border': '1px solid #ddd', 'textAlign': 'right'}),
            html.Th("Incl.", style={'padding': '4px 8px', 'fontSize': '12px', 'backgroundColor': '#f0f0f0', 'border': '1px solid #ddd', 'textAlign': 'center'}),
        ])

        rows = []
        for s in model.standards:
            style_base = {'padding': '4px 8px', 'fontSize': '12px', 'border': '1px solid #ddd'}
            if not s.included:
                style_base['color'] = '#999'
                style_base['textDecoration'] = 'line-through'
            rows.append(html.Tr([
                html.Td(s.sample_name, style=style_base),
                html.Td(f"{s.concentration:.4g}", style={**style_base, 'textAlign': 'right'}),
                html.Td(f"{s.area:.1f}", style={**style_base, 'textAlign': 'right'}),
                html.Td("Yes" if s.included else "No",
                         style={**style_base, 'textAlign': 'center'}),
            ]))

        return html.Table([header] + rows, style={
            'width': '100%', 'borderCollapse': 'collapse', 'marginTop': '6px'})

    # ── Create Model ──────────────────────────────────────────────────

    @app.callback(
        [Output('cal-active-model', 'data'),
         Output('cal-active-model', 'value'),
         Output('cal-standards-table', 'children', allow_duplicate=True)],
        Input('cal-create-btn', 'n_clicks'),
        [State('cal-analyte-name', 'value'),
         State('cal-units', 'value'),
         State('cal-fit-type', 'value'),
         State('cal-force-zero', 'checked'),
         State('cal-peak-group', 'value')],
        prevent_initial_call=True,
    )
    def create_model(n_clicks, analyte_name, units, fit_type, force_zero, peak_group):
        if not n_clicks or not analyte_name:
            return dash.no_update, dash.no_update, dash.no_update

        model = cal_svc.create_model(
            analyte_name=analyte_name,
            group_id=peak_group or '',
            fit_type=fit_type or 'linear',
            force_zero=bool(force_zero),
            units=units or '',
        )
        log.debug(f"Created calibration model: {model.analyte_name} ({model.model_id})")

        opts = _model_options()
        return opts, model.model_id, _standards_table(model.model_id)

    # ── Add Standard ──────────────────────────────────────────────────

    @app.callback(
        [Output('cal-standards-table', 'children', allow_duplicate=True),
         Output('cal-std-sample', 'value'),
         Output('cal-std-conc', 'value'),
         Output('cal-std-area', 'value')],
        Input('cal-add-std-btn', 'n_clicks'),
        [State('cal-active-model', 'value'),
         State('cal-std-sample', 'value'),
         State('cal-std-conc', 'value'),
         State('cal-std-area', 'value')],
        prevent_initial_call=True,
    )
    def add_standard(n_clicks, model_id, sample, conc, area):
        if not n_clicks or not model_id or not sample or conc is None or area is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        cal_svc.add_standard(model_id, sample, float(conc), float(area))
        log.debug(f"Added standard: {sample} conc={conc} area={area}")

        return _standards_table(model_id), '', None, None

    # ── Fit Model ─────────────────────────────────────────────────────

    @app.callback(
        [Output('cal-curve-graph', 'figure'),
         Output('cal-results-info', 'children'),
         Output('cal-active-model', 'data', allow_duplicate=True)],
        Input('cal-fit-btn', 'n_clicks'),
        State('cal-active-model', 'value'),
        prevent_initial_call=True,
    )
    def fit_model(n_clicks, model_id):
        if not n_clicks or not model_id:
            return dash.no_update, dash.no_update, dash.no_update

        try:
            model = cal_svc.fit_model(model_id)
            fig = cal_svc.create_calibration_figure(model_id)

            info_parts = [
                f"Analyte: {model.analyte_name}",
                f"Fit: {model.fit_type}" + (" (forced zero)" if model.force_zero else ""),
                f"R² = {model.r_squared:.6f}" if model.r_squared is not None else "",
                f"Standards: {sum(1 for s in model.standards if s.included)} included, "
                f"{sum(1 for s in model.standards if not s.included)} excluded",
            ]
            info = html.Div([html.P(p, style={'margin': '2px 0'}) for p in info_parts if p])

            return fig, info, _model_options()

        except Exception as e:
            log.exception(f"Calibration fit failed: {e}")
            return dash.no_update, html.P(f"Error: {e}", style={'color': 'red'}), dash.no_update

    # ── Predict Concentrations ────────────────────────────────────────

    @app.callback(
        Output('cal-results-info', 'children', allow_duplicate=True),
        Input('cal-predict-btn', 'n_clicks'),
        State('cal-active-model', 'value'),
        prevent_initial_call=True,
    )
    def predict_concentrations(n_clicks, model_id):
        if not n_clicks or not model_id:
            return dash.no_update

        model = cal_svc.get_model(model_id)
        if model is None or model.coefficients is None:
            return html.P("Fit the model first before predicting",
                          style={'color': '#999'})

        # Predict for all peaks in PeakService that match the model's group
        results = []
        all_peaks = data_manager.peak_service.get_all_peaks()
        for fid, peaks in all_peaks.items():
            for peak in peaks:
                conc = cal_svc.predict_concentration(model_id, peak.area)
                if conc is not None:
                    peak.concentration = conc
                    peak.calibration_id = model_id
                    results.append(f"{peak.name} ({fid[:8]}): {conc:.4g} {model.units}")

        if not results:
            return html.P("No peaks found to predict", style={'color': '#999'})

        return html.Div([
            html.P(f"Predicted {len(results)} concentrations:", style={'fontWeight': 'bold', 'marginBottom': '4px'}),
            html.Ul([html.Li(r, style={'fontSize': '11px'}) for r in results[:20]]),
            html.P(f"... and {len(results) - 20} more" if len(results) > 20 else "",
                   style={'fontSize': '11px', 'color': '#999'}),
        ])

    # ── Update standards table when model selection changes ───────────

    @app.callback(
        Output('cal-standards-table', 'children'),
        Input('cal-active-model', 'value'),
        prevent_initial_call=True,
    )
    def update_standards_display(model_id):
        if not model_id:
            return html.P("Select or create a model", style={'color': '#999', 'fontSize': '12px'})
        return _standards_table(model_id)
