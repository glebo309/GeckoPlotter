from dash import html, dcc, Input, Output, State

def create_fonts_labels_layout(current_settings=None):
    """Create the fonts and labels section layout."""
    if current_settings is None:
        current_settings = get_default_font_settings()
    
    return html.Div([
        # Font Family Section
        html.Div([
            html.H5("🔤 Font Family", className="font-category"),
            dcc.Dropdown(
                id="font-family-dropdown",
                options=[
                    # Scientific & Technical
                    {"label": "📊 Arial", "value": "Arial"},
                    {"label": "📊 Helvetica", "value": "Helvetica"},
                    {"label": "📜 Times New Roman", "value": "Times New Roman"},
                    {"label": "📜 Georgia", "value": "Georgia"},
                    {"label": "📜 Cambria", "value": "Cambria"},
                    
                    # Modern Sans
                    {"label": "🤖 Roboto", "value": "Roboto"},
                    {"label": "🌐 Open Sans", "value": "Open Sans"},
                    {"label": "⛰️ Montserrat", "value": "Montserrat"},
                    {"label": "💚 Verdana", "value": "Verdana"},
                    {"label": "🪟 Segoe UI", "value": "Segoe UI"},
                    
                    # Data Visualization
                    {"label": "📈 Inter", "value": "Inter"},
                    {"label": "📊 Lato", "value": "Lato"},
                    {"label": "💻 Source Sans Pro", "value": "Source Sans Pro"},
                    {"label": "🐧 Ubuntu", "value": "Ubuntu"},
                    
                    # Elegant & Clean
                    {"label": "🎯 Futura", "value": "Futura"},
                    {"label": "🎨 Gill Sans", "value": "Gill Sans"},
                    {"label": "✨ Century Gothic", "value": "Century Gothic"},
                    {"label": "📐 Optima", "value": "Optima"},
                    {"label": "👑 Garamond", "value": "Garamond"}
                ],
                value=current_settings.get("font_family", "Arial"),
                className="sidebar-dropdown",
                clearable=False
            )
        ], className="font-section"),
        
        # Font Sizes Section
        html.Div([
            html.H5("📏 Font Sizes", className="font-category"),
            
            html.Div([
                # Left Column
                html.Div([
                    html.Div([
                        html.Label("Title Font", className="font-label"),
                        dcc.Slider(
                            id="title-font-slider",
                            min=8, max=30, step=1,
                            value=current_settings.get("title_fs", 18),
                            marks={8: '8', 14: '14', 18: '18', 24: '24', 30: '30'},
                            className="sidebar-slider"
                        ),
                        html.Div(id="title-font-display", className="font-size-display")
                    ], className="font-control"),
                    
                    html.Div([
                        html.Label("Axis Font", className="font-label"),
                        dcc.Slider(
                            id="axis-font-slider",
                            min=6, max=24, step=1,
                            value=current_settings.get("axis_fs", 14),
                            marks={6: '6', 10: '10', 14: '14', 18: '18', 24: '24'},
                            className="sidebar-slider"
                        ),
                        html.Div(id="axis-font-display", className="font-size-display")
                    ], className="font-control"),
                ], className="font-column"),
                
                # Right Column
                html.Div([
                    html.Div([
                        html.Label("Legend Font", className="font-label"),
                        dcc.Slider(
                            id="legend-font-slider",
                            min=6, max=24, step=1,
                            value=current_settings.get("legend_fs", 12),
                            marks={6: '6', 10: '10', 12: '12', 16: '16', 24: '24'},
                            className="sidebar-slider"
                        ),
                        html.Div(id="legend-font-display", className="font-size-display")
                    ], className="font-control"),
                    
                    html.Div([
                        html.Label("Tick Font", className="font-label"),
                        dcc.Slider(
                            id="tick-font-slider",
                            min=6, max=20, step=1,
                            value=current_settings.get("tick_fs", 10),
                            marks={6: '6', 8: '8', 10: '10', 14: '14', 20: '20'},
                            className="sidebar-slider"
                        ),
                        html.Div(id="tick-font-display", className="font-size-display")
                    ], className="font-control"),
                ], className="font-column"),
            ], className="font-grid"),
        ], className="font-section"),
        
        # Axis Labels Section
        html.Div([
            html.H5("🏷️ Axis Labels", className="font-category"),
            
            html.Div([
                html.Div([
                    html.Label("X-Axis Label"),
                    dcc.Input(
                        id="x-axis-label-input",
                        type="text",
                        value=current_settings.get("xaxis_title", "Time (min)"),
                        className="sidebar-input",
                        placeholder="e.g. Time (min)"
                    )
                ], className="label-input-group"),
                
                html.Div([
                    html.Label("Y-Axis Label"),
                    dcc.Input(
                        id="y-axis-label-input",
                        type="text",
                        value=current_settings.get("yaxis_title", "Signal (a.u.)"),
                        className="sidebar-input",
                        placeholder="e.g. Signal (a.u.)"
                    )
                ], className="label-input-group"),
            ], className="label-grid"),
            
            html.Div([
                html.Label("Axis Label Color"),
                dcc.Input(
                    id="axis-color-picker",
                    type="text",
                    value=current_settings.get("axis_label_color", "#000000"),
                    className="sidebar-color-picker",
                    style={
                        'width': '60px',
                        'height': '32px',
                        'background': current_settings.get("axis_label_color", "#000000"),
                        'border': '1px solid #ccc',
                        'borderRadius': '4px'
                    }
                )
            ], className="color-control"),
        ], className="font-section"),
        
        # Legend Settings Section
        html.Details([
            html.Summary("📋 Legend Settings"),
            html.Div([
                html.Div([
                    html.Div([
                        html.Label("Legend X Position"),
                        dcc.Slider(
                            id="legend-x-slider",
                            min=0.0, max=1.0, step=0.01,
                            value=current_settings.get("legend_x", 0.9),
                            marks={0: 'Left', 0.5: 'Center', 1: 'Right'},
                            className="sidebar-slider"
                        )
                    ], className="position-control"),
                    
                    html.Div([
                        html.Label("Legend Y Position"),
                        dcc.Slider(
                            id="legend-y-slider",
                            min=0.0, max=2.0, step=0.01,
                            value=current_settings.get("legend_y", 0.95),
                            marks={0: 'Bottom', 1: 'Top', 2: 'Above'},
                            className="sidebar-slider"
                        )
                    ], className="position-control"),
                ], className="position-grid"),
                
                html.Div([
                    html.Label("Orientation"),
                    dcc.RadioItems(
                        id="legend-orientation-radio",
                        options=[
                            {"label": "📊 Horizontal", "value": "horizontal"},
                            {"label": "📋 Vertical", "value": "vertical"}
                        ],
                        value=current_settings.get("legend_orientation", "vertical"),
                        className="radio-group"
                    )
                ], className="orientation-control"),
                
                html.Div([
                    dcc.Checklist(
                        id="legend-options-checkbox",
                        options=[
                            {"label": "Show Border", "value": "show_border"},
                            {"label": "Background", "value": "show_background"},
                            {"label": "Outside Plot", "value": "outside_plot"}
                        ],
                        value=current_settings.get("legend_options", ["show_background"]),
                        className="sidebar-checkbox"
                    )
                ])
            ])
        ], open=False, className="advanced-section"),
        
        # Plot Title Section
        html.Details([
            html.Summary("📝 Plot Title"),
            html.Div([
                html.Div([
                    html.Label("Plot Title"),
                    dcc.Input(
                        id="plot-title-input",
                        type="text",
                        value=current_settings.get("title", "Chromatogram Analysis"),
                        className="sidebar-input",
                        placeholder="Enter plot title"
                    )
                ], className="title-input-group"),
                
                html.Div([
                    html.Label("Title Color"),
                    dcc.Input(
                        id="title-color-picker", 
                        type="text",
                        value=current_settings.get("title_color", "#000000"),
                        className="sidebar-color-picker",
                        style={
                            'width': '60px',
                            'height': '32px', 
                            'background': current_settings.get("title_color", "#000000"),
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        }
                    )
                ], className="color-control"),
            ])
        ], open=False, className="advanced-section"),
        
        # Reset Button
        html.Button("🔄 Reset Font Settings", id="reset-font-settings-btn", className="sidebar-btn-full")
        
    ], className="fonts-labels-container")

