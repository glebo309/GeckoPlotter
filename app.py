import dash
from dash import dcc, html
from data_manager import DataManager
from layouts.main_layout import create_layout
from callbacks.upload_callbacks import register_upload_callbacks, register_clear_callbacks
from callbacks.viz_callbacks import register_viz_callbacks
from callbacks.sidebar_callbacks import register_sidebar_callbacks
from callbacks.plot_settings_callbacks import register_plot_settings_callbacks
from callbacks.baseline_integration_callbacks import register_baseline_integration_callbacks
from file_tree_manager import register_tree_callbacks
from utils.toast_system import register_toast_callbacks
from callbacks.interaction_callbacks import register_interaction_callbacks
from callbacks.hplc_callbacks import register_peak_grouping_callback


# Initialize Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Global data manager
data_manager = DataManager()

# Set layout
app.layout = create_layout()

# Register all callbacks
register_upload_callbacks(app, data_manager)
register_clear_callbacks(app, data_manager)
register_viz_callbacks(app, data_manager)
register_sidebar_callbacks(app, data_manager)
register_toast_callbacks(app)
register_tree_callbacks(app, data_manager)
register_interaction_callbacks(app, data_manager)
register_peak_grouping_callback(app, data_manager)
register_plot_settings_callbacks(app, data_manager)

# Register baseline integration callbacks
register_baseline_integration_callbacks(app, data_manager)

# Add enhanced CSS styling
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            /* Peak Detection Enhanced Styles */
            .peak-detection-controls {
                padding: 15px;
                max-height: 100%;
                overflow-y: auto;
            }
            
            .peak-section {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                border-left: 4px solid #007bff;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .section-title {
                margin: 0 0 15px 0;
                color: #2c3e50;
                font-size: 14px;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .form-group {
                margin-bottom: 12px;
            }
            
            .form-label {
                display: block;
                margin-bottom: 5px;
                font-size: 12px;
                font-weight: 500;
                color: #495057;
            }
            
            .form-input {
                width: 100%;
                padding: 8px 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 13px;
                transition: all 0.15s ease-in-out;
            }
            
            .form-input:focus {
                outline: none;
                border-color: #007bff;
                box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
            }
            
            .btn-primary {
                background: linear-gradient(135deg, #007bff, #0056b3);
                border: none;
                color: white;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 2px 4px rgba(0,123,255,0.3);
            }
            
            .btn-primary:hover {
                background: linear-gradient(135deg, #0056b3, #004085);
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(0,123,255,0.4);
            }
            
            .btn-secondary {
                background: linear-gradient(135deg, #6c757d, #545b62);
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            
            .btn-secondary:hover {
                background: linear-gradient(135deg, #545b62, #4e555b);
                transform: translateY(-1px);
            }
            
            .feedback-text {
                font-size: 11px;
                margin-top: 5px;
                padding: 8px;
                border-radius: 4px;
                min-height: 20px;
                background: #f8f9fa;
                border: 1px solid #e9ecef;
            }
            
            .slider {
                margin: 15px 0;
            }
            
            .advanced-section {
                margin-top: 15px;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                background: white;
                overflow: hidden;
            }
            
            .advanced-section summary {
                cursor: pointer;
                padding: 12px 15px;
                background: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
                margin: 0;
                font-weight: 500;
                transition: background-color 0.2s;
            }
            
            .advanced-section summary:hover {
                background: #e9ecef;
            }
            
            .advanced-section[open] summary {
                background: #007bff;
                color: white;
            }
            
            .advanced-section > div {
                padding: 15px;
            }
            
            .results-section {
                background: white;
                border: 2px solid #007bff;
                border-radius: 8px;
                padding: 15px;
                max-height: 500px;
                overflow-y: auto;
                box-shadow: 0 4px 8px rgba(0,123,255,0.1);
            }
            
            .no-data-message {
                text-align: center;
                color: #6c757d;
                font-style: italic;
                padding: 30px;
                background: #f8f9fa;
                border-radius: 6px;
                border: 2px dashed #dee2e6;
            }
            
            .error-message {
                color: #dc3545;
                background: #f8d7da;
                border: 1px solid #f5c6cb;
                border-radius: 4px;
                padding: 10px;
                font-size: 12px;
            }
            
            /* Enhanced Tab Styles */
            .tab-header {
                display: flex;
                border-bottom: 3px solid #007bff;
                margin-bottom: 0;
                background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                border-radius: 8px 8px 0 0;
            }
            
            .tab-button {
                background: none;
                border: none;
                padding: 15px 20px;
                cursor: pointer;
                border-bottom: 3px solid transparent;
                font-weight: 500;
                color: #6c757d;
                transition: all 0.3s ease;
                font-size: 14px;
                position: relative;
                flex: 1;
                text-align: center;
            }
            
            .tab-button:hover {
                color: #007bff;
                background: rgba(0,123,255,0.1);
                transform: translateY(-2px);
            }
            
            .tab-button.active {
                color: #007bff;
                border-bottom-color: #007bff;
                background: white;
                font-weight: 600;
                box-shadow: 0 -2px 8px rgba(0,123,255,0.2);
            }
            
            .tab-content {
                background: white;
                min-height: 400px;
                border-radius: 0 0 8px 8px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            .tab-panel {
                display: none;
                padding: 20px;
                height: 100%;
                overflow-y: auto;
                animation: fadeIn 0.3s ease-in-out;
            }
            
            .tab-panel.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            /* Peak visualization enhancements */
            .peak-marker {
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.7; }
                100% { opacity: 1; }
            }
            
            /* Improved data table styling */
            .dash-table-container {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            /* Toast enhancements */
            .toast-container {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
                max-width: 400px;
            }
            
            .toast {
                margin-bottom: 10px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                animation: slideInRight 0.3s ease-out;
            }
            
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            
            /* Hide dummy outputs */
            #dummy-output-for-tab-styling,
            #dummy-output-for-tab-setup {
                display: none !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .tab-button {
                    padding: 12px 15px;
                    font-size: 12px;
                }
                
                .peak-section {
                    padding: 12px;
                    margin-bottom: 12px;
                }
                
                .section-title {
                    font-size: 13px;
                }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Run app
if __name__ == "__main__":
    app.run(debug=True, port=8051)