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


def apply_group_move(dm, file_id, target_group=None, group_key=None):
    """Regroup a bundle so its signals are drawn in the target group's figure.

    *target_group* is a plot-tab id from the tree (None creates a new custom
    group). The override stores the target's exact group key, so the plot tab
    matches by key; moving a file back to its natural group drops the override.
    *group_key* (new-group case only) reuses an existing custom key so several
    files dragged together share one new figure. Returns the new group key, or None.
    """
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
    if not hasattr(dm, 'group_overrides'):
        dm.group_overrides = {}
    owner = dm.get_bundle_for_component(file_id) if not dm.get_bundle(file_id) else None
    if owner:
        file_id = owner.bundle_id

    if not target_group:
        key = tuple(group_key) if group_key else (f'custom_{file_id[:8]}', 'X')
        dm.group_overrides[file_id] = key
        return key
    target = None
    for fid, fdata in dm.loaded_data.items():
        group = _get_overlay_group(fdata.get('metadata', {}), fdata, file_id=fid, dm=dm)
        if _tab_id_from_group(group) == target_group:
            target = group
            break
    if target is None:
        parts = target_group.replace('tab-', '', 1).rsplit('_', 1)
        target = tuple(parts) if len(parts) == 2 else (target_group, 'X')
    entry = dm.get_data_by_id(file_id) or {}
    natural = _get_overlay_group(entry.get('metadata', {}), entry, file_id=file_id,
                                 dm=dm, ignore_override=True)
    if tuple(target) == tuple(natural):
        dm.group_overrides.pop(file_id, None)
    else:
        dm.group_overrides[file_id] = tuple(target)


def _bulk_targets(clicked_id, multi_selection):
    """Rows an eye/trash click applies to: the whole Cmd/Shift-click multi-selection
    when the clicked row is part of it, otherwise just the clicked row."""
    selected = [fid for fid in (multi_selection or []) if isinstance(fid, str)]
    return selected if len(selected) > 1 and clicked_id in selected else [clicked_id]


def _apply_visibility(data_manager, file_id, new_visibility):
    """Set one tree row's visibility, cascading to its bundle components / wells and parent bundle."""
    data_manager.visibility_state[file_id] = new_visibility

    bundle = data_manager.get_bundle(file_id)
    if bundle and bundle.bundle_type.value in ('chromatogram', 'lcms'):
        from services.channel_visibility import set_sample_visibility
        set_sample_visibility(data_manager, file_id, new_visibility)
    elif bundle:
        for component in bundle.component_list:
            data_manager.visibility_state[component.component_id] = new_visibility
            for well in component.metadata.get('filled_wells', []):
                data_manager.visibility_state[f"{component.component_id}|{well}"] = new_visibility
    else:
        file_data = data_manager.get_data_by_id(file_id)
        if _is_multi_well(file_data):
            for well in file_data.get('metadata', {}).get('filled_wells', []):
                data_manager.visibility_state[f"{file_id}|{well}"] = new_visibility

    # The bundle eye reflects whether any component remains visible. A
    # child can be shown after Hide bundle without leaving its parent dimmed.
    parent_bundle = data_manager.get_bundle_for_component(file_id)
    if parent_bundle is not None and parent_bundle.bundle_id != file_id:
        if new_visibility:
            getattr(data_manager, '_hidden_sample_channels', {}).pop(parent_bundle.bundle_id, None)
        data_manager.visibility_state[parent_bundle.bundle_id] = any(
            data_manager.visibility_state.get(c.component_id, True)
            for c in parent_bundle.component_list)


def same_tree(tree, shown) -> bool:
    """True when the rendered ``tree`` is what the browser shows (``shown``, the file-tree children as sent back)."""
    import json
    from plotly.utils import PlotlyJSONEncoder
    try:
        return json.loads(json.dumps(tree, cls=PlotlyJSONEncoder)) == shown
    except (TypeError, ValueError):
        return False