def get_default_font_settings():
    """Get default font and label settings."""
    return {
        "font_family": "Arial",
        "title_fs": 18,
        "axis_fs": 14,
        "legend_fs": 12,
        "tick_fs": 10,
        "title": "Chromatogram Analysis",
        "xaxis_title": "Time (min)",
        "yaxis_title": "Signal (a.u.)",
        "axis_label_color": "#000000",
        "title_color": "#000000",
        "legend_x": 0.9,
        "legend_y": 0.95,
        "legend_orientation": "vertical",
        "legend_options": ["show_background"]
    }

def register_fonts_labels_callbacks(app):
    """Register callbacks for fonts and labels functionality."""
    
    # Font size display updates
    @app.callback(
        [Output("title-font-display", "children"),
         Output("axis-font-display", "children"),
         Output("legend-font-display", "children"),
         Output("tick-font-display", "children")],
        [Input("title-font-slider", "value"),
         Input("axis-font-slider", "value"),
         Input("legend-font-slider", "value"),
         Input("tick-font-slider", "value")]
    )
    def update_font_displays(title_fs, axis_fs, legend_fs, tick_fs):
        return f"{title_fs}px", f"{axis_fs}px", f"{legend_fs}px", f"{tick_fs}px"
    
    # Font family change
    @app.callback(
        Output("font-family-store", "data"),
        Input("font-family-dropdown", "value"),
        prevent_initial_call=True
    )
    def update_font_family(font_family):
        print(f"Font family changed to: {font_family}")
        return {"font_family": font_family}
    
    # Font sizes change
    @app.callback(
        Output("font-sizes-store", "data"),
        [Input("title-font-slider", "value"),
         Input("axis-font-slider", "value"),
         Input("legend-font-slider", "value"),
         Input("tick-font-slider", "value")],
        prevent_initial_call=True
    )
    def update_font_sizes(title_fs, axis_fs, legend_fs, tick_fs):
        print(f"Font sizes updated: Title={title_fs}, Axis={axis_fs}, Legend={legend_fs}, Tick={tick_fs}")
        return {
            "title_fs": title_fs,
            "axis_fs": axis_fs,
            "legend_fs": legend_fs,
            "tick_fs": tick_fs
        }
    
    # Axis labels change
    @app.callback(
        Output("axis-labels-store", "data"),
        [Input("x-axis-label-input", "value"),
         Input("y-axis-label-input", "value"),
         Input("axis-color-picker", "value")],
        prevent_initial_call=True
    )
    def update_axis_labels(x_label, y_label, axis_color):
        print(f"Axis labels updated: X='{x_label}', Y='{y_label}', Color={axis_color}")
        return {
            "xaxis_title": x_label,
            "yaxis_title": y_label,
            "axis_label_color": axis_color
        }
    
    # Legend settings change
    @app.callback(
        Output("legend-settings-store", "data"),
        [Input("legend-x-slider", "value"),
         Input("legend-y-slider", "value"),
         Input("legend-orientation-radio", "value"),
         Input("legend-options-checkbox", "value")],
        prevent_initial_call=True
    )
    def update_legend_settings(legend_x, legend_y, orientation, options):
        print(f"Legend settings updated: X={legend_x}, Y={legend_y}, Orientation={orientation}")
        return {
            "legend_x": legend_x,
            "legend_y": legend_y,
            "legend_orientation": orientation,
            "legend_options": options or []
        }
    
    # Plot title change
    @app.callback(
        Output("plot-title-store", "data"),
        [Input("plot-title-input", "value"),
         Input("title-color-picker", "value")],
        prevent_initial_call=True
    )
    def update_plot_title(title, title_color):
        print(f"Plot title updated: '{title}', Color={title_color}")
        return {
            "title": title,
            "title_color": title_color
        }
    
    # Reset font settings
    @app.callback(
        [Output("font-family-dropdown", "value"),
         Output("title-font-slider", "value"),
         Output("axis-font-slider", "value"),
         Output("legend-font-slider", "value"),
         Output("tick-font-slider", "value"),
         Output("x-axis-label-input", "value"),
         Output("y-axis-label-input", "value"),
         Output("axis-color-picker", "value"),
         Output("plot-title-input", "value"),
         Output("title-color-picker", "value")],
        Input("reset-font-settings-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def reset_font_settings(n_clicks):
        if n_clicks:
            defaults = get_default_font_settings()
            print("Font settings reset to defaults")
            return (
                defaults["font_family"],
                defaults["title_fs"],
                defaults["axis_fs"],
                defaults["legend_fs"],
                defaults["tick_fs"],
                defaults["xaxis_title"],
                defaults["yaxis_title"],
                defaults["axis_label_color"],
                defaults["title"],
                defaults["title_color"]
            )
        return dash.no_update

def apply_font_settings_to_figure(fig, font_settings):
    """Apply font settings to a plotly figure."""
    if not font_settings:
        return fig
    
    # Apply global font family
    font_family = font_settings.get('font_family', 'Arial')
    fig.update_layout(font=dict(family=font_family))
    
    # Apply title settings
    title_text = font_settings.get('title', 'Chromatogram Analysis')
    title_color = font_settings.get('title_color', '#000000')
    title_size = font_settings.get('title_fs', 18)
    
    fig.update_layout(
        title=dict(
            text=title_text,
            font=dict(
                family=font_family,
                size=title_size,
                color=title_color
            )
        )
    )
    
    # Apply axis settings
    axis_color = font_settings.get('axis_label_color', '#000000')
    axis_size = font_settings.get('axis_fs', 14)
    tick_size = font_settings.get('tick_fs', 10)
    
    fig.update_xaxes(
        title=dict(
            text=font_settings.get('xaxis_title', 'Time (min)'),
            font=dict(
                family=font_family,
                size=axis_size,
                color=axis_color
            )
        ),
        tickfont=dict(
            family=font_family,
            size=tick_size
        )
    )
    
    fig.update_yaxes(
        title=dict(
            text=font_settings.get('yaxis_title', 'Signal (a.u.)'),
            font=dict(
                family=font_family,
                size=axis_size,
                color=axis_color
            )
        ),
        tickfont=dict(
            family=font_family,
            size=tick_size
        )
    )
    
    # Apply legend settings
    legend_size = font_settings.get('legend_fs', 12)
    legend_x = font_settings.get('legend_x', 0.9)
    legend_y = font_settings.get('legend_y', 0.95)
    legend_orientation = font_settings.get('legend_orientation', 'vertical')
    legend_options = font_settings.get('legend_options', [])
    
    fig.update_layout(
        legend=dict(
            font=dict(
                family=font_family,
                size=legend_size
            ),
            x=legend_x,
            y=legend_y,
            orientation='h' if legend_orientation == 'horizontal' else 'v',
            bgcolor='rgba(255,255,255,0.9)' if 'show_background' in legend_options else 'rgba(0,0,0,0)',
            borderwidth=1 if 'show_border' in legend_options else 0,
            bordercolor='black' if 'show_border' in legend_options else 'rgba(0,0,0,0)'
        )
    )
    
    return fig