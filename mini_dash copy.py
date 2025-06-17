# mini_dash.py  –  standalone Dash HPLC viewer
# Needs: dash>=2.15, pandas, numpy, scipy, plotly

import dash
from dash import html, dcc, dash_table, Input, Output, State
import plotly.graph_objs as go
import pandas as pd
import numpy as np
from scipy.signal import find_peaks
from scipy.integrate import trapezoid

# ---------- helpers ---------------------------------------------------------
def detect_peaks(df, height_pc, min_dist_pts):
    """Auto-detect peaks above percentile threshold."""
    y = df["Intensity (mAU)"].values
    peaks, _ = find_peaks(
        y,
        height=np.percentile(y, height_pc),
        distance=min_dist_pts,
    )
    res = []
    for no, idx in enumerate(peaks, 1):
        rt = df.at[idx, "Time (min)"]
        ht = y[idx]
        # crude left/right = first returns to ~baseline (<= 0) either side
        l_idx = idx - np.argmax(y[:idx][::-1] <= 0) if (y[:idx] <= 0).any() else max(0, idx-2)
        r_idx = idx + np.argmax(y[idx:] <= 0)        if (y[idx:] <= 0).any() else min(len(y)-1, idx+2)
        area = trapezoid(y[l_idx:r_idx+1], df["Time (min)"][l_idx:r_idx+1])
        res.append(
            dict(No=no, RT=f"{rt:.2f}", Height=f"{ht:.2f}", Area=f"{area:.2f}",
                 start=l_idx, end=r_idx)
        )
    return res


def fill_poly(df, start, end, color):
    """Return a Plotly filled-area trace for df[start:end] → baseline."""
    x = df["Time (min)"].values[start:end+1]
    y = df["Intensity (mAU)"].values[start:end+1]
    return go.Scatter(
        x=np.r_[x, x[-1], x[0]],
        y=np.r_[y, 0, 0],
        fill="toself",
        fillcolor=color,
        line=dict(width=0),
        hoverinfo="skip",
        showlegend=False,
    )


def manual_area(df, t1, t2, baseline="zero"):
    """Integrate between t1-t2 under chosen baseline."""
    if t2 < t1:
        t1, t2 = t2, t1
    # nearest indices
    start = np.abs(df["Time (min)"]-t1).idxmin()
    end   = np.abs(df["Time (min)"]-t2).idxmin()
    y = df["Intensity (mAU)"].values[start:end+1].copy()

    if baseline == "valley":
        base = y.min()
        y = y - base
    elif baseline == "tangent":
        # linear interp between endpoints
        x_seg = df["Time (min)"].values[start:end+1]
        y -= np.interp(x_seg, [x_seg[0], x_seg[-1]], [y[0], y[-1]])
        y = np.maximum(y, 0)

    area = trapezoid(y, df["Time (min)"][start:end+1])
    return start, end, area

# ---------- Dash app --------------------------------------------------------
app = dash.Dash(__name__)
app.title = "Mini HPLC viewer"

app.layout = html.Div([
    html.H3("Mini HPLC peak-fill viewer"),
    dcc.Upload(id="uploader", children=html.Button("Upload CSV")),
    html.Div(style={"margin": "8px 0"}),

    # detection controls -----------------------------------------------------
    html.Div([
        "Height percentile:",
        html.Div(
            dcc.Slider(50, 99, 1, value=90, id="height", tooltip={"placement": "bottom"}),
            style={"width": 200, "display": "inline-block", "margin": "0 12px"},
        ),
        "Min. peak distance (pts):",
        dcc.Input(30, type="number", id="mindist", style={"width": 80, "margin": "0 12px"}),
        html.Button("Detect peaks", id="detect"),
        html.Button("Clear",   id="clear", style={"margin-left": 6}),
    ]),

    # manual integration controls -------------------------------------------
    html.Div([
        "Drag-select region:",
        html.Div(
            dcc.RangeSlider(
                id="range",
                min=0, max=1, value=[0, 1],
                allowCross=False,
                tooltip={"placement": "bottom", "always_visible": True},
                disabled=True,
            ),
            style={"width": 300, "display": "inline-block", "margin": "0 12px"},
        ),
        "Baseline:",
        dcc.Dropdown(
            ["zero", "tangent", "valley"], "zero",
            id="baseline", clearable=False,
            style={"width": 120, "display": "inline-block"},
        ),
    ], style={"margin": "12px 0"}),

    dcc.Graph(id="plot", style={"height": 450}),
    dash_table.DataTable(
        id="table",
        columns=[dict(id=i, name=i) for i in ["No", "RT", "Height", "Area"]],
        style_cell={"textAlign": "center"},
        page_size=12,
    ),

    # hidden stores ----------------------------------------------------------
    dcc.Store(id="raw"),     # chromatogram
    dcc.Store(id="peaks"),   # list of dicts
])

