from dash import html, dcc, Input, Output, State

def create_plot_settings_layout(current_settings=None):
    """Create the plot settings section layout."""
    if current_settings is None:
        current_settings = get_default_plot_settings()
    
    return html.Div([
        # Plot Style
        html.Div([
            html.Label("Plot Style", className="settings-label"),
            dcc.Dropdown(
                id="plot-style-dropdown",
                options=[
                    {"label": "📈 Lines", "value": "lines"},
                    {"label": "⚫ Markers", "value": "markers"},
                    {"label": "📊 Lines + Markers", "value": "lines+markers"},
                    {"label": "📉 Filled Area", "value": "fill"}
                ],
                value=current_settings.get("style", "lines"),
                className="sidebar-dropdown",
                clearable=False
            )
        ], className="settings-group"),
        
        # Color Scheme
        html.Div([
            html.Label("Color Scheme", className="settings-label"),
            dcc.Dropdown(
                id="color-scheme-dropdown", 
                options=[
                    {"label": "🎨 Default", "value": "default"},
                    {"label": "🌈 Viridis", "value": "viridis"},
                    {"label": "🔥 Plasma", "value": "plasma"},
                    {"label": "🌊 Ocean", "value": "ocean"},
                    {"label": "🍃 Earth", "value": "earth"},
                    {"label": "🌙 Dark", "value": "dark"}
                ],
                value=current_settings.get("color_scheme", "default"),
                className="sidebar-dropdown",
                clearable=False
            )
        ], className="settings-group"),
        
        # Line Properties
        html.Div([
            html.Label("Line Width", className="settings-label"),
            dcc.Slider(
                id="line-width-slider",
                min=1, max=5, step=0.5,
                value=current_settings.get("line_width", 2),
                marks={1: '1', 2: '2', 3: '3', 4: '4', 5: '5'},
                className="sidebar-slider"
            )
        ], className="settings-group"),
        
        # Marker Properties (when applicable)
        html.Div([
            html.Label("Marker Size", className="settings-label"),
            dcc.Slider(
                id="marker-size-slider",
                min=2, max=12, step=1,
                value=current_settings.get("marker_size", 6),
                marks={2: '2', 6: '6', 10: '10', 12: '12'},
                className="sidebar-slider"
            )
        ], className="settings-group"),
        
        # Opacity
        html.Div([
            html.Label("Opacity", className="settings-label"),
            dcc.Slider(
                id="opacity-slider",
                min=0.1, max=1.0, step=0.1,
                value=current_settings.get("opacity", 0.8),
                marks={0.2: '20%', 0.5: '50%', 0.8: '80%', 1.0: '100%'},
                className="sidebar-slider"
            )
        ], className="settings-group"),
        
        # Plot Options Checkboxes
        html.Div([
            html.Label("Display Options", className="settings-label"),
            dcc.Checklist(
                id="plot-options-checkbox",
                options=[
                    {"label": "📊 Show Grid", "value": "show_grid"},
                    {"label": "🏷️ Show Legend", "value": "show_legend"},
                    {"label": "📏 Auto-scale Y", "value": "auto_scale"},
                    {"label": "🔍 Show Hover Info", "value": "show_hover"},
                    {"label": "📐 Show Axis Labels", "value": "show_labels"}
                ],
                value=current_settings.get("options", ["show_grid", "show_legend", "auto_scale", "show_hover", "show_labels"]),
                className="sidebar-checkbox"
            )
        ], className="settings-group"),
        
        # Axis Settings
        html.Details([
            html.Summary("⚙️ Advanced Axis Settings"),
            html.Div([
                html.Div([
                    html.Label("X-axis Range (min)"),
                    dcc.Input(
                        id="x-min-input",
                        type="number",
                        value=current_settings.get("x_min"),
                        className="sidebar-input-small"
                    )
                ], className="input-row"),
                
                html.Div([
                    html.Label("X-axis Range (max)"),
                    dcc.Input(
                        id="x-max-input", 
                        type="number",
                        value=current_settings.get("x_max"),
                        className="sidebar-input-small"
                    )
                ], className="input-row"),
                
                html.Div([
                    html.Label("Y-axis Range (min)"),
                    dcc.Input(
                        id="y-min-input",
                        type="number", 
                        value=current_settings.get("y_min"),
                        className="sidebar-input-small"
                    )
                ], className="input-row"),
                
                html.Div([
                    html.Label("Y-axis Range (max)"),
                    dcc.Input(
                        id="y-max-input",
                        type="number",
                        value=current_settings.get("y_max"),
                        className="sidebar-input-small"
                    )
                ], className="input-row"),
                
                html.Button("Reset Zoom", id="reset-zoom-btn", className="sidebar-btn")
            ])
        ], open=False, className="advanced-section"),
        
        # Reset button
        html.Button("🔄 Reset to Defaults", id="reset-plot-settings-btn", className="sidebar-btn-full")
        
    ], className="plot-settings-container")

