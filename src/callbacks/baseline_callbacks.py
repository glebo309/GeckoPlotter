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

from callbacks.peak_overlay import (
    overlay_peaks_on_figure,
    patch_figure_with_peaks,
    add_selected_baseline_handle,
    _y_curve,
)

log = logging.getLogger('geckoplotter.baseline')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def _find_peak_file_id(peak_service, peak_id):
    """Return the file id that owns ``peak_id``, or None."""
    if not peak_id:
        return None
    for fid, peaks in peak_service.get_all_peaks().items():
        if any(p.peak_id == peak_id for p in peaks):
            return fid
    return None


# ---------------------------------------------------------------------------
# Math helpers (ported from old DashPlotter baseline_integration_callbacks.py)
# ---------------------------------------------------------------------------



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
# Shared: get X/Y arrays from any file
# ---------------------------------------------------------------------------

def get_xy_arrays(data_manager, file_id):
    """Extract (x, y) arrays from any loaded file using pipeline metadata.

    Uses auto_x / auto_y set by the ingestion pipeline, falling back to
    StandardizedResult column roles, then to the first two numeric columns.
    Works on chromatograms, spectra, kinetics, generic CSVs — anything.
    """
    file_data = data_manager.get_data_by_id(file_id)
    if file_data is None:
        bundle = data_manager.get_bundle_by_id(file_id)
        if bundle and bundle.main_file:
            main_id = bundle.main_file.get('id')
            log.debug(f"get_chromatogram_arrays: falling back from bundle {file_id} to main file {main_id}")
            file_data = data_manager.get_data_by_id(main_id)
    if file_data is None:
        return None, None

    df = file_data.get('data')
    if df is None:
        return None, None

    metadata = file_data.get('metadata', {})
    x_col = metadata.get('auto_x')
    y_cols = metadata.get('auto_y')

    if not x_col or not y_cols:
        sr = file_data.get('standardized')
        if sr:
            if not x_col and sr.x_columns:
                x_col = sr.x_columns[0]
            if not y_cols and sr.y_columns:
                y_cols = sr.y_columns

    if not x_col or not y_cols:
        numeric = df.select_dtypes(include='number').columns.tolist()
        if len(numeric) >= 2:
            x_col = numeric[0]
            y_cols = [numeric[1]]

    if not x_col or not y_cols:
        return None, None

    y_col = y_cols[0] if isinstance(y_cols, list) else y_cols
    if x_col not in df.columns or y_col not in df.columns:
        return None, None

    return (
        df[x_col].to_numpy(dtype=float),
        df[y_col].to_numpy(dtype=float),
    )