# --------------------- CALLBACKS -------------------------------------------

# Upload → raw data + enable slider
@app.callback(
    Output("raw",      "data"),
    Output("range",    "min"),
    Output("range",    "max"),
    Output("range",    "value"),
    Output("range",    "disabled"),
    Input("uploader",  "contents"),
    State("uploader",  "filename"),
    prevent_initial_call=True,
)
def load_csv(content, fname):
    if not content or not fname.endswith(".csv"):
        return dash.no_update
    df = pd.read_csv(fname)
    if {"Time (min)", "Intensity (mAU)"} <= set(df.columns):
        xmin, xmax = df["Time (min)"].iloc[[0, -1]]
        return (
            df.to_json(date_format="iso"),
            xmin, xmax, [xmin, xmax], False
        )
    # wrong format
    return dash.no_update


# Detect button → peak list
@app.callback(
    Output("peaks", "data"),
    Input("detect", "n_clicks"),
    State("raw", "data"),
    State("height", "value"),
    State("mindist", "value"),
    prevent_initial_call=True,
)
def run_detection(n_clicks, raw_json, height_pc, min_dist_pts):
    if not n_clicks or not raw_json:
        return dash.no_update
    df = pd.read_json(raw_json)
    return detect_peaks(df, height_pc, int(min_dist_pts))


# Clear button → reset peak list & range slider selection
@app.callback(
    Output("peaks",  "clear_data"),
    Output("range",  "value", allow_duplicate=True),
    Input("clear",   "n_clicks"),
    State("range",   "min"),
    State("range",   "max"),
    prevent_initial_call=True,
)
def clear_everything(_, rmin, rmax):
    return True, [rmin, rmax]     # wipe peaks, reset selection


# Main figure + table
@app.callback(
    Output("plot",  "figure"),
    Output("table", "data"),
    Input("raw",      "data"),
    Input("peaks",    "data"),
    Input("range",    "value"),
    Input("baseline", "value"),
)
def update_plot(raw_json, peaks, rng, baseline):
    # empty fig until CSV loaded
    if not raw_json:
        return go.Figure(), []
    df = pd.read_json(raw_json)
    fig = go.Figure(
        layout=go.Layout(
            template="simple_white",
            xaxis_title="Time (min)",
            yaxis_title="Intensity (mAU)",
            margin=dict(l=40, r=20, t=20, b=40),
        )
    )
    # chromatogram line
    fig.add_scatter(
        x=df["Time (min)"],
        y=df["Intensity (mAU)"],
        mode="lines",
        name="Chromatogram",
    )

    rows = []

    # auto peaks ------------------------------------------------------------
    if peaks:
        for p in peaks:
            fig.add_trace(fill_poly(df, p["start"], p["end"], "rgba(255,165,0,0.3)"))
            fig.add_scatter(
                x=[float(p["RT"])],
                y=[float(p["Height"])],
                mode="markers",
                marker=dict(color="red", size=7),
                showlegend=False,
            )
            rows.append({k: p[k] for k in ["No", "RT", "Height", "Area"]})

    # manual region ---------------------------------------------------------
    if rng and rng[0] != rng[1]:
        start, end, area = manual_area(df, rng[0], rng[1], baseline)
        fig.add_trace(fill_poly(df, start, end, "rgba(50,150,255,0.25)"))
        rows.append(dict(No="M", RT=f"{(rng[0]+rng[1])/2:.2f}",
                         Height="-", Area=f"{area:.2f}"))

    return fig, rows


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
