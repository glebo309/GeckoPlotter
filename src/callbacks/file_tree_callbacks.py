# =============================================================================
# File: callbacks/file_tree_callbacks.py
# =============================================================================
"""
File tree interaction callbacks for GeckoPlotter V2.
"""

import logging

import dash
from dash import Input, Output, State, callback_context, html
import os
from typing import List, Dict, Any

from dash.exceptions import PreventUpdate
from services.data_store import DataStore as DataManager

log = logging.getLogger(__name__)


def _is_multi_well(file_data):
    """Check if file has individually-selectable Y columns (wells/channels)."""
    if file_data is None:
        return False
    sr = file_data.get('standardized')
    if sr is not None:
        from src.ingestion.types import PlotHint
        return sr.plot_hint == PlotHint.MULTI_Y
    metadata = file_data.get('metadata', {})
    return bool(metadata.get('filled_wells'))


def register_file_tree_callbacks(app: dash.Dash, data_manager: DataManager) -> None:
    """Register file tree interaction callbacks."""
    @app.callback(
        [Output({'type': 'expand-btn', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'bundle-children', 'index': dash.dependencies.MATCH}, 'style'),
         Output({'type': 'expand-btn', 'index': dash.dependencies.MATCH}, 'aria-expanded')],
        Input({'type': 'expand-btn', 'index': dash.dependencies.MATCH}, 'n_clicks'),
        State({'type': 'bundle-children', 'index': dash.dependencies.MATCH}, 'style'),
        prevent_initial_call=True
    )
    def toggle_bundle_expansion(n_clicks, current_style):
        """Toggle bundle expansion/collapse and update button icon."""
        if not n_clicks:
            return (dash.no_update,) * 3

        current_display = current_style.get('display', 'block')
        new_display = 'none' if current_display == 'block' else 'block'
        new_icon = '▶' if new_display == 'none' else '▼'

        ctx = callback_context
        if ctx.triggered:
            try:
                import json
                component_id = json.loads(ctx.triggered[0]['prop_id'].rsplit('.', 1)[0])
                bundle_id = component_id['index']
                if not hasattr(data_manager, 'collapse_state'):
                    data_manager.collapse_state = {}
                data_manager.collapse_state[bundle_id] = 'expanded' if new_display == 'block' else 'collapsed'
            except Exception:
                pass

        return new_icon, {**current_style, 'display': new_display}, str(new_display == 'block').lower()

    # UV-Vis file collapse/expand callback
    @app.callback(
        [Output({'type': 'collapse-btn', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'file-children', 'index': dash.dependencies.MATCH}, 'style'),
         Output({'type': 'collapse-btn', 'index': dash.dependencies.MATCH}, 'aria-expanded')],
        Input({'type': 'collapse-btn', 'index': dash.dependencies.MATCH}, 'n_clicks'),
        State({'type': 'file-children', 'index': dash.dependencies.MATCH}, 'style'),
        prevent_initial_call=True
    )
    def toggle_file_expansion(n_clicks, current_style):
        """Toggle UV-Vis file expansion/collapse and update button icon."""
        if not n_clicks:
            return (dash.no_update,) * 3
        
        current_display = current_style.get('display', 'none')  # Default collapsed
        new_display = 'block' if current_display == 'none' else 'none'
        new_icon = '▼' if new_display == 'block' else '▶'  # Expanded or collapsed
        try:
            import json
            file_id = json.loads(callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0])['index']
            data_manager.collapse_state[file_id] = 'expanded' if new_display == 'block' else 'collapsed'
        except (KeyError, ValueError, IndexError):
            pass
        
        return new_icon, {**current_style, 'display': new_display}, str(new_display == 'block').lower()

    removal_outputs = [
        Output('loaded-files', 'data', allow_duplicate=True),
        Output('file-tree', 'children', allow_duplicate=True),
        Output('render-trigger', 'data', allow_duplicate=True),
        Output('active-file', 'data', allow_duplicate=True),
        Output('metadata-container', 'children', allow_duplicate=True),
        Output('table-editor-container', 'children', allow_duplicate=True),
        Output('pub-data-store', 'data', allow_duplicate=True),
        Output('pub-selections', 'data', allow_duplicate=True),
        Output('file-removal-feedback', 'style', allow_duplicate=True),
        Output('file-removal-message', 'children', allow_duplicate=True),
        Output('undo-file-removal-btn', 'disabled', allow_duplicate=True),
        Output('hidden-files', 'data', allow_duplicate=True),
    ]

    def removal_response(record, active_file, render_counter, restored=False):
        from callbacks.upload_callbacks import render_file_tree_with_bundles
        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        files = data_manager.get_loaded_files_list()
        active_parent = (active_file or '').split('|')[0]
        active_exists = bool(active_file and data_manager.get_data_by_id(active_parent))
        if not restored and active_file in record.removed_ids:
            active_exists = False
        if not active_exists:
            remaining = data_manager.get_bundle(files[0]['id']) if files else None
            active_file = remaining.primary.component_id if remaining and remaining.primary else None
        for cache_name in ('_last_processed_files', '_last_tree_items'):
            if hasattr(data_manager, cache_name):
                delattr(data_manager, cache_name)
        tree = render_file_tree_with_bundles(files, data_manager)
        message = f'Restored {record.label}' if restored else f'Removed {record.label}'
        return (files, tree, (render_counter or 0) + 1, active_file,
                dash.no_update if active_exists else html.Div('Select a file to view data details'),
                dash.no_update if active_exists else create_data_table_editor(None, table_id='pub-table'),
                dash.no_update if active_exists else None,
                dash.no_update if active_exists else get_empty_selections(),
                {'display': 'flex'}, message, not data_manager.file_removal_service.can_undo,
                [fid for fid, visible in data_manager.visibility_state.items() if not visible])

    @app.callback(
        removal_outputs,
        Input({'type': 'delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State('loaded-files', 'data'), State('active-file', 'data'), State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_file_deletion(n_clicks_list, current_files, active_file_id, render_counter):
        if not any(n_clicks_list) or not callback_context.triggered:
            raise PreventUpdate
        try:
            import json
            trigger = callback_context.triggered[0]
            if not trigger.get('value'):
                raise PreventUpdate
            file_id = json.loads(trigger['prop_id'].rsplit('.', 1)[0])['index']
        except (KeyError, ValueError, TypeError):
            raise PreventUpdate
        record = data_manager.file_removal_service.remove(file_id, active_file=active_file_id)
        if record is None:
            raise PreventUpdate
        return removal_response(record, active_file_id, render_counter)

    @app.callback(removal_outputs, Input('undo-file-removal-btn', 'n_clicks'),
                  State('render-trigger', 'data'), prevent_initial_call=True)
    def undo_file_removal(n_clicks, render_counter):
        if not n_clicks:
            raise PreventUpdate
        record = data_manager.file_removal_service.undo()
        if record is None:
            raise PreventUpdate
        return removal_response(record, record.active_file, render_counter, restored=True)

    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('hidden-files', 'data')],
        Input({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'id'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_visibility_toggles(n_clicks_list, button_ids, render_counter):
        """Toggle visibility state, bump render-trigger, publish hidden IDs.
        The clientside callback updates the eye state without rebuilding the tree."""
        if not any(n_clicks_list):
            raise PreventUpdate

        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        try:
            import json
            component_id = json.loads(ctx.triggered[0]['prop_id'].rsplit('.', 1)[0])
            clicked_file_id = component_id['index']
        except Exception as e:
            log.error(f"Error parsing callback trigger: {e}")
            raise PreventUpdate

        if not hasattr(data_manager, 'visibility_state'):
            data_manager.visibility_state = {}

        is_visible = data_manager.visibility_state.get(clicked_file_id, True)
        new_visibility = not is_visible
        data_manager.visibility_state[clicked_file_id] = new_visibility

        log.debug(f"Toggling visibility for {clicked_file_id}: {'visible' if new_visibility else 'hidden'}")

        bundle = data_manager.get_bundle(clicked_file_id)
        if bundle:
            for component in bundle.component_list:
                data_manager.visibility_state[component.component_id] = new_visibility
                for well in component.metadata.get('filled_wells', []):
                    data_manager.visibility_state[f"{component.component_id}|{well}"] = new_visibility
        else:
            file_data = data_manager.get_data_by_id(clicked_file_id)
            if _is_multi_well(file_data):
                for well in file_data.get('metadata', {}).get('filled_wells', []):
                    data_manager.visibility_state[f"{clicked_file_id}|{well}"] = new_visibility


        # The bundle eye reflects whether any component remains visible. A
        # child can be shown after Hide bundle without leaving its parent dimmed.
        parent_bundle = data_manager.get_bundle_for_component(clicked_file_id)
        if parent_bundle is not None and parent_bundle.bundle_id != clicked_file_id:
            data_manager.visibility_state[parent_bundle.bundle_id] = any(
                data_manager.visibility_state.get(c.component_id, True)
                for c in parent_bundle.component_list)

        hidden_ids = [fid for fid, vis in data_manager.visibility_state.items() if not vis]

        return (render_counter or 0) + 1, hidden_ids

    @app.callback(
        Output('hidden-files', 'data', allow_duplicate=True),
        Input('loaded-files', 'data'),
        State('hidden-files', 'data'),
        prevent_initial_call=True,
    )
    def sync_loaded_file_visibility(_loaded_files, browser_hidden):
        """Publish import defaults as well as explicit eye toggles to the tree.

        The browser reapplies this store after tree DOM updates, so it must
        include paired exports hidden by ingestion before their first render.
        """
        hidden = [fid for fid, visible in data_manager.visibility_state.items() if not visible]
        return dash.no_update if set(hidden) == set(browser_hidden or []) else hidden

    @app.callback(
        Output('file-tree', 'children', allow_duplicate=True),
        [Input('loaded-files', 'data'),
         Input('active-plot-tab', 'data'),
         Input('file-order', 'data')],
        [State('active-file', 'data')],
        prevent_initial_call=True
    )
    def sync_file_tree_selection(loaded_files, active_plot_tab, file_order, active_file_id):
        """Re-render the file tree grouped by overlay type. Selection highlight
        is applied client-side via file-tree-ui.js (CSS-only, no re-render)."""
        ctx = dash.callback_context
        trigger = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0] if ctx.triggered else ''
        if trigger == 'file-order':
            raise PreventUpdate

        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected

        records = loaded_files or []
        return render_file_tree_with_bundles_selected(
            records, data_manager, active_file_id, active_plot_tab=active_plot_tab,
            file_order=file_order or {})

    @app.callback(
        [Output('file-order', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True)],
        Input({'type': 'group-sort-btn', 'index': dash.ALL}, 'n_clicks'),
        [State('file-order', 'data'),
         State('loaded-files', 'data'),
         State('active-file', 'data'),
         State('active-plot-tab', 'data')],
        prevent_initial_call=True
    )
    def toggle_group_sort(n_clicks_list, file_order, loaded_files, active_file, active_plot_tab):
        """Toggle sort direction when a group sort button is clicked."""
        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
        ctx = dash.callback_context
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        triggered = ctx.triggered[0]
        import json
        prop_id = triggered['prop_id'].rsplit('.', 1)[0]
        try:
            btn_id = json.loads(prop_id)
        except (json.JSONDecodeError, TypeError):
            raise PreventUpdate
        group_id = btn_id.get('index')
        if not group_id:
            raise PreventUpdate

        file_order = dict(file_order or {})
        current = file_order.get(group_id, {})
        had_custom_order = 'order' in current
        current_dir = current.get('sort_dir', 'asc')
        if had_custom_order:
            new_dir = 'asc'
        else:
            new_dir = 'desc' if current_dir == 'asc' else 'asc'
        file_order[group_id] = {'sort_dir': new_dir}
        tree = render_file_tree_with_bundles_selected(
            loaded_files or [], data_manager, active_file,
            active_plot_tab=active_plot_tab, file_order=file_order)
        return file_order, tree

    @app.callback(
        [Output('file-order', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True)],
        Input('file-reorder-event', 'data'),
        [State('file-order', 'data'),
         State('loaded-files', 'data'),
         State('active-file', 'data'),
         State('active-plot-tab', 'data')],
        prevent_initial_call=True
    )
    def handle_drag_reorder(event, file_order, loaded_files, active_file, active_plot_tab):
        """Update file order and re-render tree when user drags files to reorder."""
        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
        if not event or not event.get('group_id') or not event.get('order'):
            raise PreventUpdate
        file_order = dict(file_order or {})
        file_order[event['group_id']] = {
            'sort_dir': file_order.get(event['group_id'], {}).get('sort_dir', 'asc'),
            'order': event['order'],
        }
        tree = render_file_tree_with_bundles_selected(
            loaded_files or [], data_manager, active_file,
            active_plot_tab=active_plot_tab, file_order=file_order)
        return file_order, tree

    # -- Cross-group drag-drop: move file to different group / create new group --
    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('group-move-event', 'data'),
        [State('loaded-files', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_group_move(event, loaded_files, render_counter):
        """Move a file/bundle to a different overlay group (or create a new one)."""
        if not event or not event.get('file_id') or not event.get('source_group'):
            raise PreventUpdate

        file_id = event['file_id']
        target_group = event.get('target_group')

        if not hasattr(data_manager, 'group_overrides'):
            data_manager.group_overrides = {}

        if target_group:
            parts = target_group.replace('tab-', '', 1).rsplit('_', 1)
            if len(parts) == 2:
                cat, x_axis = parts
            else:
                cat, x_axis = target_group, 'X'
            data_manager.group_overrides[file_id] = (cat, x_axis)
        else:
            data_manager.group_overrides[file_id] = (f'custom_{file_id[:8]}', 'X')

        return loaded_files, (render_counter or 0) + 1

    # Store collapse states in data manager
    if not hasattr(data_manager, 'collapse_state'):
        data_manager.collapse_state = {}
    if not hasattr(data_manager, 'group_overrides'):
        data_manager.group_overrides = {}