get_chromatogram_arrays = get_xy_arrays


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_baseline_callbacks(app: dash.Dash, data_manager) -> None:
    """Register all manual baseline integration callbacks."""

    def _get_chrom(file_id):
        return get_xy_arrays(data_manager, file_id)

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

    def _subplot_row(subplot_key):
        """Parse a Plotly subplot key like 'x2y2' into a 1-based row number."""
        if not subplot_key or subplot_key == 'xy':
            return 1
        import re
        m = re.search(r'y(\d+)', subplot_key)
        return int(m.group(1)) if m else 1

    def _file_id_for_subplot_row(row, active_file, plot_settings, loaded_files, plot_tabs, active_tab_id):
        """Map a subplot row number to the file_id whose data occupies that row.

        Returns the same kind of ID that the file selector uses (bundle ID
        for bundled files), so peaks are stored under a consistent key.
        """
        from callbacks.viz_callbacks import _collect_visible_files
        from services.plot_settings_service import DEFAULT_PLOT_SETTINGS

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        if s.get('layout_mode') != 'stacked':
            return active_file

        tab = None
        for t in (plot_tabs or []):
            if t['id'] == active_tab_id:
                tab = t
                break
        if not tab:
            return active_file

        group_key = tuple(tab.get('group_key', []))
        visible = _collect_visible_files(data_manager, active_file, loaded_files, target_group_override=group_key)
        flat = []
        for files in visible.values():
            flat.extend(files)
        if row < 1 or row > len(flat):
            return active_file
        _, fdata = flat[row - 1]

        # Return the bundle ID if this file is bundled, matching what
        # the file selector sets as active_file.
        for bundle in data_manager.bundle_manager.bundles.values():
            if bundle.main_file and bundle.main_file.get('id') == fdata.get('record', {}).get('id'):
                return bundle.bundle_id
            if data_manager.loaded_data.get(bundle.bundle_id) is fdata:
                return bundle.bundle_id

        # Fallback: use the loaded_data key
        for fid, fd in data_manager.loaded_data.items():
            if fd is fdata:
                return fid
        return fdata.get('record', {}).get('id') or active_file

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('clear-shapes-trigger', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        [Input('main-plot', 'relayoutData'),
         Input('manual-draw-line-store', 'data')],
        [State('baseline-mode', 'data'),
         State('easy-integration', 'checked'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data'),
         State('selected-peak-idx', 'data'),
         State('clear-shapes-trigger', 'data'),
         State('current-plot-settings', 'data'),
         State('loaded-files', 'data'),
         State('plot-tabs', 'data'),
         State('active-plot-tab', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_relayout(relayout, draw_line, mode, easy_mode, active_file, current_figure, peak_counter, selected_idx, clear_counter,
                        plot_settings, loaded_files, plot_tabs, active_tab_id, render_counter):
        """Handle draw-mode new shapes and edit-mode shape drags."""
        import plotly.graph_objects as go

        tab = next((t for t in (plot_tabs or []) if t['id'] == active_tab_id), None)
        if tab and tab.get('type') == 'custom':
            raise PreventUpdate
        if not active_file:
            raise PreventUpdate

        trigger_id = callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0] if callback_context.triggered else ''

        # ── Draw mode: browser-side custom integration line ──
        if trigger_id == 'manual-draw-line-store' and draw_line and (mode == 'draw' or draw_line.get('momentary')):
            display_pts = [(draw_line.get('x0'), draw_line.get('y0')), (draw_line.get('x1'), draw_line.get('y1'))]
            if any(v is None for pt in display_pts for v in pt):
                raise PreventUpdate
            subplot_key = draw_line.get('subplot', 'xy')
            row = _subplot_row(subplot_key)
            target_file = _file_id_for_subplot_row(row, active_file, plot_settings, loaded_files, plot_tabs, active_tab_id)
            log.debug(f"Draw on subplot={subplot_key} row={row} target_file={target_file} active_file={active_file}")
            log.debug(f"  plot_settings layout_mode={plot_settings.get('layout_mode') if plot_settings else 'None'}")
            log.debug(f"  plot_tabs={plot_tabs}, active_tab_id={active_tab_id}")
            log.debug(f"  draw_line keys={list(draw_line.keys())} subplot_raw={draw_line.get('subplot')}")
            calc_pts = display_pts

            if easy_mode:
                calc_pts = [(display_pts[0][0], 0), (display_pts[1][0], 0)]

            time_arr, signal_arr = _get_chrom(target_file)
            if time_arr is None:
                raise PreventUpdate

            res, q1, q2 = _area_with_constraints(time_arr, signal_arr, *calc_pts)
            if not res:
                raise PreventUpdate

            data_manager.peak_service.save_undo()

            # Check overlap with existing peaks — replace if >50% overlap
            line_x_min = min(display_pts[0][0], display_pts[1][0])
            line_x_max = max(display_pts[0][0], display_pts[1][0])
            line_width = line_x_max - line_x_min

            all_peaks = data_manager.peak_service.get_peaks(target_file)
            replaced = False
            changed_peak = None
            for p in all_peaks:
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
                    file_id=target_file,
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

            data_manager.peak_service.group_peaks_across_samples(
                file_overlay_map=data_manager.build_file_overlay_map())
            from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
            _s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
            if _s.get('layout_mode') == 'stacked':
                return dash.no_update, (peak_counter or 0) + 1, (clear_counter or 0) + 1, None, (render_counter or 0) + 1
            fig_patch = patch_figure_with_peaks(
                data_manager.peak_service.get_peaks(target_file), current_figure, time_arr, signal_arr, None
            )
            return fig_patch, (peak_counter or 0) + 1, (clear_counter or 0) + 1, None, dash.no_update

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
            if easy_mode:
                calc_p0 = (x0, 0)
                calc_p1 = (x1, 0)

            # Determine which file owns this shape (subplot-aware)
            edit_file = active_file
            if _is_stacked(plot_settings):
                import re
                shape_yref = getattr(shape, 'yref', 'y') or 'y'
                m = re.search(r'y(\d+)', shape_yref)
                edit_row = int(m.group(1)) if m else 1
                edit_file = _file_id_for_subplot_row(edit_row, active_file, plot_settings, loaded_files, plot_tabs, active_tab_id)

            all_peaks = data_manager.peak_service.get_peaks(edit_file)
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

            time_arr, signal_arr = _get_chrom(edit_file)
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
            log.debug(f"Edit-dragged peak idx={shape_idx}: RT={res['apex_x']:.3f} file={edit_file}")

            if _is_stacked(plot_settings):
                return dash.no_update, (peak_counter or 0) + 1, (clear_counter or 0) + 1, p.peak_id if mode != 'edit' else None, (render_counter or 0) + 1

            selected_for_rebuild = None if mode == 'edit' else p.peak_id
            fig_patch = patch_figure_with_peaks(
                data_manager.peak_service.get_peaks(edit_file), current_figure, time_arr, signal_arr, selected_for_rebuild
            )
            return fig_patch, (peak_counter or 0) + 1, (clear_counter or 0) + 1, p.peak_id if mode != 'edit' else None, dash.no_update

        raise PreventUpdate

    # ── Normal mode: click a filled peak to select/highlight it ───────

    def _is_stacked(plot_settings):
        from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        return s.get('layout_mode') == 'stacked'

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('plot-peak-click-store', 'data'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('current-plot-settings', 'data'),
         State('render-trigger', 'data'),
         State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def select_peak_from_browser_hit_test(hit_data, active_file, current_figure, plot_settings, render_counter, view_mode):
        if (view_mode or 'raw') != 'raw':
            raise PreventUpdate
        if not hit_data or not active_file:
            raise PreventUpdate

        peak_id = hit_data.get('peakId') if isinstance(hit_data, dict) else None
        if not peak_id:
            raise PreventUpdate

        log.info(f"🎯 peak selected via hit-test: {peak_id}, stacked={_is_stacked(plot_settings)}")
        if _is_stacked(plot_settings):
            return peak_id, dash.no_update, (render_counter or 0) + 1

        peak_fid = active_file
        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = patch_figure_with_peaks(
            data_manager.peak_service.get_peaks(peak_fid), current_figure, time_arr, signal_arr, peak_id
        )
        return peak_id, fig_patch, dash.no_update

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('main-plot', 'clickData'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data'),
         State('current-plot-settings', 'data'),
         State('render-trigger', 'data'),
         State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def select_peak_by_click(click_data, active_file, current_figure, selected_peak_id, mode, plot_settings, render_counter, view_mode):
        import plotly.graph_objects as go

        if (view_mode or 'raw') != 'raw':
            raise PreventUpdate
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

        if _is_stacked(plot_settings):
            return next_selected, dash.no_update, (render_counter or 0) + 1

        peak_fid = active_file
        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = patch_figure_with_peaks(
            data_manager.peak_service.get_peaks(peak_fid), current_figure, time_arr, signal_arr, next_selected
        )
        return next_selected, fig_patch, dash.no_update

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('plot-empty-click-trigger', 'n_clicks'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('selected-peak-idx', 'data'),
         State('baseline-mode', 'data'),
         State('current-plot-settings', 'data'),
         State('render-trigger', 'data'),
         State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def deselect_peak_from_empty_plot_click(n_clicks, active_file, current_figure, selected_peak_id, mode, plot_settings, render_counter, view_mode):
        if (view_mode or 'raw') != 'raw':
            raise PreventUpdate
        if not n_clicks or not active_file or not selected_peak_id:
            raise PreventUpdate

        if _is_stacked(plot_settings):
            return None, dash.no_update, (render_counter or 0) + 1

        peak_fid = active_file
        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is None:
            raise PreventUpdate

        fig_patch = patch_figure_with_peaks(
            data_manager.peak_service.get_peaks(peak_fid), current_figure, time_arr, signal_arr, None
        )
        return None, fig_patch, dash.no_update

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
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('baseline-clear-btn', 'n_clicks'),
        [State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data'),
         State('selected-peak-idx', 'data'),
         State('current-plot-settings', 'data'),
         State('render-trigger', 'data'),
         State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def clear_manual_peaks(n_clicks, active_file, current_figure, peak_counter, selected_peak_id, plot_settings, render_counter, view_mode):
        if not n_clicks:
            raise PreventUpdate
        if active_file:
            peak_fid = active_file
            log.debug(f"clear_manual_peaks: active={active_file} -> peak_fid={peak_fid}, selected={selected_peak_id}")
            data_manager.peak_service.save_undo()
            if selected_peak_id:
                data_manager.peak_service.remove_peak(peak_fid, selected_peak_id)
            else:
                data_manager.peak_service.clear_manual_peaks(peak_fid)
            data_manager.peak_service.group_peaks_across_samples(
                file_overlay_map=data_manager.build_file_overlay_map())
            if _is_stacked(plot_settings):
                return dash.no_update, None, (peak_counter or 0) + 1, (render_counter or 0) + 1
            time_arr, signal_arr = _get_chrom(active_file)
            if time_arr is not None:
                fig_patch = patch_figure_with_peaks(
                    data_manager.peak_service.get_peaks(peak_fid), current_figure, time_arr, signal_arr
                )
                return fig_patch, None, (peak_counter or 0) + 1, dash.no_update
        return current_figure, None, (peak_counter or 0) + 1, dash.no_update

    # ── Keyboard Delete/Backspace → remove selected peak ─────────────

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('keyboard-delete-trigger', 'data'),
        [State('selected-peak-idx', 'data'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('peak-change-trigger', 'data'),
         State('current-plot-settings', 'data'),
         State('render-trigger', 'data'),
         State('view-mode', 'data')],
        prevent_initial_call=True,
    )
    def delete_peak_via_keyboard(trigger, selected_peak_id, active_file,
                                 current_figure, peak_counter, plot_settings,
                                 render_counter, view_mode):
        """Delete the currently selected peak when Backspace/Delete is pressed."""
        log.info(f"⌨️ keyboard-delete fired: trigger={trigger}, selected={selected_peak_id}, active={active_file}")
        if not trigger or not selected_peak_id or not active_file:
            raise PreventUpdate

        peak_fid = _find_peak_file_id(data_manager.peak_service, selected_peak_id)
        if peak_fid is None:
            log.info(f"⌨️ keyboard delete: peak {selected_peak_id} not found in any file")
            raise PreventUpdate

        log.info(f"⌨️ keyboard delete: removing peak from {peak_fid} (active={active_file})")
        data_manager.peak_service.save_undo()
        data_manager.peak_service.remove_peak(peak_fid, selected_peak_id)
        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())

        if _is_stacked(plot_settings):
            return dash.no_update, None, (peak_counter or 0) + 1, (render_counter or 0) + 1

        time_arr, signal_arr = _get_chrom(active_file)
        if time_arr is not None:
            fig_patch = patch_figure_with_peaks(
                data_manager.peak_service.get_peaks(peak_fid),
                current_figure, time_arr, signal_arr,
            )
            return fig_patch, None, (peak_counter or 0) + 1, dash.no_update

        return current_figure, None, (peak_counter or 0) + 1, dash.no_update

    # ── Keyboard: Escape (deselect), Arrows (cycle peaks), S (toggle layout) ──

    @app.callback(
        [Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('pt-layout-mode', 'value', allow_duplicate=True),
         Output('baseline-mode', 'data', allow_duplicate=True)],
        Input('keyboard-action-trigger', 'data'),
        [State('selected-peak-idx', 'data'),
         State('active-file', 'data'),
         State('main-plot', 'figure'),
         State('current-plot-settings', 'data'),
         State('pt-layout-mode', 'value'),
         State('baseline-mode', 'data')],
        prevent_initial_call=True,
    )
    def handle_keyboard_action(event, selected_peak_id, active_file, current_figure,
                               plot_settings, layout_mode, baseline_mode):
        if not event or not event.get('action'):
            raise PreventUpdate

        action = event['action']

        if action == 'escape':
            new_mode = 'navigate' if baseline_mode in ('draw', 'edit', 'deconvolve') else dash.no_update
            return None, dash.no_update, dash.no_update, new_mode

        if action == 'toggle_layout':
            new_val = 'stacked' if layout_mode == 'overlay' else 'overlay'
            return dash.no_update, dash.no_update, new_val, dash.no_update

        if action in ('prev_peak', 'next_peak') and active_file:
            all_peaks = data_manager.peak_service.get_peaks(active_file)
            if not all_peaks:
                raise PreventUpdate
            sorted_peaks = sorted(all_peaks, key=lambda p: p.rt)
            peak_ids = [p.peak_id for p in sorted_peaks]

            if not selected_peak_id or selected_peak_id not in peak_ids:
                target_id = peak_ids[0] if action == 'next_peak' else peak_ids[-1]
            else:
                cur_idx = peak_ids.index(selected_peak_id)
                if action == 'next_peak':
                    target_id = peak_ids[(cur_idx + 1) % len(peak_ids)]
                else:
                    target_id = peak_ids[(cur_idx - 1) % len(peak_ids)]

            if not _is_stacked(plot_settings):
                time_arr, signal_arr = _get_chrom(active_file)
                if time_arr is not None:
                    fig_patch = patch_figure_with_peaks(
                        all_peaks, current_figure, time_arr, signal_arr, target_id)
                    return target_id, fig_patch, dash.no_update, dash.no_update

            return target_id, dash.no_update, dash.no_update, dash.no_update

        raise PreventUpdate

    # ── Undo / Redo ───────────────────────────────────────────────────

    @app.callback(
        [Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True)],
        [Input('undo-trigger', 'data'),
         Input('redo-trigger', 'data')],
        [State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_undo_redo(undo_ts, redo_ts, peak_counter, render_counter):
        trigger_id = callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0] if callback_context.triggered else ''
        if trigger_id == 'undo-trigger' and undo_ts:
            changed = data_manager.peak_service.undo()
        elif trigger_id == 'redo-trigger' and redo_ts:
            changed = data_manager.peak_service.redo()
        else:
            raise PreventUpdate
        if not changed:
            raise PreventUpdate
        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        return (peak_counter or 0) + 1, (render_counter or 0) + 1, None

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
        count = len(all_peaks)
        if not count:
            return html.Div('No peaks', style={'fontSize': '11px', 'color': '#999', 'fontStyle': 'italic'})
        return html.Div(
            f'{count} peak{"s" if count != 1 else ""}. See Peak Analysis tab for details.',
            style={'fontSize': '11px', 'color': '#666'},
        )


# ---------------------------------------------------------------------------
# Edit-mode helpers
# ---------------------------------------------------------------------------

def _add_edit_handles(data_manager, file_id, fig):
    """Add editable line shapes for each editable peak's baseline."""
    all_peaks = data_manager.peak_service.get_peaks(file_id)
    editable = sorted(
        [p for p in all_peaks if p.p_line and len(p.p_line) == 2],
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



# _add_selected_baseline_handle, _rgba, _add_deselect_catcher,
# _patch_figure_with_peaks, _rebuild_figure_with_peaks, and FILL_COLORS
# have been extracted to callbacks/peak_overlay.py
