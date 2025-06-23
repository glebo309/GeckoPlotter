from dash import html, dcc, Input, Output, State
import json
import base64
import io

def create_export_options_layout():
    """Create the export options section layout."""
    return html.Div([
        # Image Export
        html.Div([
            html.H5("📊 Image Export", className="export-category"),
            html.Div([
                html.Button([
                    html.Span("🖼️ "),
                    html.Span("Export as PNG")
                ], id="export-png-btn", className="sidebar-btn-full export-btn"),
                
                html.Button([
                    html.Span("📄 "),
                    html.Span("Export as PDF")
                ], id="export-pdf-btn", className="sidebar-btn-full export-btn"),
                
                html.Button([
                    html.Span("🖼️ "),
                    html.Span("Export as SVG")
                ], id="export-svg-btn", className="sidebar-btn-full export-btn"),
            ], className="export-group")
        ], className="export-section"),
        
        # Data Export
        html.Div([
            html.H5("💾 Data Export", className="export-category"),
            html.Div([
                html.Button([
                    html.Span("📊 "),
                    html.Span("Export Raw Data (CSV)")
                ], id="export-csv-btn", className="sidebar-btn-full export-btn"),
                
                html.Button([
                    html.Span("📈 "),
                    html.Span("Export Peak Data (CSV)")
                ], id="export-peaks-csv-btn", className="sidebar-btn-full export-btn"),
                
                html.Button([
                    html.Span("📋 "),
                    html.Span("Export as Excel")
                ], id="export-excel-btn", className="sidebar-btn-full export-btn"),
            ], className="export-group")
        ], className="export-section"),
        
        # Report Export
        html.Div([
            html.H5("📑 Report Export", className="export-category"),
            html.Div([
                html.Button([
                    html.Span("📄 "),
                    html.Span("Generate Summary Report")
                ], id="export-report-btn", className="sidebar-btn-full export-btn"),
                
                html.Button([
                    html.Span("📊 "),
                    html.Span("Export Analysis Report")
                ], id="export-analysis-report-btn", className="sidebar-btn-full export-btn"),
            ], className="export-group")
        ], className="export-section"),
        
        # Export Settings
        html.Details([
            html.Summary("⚙️ Export Settings"),
            html.Div([
                html.Div([
                    html.Label("Image Resolution"),
                    dcc.Dropdown(
                        id="export-resolution-dropdown",
                        options=[
                            {"label": "📱 Low (72 DPI)", "value": 72},
                            {"label": "🖥️ Medium (150 DPI)", "value": 150},
                            {"label": "🖨️ High (300 DPI)", "value": 300},
                            {"label": "📈 Ultra (600 DPI)", "value": 600}
                        ],
                        value=300,
                        className="sidebar-dropdown"
                    )
                ], className="settings-group"),
                
                html.Div([
                    html.Label("Image Width (px)"),
                    dcc.Input(
                        id="export-width-input",
                        type="number",
                        value=1200,
                        min=400,
                        max=4000,
                        step=100,
                        className="sidebar-input"
                    )
                ], className="settings-group"),
                
                html.Div([
                    html.Label("Image Height (px)"),
                    dcc.Input(
                        id="export-height-input",
                        type="number",
                        value=800,
                        min=300,
                        max=3000,
                        step=100,
                        className="sidebar-input"
                    )
                ], className="settings-group"),
                
                html.Div([
                    dcc.Checklist(
                        id="export-options-checkbox",
                        options=[
                            {"label": "Include Legend", "value": "include_legend"},
                            {"label": "Include Grid", "value": "include_grid"},
                            {"label": "Transparent Background", "value": "transparent_bg"},
                            {"label": "Include Metadata", "value": "include_metadata"}
                        ],
                        value=["include_legend", "include_grid", "include_metadata"],
                        className="sidebar-checkbox"
                    )
                ])
            ])
        ], open=False, className="advanced-section"),
        
        # Download component (hidden)
        dcc.Download(id="download-export")
        
    ], className="export-options-container")

