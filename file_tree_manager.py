import dash_mantine_components as dmc
from dash import html, dcc, Input, Output, State, callback, ALL, MATCH
import dash
from dash.exceptions import PreventUpdate
import json
import re

# --- Component Creation ---

def create_file_tree_manager():
    """Create the file tree manager component."""
    return html.Div([
        dcc.Store(id="layer-state", data=[]),
        dcc.Store(id="selected-layer", data=None),
        dcc.Store(id="visibility-state", data={}),
        html.Div([
            html.Span("Files & Layers", className="tree-header-title"),
            html.Div([
                html.Button("👁", id="toggle-all-visibility", className="tree-header-btn", title="Toggle All Visibility"),
                html.Button("🗑", id="delete-selected", className="tree-header-btn", title="Delete Selected"),
            ], className="tree-header-actions")
        ], className="tree-header"),
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
    
    indent_style = {"paddingLeft": f"{level * 16}px"}
    
    if editing:
        label_element = dcc.Input(
            id={"type": "edit-input", "index": item_id},
            value=label, type="text", className="inline-edit-input", autoFocus=True,
            persistence=True, persistence_type="memory",
            style={
                "border": "1px solid #1473e6", "borderRadius": "3px", "padding": "2px 6px", 
                "fontSize": "13px", "width": "150px", "background": "white", "color": "#323232", "outline": "none"
            }
        )
    else:
        label_element = html.Span(
            label, className="item-label", 
            id={"type": "item-label", "index": item_id},
            title="Double-click to edit"
        )
    
    item_content = html.Div([
        html.Button(
            "▼" if expanded and children else "▶" if children else "•",
            id={"type": "expand-btn", "index": item_id},
            className="expand-btn" + (" has-children" if children else " no-children"),
            disabled=not children,
            title="Expand/Collapse" if children else ""
        ) if children else html.Span("", className="expand-btn no-children"),
        
        html.Button(
            "👁" if visible else "🚫",
            id={"type": "visibility-btn", "index": item_id},
            className="visibility-btn" + (" visible" if visible else " hidden"),
            title="Toggle visibility",
            style={"opacity": "1" if visible else "0.4"}
        ),
        
        html.Div([
            html.Span(icon, className="item-icon"),
            label_element,
        ], className="item-content", id={"type": "item-row", "index": item_id}),
        
        html.Div([
            html.Button("✏️", id={"type": "edit-btn", "index": item_id}, className="action-btn edit-btn", title="Rename"),
            html.Button("🗑", id={"type": "delete-btn", "index": item_id}, className="action-btn delete-btn", title="Delete"),
        ], className="item-actions", style={"display": "none" if editing else "flex"}),
        
    ], className=f"tree-item-row {'selected' if selected else ''}", style=indent_style)
    
    children_content = []
    if children and expanded:
        for child in children:
            children_content.append(create_tree_item(child, level + 1))
    
    return html.Div([
        item_content,
        html.Div(children_content, className="tree-children") if children_content else None
    ], className="tree-item")

# --- Data Conversion ---

def convert_files_to_tree_data(data_manager):
    """Convert loaded files to a stateless tree data structure."""
    files = data_manager.get_loaded_files()
    tree_data = []
    
    for fname in files:
        file_data = data_manager.get_file_data(fname)
        if not file_data:
            continue
            
        file_type = file_data['type']
        
        custom_label = data_manager.get_custom_label(fname)
        item = {
            "id": fname,
            "label": custom_label or fname.replace('_UV_VIS_1.txt', '').replace('temp_', ''),
            "icon": get_file_icon(file_type),
            "visible": True, "selected": False, "expanded": True, "editing": False, "children": []
        }
        
        if file_type == 'uvvis_csv':
            wells = file_data['metadata'].get('filled_wells', [])[:10]
            for well in wells:
                child_id = f"{fname}|{well}"
                item["children"].append({
                    "id": child_id,
                    "label": data_manager.get_custom_label(child_id) or f"Well {well}",
                    "icon": "🧪", "visible": True, "selected": False, "editing": False
                })
                
        elif file_type == 'lcms_bundle':
            meta = file_data.get("metadata", {})
            components = meta.get("components", [])
            
            for component in components:
                child_id, default_label, icon = None, None, None
                if component == 'MS+':
                    child_id, default_label, icon = f"{fname}|ms_positive", "MS+ (Positive)", "🔬"
                elif component == 'MS-':
                    child_id, default_label, icon = f"{fname}|ms_negative", "MS- (Negative)", "🔬"
                elif component == 'UV-A':
                    wl = meta.get('uv_a_wavelength', '?')
                    child_id, default_label, icon = f"{fname}|vwd_a", f"UV-A ({wl} nm)", "📊"
                elif component == 'UV-B':
                    wl = meta.get('uv_b_wavelength', '?')
                    child_id, default_label, icon = f"{fname}|vwd_b", f"UV-B ({wl} nm)", "📊"
                
                if child_id:
                    item["children"].append({
                        "id": child_id,
                        "label": data_manager.get_custom_label(child_id) or default_label,
                        "icon": icon, "visible": True, "selected": False, "editing": False
                    })

        tree_data.append(item)
    
    return tree_data

def get_file_icon(file_type):
    """Get icon for file type."""
    icons = {'uvvis_csv': '📊', 'lcms_cdf': '📈', 'lcms_bundle': '📦', 'chromeleon_bundle': '📈', 'chromatogram': '📉', 'spectra': '🌊'}
    return icons.get(file_type, '📄')

def get_visibility_state(tree_data):
    """Extract visibility state from tree data for use by plotting functions."""
    visibility = {}
    def extract_visibility(items):
        if not items: return
        for item in items:
            visibility[item["id"]] = item.get("visible", True)
            if item.get("children"):
                extract_visibility(item["children"])
    extract_visibility(tree_data)
    return visibility

# --- Callback Registration ---

def register_tree_callbacks(app, data_manager):
    """Register all callbacks for the file tree manager."""

    from callbacks.upload_callbacks import create_file_list, create_file_selector_options, create_data_overview

    def create_single_file_overview(dm, filename):
        entry = dm.get_file_data(filename)
        if not entry: return html.Div("File data not found.")
        class OneFileManager:
            def get_loaded_files(self): return [filename]
            def get_file_data(self, f): return entry
        return create_data_overview(OneFileManager())[0]

    def _perform_delete_and_update_ui(item_id, selected_layer):
        """Shared logic to delete an item and rebuild the entire UI."""
        data_manager.remove_data_entry(item_id)

        new_tree_data = convert_files_to_tree_data(data_manager)
        new_visibility_state = get_visibility_state(new_tree_data)
        new_file_list = create_file_list(data_manager)
        new_options = create_file_selector_options(data_manager)

        new_selection = None
        loaded_files = data_manager.get_loaded_files()
        if loaded_files:
            if selected_layer and selected_layer != item_id and selected_layer in loaded_files:
                new_selection = selected_layer
            else:
                new_selection = loaded_files[-1] if loaded_files else None

        if new_selection:
            overview = create_single_file_overview(data_manager, new_selection)
            viz_style, dash_style, upload_style = {"display": "block"}, {"display": "block"}, {"display": "none"}
        else:
            overview = html.Div("No files loaded", className="no-files-text")
            viz_style, dash_style, upload_style = {"display": "none"}, {"display": "none"}, {"display": "block"}

        return new_tree_data, new_visibility_state, new_selection, new_file_list, new_options, overview, viz_style, dash_style, upload_style

    delete_outputs = [
        Output("layer-state", "data", allow_duplicate=True),
        Output("visibility-state", "data", allow_duplicate=True),
        Output("selected-layer", "data", allow_duplicate=True),
        Output("file-list", "children", allow_duplicate=True),
        Output("file-selector", "options", allow_duplicate=True),
        Output("data-overview", "children", allow_duplicate=True),
        Output("viz-card", "style", allow_duplicate=True),
        Output("dashboard-container", "style", allow_duplicate=True),
        Output("upload-card", "style", allow_duplicate=True)
    ]

    @app.callback(delete_outputs, Input({"type": "delete-btn", "index": ALL}, "n_clicks"), State("selected-layer", "data"), prevent_initial_call=True)
    def handle_delete_item(n_clicks_list, selected_layer):
        if not any(n_clicks_list): raise PreventUpdate
        ctx = dash.callback_context
        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        return _perform_delete_and_update_ui(item_id, selected_layer)

    @app.callback(delete_outputs, Input("delete-selected", "n_clicks"), State("selected-layer", "data"), prevent_initial_call=True)
    def handle_delete_selected(n_clicks, selected_layer):
        if not n_clicks or not selected_layer: raise PreventUpdate
        return _perform_delete_and_update_ui(selected_layer, selected_layer)

    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True), Output("visibility-state", "data"), Output("selected-layer", "data", allow_duplicate=True)],
        [Input("upload-status", "children")],
        prevent_initial_call=True
    )
    def update_tree_data(upload_status):
        tree_data = convert_files_to_tree_data(data_manager)
        if not tree_data: return [], {}, None
        visibility = get_visibility_state(tree_data)
        newest_file_id = tree_data[-1]["id"]
        for item in tree_data: item["selected"] = (item["id"] == newest_file_id)
        return tree_data, visibility, newest_file_id

    @app.callback(Output("tree-container", "children"), Input("layer-state", "data"))
    def render_tree(tree_data):
        if not tree_data: return html.Div("No files loaded", className="empty-tree")
        return [create_tree_item(item) for item in tree_data]

    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True), Output("selected-layer", "data", allow_duplicate=True)],
        Input({"type": "item-row", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def handle_item_selection(n_clicks_list, tree_data):
        if not any(n_clicks_list): raise PreventUpdate
        ctx = dash.callback_context
        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        
        top_level_id = item_id.split('|')[0]

        def clear_all_selections(items):
            for item in items:
                item["selected"] = False
                if item.get("children"):
                    clear_all_selections(item["children"])

        def update_selection(items):
            for item in items:
                item["selected"] = (item["id"] == item_id or item["id"] == top_level_id)
                if item.get("children"):
                    update_selection(item["children"])
        
        clear_all_selections(tree_data)
        update_selection(tree_data)

        return tree_data, top_level_id

    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        Input({"type": "edit-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def start_edit_mode(n_clicks_list, tree_data):
        if not any(n_clicks_list): raise PreventUpdate
        ctx = dash.callback_context
        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        def set_editing(items):
            for item in items:
                if item["id"] == item_id: item["editing"] = True; return True
                if item.get("children") and set_editing(item["children"]): return True
            return False
        set_editing(tree_data)
        return tree_data

    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        [Input({"type": "edit-input", "index": ALL}, "n_submit"), Input({"type": "edit-input", "index": ALL}, "n_blur")],
        [State("layer-state", "data"), State({"type": "edit-input", "index": ALL}, "value")],
        prevent_initial_call=True
    )
    def finish_inline_edit(n_submit, n_blur, tree_data, values):
        if not tree_data or (not any(n_submit or []) and not any(n_blur or [])):
            raise PreventUpdate

        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate

        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        
        # Get the new value from the values list
        new_value = None
        if values:
            # Find the value that corresponds to this item_id
            for i, val in enumerate(values):
                if val is not None and val.strip():
                    new_value = val.strip()
                    break
        
        if new_value:
            data_manager.set_custom_label(item_id, new_value)

        def update_label(items):
            for item in items:
                if item["id"] == item_id:
                    if new_value:
                        item["label"] = new_value
                    item["editing"] = False
                    return True
                if item.get("children") and update_label(item["children"]): return True
            return False
        update_label(tree_data)
        return tree_data

    @app.callback(
        Output("layer-state", "data", allow_duplicate=True),
        Input({"type": "expand-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        prevent_initial_call=True
    )
    def handle_expand_collapse(n_clicks_list, tree_data):
        if not any(n_clicks_list): raise PreventUpdate
        ctx = dash.callback_context
        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        def toggle_expanded(items):
            for item in items:
                if item["id"] == item_id: item["expanded"] = not item.get("expanded", True); return True
                if item.get("children") and toggle_expanded(item["children"]): return True
            return False
        toggle_expanded(tree_data)
        return tree_data

    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True), Output("visibility-state", "data", allow_duplicate=True)],
        Input({"type": "visibility-btn", "index": ALL}, "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        prevent_initial_call=True
    )
    def handle_visibility_toggle(n_clicks_list, tree_data, visibility_state):
        if not any(n_clicks_list): raise PreventUpdate
        ctx = dash.callback_context
        triggered_prop = ctx.triggered[0]["prop_id"]
        match = re.search(r'"index":"([^"]*)"', triggered_prop)
        if not match: raise PreventUpdate
        item_id = match.group(1)
        
        # Initialize visibility_state if None
        if visibility_state is None:
            visibility_state = {}
        
        new_visibility = None
        def toggle_visibility(items):
            nonlocal new_visibility
            for item in items:
                if item["id"] == item_id:
                    new_visibility = not item.get("visible", True)
                    item["visible"] = new_visibility
                    if item.get("children"):
                        for child in item["children"]: child["visible"] = new_visibility
                    return True
                if item.get("children") and toggle_visibility(item["children"]): return True
            return False

        toggle_visibility(tree_data)
        
        if new_visibility is not None:
            visibility_state[item_id] = new_visibility
            def update_children_visibility(items):
                for item in items:
                    if item["id"] == item_id and item.get("children"):
                        for child in item["children"]: visibility_state[child["id"]] = new_visibility
                        return
                    if item.get("children"): update_children_visibility(item["children"])
            update_children_visibility(tree_data)

        return tree_data, visibility_state

    @app.callback(
        [Output("layer-state", "data", allow_duplicate=True), Output("visibility-state", "data", allow_duplicate=True)],
        Input("toggle-all-visibility", "n_clicks"),
        State("layer-state", "data"),
        State("visibility-state", "data"),
        prevent_initial_call=True
    )
    def toggle_all_visibility(n_clicks, tree_data, visibility_state):
        if not n_clicks: raise PreventUpdate
        
        all_visible = all(item.get("visible", True) for item in tree_data)
        new_visibility = not all_visible

        def set_visibility(items):
            for item in items:
                item["visible"] = new_visibility
                visibility_state[item["id"]] = new_visibility
                if item.get("children"): set_visibility(item["children"])
        
        set_visibility(tree_data)
        return tree_data, visibility_state
