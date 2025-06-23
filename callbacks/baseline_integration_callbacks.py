# callbacks/baseline_integration_callbacks.py

import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import dash
from scipy import interpolate
from scipy.integrate import trapezoid
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash import callback_context

# Global reference to data manager
data_manager = None

def _get_chrom_data(data_manager, selected_layer):
    """Get chromatogram data for the selected layer - improved version."""
    if not selected_layer:
        print("❌ [GET_CHROM_DATA] No selected layer")
        return None
        
    filename = selected_layer.split('|')[0]
    print(f"🔍 [GET_CHROM_DATA] Getting data for: {filename}")
    
    file_data = data_manager.get_file_data(filename)
    if not file_data:
        print("❌ [GET_CHROM_DATA] No file data found")
        return None
    
    print(f"🔍 [GET_CHROM_DATA] File type: {file_data.get('type')}")
    
    # Try different data locations based on file type
    df = None
    
    # Try 'data' first (most common)
    if 'data' in file_data:
        df = file_data['data']
        print(f"🔍 [GET_CHROM_DATA] Found data in 'data': {type(df)}")
    
    # Try 'chromatogram_data' 
    elif 'chromatogram_data' in file_data:
        df = file_data['chromatogram_data']
        print(f"🔍 [GET_CHROM_DATA] Found data in 'chromatogram_data': {type(df)}")
    
    # For bundle data, try to find UV component
    elif 'bundle_data' in file_data:
        bundle_data = file_data['bundle_data']
        print(f"🔍 [GET_CHROM_DATA] Bundle data keys: {list(bundle_data.keys())}")
        
        # Look for UV components first
        for comp_type in ['vwd_a', 'vwd_b']:
            if comp_type in bundle_data and 'data' in bundle_data[comp_type]:
                df = bundle_data[comp_type]['data']
                print(f"🔍 [GET_CHROM_DATA] Found data in bundle_data.{comp_type}.data")
                break
    
    if df is None or df.empty:
        print("❌ [GET_CHROM_DATA] No valid dataframe found")
        return None

    print(f"🔍 [GET_CHROM_DATA] Dataframe shape: {df.shape}")
    print(f"🔍 [GET_CHROM_DATA] Columns: {list(df.columns)}")

    # Find time column (flexible matching)
    time_col = None
    for col in df.columns:
        if 'time' in col.lower():
            time_col = col
            break
    
    if time_col is None:
        print("❌ [GET_CHROM_DATA] No time column found")
        return None
    
    print(f"🔍 [GET_CHROM_DATA] Using time column: '{time_col}'")
    
    # Find intensity column (exclude time column)
    intensity_cols = [c for c in df.columns if c != time_col]
    if not intensity_cols:
        print("❌ [GET_CHROM_DATA] No intensity columns found")
        return None

    intensity_col = intensity_cols[0]  # Use first non-time column
    print(f"🔍 [GET_CHROM_DATA] Using intensity column: '{intensity_col}'")

    # Standardize column names for consistency with mini_dash.py
    result_df = df[[time_col, intensity_col]].copy()
    result_df = result_df.rename(columns={
        time_col: 'Time (min)', 
        intensity_col: 'Value (mAU)'
    })
    
    print(f"✅ [GET_CHROM_DATA] Success! Returning {result_df.shape} dataframe")
    print(f"🔍 [GET_CHROM_DATA] Time range: {result_df['Time (min)'].min():.3f} to {result_df['Time (min)'].max():.3f}")
    print(f"🔍 [GET_CHROM_DATA] Intensity range: {result_df['Value (mAU)'].min():.1f} to {result_df['Value (mAU)'].max():.1f}")
    
    return result_df

def y_curve(df, x):
    """Get chromatogram intensity at time x - EXACT mini_dash.py logic"""
    interp = interpolate.interp1d(df['Time (min)'], df['Value (mAU)'], bounds_error=False, fill_value=0)
    return max(0, float(interp(x)))

