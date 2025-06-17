import dash_mantine_components as dmc
from dash import html, dcc, Input, Output, State, callback, ALL, MATCH
import dash
from dash.exceptions import PreventUpdate
import json


def create_file_tree_manager():
    """Create the file tree manager component."""
    return html.Div([
        # Store for layer data
        dcc.Store(id="layer-state", data=[]),
        dcc.Store(id="selected-layer", data=None),
        
        # Store for visibility state - this will trigger plot updates
        dcc.Store(id="visibility-state", data={}),
        
        # Tree header
        html.Div([
            html.Span("Files & Layers", className="tree-header-title"),
            html.Div([
                html.Button("👁", id="toggle-all-visibility", className="tree-header-btn", title="Toggle All Visibility"),
                html.Button("🗑", id="delete-selected", className="tree-header-btn", title="Delete Selected"),
            ], className="tree-header-actions")
        ], className="tree-header"),
        
        # Tree container
        html.Div(id="tree-container", className="tree-container"),
        
    ], className="file-tree-manager")

def create_tree_item(item_data, level=0):
    """Create a single tree item with controls."""
    item_id = item_data["id"]
    label = item_data["label"]
    icon = item_data.get("icon", "📄")
    visible = item_data.get("visible", True)
    children = item_data.get("children", [])
    expanded = item_data.get("expanded", True)
    selected = item_data.get("selected", False)
    editing = item_data.get("editing", False)
    
    # Indentation based on level
    indent_style = {"paddingLeft": f"{level * 16}px"}
    
    # Create label element - either input or span based on editing state
    if editing:
        label_element = dcc.Input(
            id={"type": "edit-input", "index": item_id},
            value=label,
            type="text",
            className="inline-edit-input",
            autoFocus=True,
            persistence=True,  # Keep value during re-renders
            persistence_type="memory",
            style={
                "border": "1px solid #1473e6",
                "borderRadius": "3px", 
                "padding": "2px 6px",
                "fontSize": "13px",
                "width": "150px",
                "background": "white",
                "color": "#323232",
                "outline": "none"
            }
        )
    else:
        label_element = html.Span(
            label, 
            className="item-label", 
            id={"type": "item-label", "index": item_id},
            title="Double-click to edit"
        )
    
    # Main item row
    item_content = html.Div([
        # Expand/collapse button (only if has children)
        html.Button(
            "▼" if expanded and children else "▶" if children else "•",
            id={"type": "expand-btn", "index": item_id},
            className="expand-btn" + (" has-children" if children else " no-children"),
            disabled=not children,
            title="Expand/Collapse" if children else ""
        ) if children else html.Span("", className="expand-btn no-children"),
        
        # Visibility toggle
        html.Button(
            "👁" if visible else "🚫",
            id={"type": "visibility-btn", "index": item_id},
            className="visibility-btn" + (" visible" if visible else " hidden"),
            title="Toggle visibility",
            style={"opacity": "1" if visible else "0.4"}
        ),
        
        # Icon and label
        html.Div([
            html.Span(icon, className="item-icon"),
            label_element,
        ], className="item-content", id={"type": "item-row", "index": item_id}),
        
        # Action buttons (only show when not editing)
        html.Div([
            html.Button("✏️", id={"type": "edit-btn", "index": item_id}, 
                       className="action-btn edit-btn", title="Rename"),
            html.Button("🗑", id={"type": "delete-btn", "index": item_id}, 
                       className="action-btn delete-btn", title="Delete"),
        ], className="item-actions", style={"display": "none" if editing else "flex"}),
        
    ], className=f"tree-item-row {'selected' if selected else ''}", 
       style=indent_style)
    
    # Children container (if expanded)
    children_content = []
    if children and expanded:
        for child in children:
            children_content.append(create_tree_item(child, level + 1))
    
    return html.Div([
        item_content,
        html.Div(children_content, className="tree-children") if children_content else None
    ], className="tree-item")


