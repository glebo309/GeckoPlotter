# =============================================================================
# File: callbacks/baseline_callbacks.py
# =============================================================================
"""
Manual baseline integration callbacks for GeckoPlotter V2.

Ports the p-line drawing tool from the old DashPlotter:
- Draw mode: user draws a line between two points on the chromatogram
- Edit mode: user can drag endpoints of the selected baseline
- Navigate mode: normal pan/zoom
- Easy integration: forces baseline y-coordinates to 0
- Computes area, height, apex, filled polygon for each manual peak
"""

import logging
import sys

import dash
from dash import Input, Output, State, html, callback_context
from dash.exceptions import PreventUpdate
import numpy as np
from scipy import interpolate
from scipy.integrate import trapezoid

log = logging.getLogger('geckoplotter.baseline')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Math helpers (ported from old DashPlotter baseline_integration_callbacks.py)
# ---------------------------------------------------------------------------

def _y_curve(time_arr, signal_arr, x):
    """Get chromatogram intensity at time x via interpolation."""
    interp = interpolate.interp1d(time_arr, signal_arr, bounds_error=False, fill_value=0)
    return max(0, float(interp(x)))


def _baseline_area(time_arr, signal_arr, p1, p2):
    """Calculate baseline-corrected peak area between two points.

    Returns dict with area, height, apex_x, poly_x, poly_y or None.
    """
    (x1, y1), (x2, y2) = sorted([p1, p2])
    mask = (time_arr >= x1) & (time_arr <= x2)
    x = time_arr[mask]
    y = signal_arr[mask]

    if len(x) < 2 or x1 == x2:
        return None

    # Linear baseline between the two p-points
    yb = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    d = y - yb

    idx = np.where(np.diff(np.sign(d)))[0]

    if idx.size >= 2:
        i0 = idx[0] + 1 if d[idx[0] + 1] > 0 else idx[0]
        i1 = idx[-1] if d[idx[-1]] > 0 else idx[-1] - 1
        if i0 >= i1:
            return None
        xs, ys, ybs = x[i0:i1 + 1], y[i0:i1 + 1], yb[i0:i1 + 1]
    elif idx.size == 1:
        total_area = trapezoid(y - yb, x)
        if total_area > 0:
            xs, ys, ybs = x, y, yb
        else:
            return None
    else:
        # No sign changes — chromatogram always above baseline
        total_area = trapezoid(y - yb, x)
        if total_area > 0:
            xs, ys, ybs = x, y, yb
        else:
            return None

    area = trapezoid(ys - ybs, xs)
    if area <= 0:
        return None

    baseline_clamped = np.minimum(ybs, ys)
    return dict(
        area=float(area),
        height=float((ys - ybs).max()),
        apex_x=float(xs[np.argmax(ys - ybs)]),
        poly_x=np.concatenate([xs, xs[::-1]]).tolist(),
        poly_y=np.concatenate([ys, baseline_clamped[::-1]]).tolist(),
    )


def _area_with_constraints(time_arr, signal_arr, p1, p2):
    """Apply q-point constraints and compute baseline area."""
    x1, y1 = p1
    x2, y2 = p2

    if y1 >= 0 and y2 >= 0:
        q1, q2 = p1, p2
    else:
        q1 = (x1, max(0, min(_y_curve(time_arr, signal_arr, x1), y1)) if y1 >= 0 else 0)
        q2 = (x2, max(0, min(_y_curve(time_arr, signal_arr, x2), y2)) if y2 >= 0 else 0)

    res = _baseline_area(time_arr, signal_arr, q1, q2)
    return res, q1, q2


# ---------------------------------------------------------------------------
# Shared: get chromatogram arrays from file_id
# ---------------------------------------------------------------------------

