#callbacks/sidebar_callbacks.py


from dash import Input, Output, State, html, callback_context, dcc
import dash
from utils.sample_management import create_sample_management_layout, register_sample_management_callbacks
from utils.plot_settings import create_plot_settings_layout, register_plot_settings_callbacks
from utils.export_options import create_export_options_layout, register_export_callbacks
from utils.peak_integration import peak_manager


from utils.fonts_labels import create_fonts_labels_layout, register_fonts_labels_callbacks

from utils.fonts_labels import create_fonts_labels_layout, register_fonts_labels_callbacks
from callbacks.peak_detection_callbacks import register_peak_detection_callbacks



def register_sidebar_callbacks(app, data_manager):
    """Register all sidebar-related callbacks."""
    
    # Register modular callbacks
    register_sample_management_callbacks(app, data_manager)
    register_plot_settings_callbacks(app)
    register_fonts_labels_callbacks(app)
    register_export_callbacks(app, data_manager)
    


    @app.callback(
        Output("dynamic-sidebar", "style"),
        [Input("upload-status", "children"),
        Input("file-selector", "value")]
    )
    def show_hide_sidebar(upload_status, selected_file):
        files = data_manager.get_loaded_files()
        if files:
            return {"display": "block"}
        else:
            return {"display": "none"}

    # Peak Analysis Callbacks



    # COMPLETE FIXED CALLBACK BLOCK - Replace your existing callbacks with this:

    # Peak Analysis Callbacks
    @app.callback(
        Output("retention-time-input", "value", allow_duplicate=True),
        Input("add-peak-btn", "n_clicks"),
        [State("retention-time-input", "value"),
        State("peak-threshold-slider", "value"),
        State("file-selector", "value")],
        prevent_initial_call=True
    )
    def add_peak_handler(n_clicks, retention_time, threshold, selected_file):
        if not n_clicks or not selected_file:
            return retention_time
        
        try:
            filename = selected_file.split('|')[0]
            file_data = data_manager.get_file_data(filename)
            
            if file_data and file_data.get('data') is not None:
                # Convert DataFrame to expected format
                data = file_data['data']
                time_col = 'Time (min)'
                intensity_cols = [col for col in data.columns if col != time_col]
                if not intensity_cols:
                    return retention_time
                    
                intensity_col = intensity_cols[0]
                
                # ✅ USE peak_manager.detect_peak_at_time (instead of detect_peak_near_click)
                peak = peak_manager.detect_peak_at_time(
                    data, retention_time, filename, height_threshold=threshold
                )
                                
                if peak:
                    print(f"Peak added: {peak['Retention Time']:.2f} min, Area: {peak['Area']:.2f}")
                else:
                    print("No peak found at specified location")
        
        except Exception as e:
            print(f"Error adding peak: {e}")
        
        return retention_time

    @app.callback(
        [Output("detect-all-peaks-btn", "children", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True)],
        Input("detect-all-peaks-btn", "n_clicks"),
        [State("peak-threshold-slider", "value"),
        State("file-selector", "value"),
        State("toast-store", "data")],
        prevent_initial_call=True
    )
    def detect_all_peaks_handler(n_clicks, threshold, selected_file, current_toasts):
        if not n_clicks or not selected_file:
            return "🔍 Detect All Peaks", dash.no_update
        
        try:
            filename = selected_file.split('|')[0]
            file_data = data_manager.get_file_data(filename)
            
            if file_data and file_data.get('data') is not None:
                peaks = peak_manager.auto_detect_peaks(
                    file_data['data'], filename, height_threshold=threshold
                )
                
                if peaks:
                    # ✅ CRITICAL DEBUG - Check what's actually stored
                    print(f"[AUTO-DETECT DEBUG] Stored {len(peaks)} peaks under key: '{filename}'")
                    # Force immediate plot refresh
                    from dash import ctx
                    ctx.response.set_cookie('force_refresh', 'true')
                    print(f"[AUTO-DETECT DEBUG] peak_manager keys: {list(peak_manager.detected_peaks.keys())}")
                    print(f"[AUTO-DETECT DEBUG] peak_manager instance ID: {id(peak_manager)}")
                    
                    new_toasts = add_toast_to_store(
                        current_toasts, 
                        f"🎯 Found {len(peaks)} peaks in {filename}!", 
                        "success", 
                        4000
                    )
                    return f"✅ Found {len(peaks)} peaks!", new_toasts
                else:
                    new_toasts = add_toast_to_store(current_toasts, "⚠️ No peaks detected with current threshold", "warning")
                    return "😞 No peaks found", new_toasts
                    
        except Exception as e:
            new_toasts = add_toast_to_store(current_toasts, f"❌ Peak detection failed: {str(e)}", "error")
            return "❌ Detection failed", new_toasts

            


    # Peak threshold slider range update
    @app.callback(
        [Output("peak-threshold-slider", "max"),
         Output("peak-threshold-slider", "value", allow_duplicate=True)],
        Input("file-selector", "value"),
        prevent_initial_call=True
    )
    def update_peak_threshold_range(selected_file):
        if not selected_file:
            return 1000, 50
        
        try:
            filename = selected_file.split('|')[0]
            file_data = data_manager.get_file_data(filename)
            
            if file_data and file_data.get('data') is not None:
                data = file_data['data']
                
                # Get max intensity
                if hasattr(data, 'max'):
                    max_intensity = float(data.max().max())
                elif isinstance(data, dict) and 'y' in data:
                    max_intensity = max(data['y']) if data['y'] else 1000
                else:
                    max_intensity = 1000
                
                return max_intensity, max_intensity * 0.05  # 5% of max as default
                
        except Exception as e:
            print(f"Error updating threshold range: {e}")
        
        return 1000, 50

