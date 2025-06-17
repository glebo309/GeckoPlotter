# callbacks/peak_detection_callbacks.py
from dash import Input, Output, State, html, dash_table, dcc, callback_context
import pandas as pd
import plotly.graph_objects as go
from utils.toast_system import add_toast_to_store
from utils.peak_integration import peak_manager
import dash


def register_peak_detection_callbacks(app, data_manager):
    """Register callbacks for peak detection functionality."""
    
    # Manual peak detection at specific retention time
    @app.callback(
        [Output('peak-detection-feedback', 'children'),
         Output('toast-store', 'data', allow_duplicate=True),
         Output('retention-time-input', 'value', allow_duplicate=True)],
        Input('detect-peak-btn', 'n_clicks'),
        [State('retention-time-input', 'value'),
         State('selected-layer', 'data'),
         State('peak-height-threshold-input', 'value'),
         State('toast-store', 'data')],
        prevent_initial_call=True
    )
    def detect_peak_manual(n_clicks, retention_time, selected_layer, height_threshold, current_toasts):
        """Detect peak at specified retention time"""
        
        if not n_clicks or not retention_time or not selected_layer:
            return "", current_toasts, retention_time
        
        try:
            # Get the filename from selection
            filename = selected_layer.split('|')[0] if '|' in selected_layer else selected_layer
            file_data = data_manager.get_file_data(filename)
            
            if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
                new_toasts = add_toast_to_store(current_toasts, "⚠️ Please select an HPLC chromatogram file", "warning")
                return "❌ No HPLC file selected", new_toasts, retention_time
            
            # Get chromatogram data
            chromatogram_data = file_data.get('data')
            if chromatogram_data is None or chromatogram_data.empty:
                new_toasts = add_toast_to_store(current_toasts, "❌ No chromatogram data found", "error")
                return "❌ No data", new_toasts, retention_time
            
            # Detect peak
            peak_info = peak_manager.detect_peak_at_time(
                chromatogram_data, 
                retention_time, 
                filename,
                height_threshold
            )
            
            if peak_info:
                # Success!
                peak_rt = peak_info['Retention Time']
                peak_area = peak_info['Area']
                peak_height = peak_info['Height']
                
                success_msg = f"🎯 Peak detected at {peak_rt:.3f} min (Area: {peak_area:.2f}, Height: {peak_height:.1f})"
                new_toasts = add_toast_to_store(current_toasts, success_msg, "success", 5000)
                
                return f"✅ Peak {peak_info['No.']} detected!", new_toasts, ""
            else:
                warning_msg = f"🔍 No significant peak found near {retention_time:.3f} min"
                new_toasts = add_toast_to_store(current_toasts, warning_msg, "warning", 4000)
                return "❌ No peak found", new_toasts, retention_time
                
        except Exception as e:
            error_msg = f"❌ Peak detection failed: {str(e)}"
            new_toasts = add_toast_to_store(current_toasts, error_msg, "error", 5000)
            return "❌ Error", new_toasts, retention_time
    
    # Auto-detect all peaks
    @app.callback(
        [Output('auto-detect-feedback', 'children'),
         Output('toast-store', 'data', allow_duplicate=True)],
        Input('auto-detect-peaks-btn', 'n_clicks'),
        [State('selected-layer', 'data'),
         State('peak-height-threshold-input', 'value'),
         State('min-peak-distance-input', 'value'),
         State('toast-store', 'data')],
        prevent_initial_call=True
    )
    def auto_detect_peaks(n_clicks, selected_layer, height_threshold, min_distance, current_toasts):
        """Auto-detect all peaks in chromatogram"""
        
        if not n_clicks or not selected_layer:
            return "", current_toasts
        
        try:
            # Get the filename from selection
            filename = selected_layer.split('|')[0] if '|' in selected_layer else selected_layer
            file_data = data_manager.get_file_data(filename)
            
            if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
                new_toasts = add_toast_to_store(current_toasts, "⚠️ Please select an HPLC chromatogram file", "warning")
                return "❌ No HPLC file selected", new_toasts
            
            # Get chromatogram data
            chromatogram_data = file_data.get('data')
            if chromatogram_data is None or chromatogram_data.empty:
                new_toasts = add_toast_to_store(current_toasts, "❌ No chromatogram data found", "error")
                return "❌ No data", new_toasts
            
            # Auto-detect peaks
            detected_peaks = peak_manager.auto_detect_peaks(
                chromatogram_data, 
                filename,
                height_threshold,
                min_distance or 10
            )
            
            if detected_peaks:
                success_msg = f"🔍 Auto-detected {len(detected_peaks)} peaks in {filename}"
                new_toasts = add_toast_to_store(current_toasts, success_msg, "success", 5000)
                return f"✅ Found {len(detected_peaks)} peaks!", new_toasts
            else:
                warning_msg = "🔍 No peaks found with current settings"
                new_toasts = add_toast_to_store(current_toasts, warning_msg, "warning", 4000)
                return "❌ No peaks found", new_toasts
                
        except Exception as e:
            error_msg = f"❌ Auto-detection failed: {str(e)}"
            new_toasts = add_toast_to_store(current_toasts, error_msg, "error", 5000)
            return "❌ Error", new_toasts
    
    # Clear detected peaks
    @app.callback(
        [Output('clear-peaks-feedback', 'children'),
         Output('toast-store', 'data', allow_duplicate=True)],
        Input('clear-detected-peaks-btn', 'n_clicks'),
        [State('selected-layer', 'data'),
         State('toast-store', 'data')],
        prevent_initial_call=True
    )
    def clear_detected_peaks(n_clicks, selected_layer, current_toasts):
        """Clear detected peaks for current file"""
        
        if not n_clicks:
            return "", current_toasts
        
        try:
            if selected_layer:
                filename = selected_layer.split('|')[0] if '|' in selected_layer else selected_layer
                peak_manager.clear_detected_peaks(filename)
                
                success_msg = f"🗑️ Cleared detected peaks for {filename}"
                new_toasts = add_toast_to_store(current_toasts, success_msg, "info", 3000)
                return "✅ Peaks cleared", new_toasts
            else:
                # Clear all detected peaks
                peak_manager.clear_detected_peaks()
                
                success_msg = "🗑️ Cleared all detected peaks"
                new_toasts = add_toast_to_store(current_toasts, success_msg, "info", 3000)
                return "✅ All peaks cleared", new_toasts
                
        except Exception as e:
            error_msg = f"❌ Clear failed: {str(e)}"
            new_toasts = add_toast_to_store(current_toasts, error_msg, "error", 5000)
            return "❌ Error", new_toasts
    
    # Update peak detection settings
    @app.callback(
        Output('peak-settings-feedback', 'children'),
        [Input('slope-threshold-slider', 'value'),
         Input('extension-factor-slider', 'value'),
         Input('search-radius-input', 'value')],
        prevent_initial_call=True
    )
    def update_peak_settings(slope_threshold, extension_factor, search_radius):
        """Update peak detection algorithm settings"""
        
        try:
            # Update settings in peak manager
            settings_updated = {}
            
            if slope_threshold is not None:
                settings_updated['slope_threshold'] = slope_threshold / 100.0  # Convert percentage
            
            if extension_factor is not None:
                settings_updated['extension_factor'] = extension_factor
            
            if search_radius is not None:
                settings_updated['search_radius'] = search_radius
            
            if settings_updated:
                peak_manager.update_settings(**settings_updated)
                return f"⚙️ Settings updated: {', '.join(settings_updated.keys())}"
            
            return ""
            
        except Exception as e:
            return f"❌ Settings error: {str(e)}"
    
    # Update peak height threshold based on current file
    @app.callback(
        [Output('peak-height-threshold-input', 'value'),
         Output('peak-height-threshold-input', 'placeholder')],
        Input('selected-layer', 'data'),
        prevent_initial_call=True
    )
    def update_height_threshold(selected_layer):
        """Auto-update height threshold based on current chromatogram"""
        
        if not selected_layer:
            return None, "Auto threshold"
        
        try:
            filename = selected_layer.split('|')[0] if '|' in selected_layer else selected_layer
            file_data = data_manager.get_file_data(filename)
            
            if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
                return None, "Select HPLC file"
            
            chromatogram_data = file_data.get('data')
            if chromatogram_data is None or chromatogram_data.empty:
                return None, "No data"
            
            # Calculate suggested threshold (5% of max intensity)
            intensity_cols = [col for col in chromatogram_data.columns if col != 'Time (min)']
            if intensity_cols:
                max_intensity = chromatogram_data[intensity_cols[0]].max()
                suggested_threshold = max_intensity * 0.05
                
                return None, f"Auto: {suggested_threshold:.1f} mAU (5% of max)"
            
            return None, "Auto threshold"
            
        except Exception as e:
            print(f"[DEBUG] Error updating threshold: {e}")
            return None, "Auto threshold"

