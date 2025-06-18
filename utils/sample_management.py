from dash import html, dcc, Input, Output, State, callback_context

import dash
import dash.dependencies
import plotly.graph_objects as go
from utils.toast_system import add_toast_to_store


def create_sample_management_layout(data_manager):
    """Create the sample management section layout."""
    files = data_manager.get_loaded_files()
    if not files:
        return html.Div("No samples loaded")
    
    sample_items = []
    for i, fname in enumerate(files):
        file_data = data_manager.get_file_data(fname)
        if not file_data:
            continue
            
        # Get file type icon and info
        icons = {
            'uvvis_csv': '📊',
            'lcms_cdf': '📈', 
            'lcms_bundle': '📦',
            'chromeleon_bundle': '📈',
            'chromatogram': '📉',
            'spectra': '🌊'
        }
        icon = icons.get(file_data['type'], '📄')
        
        # Get metadata for display
        metadata = file_data.get('metadata', {})
        
        # Create display info based on file type
        if file_data['type'] == 'uvvis_csv':
            wells_count = metadata.get('filled_well_count', 0)
            info_text = f"{wells_count} wells"
        elif file_data['type'] == 'chromeleon_bundle':
            injection_date = metadata.get('Injection Date', '')
            info_text = injection_date
        elif file_data['type'] == 'lcms_bundle':
            components = metadata.get('components', [])
            info_text = f"{len(components)} components"
        else:
            wavelength = metadata.get('wavelength', metadata.get('Wavelength (nm)', ''))
            info_text = f"{wavelength} nm" if wavelength else "Chromatogram"
        
        # Shortened name
        display_name = fname.replace('_UV_VIS_1.txt', '').replace('temp_', '')
        if len(display_name) > 25:
            display_name = display_name[:22] + '...'
        
        # Create sample row
        sample_items.append(
            html.Div([
                # Left side - checkbox and info
                html.Div([
                    dcc.Checklist(
                        id={'type': 'sample-visibility', 'index': fname},
                        options=[{"label": "", "value": "visible"}],
                        value=["visible"],  # Default visible
                        className="sample-checkbox"
                    ),
                    html.Div([
                        html.Div(f"{icon} {display_name}", className="sample-name"),
                        html.Div(info_text, className="sample-info")
                    ], className="sample-text")
                ], className="sample-left"),
                
                # Color picker
                html.Div([


                    dcc.Input(
                        id={'type': 'sample-color', 'index': fname},
                        type="text",
                        value=get_sample_color(file_data),
                        className="sample-color-picker",
                        style={
                            'width': '30px', 
                            'height': '30px',
                            'background': get_sample_color(file_data),
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        }
                    )

                ], className="sample-color"),
                
                # Right side - action buttons
                html.Div([
                    html.Button("👁", 
                        id={'type': 'sample-view', 'index': fname},
                        className="sample-btn", 
                        title="View"),
                    html.Button("✏️", 
                        id={'type': 'sample-edit', 'index': fname},
                        className="sample-btn", 
                        title="Rename"),
                    html.Button("🗑", 
                        id={'type': 'sample-delete', 'index': fname},
                        className="sample-btn sample-btn-danger", 
                        title="Delete"),
                ], className="sample-actions")
            ], className="sample-row", id=f"sample-row-{i}")
        )
    
    # Add the "Add Sample" button
    sample_items.append(
        html.Button([
            html.Span("+ "),
            html.Span("Add Sample")
        ], id="add-sample-btn", className="sidebar-btn-full sample-add-btn")
    )
    
    # Add feedback divs (hidden)
    sample_items.extend([
        html.Div(id="sample-visibility-feedback", style={"display": "none"}),
        html.Div(id="sample-color-feedback", style={"display": "none"}),
        html.Div(id="sample-edit-feedback", style={"display": "none"}),
        html.Div(id="sample-management-feedback", style={"display": "none"}),
    ])


    return html.Div(sample_items, className="sample-list")