def get_default_plot_settings():
    """Get default plot settings."""
    return {
        "style": "lines",
        "color_scheme": "default",
        "line_width": 2,
        "marker_size": 6,
        "opacity": 0.8,
        # Gridlines OFF by default: remove 'show_grid' from default options
        "options": ["show_legend", "auto_scale", "show_hover", "show_labels"],
        "x_min": None,
        "x_max": None,
        "y_min": None,
        "y_max": None
    }

def register_plot_settings_callbacks(app):
    """Register callbacks for plot settings."""
    
    # Plot style change
    @app.callback(
        Output("plot-style-store", "data"),
        Input("plot-style-dropdown", "value"),
        prevent_initial_call=True
    )
    def update_plot_style(style):
        print(f"Plot style changed to: {style}")
        return {"style": style}
    
    # Color scheme change
    @app.callback(
        Output("color-scheme-store", "data"),
        Input("color-scheme-dropdown", "value"),
        prevent_initial_call=True
    )
    def update_color_scheme(scheme):
        print(f"Color scheme changed to: {scheme}")
        return {"color_scheme": scheme}
    
    # Line width change
    @app.callback(
        Output("line-width-store", "data"),
        Input("line-width-slider", "value"),
        prevent_initial_call=True
    )
    def update_line_width(width):
        print(f"Line width changed to: {width}")
        return {"line_width": width}
    
    # Plot options change
    @app.callback(
        Output("plot-options-store", "data"),
        Input("plot-options-checkbox", "value"),
        prevent_initial_call=True
    )
    def update_plot_options(options):
        print(f"Plot options changed to: {options}")
        return {"options": options}
    
    # Reset plot settings
    @app.callback(
        [Output("plot-style-dropdown", "value"),
         Output("color-scheme-dropdown", "value"),
         Output("line-width-slider", "value"),
         Output("marker-size-slider", "value"),
         Output("opacity-slider", "value"),
         Output("plot-options-checkbox", "value")],
        Input("reset-plot-settings-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def reset_plot_settings(n_clicks):
        if n_clicks:
            defaults = get_default_plot_settings()
            print("Plot settings reset to defaults")
            return (
                defaults["style"],
                defaults["color_scheme"], 
                defaults["line_width"],
                defaults["marker_size"],
                defaults["opacity"],
                defaults["options"]
            )
        return dash.no_update
    
    # Axis range updates
    @app.callback(
        Output("axis-range-store", "data"),
        [Input("x-min-input", "value"),
         Input("x-max-input", "value"),
         Input("y-min-input", "value"),
         Input("y-max-input", "value")],
        prevent_initial_call=True
    )
    def update_axis_ranges(x_min, x_max, y_min, y_max):
        print(f"Axis ranges updated: X({x_min}, {x_max}), Y({y_min}, {y_max})")
        return {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max
        }
    
    # Reset zoom
    @app.callback(
        [Output("x-min-input", "value"),
         Output("x-max-input", "value"),
         Output("y-min-input", "value"),
         Output("y-max-input", "value")],
        Input("reset-zoom-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def reset_zoom(n_clicks):
        if n_clicks:
            print("Zoom reset")
            return None, None, None, None
        return dash.no_update