def convert_files_to_tree_data(data_manager):
    """Convert loaded files to tree data structure."""
    files = data_manager.get_loaded_files()
    tree_data = []
    
    # Get existing tree state to preserve deletions
    if hasattr(convert_files_to_tree_data, '_deleted_items'):
        deleted_items = convert_files_to_tree_data._deleted_items
    else:
        convert_files_to_tree_data._deleted_items = set()
        deleted_items = convert_files_to_tree_data._deleted_items
    
    for fname in files:
        # Skip if this file was deleted
        if fname in deleted_items:
            continue
            
        file_data = data_manager.get_file_data(fname)
        if not file_data:
            continue
            
        file_type = file_data['type']
        
        # Create base item
        item = {
            "id": fname,
            "label": fname.replace('_UV_VIS_1.txt', '').replace('temp_', ''),
            "icon": get_file_icon(file_type),
            "visible": True,
            "selected": False,
            "expanded": True,
            "editing": False,
            "children": []
        }
        
        # Add children based on file type
        if file_type == 'uvvis_csv':
            wells = file_data['metadata'].get('filled_wells', [])[:10]
            for well in wells:
                item["children"].append({
                    "id": f"{fname}|{well}",
                    "label": f"Well {well}",
                    "icon": "🧪",
                    "visible": True,
                    "selected": False,
                    "editing": False
                })
                
        elif file_type == 'lcms_bundle':
            bundle_data = file_data.get("bundle_data", {})
            meta = file_data.get("metadata", {})
            components = meta.get("components", [])
            
            for component in components:
                if component == 'MS+':
                    item["children"].append({
                        "id": f"{fname}|ms_positive",
                        "label": "MS+ (Positive)",
                        "icon": "🔬",
                        "visible": True,
                        "selected": False,
                        "editing": False
                    })
                elif component == 'MS-':
                    item["children"].append({
                        "id": f"{fname}|ms_negative", 
                        "label": "MS- (Negative)",
                        "icon": "🔬",
                        "visible": True,
                        "selected": False,
                        "editing": False
                    })
                elif component == 'UV-A':
                    wl = meta.get('uv_a_wavelength', '?')
                    item["children"].append({
                        "id": f"{fname}|vwd_a",
                        "label": f"UV-A ({wl} nm)",
                        "icon": "📊",
                        "visible": True,
                        "selected": False,
                        "editing": False
                    })
                elif component == 'UV-B':
                    wl = meta.get('uv_b_wavelength', '?')
                    item["children"].append({
                        "id": f"{fname}|vwd_b",
                        "label": f"UV-B ({wl} nm)", 
                        "icon": "📊",
                        "visible": True,
                        "selected": False,
                        "editing": False
                    })

        elif file_type in ['chromeleon_bundle', 'chromatogram']:
            # Single file - no children needed
            pass

        tree_data.append(item)
    
    return tree_data


def get_file_icon(file_type):
    """Get icon for file type."""
    icons = {
        'uvvis_csv': '📊',
        'lcms_cdf': '📈', 
        'lcms_bundle': '📦',
        'chromeleon_bundle': '📈',
        'chromatogram': '📉',
        'spectra': '🌊'
    }
    return icons.get(file_type, '📄')

def get_visibility_state(tree_data):
    """Extract visibility state from tree data for use by plotting functions."""
    visibility = {}
    
    def extract_visibility(items):
        if not items:  # Handle None or empty
            return
        for item in items:
            visibility[item["id"]] = item.get("visible", True)
            if item.get("children"):
                extract_visibility(item["children"])
    
    extract_visibility(tree_data)
    return visibility

def propagate_visibility_to_children(items, target_id, visible):
    """When hiding/showing bundle, also hide/show all children"""
    for item in items:
        if item["id"] == target_id:
            item["visible"] = visible
            # Also set visibility for all children
            if item.get("children"):
                for child in item["children"]:
                    child["visible"] = visible
            return True
        if item.get("children"):
            if propagate_visibility_to_children(item["children"], target_id, visible):
                return True
    return False

