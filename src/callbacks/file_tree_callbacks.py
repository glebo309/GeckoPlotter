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
         Output({'type': 'bundle-children', 'index': dash.dependencies.MATCH}, 'style')],
        Input({'type': 'expand-btn', 'index': dash.dependencies.MATCH}, 'n_clicks'),
        State({'type': 'bundle-children', 'index': dash.dependencies.MATCH}, 'style'),
        prevent_initial_call=True
    )
    def toggle_bundle_expansion(n_clicks, current_style):
        """Toggle bundle expansion/collapse and update button icon."""
        if not n_clicks:
            return dash.no_update, dash.no_update

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

        return new_icon, {**current_style, 'display': new_display}

    @app.callback(
        Output('active-file', 'data', allow_duplicate=True),
        Input({'type': 'expand-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def select_bundle_on_expand(n_clicks_list):
        """Select the bundle when its expand button is clicked."""
        if not any(n_clicks_list):
            return dash.no_update
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update
        try:
            import json
            component_id = json.loads(ctx.triggered[0]['prop_id'].rsplit('.', 1)[0])
            return component_id['index']
        except Exception:
            return dash.no_update

    # UV-Vis file collapse/expand callback
    @app.callback(
        [Output({'type': 'collapse-btn', 'index': dash.dependencies.MATCH}, 'children'),
         Output({'type': 'file-children', 'index': dash.dependencies.MATCH}, 'style')],
        Input({'type': 'collapse-btn', 'index': dash.dependencies.MATCH}, 'n_clicks'),
        State({'type': 'file-children', 'index': dash.dependencies.MATCH}, 'style'),
        prevent_initial_call=True
    )
    def toggle_file_expansion(n_clicks, current_style):
        """Toggle UV-Vis file expansion/collapse and update button icon."""
        if not n_clicks:
            return dash.no_update, dash.no_update
        
        current_display = current_style.get('display', 'none')  # Default collapsed
        new_display = 'block' if current_display == 'none' else 'none'
        new_icon = '▼' if new_display == 'block' else '▶'  # Expanded or collapsed
        
        return new_icon, {**current_style, 'display': new_display}

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('pub-selections', 'data', allow_duplicate=True)],
        Input({'type': 'delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State('loaded-files', 'data'),
         State('active-file', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_file_deletion(n_clicks_list, current_files, active_file_id, render_counter):
        if not any(n_clicks_list):
            return (dash.no_update,) * 8

        ctx = callback_context
        if not ctx.triggered:
            return (dash.no_update,) * 8

        triggered_id = ctx.triggered[0]['prop_id']
        try:
            import json
            component_id = json.loads(triggered_id.rsplit('.', 1)[0])
            file_id = component_id['index']
        except:
            return (dash.no_update,) * 8

        log.debug(f"Deleting file/bundle: {file_id}")

        files_to_remove = []

        if '|' in file_id:
            parent_file_id, well_name = file_id.split('|', 1)
            log.debug(f"Deleting well: {well_name} from parent file: {parent_file_id}")

            parent_file_data = data_manager.get_data_by_id(parent_file_id)
            if _is_multi_well(parent_file_data):
                filled_wells = parent_file_data.get('metadata', {}).get('filled_wells', [])
                if well_name in filled_wells:
                    filled_wells.remove(well_name)
                    parent_file_data['metadata']['filled_wells'] = filled_wells
                    log.debug(f"Removed well {well_name} from parent file metadata")

                    if 'data' in parent_file_data and parent_file_data['data'] is not None:
                        df = parent_file_data['data']
                        if well_name in df.columns:
                            df = df.drop(columns=[well_name])
                            parent_file_data['data'] = df

                    if not filled_wells:
                        log.debug(f"No wells left, deleting entire parent file: {parent_file_id}")
                        if parent_file_id in data_manager.loaded_data:
                            del data_manager.loaded_data[parent_file_id]
                        updated_files = [f for f in current_files if f.get('id') != parent_file_id]
                    else:
                        updated_files = current_files.copy()
                else:
                    log.warning(f"Well {well_name} not found in parent file")
                    updated_files = current_files.copy()
            else:
                log.error(f"Parent file not found or not multi-well: {parent_file_id}")
                updated_files = current_files.copy()

        elif data_manager.bundle_manager.get_bundle_by_id(file_id) or data_manager.get_lcms_bundle_by_id(file_id):
            bundle = data_manager.bundle_manager.get_bundle_by_id(file_id)
            lcms_bundle = data_manager.get_lcms_bundle_by_id(file_id)
            if bundle:
                bundle_base_name = bundle.base_name
            elif lcms_bundle:
                bundle_base_name = file_id[: -len('_LCMS_BUNDLE')]

            files_to_remove = []
            for f in current_files:
                file_name = f.get('name', '')
                if bundle:
                    if (bundle_base_name in file_name and
                        (file_name.endswith('_UV_VIS_1.txt') or
                         file_name.endswith('_Chromatogram.txt') or
                         file_name.endswith('_Integration.txt') or
                         file_name.endswith('_Peak Analysis.txt') or
                         file_name.endswith('_SST.txt'))):
                        files_to_remove.append(f.get('id'))
                else:
                    _, bundle_record = data_manager.find_lcms_bundle_for_component(f.get('id'))
                    if bundle_record and bundle_record.get('base_name') == bundle_base_name:
                        files_to_remove.append(f.get('id'))
                    elif file_name.startswith(bundle_base_name):
                        files_to_remove.append(f.get('id'))
            if lcms_bundle:
                files_to_remove.append(file_id)

            if lcms_bundle:
                data_manager.remove_lcms_bundle(bundle_base_name)

            updated_files = [f for f in current_files if f.get('id') not in files_to_remove]
            if bundle:
                data_manager.bundle_manager.remove_bundle(file_id)
            if lcms_bundle:
                updated_files = [f for f in updated_files if f.get('id') != file_id]

        else:
            log.debug(f"Deleting individual file: {file_id}")

            lcms_base, lcms_bundle = data_manager.find_lcms_bundle_for_component(file_id)
            is_lcms_component_deletion = False
            lcms_parent_id = None
            if lcms_bundle:
                if not hasattr(data_manager, 'collapse_state'):
                    data_manager.collapse_state = {}
                lcms_parent_id = f"{lcms_base}_LCMS_BUNDLE"
                data_manager.collapse_state[lcms_parent_id] = 'expanded'
                is_lcms_component_deletion = True
                bundle_files = lcms_bundle.get('files', [])
                if file_id in bundle_files:
                    bundle_files.remove(file_id)
                if file_id in lcms_bundle.get('records', {}):
                    lcms_bundle['records'].pop(file_id, None)
                lcms_bundle.setdefault('components', {}).pop(file_id, None)

            data_manager.remove_bundle(file_id)

            updated_files = [f for f in current_files if f.get('id') != file_id]

        # Clean up peaks for all deleted files/bundles
        deleted_ids = set(files_to_remove) if files_to_remove else set()
        deleted_ids.add(file_id)
        for did in deleted_ids:
            data_manager.peak_service.clear_peaks(did)

        # Rebuild tree
        parent_to_expand = None
        if '|' in file_id:
            parent_to_expand = file_id.split('|')[0]
        elif 'is_lcms_component_deletion' in locals() and is_lcms_component_deletion and lcms_parent_id:
            parent_to_expand = lcms_parent_id

        if parent_to_expand:
            if not hasattr(data_manager, 'collapse_state'):
                data_manager.collapse_state = {}
            data_manager.collapse_state[parent_to_expand] = 'expanded'

        if hasattr(data_manager, '_last_processed_files'):
            delattr(data_manager, '_last_processed_files')
        if hasattr(data_manager, '_last_tree_items'):
            delattr(data_manager, '_last_tree_items')

        updated_files = data_manager.get_loaded_files_list()

        from callbacks.upload_callbacks import render_file_tree_with_bundles
        tree_items = render_file_tree_with_bundles(updated_files, data_manager)

        log.debug(f"Delete complete. Remaining files: {len(updated_files)}")

        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        active_was_deleted = False
        if active_file_id:
            main_active = active_file_id.split('|')[0] if '|' in active_file_id else active_file_id
            if main_active in (files_to_remove or []) or file_id == active_file_id or file_id == main_active:
                active_was_deleted = True

        if active_was_deleted or not updated_files:
            new_active = updated_files[0]['id'] if updated_files else None
            table_editor = create_data_table_editor(None, table_id='pub-table')
            pub_data = None
            pub_sel = get_empty_selections()
        else:
            new_active = active_file_id
            table_editor = dash.no_update
            pub_data = dash.no_update
            pub_sel = dash.no_update

        return (updated_files, tree_items, (render_counter or 0) + 1, new_active,
                html.Div("Select a file to view data details", style={'color': '#666', 'padding': '20px'}),
                table_editor, pub_data, pub_sel)

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
        The eye icon stays unchanged; CSS dimming via clientside callback
        handles the visual feedback (no button style changes = no layout shift)."""
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

        bundle = data_manager.bundle_manager.get_bundle_by_id(clicked_file_id)
        if bundle:
            for aux_file in bundle.auxiliary_files:
                aux_file_id = aux_file.get('id')
                if aux_file_id:
                    data_manager.visibility_state[aux_file_id] = new_visibility
        else:
            lcms_bundle = data_manager.get_lcms_bundle_by_id(clicked_file_id)
            if lcms_bundle:
                for comp_id in lcms_bundle.get('files', []):
                    data_manager.visibility_state[comp_id] = new_visibility
            else:
                file_data = data_manager.get_data_by_id(clicked_file_id)
                if _is_multi_well(file_data):
                    filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
                    for well in filled_wells:
                        data_manager.visibility_state[f"{clicked_file_id}|{well}"] = new_visibility

        hidden_ids = [fid for fid, vis in data_manager.visibility_state.items() if not vis]

        return (render_counter or 0) + 1, hidden_ids

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

