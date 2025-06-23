# File: layouts/main_layout.py - Updated with Enhanced Peak Detection

from dash import html, dcc
from utils.toast_system import create_toast_container
from file_tree_manager import create_file_tree_manager
from callbacks.baseline_integration_callbacks import create_baseline_integration_controls
from callbacks.peak_detection_callbacks import create_peak_detection_controls  # ADD THIS IMPORT

def create_layout():
    return html.Div([
        # Hidden stores for baseline integration state
        dcc.Store(id="baseline-mode", data="draw"),
        dcc.Store(id="p-line-store"),
        dcc.Store(id="stored-peaks", data=[]),
        dcc.Store(id="selected-peak-idx"),
        dcc.Store(id="p-line-visible", data=True),
        dcc.Store(id="clear-shapes-trigger", data=0),
        dcc.Store(id='baseline-overlays-store'),
        dcc.Store(id='plot-zoom-state', data=None),
        # Hidden dummy divs for tab switching
        html.Div(id='_sidebar_tab_dummy', style={'display': 'none'}),
        html.Div(id='_analysis_tab_dummy', style={'display': 'none'}),
        # Toast System
        create_toast_container(),

        # Header - Adobe Style
        html.Div([
            html.Div([
                html.Span("🦎", className="logo-icon"),
                html.Span("GeckoPlotter")
            ], className="logo"),
            
            # Header Navigation Pills
            html.Div([
                html.Div("📊 UV-VIS", className="nav-pill", id="pill-uvvis_csv"),
                html.Div("📈 HPLC", className="nav-pill", id="pill-chromatogram"), 
                html.Div("📦 LC-MS", className="nav-pill", id="pill-lcms_bundle"),
                html.Div("🌊 Spectral", className="nav-pill", id="pill-spectra"),
            ], className="header-nav"),

            dcc.Upload(
                id="upload-data",
                className="upload-btn",
                children=[
                    html.Span("📁"),
                    html.Span("Upload Data")
                ],
                multiple=True
            ),
        ], className="header"),

        # Main Container
        html.Div([
            # Split Sidebar
            html.Div([
                # Top Half - Tabbed Controls
                html.Div([
                    # Tab Header
                    html.Div([
                        html.Button("Sample", id="sample-tab-btn", className="tab-button active", **{"data-tab": "sample"}),
                        html.Button("Peak", id="peak-tab-btn", className="tab-button", **{"data-tab": "peak"}),
                        html.Button("Plot", id="plot-tab-btn", className="tab-button", **{"data-tab": "plot"}),
                        html.Button("Export", id="export-tab-btn", className="tab-button", **{"data-tab": "export"}),
                    ], className="tab-header"),

                    # Tab Content Container
                    html.Div([
                        # Sample Management Tab
                        html.Div([
                            html.Div(id="data-overview", style={
                                "fontSize": "12px",
                                "color": "#505050",
                                "maxHeight": "100%",
                                "overflowY": "auto"
                            })
                        ], className="tab-panel active", id="sample-tab"),

                        # Enhanced Peak Analysis Tab
                        html.Div([
                            # Baseline Integration Controls
                            create_baseline_integration_controls(),
                            
                            html.Hr(style={'margin': '20px 0'}),
                            
                            # Peak Detection Controls
                            create_peak_detection_controls()
                        ], className="tab-panel", id="peak-tab"),

                        # Plot Settings Tab
                        html.Div([
                            # Line Appearance
                            html.Div([
                                html.Label("Line Appearance", className="form-label"),
                                html.Div([
                                    html.Label("Line Thickness", className="form-sublabel"),
                                    dcc.Slider(
                                        id="line-thickness-slider",
                                        min=0.5, max=5.0, value=1.5, step=0.1,
                                        className="slider",
                                        marks={0.5: "0.5", 1.5: "1.5", 3.0: "3.0", 5.0: "5.0"},
                                        tooltip={"placement": "bottom", "always_visible": True}
                                    ),
                                ], className="slider-group"),
                            ], className="form-group"),

                            # Plot Layout Options
                            html.Div([
                                html.Label("Plot Layout", className="form-label"),
                                dcc.Checklist(
                                    id="plot-layout-options",
                                    options=[
                                        {"label": "Separate plots", "value": "separate_plots"},
                                        {"label": "Show legend", "value": "legend"},
                                        {"label": "Smooth lines", "value": "smooth"},
                                    ],
                                    value=["legend"],
                                    className="checkbox-group",
                                    labelStyle={"display": "flex", "alignItems": "center", "gap": "8px"}
                                )
                            ], className="form-group"),

                            # Grid Options
                            html.Div([
                                html.Label("Grid Options", className="form-label"),
                                dcc.Checklist(
                                    id="grid-options",
                                    options=[
                                        {"label": "Horizontal grid", "value": "horizontal"},
                                        {"label": "Vertical grid", "value": "vertical"},
                                    ],
                                    value=[],
                                    className="checkbox-group",
                                    labelStyle={"display": "flex", "alignItems": "center", "gap": "8px"}
                                )
                            ], className="form-group"),

                            # Axis Labels
                            html.Div([
                                html.Label("Axis Labels", className="form-label"),
                                dcc.Input(
                                    id="x-axis-label",
                                    type="text",
                                    placeholder="X-axis label",
                                    value="Time (min)",
                                    className="form-input"
                                ),
                                dcc.Input(
                                    id="y-axis-label",
                                    type="text",
                                    placeholder="Y-axis label",
                                    value="Signal Intensity",
                                    className="form-input",
                                    style={"marginTop": "4px"}
                                ),
                            ], className="form-group"),

                            # Axis Bounds
                            html.Div([
                                html.Label("Axis Bounds", className="form-label"),
                                
                                # X-axis bounds
                                html.Div([
                                    html.Label("X-axis (Time)", className="form-sublabel"),
                                    html.Div([
                                        dcc.Input(
                                            id="x-min-input",
                                            type="number",
                                            placeholder="X min",
                                            step=0.001,
                                            className="form-input"
                                        ),
                                        dcc.Input(
                                            id="x-max-input",
                                            type="number",
                                            placeholder="X max",
                                            step=0.001,
                                            className="form-input"
                                        ),
                                    ], style={"display": "flex", "gap": "8px"}),
                                ], style={"marginBottom": "8px"}),
                                
                                # Y-axis bounds
                                html.Div([
                                    html.Label("Y-axis (Signal)", className="form-sublabel"),
                                    html.Div([
                                        dcc.Input(
                                            id="y-min-input",
                                            type="number",
                                            placeholder="Y min",
                                            step=0.01,
                                            className="form-input"
                                        ),
                                        dcc.Input(
                                            id="y-max-input",
                                            type="number",
                                            placeholder="Y max",
                                            step=0.01,
                                            className="form-input"
                                        ),
                                    ], style={"display": "flex", "gap": "8px"}),
                                ]),
                                
                                # Reset button
                                html.Button(
                                    "Reset to Auto Range", 
                                    id="reset-axis-bounds-btn", 
                                    className="btn-secondary",
                                    style={"marginTop": "8px", "width": "100%"}
                                ),
                            ], className="form-group"),

                        ], className="tab-panel", id="plot-tab"),

                        # Export Tab
                        html.Div([
                            html.Div([
                                html.Label("Format", className="form-label"),
                                dcc.Dropdown(
                                    id="export-format",
                                    options=[
                                        {"label": "PNG (High Quality)", "value": "png"},
                                        {"label": "SVG (Vector)", "value": "svg"},
                                        {"label": "PDF (Print)", "value": "pdf"},
                                        {"label": "CSV (Data)", "value": "csv"},
                                    ],
                                    value="png",
                                    className="form-select"
                                ),
                            ], className="form-group"),

                            html.Div([
                                html.Label("Size", className="form-label"),
                                html.Div([
                                    dcc.Input(
                                        id="export-width",
                                        type="number",
                                        placeholder="Width",
                                        value=1200,
                                        className="form-input"
                                    ),
                                    dcc.Input(
                                        id="export-height",
                                        type="number",
                                        placeholder="Height",
                                        value=800,
                                        className="form-input"
                                    ),
                                ], style={"display": "flex", "gap": "8px"}),
                            ], className="form-group"),

                            html.Div([
                                html.Label("DPI", className="form-label"),
                                dcc.Dropdown(
                                    id="export-dpi",
                                    options=[
                                        {"label": "300 (Print)", "value": 300},
                                        {"label": "150 (Screen)", "value": 150},
                                        {"label": "72 (Web)", "value": 72},
                                    ],
                                    value=300,
                                    className="form-select"
                                ),
                            ], className="form-group"),

                            html.Button("Export Plot", className="btn-primary", style={"width": "100%"}),
                        ], className="tab-panel", id="export-tab"),

                    ], className="tab-content"),
                ], className="sidebar-top"),

                # Bottom Half - File Tree Manager
                html.Div([
                    create_file_tree_manager()
                ], className="sidebar-bottom"),

            ], className="sidebar", id="dynamic-sidebar", style={"display": "none"}),

            # Storage components for settings
            dcc.Store(id="baseline-mode-store", data="zoom"),
            dcc.Store(id="peak-settings-store"),
            dcc.Store(id="plot-style-store"),
            dcc.Store(id="color-scheme-store"),
            dcc.Store(id="line-width-store"),
            dcc.Store(id="plot-options-store"),
            dcc.Store(id="axis-range-store"),
            dcc.Store(id="font-family-store"),
            dcc.Store(id="font-sizes-store"),
            dcc.Store(id="axis-labels-store"),
            dcc.Store(id="legend-settings-store"),
            dcc.Store(id="plot-title-store"),
            dcc.Store(id="active-hplc-tab-store", data="current"),
            dcc.Store(id="selected-peak-group-store", data=0),
            dcc.Store(id="peak-detection-trigger", data={}), 

            # Hidden components that callbacks expect
            html.Div([
                html.Div(id="file-list", children="No files loaded"),
                html.Button("🗑 Clear All", id="clear-data-btn", n_clicks=0, style={"display": "none"}),
                html.Span(id="clear-feedback", style={"display": "none"}),
                dcc.Dropdown(id="file-selector", style={"display": "none"}),
            ], style={"display": "none"}),

            # Main Content Area
            html.Div([
                # Dashboard Container (wrapper for main content when files are loaded)
                html.Div([
                    # Viz Card (wrapper for plot)
                    html.Div([
                        # Content Header
                        html.Div([
                            html.Div([
                                html.Button("🖊️ Draw", id="draw-peak", className="icon-btn floating-btn", title="Draw Peak"),
                                html.Button("✏️ Edit", id="edit-peak", className="icon-btn floating-btn", title="Edit Peak"),
                                html.Button("🔍 Zoom", id="nav-peak", className="icon-btn floating-btn", title="Zoom/Pan Mode"),
                                html.Button("🗑️ Clear", id="clear-peak", className="icon-btn floating-btn", title="Clear Peak"),
                            ], className="floating-tools", style={
                                'position': 'absolute', 'top': '10px', 'right': '10px', 'z-index': '1000',
                                'background': 'rgba(255,255,255,0.95)', 'border-radius': '8px', 'padding': '4px',
                                'box-shadow': '0 2px 8px rgba(0,0,0,0.15)', 'display': 'flex', 'gap': '4px'
                            }),
                        ], className="content-header"),

                        # Upload Status
                        html.Div(id='upload-status', style={'margin-bottom': '4px'}),

                        html.Div([
                            # Plot container (shows one or more graphs)
                            html.Div([
                                dcc.Graph(id='ms-plot', style={'width': '100%', 'height': '100%', 'display': 'none'},
                                        config={"toImageButtonOptions": {"format": "png", "filename": "uv_chromatogram_plot","scale": 10}}
                                ),

                                dcc.Graph(id='uv-chromatogram-plot', 
                                          style={'width': '100%', 'height': '100%', 'display': 'none'},
                                        config={"toImageButtonOptions": {"format": "png", "filename": "uv_chromatogram_plot","scale": 10}}
                                          ),

                                dcc.Graph(id='uvvis-plate-plot', style={'width': '100%', 'height': '100%', 'display': 'none'},
                                    config={"toImageButtonOptions": {"format": "png", "filename": "uv_chromatogram_plot","scale": 10}}
                                ),

                                dcc.Graph(id='spectra-plot', style={'width': '100%', 'height': '100%', 'display': 'none'},
                                config={"toImageButtonOptions": {"format": "png", "filename": "uv_chromatogram_plot","scale": 10}}
                                )
                            ], id='plot-container', className="resizable-plot-container"),

                            # === DRAGGABLE RESIZE HANDLE ===
                            html.Div(id='resize-handle', className="resize-handle"),

                            # HPLC Analysis Results Section
                            html.Div([
                                html.Div([
                                    # Tab Header for Analysis Tables
                                    html.Div([
                                        html.Button("Integration", id="integration-tab-btn", className="tab-button active", **{"data-tab": "integration"}),
                                        html.Button("Across Samples", id="across-samples-tab-btn", className="tab-button", **{"data-tab": "across-samples"}),
                                        html.Button("Calibration", id="calibration-tab-btn", className="tab-button", **{"data-tab": "calibration"}),
                                    ], className="tab-header analysis-tabs"),
                                    
                                    # Tab Content for Analysis Tables
                                    html.Div([
                                        # Integration Table Tab - Current sample peaks
                                        html.Div(id="integration-table-container", className="tab-panel active table-container", **{"data-tab-content": "integration"}),
                                        
                                        # Across Samples Tab - Selected peak across all samples
                                        html.Div(id="across-samples-container", className="tab-panel table-container", **{"data-tab-content": "across-samples"}),
                                        
                                        # Calibration Tab - For calibration curves
                                        html.Div(id="calibration-container", className="tab-panel table-container", **{"data-tab-content": "calibration"}),
                                    ], className="tab-content analysis-tab-content")
                                ], className="hplc-analysis-content")
                            ],
                                className="resizable-table-container",
                                id="hplc-analysis-section",
                                style={'display': 'block'}
                            ),

                        ], className="resizable-layout", id="main-resizable-layout"),

                        # Details Overlay (for toggleable details panel)
                        html.Div([
                            html.Div([
                                html.Button("✕", id="close-details-btn", className="close-btn")
                            ], className="card-header"),
                            html.Div(id='details-overlay-content', className="card-content")
                        ], className="details-overlay", id="details-overlay", style={'display': 'none'}),
                        
                        dcc.Store(id='plot-height-store', data=60), 

                    ], className="viz-card", id="viz-card", style={'display': 'none'}),
                ], className="dashboard-container", id="dashboard-container", style={'display': 'none'}),

                # Upload Card (only when no data)
                html.Div([
                    html.Div([
                        html.Div("📁 Upload New Data", className="card-title"),
                    ], className="card-header"),
                    dcc.Upload(
                        id="upload-data-zone",
                        className="upload-zone",
                        children=[
                            html.Div("📁", className="upload-icon"),
                            html.Div("Drag & drop your analytical files", className="upload-subtitle"),
                            html.Div("CDF, CSV, TXT formats supported", className="upload-subtitle"),
                        ],
                        multiple=True
                    )
                ], className="card", id="upload-card", style={'display': 'block'}),

            ], className="content")
        ], className="main-container")
    ])