def get_sample_color(file_data):
    """Get a default color for a sample based on its type."""
    color_map = {
        'uvvis_csv': '#3498db',      # Blue
        'lcms_cdf': '#e74c3c',       # Red
        'lcms_bundle': '#9b59b6',    # Purple
        'chromeleon_bundle': '#2ecc71', # Green
        'chromatogram': '#f39c12',   # Orange
        'spectra': '#1abc9c'         # Teal
    }
    return color_map.get(file_data.get('type'), '#95a5a6')

def register_sample_management_callbacks(app, data_manager):
    """Register callbacks for sample management."""
    
    # Sample visibility toggle
    @app.callback(
        Output("sample-visibility-feedback", "children"),
        Input({'type': 'sample-visibility', 'index': dash.dependencies.ALL}, 'value'),
        prevent_initial_call=True
    )
    def toggle_sample_visibility(visibility_values):
        # TODO: Implement visibility logic
        print(f"Sample visibility toggled: {visibility_values}")
        return ""
    
    # Sample color change
    @app.callback(
        Output("sample-color-feedback", "children"),
        Input({'type': 'sample-color', 'index': dash.dependencies.ALL}, 'value'),
        prevent_initial_call=True
    )
    def change_sample_color(color_values):
        # TODO: Implement color change logic
        print(f"Sample colors changed to: {color_values}")
        return ""
    
    # Sample view button
    @app.callback(
        Output("file-selector", "value", allow_duplicate=True),
        Input({'type': 'sample-view', 'index': dash.dependencies.ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def view_sample(n_clicks_list):
        if not any(n_clicks_list):
            return dash.no_update
        
        ctx = callback_context
        if ctx.triggered:
            button_id = ctx.triggered[0]['prop_id']
            # Extract filename from button ID
            import json
            button_data = json.loads(button_id.split('.')[0])
            filename = button_data['index']
            print(f"Viewing sample: {filename}")
            return filename
        
        return dash.no_update
    
    # Sample edit button
    @app.callback(
        Output("sample-edit-feedback", "children"),
        Input({'type': 'sample-edit', 'index': dash.dependencies.ALL}, 'n_clicks'),
        prevent_initial_call=True
    )
    def edit_sample(n_clicks_list):
        if any(n_clicks_list):
            # TODO: Implement rename dialog/functionality
            print("Sample edit clicked")
            return "Edit mode activated"
        return ""
    
    # Sample delete button
    @app.callback(
        [Output("sample-list-container", "children", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True)],
        Input({'type': 'sample-delete', 'index': dash.dependencies.ALL}, 'n_clicks'),
        State("toast-store", "data"),
        prevent_initial_call=True
    )
    def delete_sample(n_clicks_list, current_toasts):
        if not n_clicks_list or not any(n_clicks_list):
            return dash.no_update, dash.no_update
        
        try:
            ctx = callback_context
            if ctx.triggered:
                button_id = ctx.triggered[0]['prop_id']
                import json
                button_data = json.loads(button_id.split('.')[0])
                filename = button_data['index']
                
                # Delete from data manager
                if hasattr(data_manager, 'loaded_data') and filename in data_manager.loaded_data:
                    del data_manager.loaded_data[filename]
                    
                    # Success toast
                    new_toasts = add_toast_to_store(current_toasts, f"🗑️ Deleted {filename}", "success")
                    
                    return create_sample_management_layout(data_manager), new_toasts
                else:
                    # Error toast
                    new_toasts = add_toast_to_store(current_toasts, f"❌ Could not find {filename}", "error")
                    return dash.no_update, new_toasts
                    
        except Exception as e:
            # Error toast
            new_toasts = add_toast_to_store(current_toasts, f"❌ Delete failed: {str(e)}", "error")
            return dash.no_update, new_toasts
        
        return dash.no_update, dash.no_update

    # Add sample button
    @app.callback(
        Output("add-sample-btn", "children", allow_duplicate=True),
        Input("add-sample-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def add_sample(n_clicks):
        if n_clicks:
            # TODO: Implement add sample functionality (file dialog, etc.)
            print("Add sample clicked")
            return ["+ ", "Adding... ✨"]
        return ["+ ", "Add Sample"]