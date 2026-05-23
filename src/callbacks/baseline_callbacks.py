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
from dash import Input, Output, State, html, callback_context, Patch
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
         Output('selected-peak-idx', 'data', allow_duplicate=True)],
        [Input('baseline-draw-btn', 'n_clicks'),
         Input('baseline-nav-btn', 'n_clicks')],
        State('baseline-mode', 'data'),
        prevent_initial_call=True,
    )
    def set_baseline_mode(n_draw, n_nav, current_mode):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        button_id = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0]
        if button_id == 'baseline-draw-btn':
            mode = 'navigate' if current_mode == 'draw' else 'draw'
        elif button_id == 'baseline-nav-btn':
            mode = 'navigate'
        else:
            mode = current_mode or 'navigate'

        indicator = 'Draw: on' if mode == 'draw' else 'Draw: off'
        return mode, indicator, None

    # ── Sync button active states ───────────────────────────────────

    @app.callback(
        [Output('baseline-draw-btn', 'className'),
         Output('baseline-nav-btn', 'className')],
        Input('baseline-mode', 'data'),
        prevent_initial_call=True,
    )
    def sync_baseline_button_styles(mode):
        base = 'btn btn-secondary'
        active = 'btn btn-primary active'
        return (
            active if mode == 'draw' else base,
            active if mode == 'navigate' else base,
        )

    app.clientside_callback(
        """
        function(mode) {
            window.setTimeout(function() {
                if (window.GeckoPlotterManualIntegration) {
                    window.GeckoPlotterManualIntegration.installEmptyClickHandler();
                    window.GeckoPlotterManualIntegration.syncDrawMode('main-plot', mode);
                }
            }, 0);
            return '';
        }
        """,
        Output('dummy-output', 'children', allow_duplicate=True),
        Input('baseline-mode', 'data'),
        prevent_initial_call=True,
    )

    # ── Draw mode: capture new line from relayoutData ────────────────

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('clear-shapes-trigger', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True)],
        [Input('main-plot', 'relayoutData'),
         Input('manual-draw-line-store', 'data')],
        [State('baseline-mode', 'data'),
         State('easy-integration', 'value'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data'),
         State('selected-peak-idx', 'data'),
         State('clear-shapes-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_relayout(relayout, draw_line, mode, easy_mode, active_file, current_figure, peak_counter, selected_idx, clear_counter):
        """Handle draw-mode new shapes and edit-mode shape drags."""
        import plotly.graph_objects as go

        if not active_file:
            raise PreventUpdate

        trigger_id = callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0] if callback_context.triggered else ''

        # ── Draw mode: browser-side custom integration line ──
        if trigger_id == 'manual-draw-line-store' and mode == 'draw' and draw_line:
            display_pts = [(draw_line.get('x0'), draw_line.get('y0')), (draw_line.get('x1'), draw_line.get('y1'))]
            if any(v is None for pt in display_pts for v in pt):
                raise PreventUpdate
            calc_pts = display_pts

            if easy_mode and 'easy' in easy_mode:
                calc_pts = [(display_pts[0][0], 0), (display_pts[1][0], 0)]

            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is None:
                raise PreventUpdate

            res, q1, q2 = _area_with_constraints(time_arr, signal_arr, *calc_pts)
            if not res:
                raise PreventUpdate

            # Check overlap with existing peaks — replace if >50% overlap
            line_x_min = min(display_pts[0][0], display_pts[1][0])
            line_x_max = max(display_pts[0][0], display_pts[1][0])
            line_width = line_x_max - line_x_min

            all_peaks = data_manager.peak_service.get_peaks(active_file)
            replaced = False
            changed_peak = None
            for p in all_peaks:
                if p.source not in ('manual', 'detected'):
                    continue
                if p.p_line and len(p.p_line) == 2:
                    p_x_min = min(p.p_line[0][0], p.p_line[1][0])
                    p_x_max = max(p.p_line[0][0], p.p_line[1][0])
                else:
                    p_x_min = p.rt_start
                    p_x_max = p.rt_end
                overlap = max(0, min(line_x_max, p_x_max) - max(line_x_min, p_x_min))
                p_width = p_x_max - p_x_min
                if p_width > 0 and overlap / p_width > 0.5:
                    p.area = res['area']
                    p.height = res['height']
                    p.rt = res['apex_x']
                    p.poly_x = res['poly_x']
                    p.poly_y = res['poly_y']
                    p.p_line = list(display_pts)
                    p.q1 = q1
                    p.q2 = q2
                    p.rt_start = line_x_min
                    p.rt_end = line_x_max
                    p.width = line_width
                    if p.source == 'detected':
                        p.source = 'manual'
                    replaced = True
                    changed_peak = p
                    log.debug(f"Replaced peak RT={p.rt:.3f}, area={res['area']:.1f}")
                    break

            if not replaced:
                changed_peak = data_manager.peak_service.add_baseline_peak(
                    file_id=active_file,
                    area=res['area'],
                    height=res['height'],
                    apex_x=res['apex_x'],
                    poly_x=res['poly_x'],
                    poly_y=res['poly_y'],
                    p_line=list(display_pts),
                    q1=q1,
                    q2=q2,
                )
                log.debug(f"Added peak RT={res['apex_x']:.3f}, area={res['area']:.1f}")

            fig_patch = _patch_figure_with_peaks(
                data_manager, active_file, current_figure, time_arr, signal_arr, None
            )
            return fig_patch, (peak_counter or 0) + 1, (clear_counter or 0) + 1, None

        # ── Edit selected/all baseline shape endpoint(s) ──
        if not relayout:
            raise PreventUpdate
        if mode == 'edit' or selected_idx:
            shape_keys = [k for k in relayout if k.startswith('shapes[')]
            if not shape_keys:
                raise PreventUpdate

            # Parse which shape was edited and its new coordinates
            shape_updates = {}
            for k, v in relayout.items():
                if k.startswith('shapes['):
                    shape_updates[k] = v

            # Find the shape index and new coordinates
            shape_idx = None
            for k in shape_updates:
                try:
                    idx_str = k.split('[')[1].split(']')[0]
                    shape_idx = int(idx_str)
                    break
                except (IndexError, ValueError):
                    pass

            if shape_idx is None:
                raise PreventUpdate

            # Get current figure shapes to find original + updates
            fig_obj = go.Figure(current_figure) if isinstance(current_figure, dict) else current_figure
            shapes = list(fig_obj.layout.shapes) if fig_obj.layout.shapes else []
            if shape_idx >= len(shapes):
                raise PreventUpdate

            shape = shapes[shape_idx]
            x0 = shape_updates.get(f'shapes[{shape_idx}].x0', shape.x0)
            y0 = shape_updates.get(f'shapes[{shape_idx}].y0', shape.y0)
            x1 = shape_updates.get(f'shapes[{shape_idx}].x1', shape.x1)
            y1 = shape_updates.get(f'shapes[{shape_idx}].y1', shape.y1)

            display_p0 = (x0, y0)
            display_p1 = (x1, y1)
            calc_p0 = display_p0
            calc_p1 = display_p1
            if easy_mode and 'easy' in easy_mode:
                calc_p0 = (x0, 0)
                calc_p1 = (x1, 0)

            all_peaks = data_manager.peak_service.get_peaks(active_file)
            shape_name = getattr(shape, 'name', None)
            p = None
            if isinstance(shape_name, str) and shape_name.startswith('baseline:'):
                shape_peak_id = shape_name.split(':', 1)[1]
                if selected_idx and shape_peak_id != selected_idx:
                    raise PreventUpdate
                p = next((peak for peak in all_peaks if peak.peak_id == shape_peak_id), None)
            if p is None:
                if selected_idx:
                    raise PreventUpdate
                editable = sorted(
                    [peak for peak in all_peaks if peak.source in ('manual', 'detected') and peak.p_line],
                    key=lambda peak: peak.rt,
                )
                if shape_idx < len(editable):
                    p = editable[shape_idx]
            if p is None:
                raise PreventUpdate

            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is None:
                raise PreventUpdate

            res, q1, q2 = _area_with_constraints(time_arr, signal_arr, calc_p0, calc_p1)
            if not res:
                raise PreventUpdate

            p.area = res['area']
            p.height = res['height']
            p.rt = res['apex_x']
            p.poly_x = res['poly_x']
            p.poly_y = res['poly_y']
            p.p_line = [display_p0, display_p1]
            p.q1 = q1
            p.q2 = q2
            p.rt_start = min(x0, x1)
            p.rt_end = max(x0, x1)
            p.width = p.rt_end - p.rt_start
            if p.source == 'detected':
                p.source = 'manual'
            log.debug(f"Edit-dragged peak idx={shape_idx}: RT={res['apex_x']:.3f}")

            selected_for_rebuild = None if mode == 'edit' else p.peak_id
            fig_patch = _patch_figure_with_peaks(
                data_manager, active_file, current_figure, time_arr, signal_arr, selected_for_rebuild
            )
            return fig_patch, (peak_counter or 0) + 1, (clear_counter or 0) + 1, p.peak_id if mode != 'edit' else None

        raise PreventUpdate

    # ── Normal mode: click a filled peak to select/highlight it ───────

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True)],
        Input('plot-peak-click-store', 'data'),
        [State('active-file', 'data'),
         State('main-plot', 'figure')],
        prevent_initial_call=True,
    )
    def select_peak_from_browser_hit_test(hit_data, active_file, current_figure):
        """Select a peak from the browser-side pointer hit test before Plotly starts drawing."""
        if not hit_data or not active_file:
            raise PreventUpdate

        peak_id = hit_data.get('peakId') if isinstance(hit_data, dict) else None
        if not peak_id:
            raise PreventUpdate

        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = _patch_figure_with_peaks(
            data_manager, active_file, current_figure, time_arr, signal_arr, peak_id
        )
        return peak_id, fig_patch

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True)],
        Input('main-plot', 'clickData'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data')],
        prevent_initial_call=True,
    )
    def select_peak_by_click(click_data, active_file, current_figure, selected_peak_id, mode):
        """Select peaks from any mode; the invisible catcher deselects."""
        import plotly.graph_objects as go

        if not click_data or not active_file:
            raise PreventUpdate

        points = click_data.get('points') or []
        if not points:
            raise PreventUpdate

        customdata = points[0].get('customdata')
        kind = None
        if isinstance(customdata, (list, tuple)):
            peak_id = customdata[0]
            kind = customdata[1] if len(customdata) > 1 else None
        else:
            peak_id = customdata
        if not peak_id:
            raise PreventUpdate

        next_selected = None if peak_id == '__deselect__' else peak_id
        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = _patch_figure_with_peaks(
            data_manager, active_file, current_figure, time_arr, signal_arr, next_selected
        )
        return next_selected, fig_patch

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True)],
        Input('plot-empty-click-trigger', 'n_clicks'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data')],
        prevent_initial_call=True,
    )
    def deselect_peak_from_empty_plot_click(n_clicks, active_file, current_figure, selected_peak_id, mode):
        """Deselect the current peak when the browser detects a blank plot click."""
        import plotly.graph_objects as go

        if not n_clicks or not active_file or not selected_peak_id:
            raise PreventUpdate

        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = _patch_figure_with_peaks(
            data_manager, active_file, current_figure, time_arr, signal_arr, None
        )
        return None, fig_patch

    # ── Client-side cleanup for Plotly's transient draw shape ─────────

    app.clientside_callback(
        """
        function(trigger) {
            if (!trigger) {
                return window.dash_clientside.no_update;
            }
            window.setTimeout(function() {
                if (window.GeckoPlotterManualIntegration) {
                    window.GeckoPlotterManualIntegration.installEmptyClickHandler();
                    window.GeckoPlotterManualIntegration.clearTransientShapes('main-plot');
                }
            }, 80);
            return '';
        }
        """,
        Output('clear-transient-shapes-output', 'children'),
        Input('clear-shapes-trigger', 'data'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(selectedPeakId) {
            window.setTimeout(function() {
                if (window.GeckoPlotterManualIntegration) {
                    window.GeckoPlotterManualIntegration.installEmptyClickHandler();
                    window.GeckoPlotterManualIntegration.syncSelectedShape('main-plot', selectedPeakId);
                }
            }, 80);
            return '';
        }
        """,
        Output('selected-shapes-sync-output', 'children'),
        Input('selected-peak-idx', 'data'),
        prevent_initial_call=True,
    )

    # ── Clear all manual peaks ────────────────────────────────────────

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True)],
        Input('baseline-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data'),
         State('selected-peak-idx', 'data')],
        prevent_initial_call=True,
    )
    def clear_manual_peaks(n_clicks, active_file, current_figure, peak_counter, selected_peak_id):
        if not n_clicks:
            raise PreventUpdate
        if active_file:
            if selected_peak_id:
                data_manager.peak_service.remove_peak(active_file, selected_peak_id)
            else:
                data_manager.peak_service.clear_manual_peaks(active_file)
            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is not None:
                fig_patch = _patch_figure_with_peaks(
                    data_manager, active_file, current_figure, time_arr, signal_arr
                )
                return fig_patch, None, (peak_counter or 0) + 1
        return current_figure, None, (peak_counter or 0) + 1

    # ── Peak count indicator in toolbox ───────────────────────────────

    @app.callback(
        Output('manual-peak-table-container', 'children'),
        [Input('peak-change-trigger', 'data')],
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
# Edit-mode helpers
# ---------------------------------------------------------------------------

def _add_edit_handles(data_manager, file_id, fig):
    """Add editable line shapes for each editable peak's baseline."""
    all_peaks = data_manager.peak_service.get_peaks(file_id)
    editable = sorted(
        [p for p in all_peaks if p.source in ('manual', 'detected') and p.p_line and len(p.p_line) == 2],
        key=lambda p: p.rt,
    )
    for p in editable:
        fig.add_shape(
            type='line',
            x0=p.p_line[0][0], y0=p.p_line[0][1],
            x1=p.p_line[1][0], y1=p.p_line[1][1],
            name=f'baseline:{p.peak_id}',
            line=dict(color='rgba(100,100,100,0.7)', width=2, dash='dot'),
            editable=True,
        )


def _add_selected_baseline_handle(fig, peak):
    """Show the selected peak's baseline plus visible p-point markers."""
    import plotly.graph_objects as go

    if not peak.p_line or len(peak.p_line) != 2:
        return

    line_color = peak.color or '#E69F00'
    p0, p1 = peak.p_line
    fig.add_shape(
        type='line',
        x0=p0[0], y0=p0[1],
        x1=p1[0], y1=p1[1],
        name=f'baseline:{peak.peak_id}',
        line=dict(color=line_color, width=2, dash='dot'),
        editable=True,
    )
    fig.add_trace(go.Scatter(
        x=[p0[0], p1[0]],
        y=[p0[1], p1[1]],
        mode='markers',
        marker=dict(
            size=9,
            color='#ffffff',
            line=dict(color=line_color, width=2),
            symbol='circle',
        ),
        customdata=[[peak.peak_id, 'p-point'], [peak.peak_id, 'p-point']],
        hoverinfo='skip',
        showlegend=False,
        meta='peak_overlay',
    ))


# ---------------------------------------------------------------------------
# Figure builder with peak overlays
# ---------------------------------------------------------------------------

def _rgba(hex_color, alpha):
    """Convert #RRGGBB to rgba(...) while accepting existing rgba values."""
    if isinstance(hex_color, str) and hex_color.startswith('#') and len(hex_color) == 7:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    return hex_color


def _add_deselect_catcher(fig, time_arr, signal_arr):
    """Add a near-transparent plot-area trace that clicks to deselect."""
    import plotly.graph_objects as go

    x_vals = np.asarray(time_arr, dtype=float)
    y_vals = np.asarray(signal_arr, dtype=float)
    finite_x = x_vals[np.isfinite(x_vals)]
    finite_y = y_vals[np.isfinite(y_vals)]
    if finite_x.size < 2 or finite_y.size < 2:
        return

    x0, x1 = float(np.nanmin(finite_x)), float(np.nanmax(finite_x))
    y0, y1 = float(np.nanmin(finite_y)), float(np.nanmax(finite_y))
    y_pad = max((y1 - y0) * 0.08, 1e-9)
    y0 -= y_pad
    y1 += y_pad

    fig.add_trace(go.Scatter(
        x=[x0, x1, x1, x0, x0],
        y=[y0, y0, y1, y1, y0],
        fill='toself',
        fillcolor='rgba(255,255,255,0.001)',
        mode='lines',
        line=dict(width=0, color='rgba(255,255,255,0)'),
        customdata=[['__deselect__', 'catcher']] * 5,
        hoverinfo='skip',
        showlegend=False,
        meta='peak_overlay',
    ))


def _patch_figure_with_peaks(data_manager, file_id, current_figure, time_arr, signal_arr, selected_peak_id=None):
    """Patch only peak overlays and editable shapes, leaving plot layout untouched."""
    fig = _rebuild_figure_with_peaks(
        data_manager, file_id, current_figure, time_arr, signal_arr, selected_peak_id
    )
    fig_json = fig.to_plotly_json()

    patch = Patch()
    patch['data'] = fig_json.get('data', [])
    patch['layout']['shapes'] = fig_json.get('layout', {}).get('shapes', [])
    return patch


def _rebuild_figure_with_peaks(data_manager, file_id, current_figure, time_arr, signal_arr, selected_peak_id=None):
    """Rebuild the current figure, adding all peak overlays."""
    import plotly.graph_objects as go

    fig = go.Figure(current_figure) if current_figure else go.Figure()

    # Remove old peak traces (identified by meta tag)
    fig.data = [t for t in fig.data if not (hasattr(t, 'meta') and t.meta == 'peak_overlay')]
    # Clear drawn/editable shapes before adding the selected peak's baseline.
    fig.layout.shapes = ()
    fig.update_layout(uirevision='main-plot')

    all_peaks = data_manager.peak_service.get_peaks(file_id)

    FILL_COLORS = [
        'rgba(180, 120, 220, 0.30)',
        'rgba(100, 180, 120, 0.30)',
        'rgba(80, 160, 220, 0.30)',
        'rgba(220, 160, 80, 0.30)',
        'rgba(220, 100, 120, 0.30)',
        'rgba(120, 200, 200, 0.30)',
    ]

    for i, peak in enumerate(all_peaks):
        is_selected = peak.peak_id == selected_peak_id
        fill_color = _rgba(peak.color, 0.58 if is_selected else 0.30) if peak.color else FILL_COLORS[i % len(FILL_COLORS)]
        line_color = peak.color if is_selected else 'rgba(0,0,0,0)'

        has_custom_label = bool(peak.label) if hasattr(peak, 'label') else False

        if peak.poly_x and peak.poly_y:
            poly_x = list(peak.poly_x)
            poly_y = list(peak.poly_y)
            fig.add_trace(go.Scatter(
                x=poly_x, y=poly_y,
                fill='toself', fillcolor=fill_color,
                mode='lines',
                line=dict(color=line_color, width=2 if is_selected else 0),
                customdata=[peak.peak_id] * len(poly_x),
                hoverinfo='skip',
                showlegend=False, meta='peak_overlay',
            ))
            if has_custom_label:
                fig.add_trace(go.Scatter(
                    x=[peak.rt],
                    y=[peak.height],
                    mode='text',
                    text=[peak.label],
                    textposition='top center',
                    textfont=dict(size=9, color='#333'),
                    hoverinfo='skip',
                    showlegend=False,
                        meta='peak_overlay',
                ))
            if is_selected:
                _add_selected_baseline_handle(fig, peak)

        elif has_custom_label:
            marker_y = _y_curve(time_arr, signal_arr, peak.rt)
            fig.add_trace(go.Scatter(
                x=[peak.rt],
                y=[marker_y],
                mode='text',
                text=[peak.label],
                textposition='top center',
                textfont=dict(size=9, color='#333'),
                hovertemplate=f'{peak.name} ({peak.source})<br>RT: {peak.rt:.3f} min<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False,
                meta='peak_overlay',
            ))

    return fig
