# =============================================================================
# File: callbacks/context_menu_callbacks.py
# =============================================================================
"""Right-click context-menu callbacks for peaks (GeckoPlotter V2).

The browser publishes a right-click on a peak polygon to ``context-menu-store``
(see manual-integration.js). These callbacks open a positioned dmc.Menu and
handle the three actions:

- Delete Peak
- Rename Peak (via a small modal)
- Integrate in All Files (find + integrate the same peak across the overlay group)
"""

import logging
import sys

import dash
from dash import Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

from callbacks.baseline_callbacks import get_xy_arrays

log = logging.getLogger('geckoplotter.contextmenu')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)

_ANCHOR_BASE = {
    'position': 'fixed', 'width': '1px', 'height': '1px',
    'zIndex': 4000, 'pointerEvents': 'none',
}


def register_context_menu_callbacks(app: dash.Dash, data_manager) -> None:
    """Register peak context-menu callbacks."""

    ps = data_manager.peak_service

    def _find_peak(peak_id):
        """Return (file_id, Peak) for a peak_id, or (None, None)."""
        for fid, peaks in ps.get_all_peaks().items():
            for p in peaks:
                if p.peak_id == peak_id:
                    return fid, p
        return None, None

    def _overlay_group_files(file_id):
        """All file_ids sharing the overlay group of file_id (incl. itself)."""
        omap = data_manager.build_file_overlay_map()
        key = omap.get(file_id)
        if key is None:
            return [file_id]
        return [fid for fid, k in omap.items() if k == key]

    # ── Open + position the menu ──────────────────────────────────────
    @app.callback(
        [Output('context-menu', 'opened'),
         Output('context-menu-anchor', 'style'),
         Output('ctx-integrate-item', 'disabled')],
        Input('context-menu-store', 'data'),
        prevent_initial_call=True,
    )
    def open_menu(store):
        if not store or not store.get('peak_id'):
            raise PreventUpdate
        x = store.get('x', 0)
        y = store.get('y', 0)
        style = {**_ANCHOR_BASE, 'left': f'{x}px', 'top': f'{y}px'}

        fid, _peak = _find_peak(store['peak_id'])
        # Disable cross-file integration when the group has only one file.
        single = fid is None or len(_overlay_group_files(fid)) <= 1
        return True, style, single

    # ── Close on outside click / Escape ───────────────────────────────
    @app.callback(
        Output('context-menu', 'opened', allow_duplicate=True),
        Input('context-menu-close-store', 'data'),
        prevent_initial_call=True,
    )
    def close_menu(close_event):
        if not close_event:
            raise PreventUpdate
        return False

    # ── Delete Peak ───────────────────────────────────────────────────
    @app.callback(
        [Output('context-menu', 'opened', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('ctx-delete-item', 'n_clicks'),
        [State('context-menu-store', 'data'),
         State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def delete_peak(n_clicks, store, peak_counter, render_counter):
        if not n_clicks or not store or not store.get('peak_id'):
            raise PreventUpdate
        fid, _peak = _find_peak(store['peak_id'])
        if fid is None:
            return False, dash.no_update, dash.no_update
        ps.save_undo()
        ps.remove_peak(fid, store['peak_id'])
        ps.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"context-menu delete: {store['peak_id']} from {fid}")
        return False, (peak_counter or 0) + 1, (render_counter or 0) + 1

    # ── Rename: open modal prefilled ──────────────────────────────────
    @app.callback(
        [Output('ctx-rename-modal', 'opened'),
         Output('ctx-rename-input', 'value'),
         Output('context-menu', 'opened', allow_duplicate=True)],
        Input('ctx-rename-item', 'n_clicks'),
        State('context-menu-store', 'data'),
        prevent_initial_call=True,
    )
    def open_rename(n_clicks, store):
        if not n_clicks or not store or not store.get('peak_id'):
            raise PreventUpdate
        _fid, peak = _find_peak(store['peak_id'])
        current = (peak.label or peak.name) if peak else ''
        return True, current, False

    # ── Rename: save ──────────────────────────────────────────────────
    @app.callback(
        [Output('ctx-rename-modal', 'opened', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('ctx-rename-save', 'n_clicks'),
        [State('ctx-rename-input', 'value'),
         State('context-menu-store', 'data'),
         State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def save_rename(n_clicks, new_name, store, peak_counter, render_counter):
        if not n_clicks or not store or not store.get('peak_id'):
            raise PreventUpdate
        name = (new_name or '').strip()
        if not name:
            return False, dash.no_update, dash.no_update
        fid, peak = _find_peak(store['peak_id'])
        if fid is None:
            return False, dash.no_update, dash.no_update
        # rename_peak sets name and propagates to grouped peaks; also set label
        # so the compound name shows above the peak on the plot.
        ps.rename_peak(fid, store['peak_id'], name)
        if peak is not None:
            peak.label = name
        log.debug(f"context-menu rename: {store['peak_id']} -> {name}")
        return False, (peak_counter or 0) + 1, (render_counter or 0) + 1

    # ── Integrate in All Files ────────────────────────────────────────
    @app.callback(
        [Output('context-menu', 'opened', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('ctx-status', 'children')],
        Input('ctx-integrate-item', 'n_clicks'),
        [State('context-menu-store', 'data'),
         State('int-rt-tolerance', 'value'),
         State('peak-change-trigger', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def integrate_all(n_clicks, store, tolerance, peak_counter, render_counter):
        if not n_clicks or not store or not store.get('peak_id'):
            raise PreventUpdate
        src_fid, src_peak = _find_peak(store['peak_id'])
        if src_fid is None:
            return False, dash.no_update, dash.no_update, dash.no_update

        tol = float(tolerance) if tolerance else 0.3
        targets = [f for f in _overlay_group_files(src_fid) if f != src_fid]
        if not targets:
            return False, dash.no_update, dash.no_update, 'Only one file in group.'

        ps.save_undo()
        matched = 0
        for fid in targets:
            time_arr, signal_arr = get_xy_arrays(data_manager, fid)
            if time_arr is None:
                continue
            # Note: integrates against a local straight baseline; per-file
            # baseline correction (IntegrationService) is not applied in v1.
            res = ps.find_matching_peak(fid, src_peak.rt, tol, signal_arr, time_arr)
            if not res:
                continue
            ps.add_baseline_peak(
                file_id=fid,
                area=res['area'], height=res['height'], apex_x=res['apex_x'],
                poly_x=res['poly_x'], poly_y=res['poly_y'],
                p_line=res['p_line'], q1=res['q1'], q2=res['q2'],
                source='cross_integrated',
                name=src_peak.name,
                label=src_peak.label or None,
            )
            matched += 1

        ps.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())

        n_targets = len(targets)
        if matched == n_targets:
            status = f'Integrated in {matched}/{n_targets} files.'
        else:
            status = f'Integrated in {matched}/{n_targets} files (peak not found in {n_targets - matched}).'
        log.debug(f"context-menu integrate-all: {status}")
        return False, (peak_counter or 0) + 1, (render_counter or 0) + 1, status