def create_peak_detection_controls():
    """Create the peak detection UI controls for the sidebar"""
    
    return html.Div([
        # Manual Peak Detection Section
        html.Div([
            html.H5("🎯 Manual Peak Detection", className="section-title"),
            
            html.Div([
                html.Label("Retention Time (min)", className="form-label"),
                dcc.Input(
                    id="retention-time-input",
                    type="number",
                    placeholder="Enter RT (e.g., 5.25)",
                    step=0.001,
                    className="form-input",
                    style={'width': '100%'}
                )
            ], className="form-group"),
            
            html.Div([
                html.Label("Height Threshold (mAU)", className="form-label"),
                dcc.Input(
                    id="peak-height-threshold-input",
                    type="number",
                    placeholder="Auto threshold",
                    step=0.1,
                    className="form-input",
                    style={'width': '100%'}
                )
            ], className="form-group"),
            
            html.Button(
                "🔍 Detect Peak",
                id="detect-peak-btn",
                className="btn-primary",
                style={'width': '100%', 'marginBottom': '10px'}
            ),
            
            html.Div(id="peak-detection-feedback", className="feedback-text")
        ], className="peak-section"),
        
        # Auto Detection Section
        html.Div([
            html.H5("🤖 Auto Detection", className="section-title"),
            
            html.Div([
                html.Label("Min Peak Distance (points)", className="form-label"),
                dcc.Input(
                    id="min-peak-distance-input",
                    type="number",
                    value=10,
                    min=1,
                    max=100,
                    step=1,
                    className="form-input",
                    style={'width': '100%'}
                )
            ], className="form-group"),
            
            html.Button(
                "🔍 Auto-Detect All Peaks",
                id="auto-detect-peaks-btn",
                className="btn-primary",
                style={'width': '100%', 'marginBottom': '10px'}
            ),
            
            html.Div(id="auto-detect-feedback", className="feedback-text")
        ], className="peak-section"),
        
        # Peak Management Section
        html.Div([
            html.H5("🔧 Peak Management", className="section-title"),
            
            html.Button(
                "🗑️ Clear Detected Peaks",
                id="clear-detected-peaks-btn",
                className="btn-secondary",
                style={'width': '100%', 'marginBottom': '10px'}
            ),
            
            html.Div(id="clear-peaks-feedback", className="feedback-text")
        ], className="peak-section"),
        
        # Advanced Settings
        html.Details([
            html.Summary("⚙️ Advanced Settings", className="section-title"),
            
            html.Div([
                html.Label("Slope Threshold (%)", className="form-label"),
                dcc.Slider(
                    id="slope-threshold-slider",
                    min=0.5,
                    max=10.0,
                    step=0.1,
                    value=2.0,
                    marks={0.5: '0.5%', 2: '2%', 5: '5%', 10: '10%'},
                    className="slider"
                )
            ], className="form-group"),
            
            html.Div([
                html.Label("Extension Factor", className="form-label"),
                dcc.Slider(
                    id="extension-factor-slider",
                    min=1.0,
                    max=2.0,
                    step=0.1,
                    value=1.2,
                    marks={1.0: '1.0', 1.2: '1.2', 1.5: '1.5', 2.0: '2.0'},
                    className="slider"
                )
            ], className="form-group"),
            
            html.Div([
                html.Label("Search Radius (min)", className="form-label"),
                dcc.Input(
                    id="search-radius-input",
                    type="number",
                    value=0.5,
                    min=0.1,
                    max=2.0,
                    step=0.1,
                    className="form-input"
                )
            ], className="form-group"),
            
            html.Div(id="peak-settings-feedback", className="feedback-text")
        ], open=False, className="advanced-section"),
        

    ], className="peak-detection-controls")