def get_chromatogram_arrays(data_manager, file_id):
    """Extract (time, signal) arrays from the active chromatogram.

    Exported so integration_callbacks can reuse it.
    """
    file_data = data_manager.get_data_by_id(file_id)
    if file_data is None:
        bundle = data_manager.get_bundle_by_id(file_id)
        if bundle and bundle.main_file:
            file_data = data_manager.get_data_by_id(bundle.main_file.get('id'))
    if file_data is None:
        return None, None

    df = file_data.get('data')
    if df is None:
        return None, None

    time_col = signal_col = None
    for c in df.columns:
        cl = c.lower()
        if 'time' in cl:
            time_col = c
        elif any(k in cl for k in ('value', 'intensity', 'mau', 'absorbance', 'signal')):
            signal_col = c
    if time_col is None or signal_col is None:
        return None, None

    return (
        df[time_col].to_numpy(dtype=float),
        df[signal_col].to_numpy(dtype=float),
    )


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_baseline_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all manual baseline integration callbacks."""

    def _get_chrom(file_id):
        return get_chromatogram_arrays(data_manager, file_id)

    # ── Mode switching ────────────────────────────────────────────────

    @app.callback(
        [Output('baseline-mode', 'data'),
         Output('baseline-mode-indicator', 'children'),
         Output('p-line-visible', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True)],
        [Input('baseline-draw-btn', 'n_clicks'),
         Input('baseline-edit-btn', 'n_clicks'),
         Input('baseline-nav-btn', 'n_clicks')],
        State('baseline-mode', 'data'),
        prevent_initial_call=True,
    )
    def set_baseline_mode(n_draw, n_edit, n_nav, current_mode):
        ctx = callback_context
        if not ctx.triggered:
            return current_mode, f'Mode: {current_mode}', False, None
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        mode_map = {
            'baseline-draw-btn': 'draw',
            'baseline-edit-btn': 'edit',
            'baseline-nav-btn': 'navigate',
        }
        mode = mode_map.get(button_id, current_mode)
        return mode, f'Mode: {mode}', False, None

    # ── Sync button active states ───────────────────────────────────

    @app.callback(
        [Output('baseline-draw-btn', 'className'),
         Output('baseline-edit-btn', 'className'),
         Output('baseline-nav-btn', 'className')],
        Input('baseline-mode', 'data'),
        prevent_initial_call=True,
    )
    def sync_baseline_button_styles(mode):
        base = 'btn btn-secondary'
        active = 'btn btn-primary active'
        return (
            active if mode == 'draw' else base,
            active if mode == 'edit' else base,
            active if mode == 'navigate' else base,
        )

    # ── Store drawn line from relayoutData ────────────────────────────

    @app.callback(
        [Output('p-line-store', 'data', allow_duplicate=True),
         Output('clear-shapes-trigger', 'data', allow_duplicate=True)],
        Input('main-plot', 'relayoutData'),
        [State('p-line-store', 'data'),
         State('baseline-mode', 'data'),
         State('clear-shapes-trigger', 'data'),
         State('easy-integration', 'value'),
         State('active-file', 'data')],
        prevent_initial_call=True,
    )
    def store_line(relayout, line, mode, clear_counter, easy_mode, active_file):
        if not relayout or not active_file:
            return line or [], clear_counter or 0

        # Draw mode: user finished drawing a new shape
        if mode == 'draw' and 'shapes' in relayout and relayout['shapes']:
            s = relayout['shapes'][-1]
            pts = [(s['x0'], s['y0']), (s['x1'], s['y1'])]

            if easy_mode and 'easy' in easy_mode:
                pts = [(pts[0][0], 0), (pts[1][0], 0)]

            # Validate integration
            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is not None:
                res, *_ = _area_with_constraints(time_arr, signal_arr, *pts)
                if res is None:
                    return [], (clear_counter or 0) + 1
            return pts, clear_counter or 0

        # Edit mode: user dragged shape endpoints
        if mode == 'edit' and line and len(line) == 2:
            (x0, y0), (x1, y1) = line
            for k, v in relayout.items():
                if k.startswith('shapes[0].'):
                    if k.endswith('.x0'):
                        x0 = v
                    elif k.endswith('.y0'):
                        y0 = v
                    elif k.endswith('.x1'):
                        x1 = v
                    elif k.endswith('.y1'):
                        y1 = v

            if easy_mode and 'easy' in easy_mode:
                y0, y1 = 0, 0

            return [(x0, y0), (x1, y1)], clear_counter or 0

        return line or [], clear_counter or 0

    # ── Add or update peak from drawn/edited line ──────────────────────
    # Also clears the drawn shape from the plot after committing.

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('p-line-store', 'data', allow_duplicate=True),
         Output('clear-shapes-trigger', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True)],
        Input('p-line-store', 'data'),
        [State('baseline-mode', 'data'),
         State('selected-peak-idx', 'data'),
         State('easy-integration', 'value'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('clear-shapes-trigger', 'data'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_baseline_peak(line, mode, idx, easy_mode, active_file, current_figure, counter, peak_counter):
        """Handle both drawing new peaks and editing existing ones.
        After a successful commit, clear the drawn shape from the plot.
        """
        if not line or len(line) != 2 or not active_file:
            raise PreventUpdate
        if mode not in ('draw', 'edit'):
            raise PreventUpdate
        if mode == 'edit' and idx is None:
            raise PreventUpdate

        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        # Apply easy integration
        if easy_mode and 'easy' in easy_mode:
            line = [(line[0][0], 0), (line[1][0], 0)]

        res, q1, q2 = _area_with_constraints(time_arr, signal_arr, *line)
        if not res:
            raise PreventUpdate

        if mode == 'draw':
            data_manager.peak_service.add_baseline_peak(
                file_id=active_file,
                area=res['area'],
                height=res['height'],
                apex_x=res['apex_x'],
                poly_x=res['poly_x'],
                poly_y=res['poly_y'],
                p_line=list(line),
                q1=q1,
                q2=q2,
            )
            log.debug(f"Added manual peak: RT={res['apex_x']:.3f}, area={res['area']:.1f}")
        else:
            # Edit mode — update existing peak by peak_id
            all_peaks = data_manager.peak_service.get_peaks(active_file)
            editable = sorted(
                [p for p in all_peaks if p.source in ('manual', 'detected')],
                key=lambda p: p.rt,
            )
            if 0 <= idx < len(editable):
                p = editable[idx]
                p.area = res['area']
                p.height = res['height']
                p.rt = res['apex_x']
                p.poly_x = res['poly_x']
                p.poly_y = res['poly_y']
                p.p_line = list(line)
                p.q1 = q1
                p.q2 = q2
                p.rt_start = min(line[0][0], line[1][0])
                p.rt_end = max(line[0][0], line[1][0])
                p.width = p.rt_end - p.rt_start
                # Once edited, a detected peak becomes manual
                if p.source == 'detected':
                    p.source = 'manual'

        fig = _rebuild_figure_with_peaks(
            data_manager, active_file, current_figure, time_arr, signal_arr
        )
        # Clear the drawn shape and p-line-store after committing
        return fig, [], (counter or 0) + 1, (peak_counter or 0) + 1

    # ── Select peak by click ─────────────────────────────────────────

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('p-line-visible', 'data', allow_duplicate=True)],
        Input('main-plot', 'clickData'),
        [State('baseline-mode', 'data'),
         State('active-file', 'data')],
        prevent_initial_call=True,
    )
    def select_peak_by_click(click, mode, active_file):
        if mode != 'edit' or not click or not active_file:
            raise PreventUpdate
        x_click = click['points'][0]['x']
        # Select from all editable peaks (manual + detected), not just manual
        all_peaks = data_manager.peak_service.get_peaks(active_file)
        editable = sorted(
            [p for p in all_peaks if p.source in ('manual', 'detected')],
            key=lambda p: p.rt,
        )
        if not editable:
            raise PreventUpdate
        idx = min(range(len(editable)), key=lambda i: abs(editable[i].rt - x_click))
        return idx, True

    # ── Clear all manual peaks ────────────────────────────────────────

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('clear-shapes-trigger', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('p-line-store', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True)],
        Input('baseline-clear-btn', 'n_clicks'),
        [State('clear-shapes-trigger', 'data'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def clear_manual_peaks(n_clicks, counter, active_file, current_figure, peak_counter):
        if not n_clicks:
            raise PreventUpdate
        if active_file:
            data_manager.peak_service.clear_manual_peaks(active_file)
            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is not None:
                fig = _rebuild_figure_with_peaks(
                    data_manager, active_file, current_figure, time_arr, signal_arr
                )
                return fig, (counter or 0) + 1, None, [], (peak_counter or 0) + 1
        return current_figure, (counter or 0) + 1, None, [], (peak_counter or 0) + 1

    # ── Update dragmode based on baseline-mode ────────────────────────

    @app.callback(
        Output('main-plot', 'figure', allow_duplicate=True),
        Input('baseline-mode', 'data'),
        State('main-plot', 'figure'),
        prevent_initial_call=True,
    )
    def update_dragmode(mode, current_figure):
        if current_figure is None:
            raise PreventUpdate
        import plotly.graph_objects as go
        fig = go.Figure(current_figure)
        drag_map = {
            'draw': 'drawline',
            'edit': 'select',
            'navigate': 'pan',
        }
        fig.update_layout(dragmode=drag_map.get(mode, 'pan'))
        # Clear any existing shapes when switching modes
        if mode == 'navigate':
            fig.update_layout(shapes=[])
        return fig

    # ── Peak count indicator in toolbox ───────────────────────────────

    @app.callback(
        Output('manual-peak-table-container', 'children'),
        [Input('main-plot', 'figure')],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def update_peak_count_indicator(_, active_file):
        """Show a simple peak count — the actual table is in Peak Analysis tab."""
        if not active_file:
            return html.Div()
        all_peaks = data_manager.peak_service.get_peaks(active_file)
        manual = [p for p in all_peaks if p.source == 'manual']
        detected = [p for p in all_peaks if p.source == 'detected']
        imported = [p for p in all_peaks if p.source == 'imported']
        parts = []
        if imported:
            parts.append(f'{len(imported)} imported')
        if manual:
            parts.append(f'{len(manual)} manual')
        if detected:
            parts.append(f'{len(detected)} detected')
        if not parts:
            return html.Div('No peaks', style={'fontSize': '11px', 'color': '#999', 'fontStyle': 'italic'})
        return html.Div(
            f'Peaks: {", ".join(parts)}. See Peak Analysis tab for details.',
            style={'fontSize': '11px', 'color': '#666'},
        )


# ---------------------------------------------------------------------------
# Figure builder with peak overlays
# ---------------------------------------------------------------------------

def _rebuild_figure_with_peaks(data_manager, file_id, current_figure, time_arr, signal_arr):
    """Rebuild the current figure, adding all peak overlays."""
    import plotly.graph_objects as go

    fig = go.Figure(current_figure) if current_figure else go.Figure()

    # Remove old peak traces (identified by meta tag)
    fig.data = [t for t in fig.data if not (hasattr(t, 'meta') and t.meta == 'peak_overlay')]
    # Clear old shapes (p-lines drawn by user)
    fig.update_layout(shapes=[])

    all_peaks = data_manager.peak_service.get_peaks(file_id)

    for peak in all_peaks:
        if peak.poly_x and peak.poly_y:
            # Filled polygon for peaks with baseline data (manual or detected with poly)
            fill_color = 'rgba(0, 150, 200, 0.25)' if peak.source == 'manual' else 'rgba(230, 159, 0, 0.25)'
            marker_color = '#005F8C' if peak.source == 'manual' else '#E69F00'
            fig.add_trace(go.Scatter(
                x=peak.poly_x,
                y=peak.poly_y,
                fill='toself',
                fillcolor=fill_color,
                line=dict(width=0),
                hoverinfo='skip',
                showlegend=False,
                meta='peak_overlay',
            ))
            # Apex marker with area label
            fig.add_trace(go.Scatter(
                x=[peak.rt],
                y=[peak.height],
                mode='markers+text',
                marker=dict(size=8, symbol='diamond', color=marker_color),
                text=[f'{peak.area:.0f}'],
                textposition='top center',
                textfont=dict(size=9, color=marker_color),
                hovertemplate=f'{peak.name} ({peak.source})<br>RT: {peak.rt:.3f} min<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False,
                meta='peak_overlay',
            ))
            # P-line (baseline) for manual peaks
            if peak.p_line and len(peak.p_line) == 2:
                fig.add_trace(go.Scatter(
                    x=[peak.p_line[0][0], peak.p_line[1][0]],
                    y=[peak.p_line[0][1], peak.p_line[1][1]],
                    mode='lines+markers',
                    line=dict(color=marker_color, width=2, dash='dot'),
                    marker=dict(size=6, color=marker_color, symbol='circle-open'),
                    hoverinfo='skip',
                    showlegend=False,
                    meta='peak_overlay',
                ))

        elif peak.source == 'imported':
            # Triangle markers for imported peaks (no polygon data)
            marker_y = _y_curve(time_arr, signal_arr, peak.rt)
            fig.add_trace(go.Scatter(
                x=[peak.rt],
                y=[marker_y],
                mode='markers',
                marker=dict(size=10, symbol='triangle-up', color='red'),
                hovertemplate=f'{peak.name} (imported)<br>RT: {peak.rt:.3f} min<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False,
                meta='peak_overlay',
            ))

        elif peak.source == 'detected' and not peak.poly_x:
            # Diamond markers for detected peaks without polygon data
            marker_y = _y_curve(time_arr, signal_arr, peak.rt)
            fig.add_trace(go.Scatter(
                x=[peak.rt],
                y=[marker_y],
                mode='markers+text',
                marker=dict(size=8, symbol='diamond', color='#E69F00'),
                text=[f'{peak.area:.0f}'],
                textposition='top center',
                textfont=dict(size=9, color='#E69F00'),
                hovertemplate=f'{peak.name} (detected)<br>RT: {peak.rt:.3f} min<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False,
                meta='peak_overlay',
            ))

    return fig