def baseline_area(df, p1, p2):
    """Calculate baseline corrected peak area - EXACT mini_dash.py with single sign change fallback"""
    (x1,y1),(x2,y2) = sorted([p1,p2])
    seg = df[(df["Time (min)"]>=x1)&(df["Time (min)"]<=x2)]
    if seg.empty or x1==x2: 
        print(f"[BASELINE_AREA DEBUG] Empty segment or zero width")
        return None
    
    x = seg["Time (min)"].to_numpy()
    y = seg["Value (mAU)"].to_numpy()
    yb = y1 + (y2-y1)*(x-x1)/(x2-x1)
    d  = y - yb
    
    print(f"[BASELINE_AREA DEBUG] Input: p1={p1}, p2={p2}")
    print(f"[BASELINE_AREA DEBUG] Sorted: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
    print(f"[BASELINE_AREA DEBUG] Segment size: {len(seg)}")
    print(f"[BASELINE_AREA DEBUG] y range: {y.min():.3f} to {y.max():.3f}")
    print(f"[BASELINE_AREA DEBUG] yb range: {yb.min():.3f} to {yb.max():.3f}")
    print(f"[BASELINE_AREA DEBUG] d range: {d.min():.3f} to {d.max():.3f}")
    
    idx = np.where(np.diff(np.sign(d)))[0]
    print(f"[BASELINE_AREA DEBUG] Sign changes found: {idx.size}")
    
    # Original logic: require at least 2 sign changes
    if idx.size >= 2:
        i0 = idx[0]+1 if d[idx[0]+1]>0 else idx[0]
        i1 = idx[-1]   if d[idx[-1]]  >0 else idx[-1]-1
        if i0>=i1: 
            print(f"[BASELINE_AREA DEBUG] ❌ Invalid peak boundaries: i0={i0}, i1={i1}")
            return None
        xs,ys,ybs = x[i0:i1+1], y[i0:i1+1], yb[i0:i1+1]
        print(f"[BASELINE_AREA DEBUG] ✅ Using sign change boundaries: i0={i0}, i1={i1}")
    
    # Fallback for single sign change: use segment boundaries if area is positive
    elif idx.size == 1:
        # Check if the total area under the curve is positive
        total_area = trapezoid(y - yb, x)
        if total_area > 0:
            # Use the entire segment as the peak
            xs, ys, ybs = x, y, yb
            print(f"[BASELINE_AREA DEBUG] ✅ Single sign change fallback: using entire segment, total_area={total_area:.2f}")
        else:
            print(f"[BASELINE_AREA DEBUG] ❌ Single sign change but negative total area: {total_area:.2f}")
            return None
    
    # No sign changes - fallback for when chromatogram is always above baseline
    else:
        # Check if the total area under the curve is positive
        total_area = trapezoid(y - yb, x)
        if total_area > 0:
            # Use the entire segment as the peak
            xs, ys, ybs = x, y, yb
            print(f"[BASELINE_AREA DEBUG] ✅ Zero sign change fallback: using entire segment, total_area={total_area:.2f}")
        else:
            print(f"[BASELINE_AREA DEBUG] ❌ Zero sign changes and negative/zero total area: {total_area:.2f}")
            return None
    
    area = trapezoid(ys - ybs, xs)
    if area <= 0:
        print(f"[BASELINE_AREA DEBUG] ❌ Non-positive area: {area:.3f}")
        return None
    
    print(f"[BASELINE_AREA DEBUG] ✅ Success! Area: {area:.2f}")
    # Clamp baseline so it never exceeds the curve
    baseline_clamped = np.minimum(ybs, ys)
    return dict(
        area   = area,
        height = (ys - ybs).max(),
        apex_x = xs[np.argmax(ys - ybs)],
        poly_x = np.concatenate([xs, xs[::-1]]),
        poly_y = np.concatenate([ys, baseline_clamped[::-1]]),
    )

def area_with_constraints(df, p1, p2):
    """Apply q-point constraints - EXACT mini_dash.py logic"""
    x1,y1=p1; x2,y2=p2
    print(f"[Q-POINT DEBUG] Input p1={p1}, p2={p2}")
    
    if y1>=0 and y2>=0:
        q1,q2 = p1,p2
        print(f"[Q-POINT DEBUG] Both y>=0, using p-points as q-points")
    else:
        # EXACT mini_dash.py logic for q-point calculation
        q1=(x1, max(0,min(y_curve(df, x1),y1)) if y1>=0 else 0)
        q2=(x2, max(0,min(y_curve(df, x2),y2)) if y2>=0 else 0)
        print(f"[Q-POINT DEBUG] Negative y detected, calculated q1={q1}, q2={q2}")
        
    res = baseline_area(df,q1,q2)
    print(f"[Q-POINT DEBUG] baseline_area result: {res is not None}")
    return res,q1,q2

def exact_crossings(p1, p2, df):
    """Find precise intersection points - exact copy from mini_dash.py"""
    (x1,y1),(x2,y2)=p1,p2
    seg=df[(df["Time (min)"]>=min(x1,x2))&(df["Time (min)"]<=max(x1,x2))]
    if seg.empty: return None,None
    x=seg["Time (min)"].to_numpy(); y=seg["Value (mAU)"].to_numpy()
    yb=y1+(y2-y1)*(x-x1)/(x2-x1); d=y-yb
    idx=np.where(np.diff(np.sign(d)))[0]
    if idx.size<2: return None,None
    def interp(i):
        xa,xb=x[i],x[i+1]; da,db=d[i],d[i+1]
        t=-da/(db-da) if db!=da else 0
        xi=xa+t*(xb-xa)
        return xi, y_curve(df, xi)  # ← PASS df HERE
    return interp(idx[0]), interp(idx[-1])

def debug_chromatogram_data(data_manager, selected_layer):
    """Debug function to check chromatogram data structure"""
    print(f"\n=== DEBUGGING CHROMATOGRAM DATA ===")
    print(f"Selected layer: {selected_layer}")
    
    if not selected_layer:
        print("❌ No selected layer")
        return
    
    filename = selected_layer.split('|')[0]
    print(f"Filename: {filename}")
    
    file_data = data_manager.get_file_data(filename)
    if not file_data:
        print("❌ No file data")
        return
    
    print(f"File type: {file_data.get('type')}")
    print(f"File data keys: {list(file_data.keys())}")
    
    # Check different possible data locations
    data_locations = ['data', 'chromatogram_data', 'bundle_data']
    for loc in data_locations:
        data = file_data.get(loc)
        if data is not None:
            print(f"✅ Found data in '{loc}': {type(data)}")
            if hasattr(data, 'shape'):
                print(f"   Shape: {data.shape}")
            if hasattr(data, 'columns'):
                print(f"   Columns: {list(data.columns)}")
                # Check for time and intensity columns
                time_cols = [col for col in data.columns if 'time' in col.lower()]
                intensity_cols = [col for col in data.columns if col not in time_cols]
                print(f"   Time columns: {time_cols}")
                print(f"   Intensity columns: {intensity_cols}")
                
                if time_cols and intensity_cols:
                    time_col = time_cols[0]
                    intensity_col = intensity_cols[0]
                    print(f"   Time range: {data[time_col].min():.3f} to {data[time_col].max():.3f}")
                    print(f"   Intensity range: {data[intensity_col].min():.1f} to {data[intensity_col].max():.1f}")
                    print(f"   Sample data points:")
                    print(data[[time_col, intensity_col]].head())
    
    print("=== END DEBUG ===\n")

# --- UI Generation ---

def create_baseline_integration_controls():
    """Creates the UI components for baseline integration tools - matches mini_dash.py"""
    return html.Div([
        html.Div([
            html.Button("🖊️ Draw", id="draw-baseline", n_clicks=0, className="btn-secondary"),
            html.Button("✏️ Edit", id="edit-baseline", n_clicks=0, className="btn-secondary"),
            html.Button("🔍 Nav", id="nav-baseline", n_clicks=0, className="btn-secondary"),
            html.Button("🗑️ Clear", id="clear-baseline", n_clicks=0, className="btn-secondary"),
            html.Span(id="mode-indicator", className="feedback-text", style={"marginLeft": "10px", "fontWeight": "bold", "color": "blue"})
        ], className="button-group"),
        html.Div([
            dcc.Checklist(id="easy-integration", 
                         options=[{"label": " Easy Integration (baseline to y=0)", "value": "easy"}], 
                         value=["easy"], 
                         style={"marginTop": "10px"})
        ]),
        html.Div(id="baseline-integration-table-container", style={"marginTop": "20px"})
    ])

# --- Callback Registration ---

def register_baseline_integration_callbacks(app, data_manager_instance):
    """Register all baseline integration callbacks - exact mini_dash.py logic"""
    global data_manager
    data_manager = data_manager_instance

    # Store the zoom state when the plot is zoomed
    @app.callback(
        Output("plot-zoom-state", "data"),
        [Input("uv-chromatogram-plot", "relayoutData")],
        [State("baseline-mode", "data")],
        prevent_initial_call=True
    )
    def store_zoom_state(relayout_data, mode):
        if not relayout_data:
            return dash.no_update
            
        # Only save zoom-related data (axis ranges)
        zoom_state = {}
        axis_keys = ["xaxis.range[0]", "xaxis.range[1]", "yaxis.range[0]", "yaxis.range[1]"]
        for key in axis_keys:
            if key in relayout_data:
                zoom_state[key] = relayout_data[key]
                
        # If we have a complete set of ranges, return it
        if all(key in zoom_state for key in axis_keys):
            print(f"[DEBUG] Storing zoom state: {zoom_state}")
            return zoom_state
        
        # If we have autorange events, clear the zoom state
        if "xaxis.autorange" in relayout_data or "yaxis.autorange" in relayout_data:
            return None
            
        return dash.no_update

    # Mode switch callback - exact copy from mini_dash.py
    @app.callback(
        [Output("baseline-mode", "data"),
         Output("mode-indicator", "children"),
         Output("p-line-visible", "data", allow_duplicate=True),
         Output("selected-peak-idx", "data", allow_duplicate=True)],
        [Input("draw-baseline", "n_clicks"),
     Input("edit-baseline", "n_clicks"), 
     Input("nav-baseline", "n_clicks"),
     Input("draw-peak", "n_clicks"),
     Input("edit-peak", "n_clicks"),
     Input("nav-peak", "n_clicks"),
     Input("clear-peak", "n_clicks")],
        State("baseline-mode", "data"),
        prevent_initial_call=True
    )
    def set_mode(n1, n2, n3, n4, n5, n6, n7, cur):
        ctx = callback_context
        if not ctx.triggered: return cur, f"Mode: {cur}", False, None
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        mode_map = {
            "draw-baseline": "draw",
            "edit-baseline": "edit",
            "nav-baseline": "navigate",
            "draw-peak": "draw",
            "edit-peak": "edit",
            "nav-peak": "zoom",
            "clear-peak": "draw"  # After clear, default to draw mode
        }
        mode = mode_map.get(button_id, cur)
        return mode, f"Mode: {mode}", False, None

    # Store line callback - EXACT REPLICA from mini_dash.py with debugging


    # Add peak by line drawing - EXACT REPLICA from mini_dash.py
    @app.callback(
        Output("stored-peaks", "data", allow_duplicate=True),
        [Input("p-line-store", "data"), Input("baseline-mode", "data")],
        [State("stored-peaks", "data"), State("easy-integration", "value"), 
         State("selected-layer", "data")],
        prevent_initial_call=True
    )
    def add_peak(line, mode, peaks, easy_mode, selected_layer):
        if mode != "draw" or not line or len(line) != 2:
            raise dash.exceptions.PreventUpdate
        
        print(f"🔍 [ADD_PEAK] Mode: {mode}, Line: {line}, Easy: {easy_mode}")
        print(f"🔍 [ADD_PEAK] Easy mode type: {type(easy_mode)}, Easy mode value: {easy_mode}")
        print(f"🔍 [ADD_PEAK] Easy mode check: {'easy' in easy_mode if easy_mode else 'easy_mode is falsy'}")
        
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            print("❌ [ADD_PEAK] No chromatogram data")
            raise dash.exceptions.PreventUpdate
        
        # Apply easy integration if enabled
        if easy_mode and "easy" in easy_mode:
            original_line = line.copy()
            line = [(line[0][0], 0), (line[1][0], 0)]
            print(f"🔍 [ADD_PEAK] Easy mode applied! Original: {original_line} → Easy: {line}")
        else:
            print(f"🔍 [ADD_PEAK] Easy mode NOT applied. Condition failed: easy_mode={easy_mode}")
        
        res, q1, q2 = area_with_constraints(df, *line)
        if not res: 
            print("❌ [ADD_PEAK] Invalid integration result")
            raise dash.exceptions.PreventUpdate

        peaks = peaks or []
        # overwrite if apex very close
        found = False
        for i, p in enumerate(peaks):
            if abs(p["apex_x"] - res["apex_x"]) < 0.05:
                peaks[i] = dict(p_line=line, q1=q1, q2=q2, **res)
                found = True
                print(f"✅ [ADD_PEAK] Updated existing peak {i}")
                break
        if not found:
            peaks.append(dict(p_line=line, q1=q1, q2=q2, **res))
            print(f"✅ [ADD_PEAK] Added new peak: area={res['area']:.2f}")
        return peaks

    # Select peak by click - EXACT REPLICA from mini_dash.py
    @app.callback(
        [Output("selected-peak-idx", "data"), Output("p-line-visible", "data")],
        Input("uv-chromatogram-plot", "clickData"),
        [State("baseline-mode", "data"), State("stored-peaks", "data")],
        prevent_initial_call=True
    )
    def select_peak(click, mode, peaks):
        if not click or not peaks:
            print(f"🔍 [SELECT_PEAK] No click data or no peaks available. Mode: {mode}, Peaks: {len(peaks) if peaks else 0}")
            raise dash.exceptions.PreventUpdate
        x_click = click["points"][0]["x"]
        # Only allow selection of editable peaks (those with 'p_line' or 'x' key)
        def is_editable_peak(peak):
            return ("p_line" in peak) or ("x" in peak)
        editable_idxs = [i for i, p in enumerate(peaks) if is_editable_peak(p)]
        if not editable_idxs:
            print("⚠️ [SELECT_PEAK] No editable peaks available.")
            raise dash.exceptions.PreventUpdate
        # Find closest editable peak
        idx = min(editable_idxs, key=lambda i: abs(peaks[i]["apex_x"] - x_click))
        print(f"🔍 [SELECT_PEAK] Selected editable peak {idx} at x={x_click:.3f} in mode: {mode}")
        return idx, True          # reveal its p-baseline

    @app.callback([Output("p-line-store", "data"), Output("clear-shapes-trigger", "data", allow_duplicate=True)],
                Input("uv-chromatogram-plot", "relayoutData"),
                [State("p-line-store", "data"), State("baseline-mode", "data"), State("clear-shapes-trigger", "data"),
                State("easy-integration", "value"), State("selected-layer", "data")],
                prevent_initial_call=True)
    def store_line(relayout, line, mode, clear_counter, easy_mode, selected_layer):
        if not relayout:
            return line, clear_counter

        # Draw mode: user finished drawing a new shape - EXACT mini_dash.py
        if mode == "draw" and "shapes" in relayout and relayout["shapes"]:
            s   = relayout["shapes"][-1]
            pts = [(s["x0"], s["y0"]), (s["x1"], s["y1"])]
            
            # If easy integration is on, force y-coordinates to 0 - EXACT mini_dash.py
            if easy_mode and "easy" in easy_mode:
                pts = [(pts[0][0], 0), (pts[1][0], 0)]

            # keep only if integration is valid - EXACT mini_dash.py
            df = _get_chrom_data(data_manager, selected_layer)
            if df is not None:
                res, *_ = area_with_constraints(df, *pts)
                if res is None:
                    return [], clear_counter + 1  # trigger refresh & increment counter
            return pts, clear_counter

        # Edit mode: drag of first shape - EXACT mini_dash.py
        if mode == "edit" and line:
            (x0, y0), (x1, y1) = line
            for k, v in relayout.items():
                if k.startswith("shapes[0]."):
                    if   k.endswith(".x0"): x0 = v
                    elif k.endswith(".y0"): y0 = v
                    elif k.endswith(".x1"): x1 = v
                    elif k.endswith(".y1"): y1 = v
            
            # If easy integration is on, force y-coordinates to 0 - EXACT mini_dash.py
            if easy_mode and "easy" in easy_mode:
                y0, y1 = 0, 0
                
            return [(x0, y0), (x1, y1)], clear_counter

        return line, clear_counter

    # update_peak callback - EXACT mini_dash.py logic:
    @app.callback(Output("stored-peaks","data", allow_duplicate=True),
                [Input("uv-chromatogram-plot","relayoutData"),
                Input("p-line-store","data")],
                [State("baseline-mode","data"),
                State("selected-peak-idx","data"),
                State("stored-peaks","data"),
                State("easy-integration","value"),
                State("selected-layer", "data")],
                prevent_initial_call=True)
    def update_peak(relayout, line, mode, idx, peaks, easy_mode, selected_layer):
        if mode!="edit" or idx is None or not line or len(line)!=2:
            raise dash.exceptions.PreventUpdate
        
        peaks = peaks or []
        # Prevent editing imported peaks (those without 'p_line' or 'x')
        if 0 <= idx < len(peaks):
            peak = peaks[idx]
            if not ("p_line" in peak or "x" in peak):
                print(f"⚠️ [UPDATE_PEAK] Attempted to edit imported peak at idx={idx}, skipping.")
                raise dash.exceptions.PreventUpdate
        
        # Apply easy integration if enabled - EXACT mini_dash.py
        if easy_mode and "easy" in easy_mode:
            line = [(line[0][0], 0), (line[1][0], 0)]
        
        df = _get_chrom_data(data_manager, selected_layer)
        if df is None:
            raise dash.exceptions.PreventUpdate
        
        res,q1,q2 = area_with_constraints(df,*line)
        if not res: raise dash.exceptions.PreventUpdate
        
        if 0 <= idx < len(peaks):
            peaks[idx] = dict(p_line=line,q1=q1,q2=q2,**res)
        return peaks

    # P-line visibility callback
    @app.callback(
        Output("p-line-visible", "data", allow_duplicate=True),
        Input("p-line-visible-checklist", "value"),
        prevent_initial_call=True
    )
    def update_p_line_visibility(value):
        return "show" in (value or [])

    # Clear baseline callback
    @app.callback(
        [Output("stored-peaks", "data", allow_duplicate=True),
         Output("clear-shapes-trigger", "data", allow_duplicate=True),
         Output("selected-peak-idx", "data", allow_duplicate=True),
         Output("p-line-store", "data", allow_duplicate=True)],
        Input("clear-baseline", "n_clicks"),
        State("clear-shapes-trigger", "data"),
        prevent_initial_call=True
    )
    def clear_baseline_data(n_clicks, current_counter):
        if n_clicks is None:
            raise dash.exceptions.PreventUpdate
        print("🔍 [CLEAR] Clearing all baseline data")
        # Clear all peak data and increment counter to trigger shape clearing
        return [], current_counter + 1, None, []

    # Integration table callback
    @app.callback(
        Output("baseline-integration-table-container", "children"),
        Input("stored-peaks", "data"),
        prevent_initial_call=True
    )
    def update_table(peaks):
        # Table removed as per user request
        return html.Div()