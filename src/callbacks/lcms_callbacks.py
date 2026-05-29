"""LC-MS viewer callbacks.

Wires the MS Viewer bottom-panel tab:
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

    lcms_svc = data_manager.lcms_service

    # ------------------------------------------------------------------
    # 1. Click on main-plot → update mass spectrum figure
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ms-spectrum-graph', 'figure'),
         Output('ms-spectrum-info', 'children')],
        Input('main-plot', 'clickData'),
        [State('active-file', 'data'),
         State('active-tab', 'data')],
        prevent_initial_call=True,
    )
    def update_mass_spectrum(click_data, active_file, active_tab):
        if active_tab != 'ms-viewer':
            return dash.no_update, dash.no_update

        if not click_data or not active_file:
            return _empty_spectrum("Click on the chromatogram to view a mass spectrum"), ""

        file_data = data_manager.loaded_data.get(active_file)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return _empty_spectrum("No mass spectral data for this file"), ""

        point = click_data['points'][0]
        rt = point.get('x', 0)

        try:
            mz, intensity = lcms_svc.get_mass_spectrum_at_time(file_data, rt)
        except (ValueError, IndexError) as e:
            return _empty_spectrum(str(e)), ""

        # Normalise to base peak
        max_int = intensity.max() if intensity.size else 1.0
        rel_intensity = intensity / max_int * 100 if max_int > 0 else intensity

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=mz, y=rel_intensity,
            width=0.4,
            marker_color='steelblue',
            hovertemplate='m/z: %{x:.1f}<br>Intensity: %{customdata:.0f}<br>Rel: %{y:.1f}%<extra></extra>',
            customdata=intensity,
        ))
        fig.update_layout(
            template='plotly_white',
            margin=dict(l=50, r=20, t=30, b=40),
            xaxis_title='m/z',
            yaxis_title='Relative Intensity (%)',
            hovermode='x unified',
            bargap=0,
            uirevision='ms-spectrum',
        )

        # Top 5 peaks annotation
        if mz.size > 0:
            top_n = min(5, mz.size)
            top_idx = np.argsort(intensity)[-top_n:][::-1]
            info_parts = [f"RT {rt:.2f} min — Top peaks:"]
            for i in top_idx:
                info_parts.append(f"  m/z {mz[i]:.1f} ({rel_intensity[i]:.0f}%)")
            info_text = "  |  ".join(info_parts[:1] + [", ".join(
                f"{mz[i]:.1f}" for i in top_idx
            )])
        else:
            info_text = f"RT {rt:.2f} min — no peaks"

        return fig, info_text

    # ------------------------------------------------------------------
    # 2. EIC extraction → overlay on main plot
    # ------------------------------------------------------------------
    @app.callback(
        Output('render-trigger', 'data', allow_duplicate=True),
        Input('eic-extract-btn', 'n_clicks'),
        [State('eic-mz-input', 'value'),
         State('eic-tolerance-input', 'value'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def extract_eic_trigger(n_clicks, mz_value, tolerance, active_file, current_trigger):
        if not n_clicks or not mz_value or not active_file:
            return dash.no_update

        file_data = data_manager.loaded_data.get(active_file)
        if not file_data or not lcms_svc.has_spectral_data(file_data):
            return dash.no_update

        tolerance = tolerance or 0.5

        try:
            eic_time, eic_intensity = lcms_svc.extract_eic(
                file_data, float(mz_value), float(tolerance)
            )
        except (ValueError, KeyError):
            return dash.no_update

        # Store EIC data on the file entry for the plot manager to pick up
        eic_list = file_data.setdefault('eic_overlays', [])
        eic_list.append({
            'mz': float(mz_value),
            'tolerance': float(tolerance),
            'time': eic_time,
            'intensity': eic_intensity,
        })

        return (current_trigger or 0) + 1

    @app.callback(
        Output('eic-active-list', 'children'),
        [Input('render-trigger', 'data')],
        [State('active-file', 'data')],
    )
    def update_eic_list(_, active_file):
        if not active_file:
            return []
        file_data = data_manager.loaded_data.get(active_file)
        if not file_data:
            return []
        eic_list = file_data.get('eic_overlays', [])
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

    @app.callback(
        Output('render-trigger', 'data', allow_duplicate=True),
        Input('eic-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_eic_overlays(n_clicks, active_file, current_trigger):
        if not n_clicks or not active_file:
            return dash.no_update
        file_data = data_manager.loaded_data.get(active_file)
        if file_data:
            file_data.pop('eic_overlays', None)
        return (current_trigger or 0) + 1


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