def register_export_callbacks(app, data_manager):
    """Register callbacks for export functionality."""
    
    # PNG Export
    @app.callback(
        [Output("download-export", "data"),
         Output("export-png-btn", "children")],
        Input("export-png-btn", "n_clicks"),
        [State("export-width-input", "value"),
         State("export-height-input", "value"),
         State("export-resolution-dropdown", "value"),
         State("export-options-checkbox", "value"),
         State("data-plot", "figure")],
        prevent_initial_call=True
    )
    def export_png(n_clicks, width, height, dpi, options, figure):
        if not n_clicks or not figure:
            return None, [html.Span("🖼️ "), html.Span("Export as PNG")]
        
        try:
            # Convert plotly figure to PNG
            import plotly.io as pio
            
            # Configure export settings
            img_bytes = pio.to_image(
                figure, 
                format="png",
                width=width,
                height=height,
                scale=dpi/96  # Convert DPI to scale factor
            )
            
            # Prepare download
            return dict(
                content=base64.b64encode(img_bytes).decode(),
                filename="chromatogram_plot.png",
                base64=True
            ), [html.Span("✅ "), html.Span("PNG Exported!")]
            
        except Exception as e:
            print(f"PNG export error: {e}")
            return None, [html.Span("❌ "), html.Span("Export Failed")]
    
    # CSV Export (Raw Data)
    @app.callback(
        [Output("download-export", "data", allow_duplicate=True),
         Output("export-csv-btn", "children")],
        Input("export-csv-btn", "n_clicks"),
        State("file-selector", "value"),
        prevent_initial_call=True
    )
    def export_csv(n_clicks, selected_file):
        if not n_clicks or not selected_file:
            return None, [html.Span("📊 "), html.Span("Export Raw Data (CSV)")]
        
        try:
            # Get file data
            filename = selected_file.split('|')[0]
            file_data = data_manager.get_file_data(filename)
            
            if not file_data or not file_data.get('data'):
                return None, [html.Span("❌ "), html.Span("No Data")]
            
            # Convert to CSV
            import pandas as pd
            data = file_data['data']
            
            if isinstance(data, pd.DataFrame):
                csv_string = data.to_csv(index=False)
            else:
                # Handle other data formats
                df = pd.DataFrame(data)
                csv_string = df.to_csv(index=False)
            
            return dict(
                content=csv_string,
                filename=f"{filename}_data.csv"
            ), [html.Span("✅ "), html.Span("CSV Exported!")]
            
        except Exception as e:
            print(f"CSV export error: {e}")
            return None, [html.Span("❌ "), html.Span("Export Failed")]
    
    # Peak Data Export
    @app.callback(
        [Output("download-export", "data", allow_duplicate=True),
         Output("export-peaks-csv-btn", "children")],
        Input("export-peaks-csv-btn", "n_clicks"),
        State("file-selector", "value"),
        prevent_initial_call=True
    )
    def export_peaks_csv(n_clicks, selected_file):
        if not n_clicks:
            return None, [html.Span("📈 "), html.Span("Export Peak Data (CSV)")]
        
        try:
            # Get peak data from your peak storage
            # This would need to be adapted based on how you store peaks
            from utils.peak_detection import peak_data_store
            
            if not peak_data_store:
                return None, [html.Span("❌ "), html.Span("No Peaks")]
            
            # Convert peaks to DataFrame
            import pandas as pd
            peak_rows = []
            
            for file, peaks in peak_data_store.items():
                for peak in peaks:
                    peak_rows.append({
                        'File': file,
                        'Retention Time (min)': peak.get('retention_time', 0),
                        'Height': peak.get('height', 0),
                        'Area': peak.get('area', 0),
                        'Width (min)': peak.get('width', 0),
                        'Width Half Height (min)': peak.get('width_half_height', 0)
                    })
            
            if not peak_rows:
                return None, [html.Span("❌ "), html.Span("No Peaks")]
            
            df = pd.DataFrame(peak_rows)
            csv_string = df.to_csv(index=False)
            
            return dict(
                content=csv_string,
                filename="peak_analysis.csv"
            ), [html.Span("✅ "), html.Span("Peaks Exported!")]
            
        except Exception as e:
            print(f"Peak CSV export error: {e}")
            return None, [html.Span("❌ "), html.Span("Export Failed")]
    
    # Report Export
    @app.callback(
        [Output("download-export", "data", allow_duplicate=True),
         Output("export-report-btn", "children")],
        Input("export-report-btn", "n_clicks"),
        State("file-selector", "value"),
        prevent_initial_call=True
    )
    def export_report(n_clicks, selected_file):
        if not n_clicks:
            return None, [html.Span("📄 "), html.Span("Generate Summary Report")]
        
        try:
            # Generate a simple text report
            report_content = generate_analysis_report(data_manager, selected_file)
            
            return dict(
                content=report_content,
                filename="analysis_report.txt"
            ), [html.Span("✅ "), html.Span("Report Generated!")]
            
        except Exception as e:
            print(f"Report export error: {e}")
            return None, [html.Span("❌ "), html.Span("Export Failed")]

def generate_analysis_report(data_manager, selected_file):
    """Generate a text-based analysis report."""
    from datetime import datetime
    
    report_lines = [
        "CHROMATOGRAPHY ANALYSIS REPORT",
        "=" * 40,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "SAMPLE INFORMATION:",
        "-" * 20
    ]
    
    if selected_file:
        filename = selected_file.split('|')[0]
        file_data = data_manager.get_file_data(filename)
        
        if file_data:
            metadata = file_data.get('metadata', {})
            report_lines.extend([
                f"File: {filename}",
                f"Type: {file_data.get('type', 'Unknown')}",
                f"Wavelength: {metadata.get('wavelength', 'N/A')} nm",
                f"Injection Date: {metadata.get('Injection Date', 'N/A')}",
                f"Injection Time: {metadata.get('Injection Time', 'N/A')}",
                ""
            ])
    
    # Add peak data if available
    try:
        from utils.peak_detection import peak_data_store
        if peak_data_store:
            report_lines.extend([
                "PEAK ANALYSIS:",
                "-" * 15,
                ""
            ])
            
            for file, peaks in peak_data_store.items():
                if peaks:
                    report_lines.append(f"Sample: {file}")
                    report_lines.append(f"Number of peaks: {len(peaks)}")
                    
                    for i, peak in enumerate(peaks, 1):
                        report_lines.append(
                            f"  Peak {i}: RT={peak.get('retention_time', 0):.2f} min, "
                            f"Area={peak.get('area', 0):.2f}, Height={peak.get('height', 0):.2f}"
                        )
                    report_lines.append("")
    except:
        pass
    
    report_lines.extend([
        "",
        "=" * 40,
        "End of Report"
    ])
    
    return "\n".join(report_lines)