def register_file_tree_callbacks(app: dash.Dash, data_manager: DataManager) -> None:
    """Register file tree interaction callbacks."""
    @app.callback(
        Output('plot-channel-controls', 'children'),
        Input('file-tree', 'children'), Input('active-plot-tab', 'data'), Input('view-mode', 'data'),
        Input('hidden-files', 'data'),
    )
    def update_plot_channel_controls(_tree, active_tab, view_mode, _hidden=None):
        from services.channel_visibility import channel_controls, group_bundle_ids
        from callbacks.upload_callbacks import _render_channel_controls
        if not active_tab or view_mode != 'raw':
            return []
        members = group_bundle_ids(data_manager, active_tab)
        controls = channel_controls(data_manager, members)
        if not controls:
            return []
        return _render_channel_controls(controls, active_tab)

    @app.callback(
        Output('pda-channel-controls', 'children'),
        Input('file-tree', 'children'), Input('active-plot-tab', 'data'),
        Input('view-mode', 'data'), Input('hidden-files', 'data'),
    )
    def update_pda_channel_controls(_tree, active_tab, view_mode, _hidden=None):
        from services.channel_visibility import channel_controls, group_bundle_ids
        from callbacks.upload_callbacks import _render_channel_manager
        if not active_tab or view_mode != 'raw':
            return []
        controls = channel_controls(data_manager, group_bundle_ids(data_manager, active_tab))
        return _render_channel_manager(controls, active_tab) if controls else []

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('custom-plot-figures', 'data', allow_duplicate=True),
         Output('current-plot-settings', 'data', allow_duplicate=True)],
        Input('dataset-name-edit', 'data'),
        State('render-trigger', 'data'), State('custom-plot-figures', 'data'), State('current-plot-settings', 'data'),
        prevent_initial_call=True,
    )
    def rename_dataset(event, render_counter, custom_figures, settings):
        from callbacks.upload_callbacks import render_file_tree_with_bundles
        from services.dataset_names import update_named_figures, rename_style_settings, trace_display_name
        old_names = {fid: trace_display_name(entry) for fid, entry in data_manager.loaded_data.items()}
        if not event or not data_manager.rename_dataset(event.get('file_id'), event.get('text')):
            raise PreventUpdate
        files = data_manager.get_loaded_files_list()
        renames = {fid: (old_names[fid], trace_display_name(entry))
                   for fid, entry in data_manager.loaded_data.items()
                   if fid in old_names and old_names[fid] != trace_display_name(entry)}
        data_manager._shared_plot_settings = rename_style_settings(data_manager._shared_plot_settings, renames)
        data_manager.file_ui_state = rename_style_settings(data_manager.file_ui_state, renames)
        updated_settings = rename_style_settings(settings, renames)
        return (files, render_file_tree_with_bundles(files, data_manager),
                (render_counter or 0) + 1,
                rename_style_settings(update_named_figures(custom_figures, data_manager), renames),
                updated_settings if updated_settings != settings else dash.no_update)

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

    @app.callback(
        [Output({'type': 'group-collapse-btn', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'file-group', 'index': dash.dependencies.MATCH}, 'style'),
         Output({'type': 'group-collapse-btn', 'index': dash.dependencies.MATCH}, 'aria-expanded')],
        Input({'type': 'group-collapse-btn', 'index': dash.dependencies.MATCH}, 'n_clicks'),
        State({'type': 'file-group', 'index': dash.dependencies.MATCH}, 'style'),
        prevent_initial_call=True,
    )
    def toggle_group_expansion(n_clicks, current_style):
        if not n_clicks or not callback_context.triggered:
            return (dash.no_update,) * 3
        import json
        group_id = json.loads(callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0])['index']
        expanded = (current_style or {}).get('display') == 'none'
        data_manager.collapse_state[group_id] = 'expanded' if expanded else 'collapsed'
        from services.channel_visibility import group_bundle_ids
        from callbacks.viz_callbacks import _get_overlay_group, _tab_label_from_group
        members = group_bundle_ids(data_manager, group_id)
        label = 'Data'
        if members:
            entry = data_manager.get_data_by_id(members[0])
            group = _get_overlay_group(entry['metadata'], entry, members[0], data_manager)
            label = _tab_label_from_group(group, data_manager)
        # The group title may be run-specific even though its channels span LCMS runs.
        for bundle in data_manager.iter_bundles():
            from callbacks.viz_callbacks import _tab_id_from_group
            entry = data_manager.get_data_by_id(bundle.bundle_id)
            group = _get_overlay_group(entry['metadata'], entry, bundle.bundle_id, data_manager)
            if _tab_id_from_group(group) == group_id:
                label = _tab_label_from_group(group, data_manager)
                break
        return ([html.Span('▼' if expanded else '▶', className='group-disclosure-indicator'), html.Span(label)],
                {**(current_style or {}), 'display': 'block' if expanded else 'none'}, str(expanded).lower())

    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('hidden-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True)],
        Input({'type': 'group-channel-btn', 'group': dash.dependencies.ALL, 'channel': dash.dependencies.ALL}, 'n_clicks'),
        [State('render-trigger', 'data'), State('loaded-files', 'data'),
         State('active-file', 'data'), State('active-plot-tab', 'data'), State('file-order', 'data')],
        prevent_initial_call=True,
    )
    def toggle_group_channel(clicks, counter, files, active_file, active_tab, file_order):
        if not callback_context.triggered or not callback_context.triggered[0].get('value'):
            raise PreventUpdate
        previous_active = active_file
        previous_visibility = dict(data_manager.visibility_state)
        import json
        from services.channel_visibility import group_bundle_ids, toggle_channel, visible_component_id
        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
        control = json.loads(callback_context.triggered[0]['prop_id'].rsplit('.', 1)[0])
        members = group_bundle_ids(data_manager, control['group'])
        if not toggle_channel(data_manager, members, control['channel']):
            raise PreventUpdate
        bundle = data_manager.get_bundle_for_component(active_file) or data_manager.get_bundle(active_file)
        if bundle and bundle.bundle_id in members:
            active_file = visible_component_id(data_manager, bundle, active_file)
        tree = render_file_tree_with_bundles_selected(files, data_manager, active_file, active_tab, file_order)
        changed = data_manager.visibility_state != previous_visibility
        return ((counter or 0) + 1 if changed else dash.no_update,
                [fid for fid, visible in data_manager.visibility_state.items() if not visible] if changed else dash.no_update,
                tree, active_file if active_file != previous_active else dash.no_update)

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
            from services.channel_visibility import visible_component_id
            active_file = visible_component_id(data_manager, remaining) if remaining else None
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
        [State('loaded-files', 'data'), State('active-file', 'data'), State('render-trigger', 'data'),
         State('file-multi-selection', 'data')],
        prevent_initial_call=True,
    )
    def handle_file_deletion(n_clicks_list, current_files, active_file_id, render_counter, multi_selection=None):
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
        targets = _bulk_targets(file_id, multi_selection)
        if len(targets) > 1:
            record = data_manager.file_removal_service.remove_many(targets, active_file=active_file_id)
        else:
            record = data_manager.file_removal_service.remove(file_id, active_file=active_file_id)
        if record is None:
            raise PreventUpdate
        return removal_response(record, active_file_id, render_counter)

    @app.callback(removal_outputs,
        Input({'type':'remove-channel-btn','group':dash.dependencies.ALL,'channel':dash.dependencies.ALL}, 'n_clicks'),
        State('active-file','data'), State('render-trigger','data'), prevent_initial_call=True)
    def remove_group_channel(clicks, active_file, render_counter):
        if not callback_context.triggered or not callback_context.triggered[0].get('value'):
            raise PreventUpdate
        import json
        from services.channel_visibility import group_bundle_ids
        control = json.loads(callback_context.triggered[0]['prop_id'].rsplit('.',1)[0])
        record = data_manager.file_removal_service.remove_channels(
            group_bundle_ids(data_manager, control['group']), control['channel'], active_file=active_file)
        if record is None:
            raise PreventUpdate
        return removal_response(record, active_file, render_counter)

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
         State('render-trigger', 'data'),
         State('file-multi-selection', 'data')],
        prevent_initial_call=True
    )
    def handle_visibility_toggles(n_clicks_list, button_ids, render_counter, multi_selection=None):
        """Toggle visibility state, bump render-trigger, publish hidden IDs.
        The clientside callback updates the eye state without rebuilding the tree.
        Clicking the eye of a multi-selected row applies the clicked row's new state to every selected row."""
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

        targets = _bulk_targets(clicked_file_id, multi_selection)
        log.debug(f"Toggling visibility for {targets}: {'visible' if new_visibility else 'hidden'}")
        for file_id in targets:
            _apply_visibility(data_manager, file_id, new_visibility)

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
        [State('active-file', 'data'),
         State('file-tree', 'children')],
        prevent_initial_call=True
    )
    def sync_file_tree_selection(loaded_files, active_plot_tab, file_order, active_file_id, shown=None):
        """Re-render the file tree grouped by overlay type. Selection highlight
        is applied client-side via file-tree-ui.js (CSS-only, no re-render)."""
        ctx = dash.callback_context
        trigger = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0] if ctx.triggered else ''
        if trigger == 'file-order':
            raise PreventUpdate

        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected

        records = loaded_files or []
        if trigger == 'loaded-files' and active_file_id and not active_plot_tab:
            # First data: sync_plot_tabs is about to open the active file's plot tab; draw the tree for it (as the
            # upload did).
            from callbacks.viz_callbacks import _get_active_file_group, _tab_id_from_group
            group = _get_active_file_group(data_manager, active_file_id)
            active_plot_tab = _tab_id_from_group(group) if group else active_plot_tab
        tree = render_file_tree_with_bundles_selected(
            records, data_manager, active_file_id, active_plot_tab=active_plot_tab,
            file_order=file_order or {})
        # A new tree re-fires every button callback of the tree (and what waits on them) for nothing; the upload
        # usually sent this same tree a moment ago.
        if shown is not None and same_tree(tree, shown):
            raise PreventUpdate
        return tree

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

        # `file_ids` (multi-file drag) is optional; `file_id` stays the legacy single-file key.
        file_ids = [f for f in (event.get('file_ids') or []) if isinstance(f, str) and f]
        if event['file_id'] not in file_ids:
            file_ids.insert(0, event['file_id'])
        target_group = event.get('target_group')

        new_key = None
        for fid in file_ids:
            # Files dropped on "New figure" together share one new figure.
            new_key = apply_group_move(data_manager, fid, target_group,
                                       group_key=None if target_group else new_key) or new_key

        return loaded_files, (render_counter or 0) + 1

    # Store collapse states in data manager
    if not hasattr(data_manager, 'collapse_state'):
        data_manager.collapse_state = {}
    if not hasattr(data_manager, 'group_overrides'):
        data_manager.group_overrides = {}