def register_tree_callbacks(app, data_manager):
    """Register callbacks for the tree manager."""
    
    # Initialize tree data when files are uploaded
    @app.callback(
        [Output("layer-state", "data"),
        Output("visibility-state", "data"),
        Output("selected-layer", "data", allow_duplicate=True)],  # ADD allow_duplicate=True

        [Input("upload-status", "children"),
        Input("file-list", "children")],
        prevent_initial_call=True
    )

    def update_tree_data(upload_status, file_list):
        print(f"[DEBUG] Tree update triggered. Files: {data_manager.get_loaded_files()}")
        tree_data = convert_files_to_tree_data(data_manager)
        print(f"[DEBUG] Generated tree data: {len(tree_data) if tree_data else 0} items")
        
        if not tree_data:
            return [], {}, None
        
        visibility = get_visibility_state(tree_data)
        
        # AUTO-SELECT the newest (last) file
        newest_file_id = None
        if tree_data:
            newest_file_id = tree_data[-1]["id"]  # Last file is newest
            # Set it as selected in tree data
            def set_newest_selected(items):
                for item in items:
                    item["selected"] = (item["id"] == newest_file_id)
                    if item.get("children"):
                        for child in item["children"]:
                            child["selected"] = False
            
            set_newest_selected(tree_data)
        
        return tree_data, visibility, newest_file_id

    # Render tree from data
    @app.callback(
        Output("tree-container", "children"),
        Input("layer-state", "data")
    )
    def render_tree(tree_data):
        if not tree_data:
            return html.Div("No files loaded", className="empty-tree")
        
        tree_items = []
        for item in tree_data:
            tree_items.append(create_tree_item(item))
        
        return tree_items
    
    # Handle item selection
    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True),
         Output("selected-layer", "data")],
        Input({"type": "item-row", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )






    # Add this debugging to your tree selection callback in file_tree_manager.py
    # Find your handle_item_selection function and add these debug lines:

    def handle_item_selection(n_clicks_list, tree_data):
        print(f"\n🌳 [TREE DEBUG] ===== TREE SELECTION TRIGGERED =====")
        print(f"🌳 [TREE DEBUG] n_clicks_list: {n_clicks_list}")
        print(f"🌳 [TREE DEBUG] any clicks: {any(n_clicks_list) if n_clicks_list else False}")
        
        if not any(n_clicks_list) or not tree_data:
            print("🌳 [TREE DEBUG] ❌ Early exit - no clicks or no tree data")
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            print("🌳 [TREE DEBUG] ❌ Early exit - no trigger context")
            raise PreventUpdate
        
        print(f"🌳 [TREE DEBUG] Context triggered: {ctx.triggered}")
        
        # Extract item ID from callback context more robustly
        triggered_prop = ctx.triggered[0]["prop_id"]
        print(f"🌳 [TREE DEBUG] Triggered prop: {triggered_prop}")
        
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            print("🌳 [TREE DEBUG] ❌ Early exit - no match in prop_id")
            raise PreventUpdate
        
        item_id = match.group(1)
        print(f"🌳 [TREE DEBUG] 🎯 Extracted item_id: {item_id}")
                
        # Update selection in tree data
        def update_selection(items, target_id):
            for item in items:
                was_selected = item.get("selected", False)
                item["selected"] = (item["id"] == target_id)
                if item["selected"] and not was_selected:
                    print(f"🌳 [TREE DEBUG] ✅ Set {item['id']} as selected")
                if item.get("children"):
                    update_selection(item["children"], target_id)
        
        update_selection(tree_data, item_id)
        
        print(f"🌳 [TREE DEBUG] 📡 About to return item_id: {item_id}")
        print(f"🌳 [TREE DEBUG] ===== END TREE SELECTION =====\n")
        
        return tree_data, item_id






    # Handle edit button click - start inline editing
    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        Input({"type": "edit-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def start_edit_mode(n_clicks_list, tree_data):
        if not any(n_clicks_list) or not tree_data:
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Get clicked item ID
        triggered_prop = ctx.triggered[0]["prop_id"]
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            raise PreventUpdate
        item_id = match.group(1)
        
        # Set editing state
        def set_editing(items, target_id):
            for item in items:
                if item["id"] == target_id:
                    item["editing"] = True
                    return True
                elif item.get("children"):
                    if set_editing(item["children"], target_id):
                        return True
            return False
        
        set_editing(tree_data, item_id)
        return tree_data

    # Handle edit input changes (save on Enter or blur)
    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        [Input({"type": "edit-input", "index": ALL}, "value"),
         Input({"type": "edit-input", "index": ALL}, "n_blur"),
         Input({"type": "edit-input", "index": ALL}, "n_submit")],
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def finish_inline_edit(values, n_blur, n_submit, tree_data):
        if not tree_data:
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Get the item being edited and new value
        triggered_prop = ctx.triggered[0]["prop_id"]
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            raise PreventUpdate
        item_id = match.group(1)
        
        # Check if this was a blur or submit (finish editing)
        trigger_type = ctx.triggered[0]["prop_id"].split(".")[-1]
        if trigger_type not in ["n_blur", "n_submit"]:
            raise PreventUpdate
        
        # Find the current input value
        if not values or all(v is None for v in values):
            raise PreventUpdate
        
        new_value = next((v for v in values if v is not None), None)
        if not new_value:
            raise PreventUpdate
        
        # Update the label and stop editing
        def update_label_and_stop_editing(items, target_id, new_label):
            for item in items:
                if item["id"] == target_id:
                    item["label"] = new_label
                    item["editing"] = False
                    return True
                elif item.get("children"):
                    if update_label_and_stop_editing(item["children"], target_id, new_label):
                        return True
            return False
        
        update_label_and_stop_editing(tree_data, item_id, new_value)
        return tree_data

    # Handle expand/collapse
    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        Input({"type": "expand-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def handle_expand_collapse(n_clicks_list, tree_data):
        if not any(n_clicks_list) or not tree_data:
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Get clicked item ID
        triggered_prop = ctx.triggered[0]["prop_id"]
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            raise PreventUpdate
        item_id = match.group(1)
        
        # Toggle expanded state
        def toggle_expanded(items, target_id):
            for item in items:
                if item["id"] == target_id:
                    item["expanded"] = not item.get("expanded", True)
                    return True
                if item.get("children"):
                    if toggle_expanded(item["children"], target_id):
                        return True
            return False
        
        toggle_expanded(tree_data, item_id)
        return tree_data

    # Handle visibility toggles
    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True),
         Output("visibility-state", "data", allow_duplicate=True)],
        Input({"type": "visibility-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        prevent_initial_call=True
    )
    def handle_visibility_toggle(n_clicks_list, tree_data, visibility_state):
        if not any(n_clicks_list) or not tree_data:
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Get clicked item ID
        triggered_prop = ctx.triggered[0]["prop_id"]
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            raise PreventUpdate
        item_id = match.group(1)
        
        # Toggle visibility in tree data
        def toggle_visibility(items, target_id):
            for item in items:
                if item["id"] == target_id:
                    item["visible"] = not item.get("visible", True)
                    # If this is a parent with children, also toggle children
                    if item.get("children"):
                        new_visibility = item["visible"]
                        for child in item["children"]:
                            child["visible"] = new_visibility
                    return item["visible"]
                if item.get("children"):
                    result = toggle_visibility(item["children"], target_id)
                    if result is not None:
                        return result
            return None
        
        new_visibility = toggle_visibility(tree_data, item_id)
        
        # Update visibility state
        if visibility_state is None:
            visibility_state = {}
        
        # Update visibility state for the item and potentially its children
        visibility_state[item_id] = new_visibility
        
        # If it's a parent item, also update children in visibility state
        def update_children_visibility(items, target_id, visible):
            for item in items:
                if item["id"] == target_id and item.get("children"):
                    for child in item["children"]:
                        visibility_state[child["id"]] = visible
                    return True
                if item.get("children"):
                    if update_children_visibility(item["children"], target_id, visible):
                        return True
            return False
        
        if new_visibility is not None:
            update_children_visibility(tree_data, item_id, new_visibility)
        
        return tree_data, visibility_state
    
    # Handle individual delete buttons
    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True),
         Output("visibility-state", "data", allow_duplicate=True)],
        Input({"type": "delete-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        prevent_initial_call=True
    )
    def handle_delete_item(n_clicks_list, tree_data, visibility_state):
        if not any(n_clicks_list) or not tree_data:
            raise PreventUpdate
        
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        
        # Get clicked item ID
        triggered_prop = ctx.triggered[0]["prop_id"]
        import re
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match:
            raise PreventUpdate
        item_id = match.group(1)
        
        # Remove item from tree data
        def remove_item(items, target_id):
            for i, item in enumerate(items):
                if item["id"] == target_id:
                    # If it's a file (no "|" in ID), mark as deleted for convert_files_to_tree_data
                    if "|" not in target_id:
                        if not hasattr(convert_files_to_tree_data, '_deleted_items'):
                            convert_files_to_tree_data._deleted_items = set()
                        convert_files_to_tree_data._deleted_items.add(target_id)
                    
                    items.pop(i)
                    return True
                if item.get("children"):
                    if remove_item(item["children"], target_id):
                        return True
            return False
        
        remove_item(tree_data, item_id)
        
        # Remove from visibility state
        if visibility_state and item_id in visibility_state:
            del visibility_state[item_id]
        
        return tree_data, visibility_state
    
    # Handle "Toggle All Visibility" button
    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True),
         Output("visibility-state", "data", allow_duplicate=True)],
        Input("toggle-all-visibility", "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        prevent_initial_call=True
    )
    def toggle_all_visibility(n_clicks, tree_data, visibility_state):
        if not n_clicks or not tree_data:
            raise PreventUpdate
        
        # Check if all items are currently visible
        all_visible = True
        def check_all_visible(items):
            nonlocal all_visible
            for item in items:
                if not item.get("visible", True):
                    all_visible = False
                    return
                if item.get("children"):
                    check_all_visible(item["children"])
        
        check_all_visible(tree_data)
        
        # Toggle all to opposite state
        new_visibility = not all_visible
        
        def set_all_visibility(items, visible):
            for item in items:
                item["visible"] = visible
                if item.get("children"):
                    set_all_visibility(item["children"], visible)
        
        set_all_visibility(tree_data, new_visibility)
        
        # Update visibility state
        if visibility_state is None:
            visibility_state = {}
        
        def update_visibility_state(items, visible):
            for item in items:
                visibility_state[item["id"]] = visible
                if item.get("children"):
                    update_visibility_state(item["children"], visible)
        
        update_visibility_state(tree_data, new_visibility)
        
        return tree_data, visibility_state

    # Handle "Delete Selected" button in tree header
    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True),
        Output("visibility-state", "data", allow_duplicate=True),
        Output("selected-layer", "data", allow_duplicate=True)],
        Input("delete-selected", "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        State("selected-layer", "data"),
        prevent_initial_call=True
    )
    def handle_delete_selected(n_clicks, tree_data, visibility_state, selected_layer):
        """Delete the currently selected item."""
        if not n_clicks or not tree_data or not selected_layer:
            raise PreventUpdate
        
        # Remove selected item from tree data
        def remove_item(items, target_id):
            for i, item in enumerate(items):
                if item["id"] == target_id:
                    # If it's a file (no "|" in ID), mark as deleted for convert_files_to_tree_data
                    if "|" not in target_id:
                        if not hasattr(convert_files_to_tree_data, '_deleted_items'):
                            convert_files_to_tree_data._deleted_items = set()
                        convert_files_to_tree_data._deleted_items.add(target_id)
                    
                    items.pop(i)
                    return True
                if item.get("children"):
                    if remove_item(item["children"], target_id):
                        return True
            return False
        
        remove_item(tree_data, selected_layer)
        
        # Remove from visibility state
        if visibility_state and selected_layer in visibility_state:
            del visibility_state[selected_layer]
        
        # Clear selection since item was deleted
        return tree_data, visibility_state, None