def create_peak_analysis_section(selected_file, data_manager):
    """Create the peak analysis section for chromatography data."""
    return html.Details([
        html.Summary("📈 Peak Analysis", className="sidebar-section-title"),
        html.Div([
            html.H4("Add Peak by Time"),
            html.P("📌 Hover over a peak to see its time", className="info-text"),
            
            html.Label("Peak Height Threshold"),
            dcc.Slider(
                id="peak-threshold-slider",
                min=0, max=1000, value=50, step=1,
                marks={0: '0', 250: '250', 500: '500', 750: '750', 1000: '1000'},
                className="sidebar-slider"
            ),
            
            html.Div([
                html.Div([
                    html.Label("Retention Time (min)"),
                    dcc.Input(
                        id="retention-time-input",
                        type="number", value=5.0, step=0.01,
                        className="sidebar-input"
                    )
                ], className="input-group"),
                html.Button("Add Peak", id="add-peak-btn", className="sidebar-btn-primary")
            ], className="peak-input-row"),
            
            html.Button("🔍 Detect All Peaks", id="detect-all-peaks-btn", className="sidebar-btn-full"),
            html.Button("🔍 Detect Same Peak in All Samples", id="detect-same-peak-btn", className="sidebar-btn-full"),
            
            html.Div([
                dcc.Checklist(
                    id="integrate-zero-checkbox",
                    options=[{"label": "Integrate to Zero (Baseline)", "value": "integrate_zero"}],
                    value=["integrate_zero"],
                    className="sidebar-checkbox"
                )
            ]),
            
            # Advanced Settings
            html.Details([
                html.Summary("⚙️ Advanced Peak Detection"),
                html.Div([
                    html.Label("Signal-to-noise ratio"),
                    dcc.Slider(id="snr-slider", min=1, max=10, value=3, step=0.5, className="sidebar-slider"),
                    
                    html.Label("Slope threshold (%)"),
                    dcc.Slider(id="slope-slider", min=0.5, max=20, value=2, step=0.5, className="sidebar-slider"),
                    
                    html.Label("Baseline iterations"),
                    dcc.Slider(id="baseline-slider", min=10, max=200, value=50, step=10, className="sidebar-slider"),
                    
                    html.Button("Reset to Default", id="reset-peak-settings-btn", className="sidebar-btn")
                ])
            ], open=False, className="advanced-section")
        ], className="sidebar-section-content")
    ], open=True, className="sidebar-section")