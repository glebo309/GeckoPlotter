import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import pandas as pd
import numpy as np
from scipy.integrate import trapezoid
from scipy.interpolate import interp1d


def _get_chrom_data(data_manager, selected_layer):
    if not selected_layer:
        return None
    filename = selected_layer.split('|')[0]
    file_data = data_manager.get_file_data(filename)
    if not file_data:
        return None
    df = file_data.get('data')
    if df is None or df.empty:
        return None
    time_col = 'Time (min)'
    if time_col not in df.columns:
        return None
    intensity_cols = [c for c in df.columns if c != time_col]
    if not intensity_cols:
        return None
    intensity_col = intensity_cols[0]
    if intensity_col != 'Intensity (mAU)':
        df = df.rename(columns={intensity_col: 'Intensity (mAU)'})
    return df[[time_col, 'Intensity (mAU)']]


def y_curve(df, x):
    interp = interp1d(df['Time (min)'], df['Intensity (mAU)'], bounds_error=False, fill_value=0)
    return max(0, float(interp(x)))


def baseline_area(df, p1, p2):
    (x1, y1), (x2, y2) = sorted([p1, p2])
    seg = df[(df['Time (min)'] >= x1) & (df['Time (min)'] <= x2)]
    if seg.empty or x1 == x2:
        return None
    x = seg['Time (min)'].to_numpy()
    y = seg['Intensity (mAU)'].to_numpy()
    yb = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    d = y - yb
    idx = np.where(np.diff(np.sign(d)))[0]
    if idx.size < 2:
        return None
    i0 = idx[0] + 1 if d[idx[0] + 1] > 0 else idx[0]
    i1 = idx[-1] if d[idx[-1]] > 0 else idx[-1] - 1
    if i0 >= i1:
        return None
    xs, ys, ybs = x[i0:i1 + 1], y[i0:i1 + 1], yb[i0:i1 + 1]
    area = trapezoid(ys - ybs, xs)
    if area <= 0:
        return None
    return dict(
        area=area,
        height=(ys - ybs).max(),
        apex_x=xs[np.argmax(ys - ybs)],
        poly_x=np.concatenate([xs, xs[::-1]]),
        poly_y=np.concatenate([ys, ybs[::-1]]),
    )


