# mini_dash.py  ── click–drag baseline integration
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import pandas as pd, numpy as np
from scipy.integrate import trapezoid

# ---------------------------------------------------------------------------
def load_demo_csv():
    # generates a quick synthetic chromatogram (replace with real CSV load)
    t = np.linspace(0, 10, 6_000)
    noise = np.random.normal(0, .4, t.size)
    peak1 = 500*np.exp(-((t-4.8)/0.035)**2)
    peak2 = 250*np.exp(-((t-7.3)/0.05 )**2)
    y = peak1 + peak2 + noise
    return pd.DataFrame({"Time (min)": t, "Intensity (mAU)": y})

DF = load_demo_csv()           # global demo data; keep it simple
# ---------------------------------------------------------------------------
# ── mini_dash.py – overwrite the whole helper with this version ──────────
def baseline_area(df, p1, p2):
    """
    Integrate ONLY the part of the chromatogram that sits above the
    user-drawn baseline.  The baseline is the straight line through the
    two click-points p1, p2.  A valid integration is returned **only if**

    • the trace crosses that baseline twice (left & right intersection)  
    • the region between the two crossings contains at least one
      positive point (signal > baseline)

    Otherwise we return None → the main callback shows nothing.
    """
    # sort clicks left-to-right
    (x1, y1), (x2, y2) = sorted([p1, p2])          # tuples (x, y)

    # chromatogram segment inside x-window
    seg = df[(df["Time (min)"] >= x1) & (df["Time (min)"] <= x2)]
    if seg.empty or x1 == x2:
        return None

    x = seg["Time (min)"].to_numpy()
    y = seg["Intensity (mAU)"].to_numpy()
    y_base = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    diff = y - y_base                                     # signal over baseline

    # crossing points where trace meets baseline (sign changes)
    sign = np.sign(diff)
    crossings = np.where(np.diff(sign))[0]                # indices before change
    if crossings.size < 2:
        return None                                       # 0-or-1 crossing → ignore

    # first & last crossing give the positive lobe
    i0 = crossings[0] + 1 if diff[crossings[0]+1] > 0 else crossings[0]
    i1 = crossings[-1] if diff[crossings[-1]] > 0 else crossings[-1]-1

    if i0 >= i1:
        return None                                       # nothing positive

    # final positive slice
    xs, ys, yb = x[i0:i1+1], y[i0:i1+1], y_base[i0:i1+1]
    area = trapezoid(ys - yb, xs)
    if area <= 0:
        return None                                       # should never happen but guard

    # apex for red marker
    apex_idx = np.argmax(ys - yb)
    apex_x, apex_y = xs[apex_idx], ys[apex_idx]

    # polygon for fill (trace down to baseline, back to start)
    poly_x = np.concatenate([xs, xs[::-1]])
    poly_y = np.concatenate([ys, yb[::-1]])

    return dict(
        area   = area,
        height = ys.max(),
        apex_x = apex_x,
        apex_y = apex_y,
        poly_x = poly_x,
        poly_y = poly_y,
    )
# ─────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
app = dash.Dash(__name__)
app.layout = html.Div([
    html.H4("Click-drag baseline → integrates until crossings"),
    dcc.Graph(id="plot", config={"modeBarButtonsToAdd":["drawline"]},
              style={"height":450}),
    dash_table.DataTable(id="info",
        columns=[{"name":c,"id":c} for c in ["Height","Area"]],
        style_cell={"textAlign":"center"}, data=[]),
    dcc.Store(id="line"),                      # (x,y) of 2 clicks
])

# capture the 2-point free-draw line
@app.callback(Output("line","data"),
              Input("plot","relayoutData"),
              State("line","data"))
def store_line(relayout, stored):
    if not relayout: return stored
    if "shapes" in relayout:                  # new draw action
        shp = relayout["shapes"][-1]          # last drawn
        return [(shp["x0"], shp["y0"]), (shp["x1"], shp["y1"])]
    return stored

# update plot & table --------------------------------------------------------
@app.callback(Output("plot","figure"), Output("info","data"),
              Input("line","data"))
def refresh(line):
    fig = go.Figure(layout=go.Layout(template="simple_white",
                                     xaxis_title="Time (min)",
                                     yaxis_title="Intensity (mAU)",
                                     dragmode="drawline"))
    # chromatogram
    fig.add_scatter(x=DF["Time (min)"], y=DF["Intensity (mAU)"],
                    mode="lines", name="Chromatogram")
    if not line or len(line) != 2:
        return fig, []                       # nothing drawn yet
    res = baseline_area(DF, *line)
    if not res:
        return fig, []                       # impossible baseline
    # shade
    fig.add_trace(go.Scatter(x=res["poly_x"], y=res["poly_y"], fill="toself",
                             fillcolor="rgba(0,100,255,.3)",
                             line=dict(width=0), hoverinfo="skip",
                             name="Integrated"))
    # mark apex
    fig.add_scatter(x=[res["apex_x"]], y=[res["apex_y"]],
                    mode="markers", marker=dict(color="red", size=7),
                    showlegend=False)
    return fig, [dict(Height=f"{res['height']:.2f}",
                      Area=f"{res['area']:.2f}")]

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
