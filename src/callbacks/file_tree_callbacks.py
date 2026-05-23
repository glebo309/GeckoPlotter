# =============================================================================
# File: callbacks/file_tree_callbacks.py
# =============================================================================
"""
File tree interaction callbacks for GeckoPlotter V2.
"""

import dash
from dash import Input, Output, State, callback_context, html
import os
from typing import List, Dict, Any

from services.storage_manager import DataManager


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
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('pub-selections', 'data', allow_duplicate=True)],
        Input({'type': 'delete-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State('loaded-files', 'data'),
         State('active-file', 'data')],
        prevent_initial_call=True
    )
    def handle_file_deletion(n_clicks_list, current_files, active_file_id):
        if not any(n_clicks_list):
            return (dash.no_update,) * 8

        ctx = callback_context
        if not ctx.triggered:
            return (dash.no_update,) * 8

        # Find which delete button was clicked
        triggered_id = ctx.triggered[0]['prop_id']
        try:
            import json
            component_id = json.loads(triggered_id.rsplit('.', 1)[0])
            file_id = component_id['index']
        except:
            return (dash.no_update,) * 8

        print(f"🗑️ Deleting file/bundle: {file_id}")

        files_to_remove = []

        # Check if this is a well deletion (file_id contains |)
        if '|' in file_id:
            # This is a well deletion (e.g., "fileId|H1")
            parent_file_id, well_name = file_id.split('|', 1)
            print(f"🧪 Deleting well: {well_name} from parent file: {parent_file_id}")
            
            # Get parent file data
            parent_file_data = data_manager.get_data_by_id(parent_file_id)
            if parent_file_data and parent_file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
                # Remove the well from filled_wells list
                filled_wells = parent_file_data.get('metadata', {}).get('filled_wells', [])
                if well_name in filled_wells:
                    filled_wells.remove(well_name)
                    parent_file_data['metadata']['filled_wells'] = filled_wells
                    print(f"✅ Removed well {well_name} from parent file metadata")
                    
                    # Update the data by removing the well column
                    if 'data' in parent_file_data and parent_file_data['data'] is not None:
                        df = parent_file_data['data']
                        if well_name in df.columns:
                            df = df.drop(columns=[well_name])
                            parent_file_data['data'] = df
                            print(f"✅ Removed well {well_name} column from data")
                    
                    # If no wells left, delete the entire file
                    if not filled_wells:
                        print(f"🗑️ No wells left, deleting entire parent file: {parent_file_id}")
                        if parent_file_id in data_manager.loaded_data:
                            del data_manager.loaded_data[parent_file_id]
                        
                        # Remove from file records
                        updated_files = []
                        for f in current_files:
                            if f.get('id') != parent_file_id:
                                updated_files.append(f)
                            else:
                                print(f"✅ Removed parent file from records: {f.get('name')}")
                    else:
                        # Keep the file but update it
                        updated_files = current_files.copy()
                        print(f"✅ Updated parent file, {len(filled_wells)} wells remaining: {filled_wells}")
                else:
                    print(f"⚠️ Well {well_name} not found in parent file")
                    updated_files = current_files.copy()
            else:
                print(f"❌ Parent file not found or not UV-Vis: {parent_file_id}")
                updated_files = current_files.copy()
        
        # Check if this is a bundle deletion
        elif data_manager.bundle_manager.get_bundle_by_id(file_id) or data_manager.get_lcms_bundle_by_id(file_id):
            bundle = data_manager.bundle_manager.get_bundle_by_id(file_id)
            lcms_bundle = data_manager.get_lcms_bundle_by_id(file_id)
            if bundle:
                bundle_base_name = bundle.base_name
                print(f"📦 Deleting bundle: {file_id}")
            elif lcms_bundle:
                bundle_base_name = file_id[: -len('_LCMS_BUNDLE')]
                print(f"🧪 Deleting LCMS bundle: {file_id}")
            
            # IMPORTANT: Get ALL files that belong to this bundle from the file records
            # Don't rely on the bundle structure which might be incomplete
            files_to_remove = []
            
            print(f"🔍 Looking for all files with base name: {bundle_base_name}")
            
            # Find ALL files in current_files that belong to this bundle
            for f in current_files:
                file_name = f.get('name', '')
                if bundle:
                    # Check if this file belongs to the Chromeleon bundle by name pattern
                    if (bundle_base_name in file_name and 
                        (file_name.endswith('_UV_VIS_1.txt') or 
                         file_name.endswith('_Chromatogram.txt') or
                         file_name.endswith('_Integration.txt') or
                         file_name.endswith('_Peak Analysis.txt') or
                         file_name.endswith('_SST.txt'))):
                        files_to_remove.append(f.get('id'))
                        print(f"🔒 Will remove: {file_name} (ID: {f.get('id')})")
                else:
                    # LCMS bundle: remove all component IDs tracked in bundle metadata
                    _, bundle_record = data_manager.find_lcms_bundle_for_component(f.get('id'))
                    if bundle_record and bundle_record.get('base_name') == bundle_base_name:
                        files_to_remove.append(f.get('id'))
                        print(f"🔬 Will remove LCMS member: {file_name} (ID: {f.get('id')})")
                    elif file_name.startswith(bundle_base_name):
                        files_to_remove.append(f.get('id'))
                        print(f"🔬 Will remove LCMS record by name match: {file_name}")
            if lcms_bundle:
                files_to_remove.append(file_id)
                print(f"🔬 Will remove LCMS bundle parent record: {file_id}")
            
            print(f"🔍 Total files to remove: {len(files_to_remove)}")
            
            # Remove from loaded data
            for fid in files_to_remove:
                if fid in data_manager.loaded_data:
                    del data_manager.loaded_data[fid]
                    print(f"✅ Removed from loaded_data: {fid}")
            
            # Remove bundle data itself
            if file_id in data_manager.loaded_data:
                del data_manager.loaded_data[file_id]
                print(f"✅ Removed bundle data: {file_id}")
            if lcms_bundle:
                removed_bundle = data_manager.remove_lcms_bundle(bundle_base_name)
                print(f"🧪 Removed LCMS bundle record: {removed_bundle is not None}")
            
            # Remove from file records - remove ALL files that were in the bundle
            updated_files = []
            removed_count = 0
            for f in current_files:
                if f.get('id') not in files_to_remove:
                    updated_files.append(f)
                else:
                    print(f"✅ Removed from file records: {f.get('name')} (ID: {f.get('id')})")
                    removed_count += 1
            
            print(f"🔍 Removed {removed_count} files from file records")
            
            # Remove the bundle from bundle manager
            if bundle:
                data_manager.bundle_manager.remove_bundle(file_id)
            if lcms_bundle:
                updated_files = [f for f in updated_files if f.get('id') != file_id]
            
        else:
            # Regular file deletion
            print(f"📄 Deleting individual file: {file_id}")

            lcms_base, lcms_bundle = data_manager.find_lcms_bundle_for_component(file_id)
            is_lcms_component_deletion = False
            lcms_parent_id = None
            if lcms_bundle:
                print(f"🧪 Removing LCMS component from bundle {lcms_base}")
                # Preserve collapse state for the LCMS bundle parent so it stays open
                if not hasattr(data_manager, 'collapse_state'):
                    data_manager.collapse_state = {}
                lcms_parent_id = f"{lcms_base}_LCMS_BUNDLE"
                data_manager.collapse_state[lcms_parent_id] = 'expanded'
                print(f"🔒 Stored collapse state for LCMS bundle {lcms_parent_id}: expanded")
                is_lcms_component_deletion = True
                bundle_files = lcms_bundle.get('files', [])
                if file_id in bundle_files:
                    bundle_files.remove(file_id)
                if file_id in lcms_bundle.get('records', {}):
                    lcms_bundle['records'].pop(file_id, None)
                lcms_bundle.setdefault('components', {}).pop(file_id, None)

            if file_id in data_manager.loaded_data:
                del data_manager.loaded_data[file_id]
                print(f"✅ Removed from loaded_data: {file_id}")

            # Remove from file records
            updated_files = []
            for f in current_files:
                if f.get('id') != file_id:
                    updated_files.append(f)
                else:
                    print(f"✅ Removed from file records: {f.get('name')}")
                    if is_lcms_component_deletion and 'children' in f:
                        # Ensure bundle parent stays expanded after child removal
                        bundle_parent_id = f.get('parent_bundle_id')
                        if bundle_parent_id:
                            if not hasattr(data_manager, 'collapse_state'):
                                data_manager.collapse_state = {}
                            data_manager.collapse_state[bundle_parent_id] = 'expanded'

        # For well deletion or LCMS component deletion, preserve collapse state and avoid clearing bundles
        parent_to_expand = None
        if '|' in file_id:
            parent_to_expand = file_id.split('|')[0]
        elif 'is_lcms_component_deletion' in locals() and is_lcms_component_deletion and lcms_parent_id:
            parent_to_expand = lcms_parent_id

        if parent_to_expand:
            print(f"🔄 Preserving collapse state for parent {parent_to_expand}")
            
            if not hasattr(data_manager, 'collapse_state'):
                data_manager.collapse_state = {}
            
            data_manager.collapse_state[parent_to_expand] = 'expanded'
            print(f"🔒 Stored collapse state for {parent_to_expand}: expanded")
            
            if hasattr(data_manager, '_last_processed_files'):
                delattr(data_manager, '_last_processed_files')
            if hasattr(data_manager, '_last_tree_items'):
                delattr(data_manager, '_last_tree_items')
            
            from callbacks.upload_callbacks import render_file_tree_with_bundles
            tree_items = render_file_tree_with_bundles(updated_files, data_manager)
        else:
            # Bundle/file deletion - clear cache and regenerate normally
            if hasattr(data_manager, '_last_processed_files'):
                delattr(data_manager, '_last_processed_files')
            if hasattr(data_manager, '_last_tree_items'):
                delattr(data_manager, '_last_tree_items')
            data_manager.bundle_manager.clear_bundles()
            
            from callbacks.upload_callbacks import render_file_tree_with_bundles
            tree_items = render_file_tree_with_bundles(updated_files, data_manager)

        print(f"✅ Delete complete. Remaining files: {len(updated_files)}")
        print(f"🔍 Returning tree with {len(tree_items)} items")
        
        # Auto-update plot if the deleted item affects the currently active file
        updated_plot = dash.no_update
        if active_file_id:
            print(f"🔍 Checking plot update for active file: {active_file_id}")
            # Get the main file ID (remove well suffix if present)
            main_file_id = active_file_id.split('|')[0] if '|' in active_file_id else active_file_id
            print(f"🔍 Main file ID: {main_file_id}")
            
            # Check if the deletion affects the current plot
            affects_current_plot = False
            
            if '|' in file_id:
                # Well deletion - check if it's from the current file
                deleted_parent_id = file_id.split('|')[0]
                print(f"🔍 Deleted parent ID: {deleted_parent_id}")
                if deleted_parent_id == main_file_id:
                    affects_current_plot = True
                    print(f"🎯 Well deletion affects current plot: {file_id}")
            elif file_id == main_file_id:
                # Main file deletion - affects current plot
                affects_current_plot = True
                print(f"🎯 Main file deletion affects current plot: {file_id}")
            elif main_file_id in files_to_remove:
                # Bundle deletion includes the active file
                affects_current_plot = True
                print(f"🎯 Bundle deletion affects current plot: active file {main_file_id} in removed set")
            
            print(f"🔍 Affects current plot: {affects_current_plot}")
            
            if affects_current_plot:
                print("🔄 Starting plot update...")
                try:
                    from services.plot_manager import PlotManager
                    plot_manager = PlotManager()
                    
                    # Check if the main file still exists
                    file_data = data_manager.get_data_by_id(main_file_id)
                    print(f"🔍 File data exists: {file_data is not None}")
                    
                    if file_data and file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
                        print("🧪 Processing UV-Vis file for plot update")
                        # For UV-Vis, create plot with remaining wells
                        visible_wells = []
                        filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
                        
                        print(f"🧪 Filled wells: {filled_wells}")
                        print(f"🧪 Updating plot with {len(filled_wells)} remaining wells")
                        
                        for well in filled_wells:
                            well_id = f"{main_file_id}|{well}"
                            # Initialize visibility_state if it doesn't exist
                            if not hasattr(data_manager, 'visibility_state'):
                                data_manager.visibility_state = {}
                            is_well_visible = data_manager.visibility_state.get(well_id, True)
                            print(f"   Well {well} visible: {is_well_visible}")
                            if is_well_visible:
                                visible_wells.append(well)
                        
                        print(f"🧪 Visible wells: {visible_wells}")
                        
                        if visible_wells:
                            updated_plot = plot_manager.create_uvvis_plot(
                                file_data['data'], 
                                file_data['metadata'], 
                                selected_columns=visible_wells
                            )
                            print(f"🎨 Auto-updated plot after deletion with {len(visible_wells)} wells: {visible_wells}")
                        else:
                            # No visible wells, show empty plot
                            import plotly.graph_objects as go
                            updated_plot = go.Figure()
                            updated_plot.add_annotation(
                                text="All wells deleted or hidden",
                                xref="paper", yref="paper",
                                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                                showarrow=False,
                                font=dict(size=16, color="#666")
                            )
                            print("🚫 All wells deleted/hidden, showing empty plot")
                    elif not file_data:
                        # File was completely deleted, show empty plot
                        import plotly.graph_objects as go
                        updated_plot = go.Figure()
                        updated_plot.add_annotation(
                            text="File deleted",
                            xref="paper", yref="paper",
                            x=0.5, y=0.5, xanchor='center', yanchor='middle',
                            showarrow=False,
                            font=dict(size=16, color="#666")
                        )
                        print("🗑️ File deleted, showing empty plot")
                    else:
                        print(f"🔍 File type: {file_data.get('metadata', {}).get('file_type', 'unknown')}")
                except Exception as e:
                    print(f"❌ Error updating plot after deletion: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            print("🔍 No active file for plot update")
        
        # Clear table and selections if the deleted file affects the active view
        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        # Check if the active file was deleted
        active_was_deleted = False
        if active_file_id:
            main_active = active_file_id.split('|')[0] if '|' in active_file_id else active_file_id
            if main_active in (files_to_remove or []) or file_id == active_file_id or file_id == main_active:
                active_was_deleted = True

        if active_was_deleted or not updated_files:
            table_editor = create_data_table_editor(None, table_id='pub-table')
            pub_data = None
            pub_sel = get_empty_selections()
        else:
            table_editor = dash.no_update
            pub_data = dash.no_update
            pub_sel = dash.no_update

        return (updated_files, tree_items, updated_plot, active_file_id,
                html.Div("Select a file to view data details", style={'color': '#666', 'padding': '20px'}),
                table_editor, pub_data, pub_sel)

    # Visibility button callback - ONLY handles button updates
    @app.callback(
        [Output({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'children'),
         Output({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'style')],
        Input({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'children'),
         State({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'id')],
        prevent_initial_call=True
    )
    def handle_visibility_toggles(n_clicks_list, current_icons, button_ids):
        """Handle visibility toggles - button updates only."""
        if not any(n_clicks_list):
            return dash.no_update, dash.no_update
        
        # Ensure arrays match
        if len(current_icons) != len(button_ids) or len(n_clicks_list) != len(button_ids):
            print(f"❌ Array length mismatch: icons={len(current_icons)}, ids={len(button_ids)}, clicks={len(n_clicks_list)}")
            return dash.no_update, dash.no_update
        
        # Get which button was clicked
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update
            
        try:
            import json
            component_id = json.loads(ctx.triggered[0]['prop_id'].rsplit('.', 1)[0])
            clicked_file_id = component_id['index']
        except Exception as e:
            print(f"❌ Error parsing callback trigger: {e}")
            return dash.no_update, dash.no_update
        
        # Initialize visibility state if needed
        if not hasattr(data_manager, 'visibility_state'):
            data_manager.visibility_state = {}
        
        # Toggle the clicked button's state
        current_icon = None
        for i, button_id in enumerate(button_ids):
            if button_id['index'] == clicked_file_id:
                current_icon = current_icons[i] if i < len(current_icons) else '👁'
                break
        
        if current_icon is None:
            print(f"❌ Could not find clicked button: {clicked_file_id}")
            return dash.no_update, dash.no_update
        
        # Toggle visibility state
        is_visible = current_icon == '👁'
        new_visibility = not is_visible
        data_manager.visibility_state[clicked_file_id] = new_visibility
        
        print(f"👁 Toggling visibility for {clicked_file_id}: {'visible' if new_visibility else 'hidden'}")
        
        # Check if this is a parent button and get children
        bundle = data_manager.bundle_manager.get_bundle_by_id(clicked_file_id)
        child_ids = []
        is_parent_click = False

        if bundle:
            # HPLC Bundle - get auxiliary file IDs
            is_parent_click = True
            print(f"📦 Setting all bundle children to {'visible' if new_visibility else 'hidden'}")
            for aux_file in bundle.auxiliary_files:
                aux_file_id = aux_file.get('id')
                if aux_file_id:
                    child_ids.append(aux_file_id)
                    data_manager.visibility_state[aux_file_id] = new_visibility
                    print(f"  📎 Set {aux_file.get('name')} to {'visible' if new_visibility else 'hidden'}")
        else:
            # Check for LCMS bundle parent
            lcms_bundle = data_manager.get_lcms_bundle_by_id(clicked_file_id)
            if lcms_bundle:
                is_parent_click = True
                print(f"🧪 Setting all LCMS components to {'visible' if new_visibility else 'hidden'}")
                for component_id in lcms_bundle.get('files', []):
                    child_ids.append(component_id)
                    data_manager.visibility_state[component_id] = new_visibility
                    print(f"  🧪 Set LCMS component {component_id} to {'visible' if new_visibility else 'hidden'}")
            else:
                # UV-Vis file - get well IDs
                file_data = data_manager.get_data_by_id(clicked_file_id)
                if file_data and file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
                    filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
                    if len(filled_wells) > 0:
                        is_parent_click = True
                        print(f"🧪 Setting all UV-Vis wells to {'visible' if new_visibility else 'hidden'}")
                        for well in filled_wells:
                            well_id = f"{clicked_file_id}|{well}"
                            child_ids.append(well_id)
                            data_manager.visibility_state[well_id] = new_visibility
                            print(f"  🧪 Set Well {well} to {'visible' if new_visibility else 'hidden'}")
        
        # Update ALL buttons based on their current visibility state
        new_icons = []
        new_styles = []
        
        try:
            for i, button_id in enumerate(button_ids):
                button_file_id = button_id['index']
                button_visible = data_manager.visibility_state.get(button_file_id, True)
                button_icon = '👁' if button_visible else '🚫'
                button_opacity = '1.0' if button_visible else '0.5'
                
                new_icons.append(button_icon)
                new_styles.append({
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '14px',
                    'opacity': button_opacity,
                    'width': '24px',
                    'height': '24px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center',
                    'borderRadius': '3px'
                })
        except Exception as e:
            print(f"❌ Error updating button arrays: {e}")
            return dash.no_update, dash.no_update
        
        if is_parent_click:
            print(f"🎨 Photoshop-style sync: Updated parent + {len(child_ids)} children")
        
        print(f"✅ Returning {len(new_icons)} icons and {len(new_styles)} styles")
        return new_icons, new_styles

    # Plot update callback - SEPARATE from button updates with delay
    @app.callback(
        Output('main-plot', 'figure', allow_duplicate=True),
        Input({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State('view-mode', 'data'),
         State('current-plot-settings', 'data'),
         State('active-file', 'data'),
         State('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def update_plot_on_any_visibility_change(n_clicks_list, view_mode, plot_settings, active_file, loaded_files):
        """Rebuild the raw plot using all visible files when any eye icon is toggled."""
        if not any(n_clicks_list):
            return dash.no_update
        # Only affect the raw plot
        if (view_mode or 'raw') != 'raw':
            return dash.no_update

        import time
        time.sleep(0.01)  # let visibility state settle

        from services.plot_manager import PlotManager
        from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS
        import plotly.graph_objects as go

        plot_manager = PlotManager()
        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        layout_mode = s.get('layout_mode', 'overlay')

        visible_files = _collect_visible_files(data_manager, active_file, loaded_files)

        if not visible_files:
            return plot_manager.create_hidden_state_plot()

        fig = plot_manager.create_multi_file_plot(visible_files, layout_mode)

        # Overlay peaks
        from callbacks.peak_overlay import overlay_peaks_on_figure
        from callbacks.baseline_callbacks import get_chromatogram_arrays
        time_arr, signal_arr = get_chromatogram_arrays(data_manager, active_file)
        if time_arr is not None:
            all_peaks = data_manager.peak_service.get_peaks(active_file)
            fig = overlay_peaks_on_figure(all_peaks, fig, time_arr, signal_arr)

        # Apply plot settings
        try:
            fig_obj = go.Figure(fig) if isinstance(fig, dict) else fig
            ps = PlotSettingsService.from_dict(s)
            PlotSettingsService.apply_to_figure(fig_obj, ps)
            return fig_obj
        except Exception:
            return fig

    def _collect_visible_files(dm, active_file_id=None, loaded_files=None):
        """Return list of (display_name, file_data) for visible files (deduped)."""
        from callbacks.viz_callbacks import _collect_visible_files as _shared
        return _shared(dm, active_file_id, loaded_files)

    @app.callback(
        Output('file-tree', 'children', allow_duplicate=True),
        [Input('active-file', 'data'),
         Input('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def sync_file_tree_selection(active_file_id, loaded_files):
        """Re-render the file tree so only the active file remains highlighted."""
        from callbacks.upload_callbacks import render_file_tree_with_bundles_selected

        records = loaded_files or []
        return render_file_tree_with_bundles_selected(records, data_manager, active_file_id)

    # Store collapse states in data manager
    if not hasattr(data_manager, 'collapse_state'):
        data_manager.collapse_state = {}

    # DISABLED: Clientside callback was causing JavaScript errors
    # The visibility state is properly managed server-side
    # Child buttons will show correct state when file tree refreshes
    # 
    # app.clientside_callback(
    #     """
    #     function(n_clicks_list) {
    #         return null;
    #     }
    #     """,
    #     Output('dummy-output', 'children', allow_duplicate=True),
    #     Input({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
    #     prevent_initial_call=True
    # )

    # DISABLED: Tree refresh was causing collapse state loss and plot update conflicts
    # The visibility functionality works perfectly, just the visual button sync is missing
    # This is a minor UX issue vs major functionality breaking
    # 
    # @app.callback(
    #     Output('file-tree', 'children', allow_duplicate=True),
    #     Input({'type': 'visibility-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
    #     State('loaded-files', 'data'),
    #     prevent_initial_call=True
    # )
    # def refresh_tree_for_button_sync(n_clicks_list, current_files):
    #     """DISABLED: Was causing collapse state loss and plot update conflicts."""
    #     return dash.no_update
    #     """Refresh file tree after visibility changes to sync button states."""
    #     return dash.no_update