def area_with_constraints(df, p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    if y1 >= 0 and y2 >= 0:
        q1, q2 = p1, p2
    else:
        q1 = (x1, max(0, min(y_curve(df, x1), y1)) if y1 >= 0 else 0)
        q2 = (x2, max(0, min(y_curve(df, x2), y2)) if y2 >= 0 else 0)
    res = baseline_area(df, q1, q2)
    return res, q1, q2


def exact_crossings(p1, p2, df):
    (x1, y1), (x2, y2) = p1, p2
    seg = df[(df['Time (min)'] >= min(x1, x2)) & (df['Time (min)'] <= max(x1, x2))]
    if seg.empty:
        return None, None
    x = seg['Time (min)'].to_numpy()
    y = seg['Intensity (mAU)'].to_numpy()
    yb = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    d = y - yb
    idx = np.where(np.diff(np.sign(d)))[0]
    if idx.size < 2:
        return None, None

    def interp(i):
        xa, xb = x[i], x[i + 1]
        da, db = d[i], d[i + 1]
        t = -da / (db - da) if db != da else 0
        xi = xa + t * (xb - xa)
        return xi, y_curve(df, xi)

    return interp(idx[0]), interp(idx[-1])


def create_baseline_integration_controls():
    return html.Div([
        html.H4("Multi-Peak Chromatogram Integration (p/q baselines)"),
        html.Div([
            html.Button("🖊️ Draw", id="draw", n_clicks=0, style={"margin": "5px"}),
            html.Button("✏️ Edit", id="edit", n_clicks=0, style={"margin": "5px"}),
            html.Button("🔍 Nav", id="nav", n_clicks=0, style={"margin": "5px"}),
            html.Span(id="mode-ind", style={"marginLeft": "20px", "fontWeight": "bold", "color": "blue"}),
            html.Div([
                dcc.Checklist(
                    id="easy-integration",
                    options=[{"label": " Easy Integration (baseline to y=0)", "value": "easy"}],
                    value=[],
                    style={"marginLeft": "20px", "display": "inline-block"}
                )
            ], style={"display": "inline-block"})
        ]),
        dcc.Graph(id="integration-plot", config={"displayModeBar": True, "displaylogo": False}, style={"height": 500}),
        dash_table.DataTable(
            id="integration-table",
            columns=[
                {"name": "Peak #", "id": "idx"},
                {"name": "Retention Time", "id": "rt"},
                {"name": "Height", "id": "h"},
                {"name": "Area", "id": "a"},
            ],
            style_cell={"textAlign": "center"},
            data=[],
        ),
        dcc.Store(id="mode", data="draw"),
        dcc.Store(id="line"),
        dcc.Store(id="stored-peaks", data=[]),
        dcc.Store(id="selected-idx"),
        dcc.Store(id="p-visible", data=False),
        dcc.Store(id="clear-shapes", data=0),
    ])


def register_baseline_integration_callbacks(app, data_manager):
    @app.callback([
        Output("mode", "data"),
        Output("mode-ind", "children"),
        Output("p-visible", "data", allow_duplicate=True),
        Output("selected-idx", "data", allow_duplicate=True)
    ],
        [Input("draw", "n_clicks"), Input("edit", "n_clicks"), Input("nav", "n_clicks")],
        State("mode", "data"),
        prevent_initial_call=True)
    def set_mode(n1, n2, n3, cur):
        bid = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
        new = {"draw": "draw", "edit": "edit", "nav": "navigate"}[bid]
        return new, f"Mode: {new}", False, None

    @app.callback([
        Output("line", "data"),
        Output("clear-shapes", "data")
    ],
        Input("integration-plot", "relayoutData"),
        [State("line", "data"), State("mode", "data"), State("clear-shapes", "data"), State("easy-integration", "value"), State("selected-layer", "data")])
    def store_line(relayout, line, mode, clear_counter, easy_mode, selected_layer):
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            return line, clear_counter
        if not relayout:
            return line, clear_counter
        if mode == "draw" and "shapes" in relayout and relayout["shapes"]:
            s = relayout["shapes"][-1]
            pts = [(s["x0"], s["y0"]), (s["x1"], s["y1"])]
            if easy_mode and "easy" in easy_mode:
                pts = [(pts[0][0], 0), (pts[1][0], 0)]
            res, *_ = area_with_constraints(df, *pts)
            if res is None:
                return [], clear_counter + 1
            return pts, clear_counter
        if mode == "edit" and line:
            (x0, y0), (x1, y1) = line
            for k, v in relayout.items():
                if k.startswith("shapes[0]."):
                    if k.endswith(".x0"):
                        x0 = v
                    elif k.endswith(".y0"):
                        y0 = v
                    elif k.endswith(".x1"):
                        x1 = v
                    elif k.endswith(".y1"):
                        y1 = v
            if easy_mode and "easy" in easy_mode:
                y0, y1 = 0, 0
            return [(x0, y0), (x1, y1)], clear_counter
        return line, clear_counter

    @app.callback(
        Output("stored-peaks", "data", allow_duplicate=True),
        [Input("line", "data"), Input("mode", "data")],
        [State("stored-peaks", "data"), State("easy-integration", "value"), State("selected-layer", "data")],
        prevent_initial_call=True)
    def add_peak(line, mode, peaks, easy_mode, selected_layer):
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            raise dash.exceptions.PreventUpdate
        if mode != "draw" or not line or len(line) != 2:
            raise dash.exceptions.PreventUpdate
        if easy_mode and "easy" in easy_mode:
            line = [(line[0][0], 0), (line[1][0], 0)]
        res, q1, q2 = area_with_constraints(df, *line)
        if not res:
            raise dash.exceptions.PreventUpdate
        peaks = peaks or []
        found = False
        for i, p in enumerate(peaks):
            if abs(p["apex_x"] - res["apex_x"]) < 0.05:
                peaks[i] = dict(p_line=line, q1=q1, q2=q2, **res)
                found = True
                break
        if not found:
            peaks.append(dict(p_line=line, q1=q1, q2=q2, **res))
        return peaks

    @app.callback([
        Output("selected-idx", "data"),
        Output("p-visible", "data")
    ],
        Input("integration-plot", "clickData"),
        [State("mode", "data"), State("stored-peaks", "data")],
        prevent_initial_call=True)
    def select_peak(click, mode, peaks):
        if mode != "edit" or not click or not peaks:
            raise dash.exceptions.PreventUpdate
        x_click = click["points"][0]["x"]
        idx = min(range(len(peaks)), key=lambda i: abs(peaks[i]["apex_x"] - x_click))
        return idx, True

    @app.callback(
        Output("stored-peaks", "data", allow_duplicate=True),
        [Input("integration-plot", "relayoutData"), Input("line", "data")],
        [State("mode", "data"), State("selected-idx", "data"), State("stored-peaks", "data"), State("easy-integration", "value"), State("selected-layer", "data")],
        prevent_initial_call=True)
    def update_peak(relayout, line, mode, idx, peaks, easy_mode, selected_layer):
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            raise dash.exceptions.PreventUpdate
        if mode != "edit" or idx is None or not line or len(line) != 2:
            raise dash.exceptions.PreventUpdate
        if easy_mode and "easy" in easy_mode:
            line = [(line[0][0], 0), (line[1][0], 0)]
        res, q1, q2 = area_with_constraints(df, *line)
        if not res:
            raise dash.exceptions.PreventUpdate
        peaks[idx] = dict(p_line=line, q1=q1, q2=q2, **res)
        return peaks

    @app.callback(
        Output("integration-plot", "figure"),
        [Input("stored-peaks", "data"), Input("selected-idx", "data"), Input("p-visible", "data"), Input("mode", "data"), Input("clear-shapes", "data"), Input("selected-layer", "data")])
    def refresh(peaks, sel_idx, p_show, mode, clear_shapes, selected_layer):
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            return go.Figure()
        drag = {"draw": "drawline", "edit": "select", "navigate": "pan"}[mode]
        fig = go.Figure(layout=go.Layout(template="simple_white", dragmode=drag, xaxis_title="Time (min)", yaxis_title="Intensity (mAU)", shapes=[]))
        fig.add_scatter(x=df["Time (min)"], y=df["Intensity (mAU)"], mode="lines", name="Chromatogram")
        if not peaks:
            return fig
        peaks = peaks or []
        if sel_idx is not None and p_show:
            p = peaks[sel_idx]
            p0, p1 = p["p_line"]
            fig.add_shape(type="line", x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1], line=dict(color="#005F8C", width=3), editable=True, layer="above")
        for i, p in enumerate(peaks):
            res = p
            fig.add_scatter(x=res["poly_x"], y=res["poly_y"], fill="toself", fillcolor="rgba(0,150,200,0.30)", line=dict(width=0), hoverinfo="skip", showlegend=False)
            q1, q2 = res["q1"], res["q2"]
            if i == sel_idx and p_show:
                fig.add_scatter(x=[q1[0], q2[0]], y=[q1[1], q2[1]], mode="markers", marker=dict(size=5, symbol="circle", color="#005F8C"), showlegend=False)
                p0, p1 = res["p_line"]
                fig.add_scatter(x=[p0[0], p1[0]], y=[p0[1], p1[1]], mode="markers", marker=dict(size=10, symbol="circle-open", color="#005F8C"), showlegend=False)
                if q1 != p0 or q2 != p1:
                    fig.add_shape(type="line", x0=q1[0], y0=q1[1], x1=q2[0], y1=q2[1], line=dict(color="#005F8C", width=2, dash="dot"), editable=False, layer="above")
            else:
                left, right = exact_crossings(q1, q2, df)
                if left and right:
                    fig.add_scatter(x=[left[0], right[0]], y=[left[1], right[1]], mode="markers", marker=dict(size=5, symbol="circle", color="#002B4A"), showlegend=False)
        return fig

    @app.callback(
        Output("integration-table", "data"),
        Input("stored-peaks", "data")
    )
    def update_table(peaks):
        if not peaks:
            return []
        rows = []
        for i, p in enumerate(peaks, start=1):
            rows.append({"idx": i, "rt": f"{p['apex_x']:.2f}", "h": f"{p['height']:.2f}", "a": f"{p['area']:.1f}"})
        return rows
