# callbacks/upload_callbacks.py

import base64
import os
import tempfile
from dash import Input, Output, State, html, dash_table, callback_context, dcc
import re
from dash import ALL
from dash.exceptions import PreventUpdate
import json
from utils.toast_system import add_toast_to_store
from dash import callback_context
import pandas as pd



# -----------------------------------------------------------------------------
# COMBINED UPLOAD + CLEAR CALLBACKS
# -----------------------------------------------------------------------------

def create_file_selector_options(data_manager):
    """Builds the options for the file selector dropdown."""
    options = []
    loaded_files = data_manager.get_loaded_files()
    for fname in loaded_files:
        fdata = data_manager.get_file_data(fname)
        if not fdata:
            continue
        if fdata["type"] == "lcms_bundle":
            bundle_data = fdata.get("bundle_data", {})
            options.append({
                "label": f"📦 {fname.replace('_LCMS_BUNDLE', '')} (LC-MS Bundle)",
                "value": fname
            })
            # Add sub-options for each component
            if bundle_data.get('ms_positive'):
                options.append({"label": f"  └─ 🔬 MS+ TIC", "value": f"{fname}|ms_positive"})
            if bundle_data.get('ms_negative'):
                options.append({"label": f"  └─ 🔬 MS- TIC", "value": f"{fname}|ms_negative"})
            if bundle_data.get('vwd_a'):
                wl = bundle_data['vwd_a']['metadata'].get('wavelength', '?')
                options.append({"label": f"  └─ 📊 UV Channel A ({wl} nm)", "value": f"{fname}|vwd_a"})
            if bundle_data.get('vwd_b'):
                wl = bundle_data['vwd_b']['metadata'].get('wavelength', '?')
                options.append({"label": f"  └─ 📊 UV Channel B ({wl} nm)", "value": f"{fname}|vwd_b"})
        else:
            options.append({
                "label": f"📄 {fname}",
                "value": fname
            })
    return options

def register_upload_callbacks(app, data_manager):
    """File-upload, parsing and sidebar rendering."""

    # Add CSS for peak analysis tabs
    app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                .peak-tab-nav {
                    display: flex;
                    border-bottom: 2px solid #dee2e6;
                    margin-bottom: 15px;
                }
                .peak-tab-btn {
                    background: none;
                    border: none;
                    padding: 10px 20px;
                    cursor: pointer;
                    border-bottom: 2px solid transparent;
                    font-weight: 500;
                    color: #6c757d;
                    transition: all 0.2s;
                }
                .peak-tab-btn:hover {
                    color: #495057;
                    background-color: #f8f9fa;
                }
                .peak-tab-btn.active {
                    color: #007bff;
                    border-bottom-color: #007bff;
                    background-color: #f8f9fa;
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


    # ── Combined callback for upload and clear operations ─────────────────────
    @app.callback(
        [Output("upload-status", "children"),
        Output("data-overview", "children"), 
        Output("viz-card", "style"),
        Output("dashboard-container", "style"),  # Add this to show/hide dashboard
        # REMOVED: Output("details-overlay", "style"),  # This is now handled by toggle callback
        Output("file-list", "children"),
        Output("upload-card", "style"),
        Output("file-selector", "options", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True)],

        [Input("upload-data", "contents"),
        Input("upload-data-zone", "contents"),
        Input("clear-data-btn", "n_clicks")],

        [State("upload-data", "filename"),
        State("upload-data-zone", "filename"),
        State("toast-store", "data")],
        prevent_initial_call=True
    )
    def handle_upload_and_clear(contents_list, zone_contents_list, clear_clicks, 
                           filenames_list, zone_filenames_list, current_toasts):
        """Handle both file uploads and data clearing."""
        
        # Determine what triggered this callback
        ctx = callback_context
        if not ctx.triggered:
            return ([], "No files uploaded yet.", {"display": "none"}, {"display": "none"},
                    html.Div("No files loaded", className="no-files-text"), 
                    {"display": "block"}, [], current_toasts or [])
                    
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        print(f"[DEBUG] 🎯 Callback triggered by: {trigger_id}")
        
        # Merge uploads from both sources
        all_contents = []
        all_filenames = []

        if contents_list:
            if isinstance(contents_list, str):
                all_contents.append(contents_list)
                all_filenames.append(filenames_list)
            else:
                all_contents.extend(contents_list)
                all_filenames.extend(filenames_list)

        if zone_contents_list:
            if isinstance(zone_contents_list, str):
                all_contents.append(zone_contents_list)
                all_filenames.append(zone_filenames_list)
            else:
                all_contents.extend(zone_contents_list)
                all_filenames.extend(zone_filenames_list)

        # Use merged lists for processing
        contents_list = all_contents
        filenames_list = all_filenames

        # Handle clear button click
        if trigger_id == "clear-data-btn" and clear_clicks:
            data_manager.clear_data()
            
            # Clean up any remaining temp files
            temp_dir = tempfile.gettempdir()
            for filename in os.listdir(temp_dir):
                if filename.startswith("temp_") and filename.endswith(".txt"):
                    try:
                        os.remove(os.path.join(temp_dir, filename))
                    except:
                        pass  # Ignore if file is already gone or locked
            
            return (
                [],  # No status messages - using toasts
                "No files uploaded yet.",
                {"display": "none"},  # viz-card
                {"display": "none"},  # dashboard-container
                # REMOVED: {"display": "none"},  # details-overlay style
                html.Div("No files loaded", className="no-files-text"),
                {"display": "block"},  # Show upload card
                {"display": "none"},   # Hide file selector
                add_toast_to_store(current_toasts or [], "🗑️ All data cleared!", "success", 10000)
            )

        # Handle file upload
        if trigger_id in ["upload-data", "upload-data-zone"] and contents_list:

            # Prevent duplicate processing
            if hasattr(handle_upload_and_clear, '_last_processed'):
                current_hash = hash(str(contents_list) + str(filenames_list))
                if handle_upload_and_clear._last_processed == current_hash:
                    print(f"[DEBUG] ⚠️ Skipping duplicate upload processing")
                    # Return current state without changes
                    
                    overview = "Select a file from the dropdown to view details."
                    file_list = create_file_list(data_manager)
                    
                    options = []
                    loaded_files = data_manager.get_loaded_files()
                    for fname in loaded_files:
                        fdata = data_manager.get_file_data(fname)
                        if not fdata:
                            continue
                        if fdata["type"] == "lcms_bundle":
                            bundle_data = fdata.get("bundle_data", {})
                            options.append({
                                "label": f"📦 {fname.replace('_LCMS_BUNDLE', '')} (LC-MS Bundle)",
                                "value": fname
                            })
                            # Add sub-options for each component
                            if bundle_data.get('ms_positive'):
                                options.append({"label": f"  └─ 🔬 MS+ TIC", "value": f"{fname}|ms_positive"})
                            if bundle_data.get('ms_negative'):
                                options.append({"label": f"  └─ 🔬 MS- TIC", "value": f"{fname}|ms_negative"})
                            if bundle_data.get('vwd_a'):
                                wl = bundle_data['vwd_a']['metadata'].get('wavelength', '?')
                                options.append({"label": f"  └─ 📊 UV Channel A ({wl} nm)", "value": f"{fname}|vwd_a"})
                            if bundle_data.get('vwd_b'):
                                wl = bundle_data['vwd_b']['metadata'].get('wavelength', '?')
                                options.append({"label": f"  └─ 📊 UV Channel B ({wl} nm)", "value": f"{fname}|vwd_b"})
                    
                    viz_style = {"display": "block"} if options else {"display": "none"}
                    dashboard_style = {"display": "block"} if options else {"display": "none"}
                    
                    return ([], overview, viz_style, dashboard_style, file_list,
                            {"display": "none"}, {"display": "block"}, current_toasts or [])

            handle_upload_and_clear._last_processed = hash(str(contents_list) + str(filenames_list))
            
            # First, clear any existing data that might conflict
            print(f"[DEBUG] Current loaded files before upload: {list(data_manager.loaded_data.keys())}")
            
            # Normalise single-file drag-and-drop into lists
            if isinstance(contents_list, str):
                contents_list = [contents_list]
                filenames_list = [filenames_list]

            # Initialize updated toasts with current ones
            if current_toasts is None:
                current_toasts = []
            updated_toasts = current_toasts[:]

            # --- Build an in-memory buffer ------------------------------------------------
            buffer: dict[str, bytes | str] = {}
            for content, filename in zip(contents_list, filenames_list):
                try:
                    _header, b64 = content.split(",", 1)
                    raw = base64.b64decode(b64)
                    
                    # Handle different file types appropriately
                    if filename.lower().endswith((".xls", ".cdf")):
                        # Keep binary files as bytes
                        buffer[filename] = raw
                        print(f"[DEBUG] Added to buffer: {filename} (binary)")
                    else:
                        # Decode text files to UTF-8
                        buffer[filename] = raw.decode('utf-8')
                        print(f"[DEBUG] Added to buffer: {filename} (text)")
                        
                except UnicodeDecodeError as err:
                    # If UTF-8 decoding fails, treat as binary
                    buffer[filename] = raw
                    print(f"[DEBUG] Added to buffer: {filename} (binary - UTF-8 decode failed)")
                except Exception as err:
                    updated_toasts = add_toast_to_store(updated_toasts, f"❌ Error decoding {filename}: {err}", "error", 10000)

            print(f"[DEBUG] Total files in buffer: {list(buffer.keys())}")

            # Process other files individually
            for fname in buffer.keys():
                try:
                    print(f"[DEBUG] Processing individual file: {fname}")
                    ok, msg = data_manager.load_file(fname, buffer[fname], extra_files=buffer)
                    toast_type = "success" if ok else "error"
                    updated_toasts = add_toast_to_store(updated_toasts, msg, toast_type, 10000)
                except Exception as err:
                    updated_toasts = add_toast_to_store(updated_toasts, f"❌ Error processing {fname}: {err}", "error", 10000)

            # --- Build <select> options for the Viz card --------------------------
            overview = "Select a file from the dropdown to view details."
            viz_style = {"display": "block"}
            dashboard_style = {"display": "block"}  # Show dashboard when files loaded
            file_list = create_file_list(data_manager)

            loaded_files = data_manager.get_loaded_files()
            if loaded_files:
                overview = create_single_file_overview(data_manager, loaded_files[-1])
            else:
                overview = "No files loaded."

            options = create_file_selector_options(data_manager)

            return (
                [],  # Empty status - now using toasts only
                overview,
                viz_style,
                dashboard_style,  # Show dashboard
                # REMOVED: details_style,  # details-overlay style now handled by toggle callback
                file_list,
                {"display": "none"},   # Hide upload card
                options,  # Update file selector options
                updated_toasts
            )




        # Default return (shouldn't reach here normally)
        return ([], "No files uploaded yet.", {"display": "none"}, {"display": "none"},
                html.Div("No files loaded", className="no-files-text"), 
                {"display": "block"}, [], current_toasts or [])

    @app.callback(
        [Output("details-overlay", "style"),
         Output("dashboard-container", "className")],
        [Input("close-details-btn", "n_clicks")],
        [State("details-overlay", "style"),
         State("dashboard-container", "className")]
    )
    def toggle_details_panel(close_clicks, current_style, current_class):
        ctx = callback_context
        if not ctx.triggered:
            return {"display": "none"}, "dashboard-split details-hidden"
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if button_id == "close-details-btn":
            return {"display": "none"}, "dashboard-split details-hidden"
        return {"display": "none"}, "dashboard-split details-hidden"

    @app.callback(
        [Output("pill-uvvis_csv", "style", allow_duplicate=True),
         Output("pill-chromatogram", "style", allow_duplicate=True), 
         Output("pill-lcms_bundle", "style", allow_duplicate=True),
         Output("pill-spectra", "style", allow_duplicate=True)],
        Input("file-selector", "value"),
        prevent_initial_call=True
    )
    def update_nav_pills(selected_file):
        default_visible = {"display": "block"}
        if not selected_file:
            return default_visible, default_visible, default_visible, default_visible
        filename = selected_file.split('|')[0]
        file_data = data_manager.get_file_data(filename)
        # Always show all pills
        return default_visible, default_visible, default_visible, default_visible

    @app.callback(
        [Output("pill-uvvis_csv", "className", allow_duplicate=True),
        Output("pill-chromatogram", "className", allow_duplicate=True), 
        Output("pill-lcms_bundle", "className", allow_duplicate=True),
        Output("pill-spectra", "className", allow_duplicate=True)],
        Input("file-selector", "value"),
        prevent_initial_call=True
    )

    def update_active_pill(selected_file):
        base_class = "nav-pill"
        active_class = "nav-pill active"
        
        if not selected_file:
            return base_class, base_class, base_class, base_class
        
        filename = selected_file.split('|')[0]
        file_data = data_manager.get_file_data(filename)
        
        if not file_data:
            return base_class, base_class, base_class, base_class
        
        file_type = file_data.get('type', '')
        
        # Set active class for matching pill
        uvvis_class = active_class if 'uvvis' in file_type else base_class
        chrom_class = active_class if 'chromatogram' in file_type or 'chromeleon' in file_type else base_class
        lcms_class = active_class if 'lcms' in file_type else base_class
        spectral_class = active_class if 'spectra' in file_type else base_class
        
        return uvvis_class, chrom_class, lcms_class, spectral_class

    # Add these callbacks to your main app
    @app.callback(
        Output('measurement-info-display', 'children'),
        [Input('file-selector', 'value')]
    )

    def update_sample_tab(selected_file):
        if not selected_file:
            return "No file selected"
        
        # Get actual file data instead of hardcoded values
        filename = selected_file.split('|')[0] if '|' in selected_file else selected_file
        file_data = data_manager.get_file_data(filename)
        
        if not file_data:
            return "File data not found"
        
        meta = file_data.get("metadata", {})
        
        # Extract real metadata or use defaults
        date = meta.get('Date', 'Unknown').split(',')[0] if meta.get('Date') else 'Unknown'
        time = meta.get('Time', 'Unknown').split(',')[0] if meta.get('Time') else 'Unknown'
        reader = meta.get('Reader Type', 'Unknown')
        plate = meta.get('Plate Type', 'Unknown')
        read_type = meta.get('Read', 'Unknown')
        
        measurement_info = html.Div([
            html.Div([html.B("Date: "), date]),
            html.Div([html.B("Time: "), time]),
            html.Div([html.B("Reader: "), reader]),
            html.Div([html.B("Plate: "), plate]),
            html.Div([html.B("Type: "), read_type]),
        ])
        
        return measurement_info


    @app.callback(
        [Output({'type': 'peak-content', 'index': ALL}, 'style'),
        Output({'type': 'peak-tab', 'index': ALL}, 'className')],
        [Input({'type': 'peak-tab', 'index': ALL}, 'n_clicks')],
        [State({'type': 'peak-tab', 'index': ALL}, 'id')],
        prevent_initial_call=True
    )
    def switch_peak_tabs(n_clicks, tab_ids):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks):
            raise PreventUpdate
        
        # Find which tab was clicked
        clicked_tab = ctx.triggered[0]['prop_id'].replace('.n_clicks', '')
        clicked_tab_id = eval(clicked_tab)['index']
        
        # Extract base name (remove tab suffix)
        base_name = '_'.join(clicked_tab_id.split('_')[:-1])
        
        # Prepare styles and classes
        content_styles = []
        tab_classes = []
        
        for tab_id in tab_ids:
            tab_index = tab_id['index']
            
            # Only affect tabs from the same sample
            if tab_index.startswith(base_name):
                # Show content if this is the clicked tab
                if tab_index == clicked_tab_id:
                    content_styles.append({'display': 'block'})
                    tab_classes.append('peak-tab-btn active')
                else:
                    content_styles.append({'display': 'none'})
                    tab_classes.append('peak-tab-btn')
            else:
                # Keep other samples' tabs unchanged  
                content_styles.append({'display': 'none'})
                tab_classes.append('peak-tab-btn')
        
        return content_styles, tab_classes



    def create_across_samples_content(data_manager, current_filename, stored_group_selection=0):
        """Create content for across samples comparison."""
        
        # Get all HPLC files
        hplc_files = []
        for filename in data_manager.get_loaded_files():
            file_data = data_manager.get_file_data(filename)
            if file_data and file_data.get('type') in ['chromatogram', 'chromeleon_bundle']:
                hplc_files.append({
                    'filename': filename,
                    'data': file_data
                })
        
        if len(hplc_files) < 2:
            return html.Div([
                html.H6("📊 Cross-Sample Peak Comparison"),
                html.P("Load at least 2 HPLC samples to compare peaks across samples."),
                html.P(f"Currently loaded: {len(hplc_files)} HPLC file(s)")
            ])
        
        # Extract all peaks from all samples
        all_peaks = []
        
        for file_info in hplc_files:
            filename = file_info['filename']
            file_data = file_info['data']
            integration_table = file_data.get('integration_table')
            peak_table = file_data.get('peak_table')
            
            if integration_table is not None and len(integration_table) > 0:
                sample_name = filename.replace('_UV_VIS_1.txt', '').replace('temp_', '')
                
                # Filter out total rows and n.a. rows
                peaks_only = integration_table[
                    (~integration_table.iloc[:, 0].astype(str).str.contains('Total', case=False, na=False)) &
                    (~integration_table.iloc[:, 0].astype(str).str.contains('n.a.', case=False, na=False)) &
                    (integration_table.iloc[:, 0].notna())
                ]
                
                # Get corresponding peak analysis data
                peak_analysis = {}
                if peak_table is not None:
                    for _, peak_row in peak_table.iterrows():
                        peak_no = peak_row.get('No.')
                        if str(peak_no).lower() != 'n.a.' and pd.notna(peak_no):
                            peak_analysis[peak_no] = peak_row
                
                for idx, peak_row in peaks_only.iterrows():
                    peak_no = peak_row.get('No.')
                    if str(peak_no).lower() == 'n.a.' or pd.isna(peak_no):
                        continue
                        
                    corresponding_peak = peak_analysis.get(peak_no, {})
                    
                    # More robust RT extraction
                    rt_value = peak_row.get('Retention Time', 0)
                    if pd.isna(rt_value) or str(rt_value).lower() == 'n.a.':
                        continue
                        
                    try:
                        rt = float(str(rt_value).replace(',', '.'))
                        if rt <= 0:
                            continue
                    except:
                        continue
                    
                    peak_data = {
                        'sample': sample_name,
                        'filename': filename,
                        'is_current': filename == current_filename,
                        'peak_no': peak_no,
                        'rt': rt,
                        'area': float(str(peak_row.get('Area', 0)).replace(',', '.')),
                        'height': float(str(peak_row.get('Height', 0)).replace(',', '.')),
                        'rel_area': float(str(peak_row.get('Relative Area', 0)).replace(',', '.')),
                        'width': float(str(corresponding_peak.get('Width (50%)', 0)).replace(',', '.')),
                        'resolution': str(corresponding_peak.get('Resolution (EP)', 'n.a.')),
                        'asymmetry': float(str(corresponding_peak.get('Asymmetry (EP)', 0)).replace(',', '.')) if corresponding_peak.get('Asymmetry (EP)', 'n.a.') != 'n.a.' else 0,
                        'plates': int(float(str(corresponding_peak.get('Plates (EP)', 0)).replace(',', '.'))) if str(corresponding_peak.get('Plates (EP)', 0)).replace(',', '.').replace('.', '').isdigit() else 0
                    }
                    all_peaks.append(peak_data)
                    print(f"[DEBUG] Added peak: {sample_name} - RT: {rt:.3f}")
        
        # Group peaks by retention time (default tolerance 0.1 min)
        def group_peaks_by_rt(peaks, tolerance=0.1):
            """Group peaks by retention time within tolerance."""
            peaks_sorted = sorted(peaks, key=lambda x: x['rt'])
            groups = []
            
            for peak in peaks_sorted:
                # Find if this peak belongs to an existing group
                assigned = False
                for group in groups:
                    group_rt_avg = sum(p['rt'] for p in group) / len(group)
                    if abs(peak['rt'] - group_rt_avg) <= tolerance:
                        group.append(peak)
                        assigned = True
                        print(f"[DEBUG] Assigned {peak['sample']} RT:{peak['rt']:.3f} to existing group (avg: {group_rt_avg:.3f})")
                        break
                
                if not assigned:
                    groups.append([peak])
                    print(f"[DEBUG] Created new group for {peak['sample']} RT:{peak['rt']:.3f}")
            
            return groups
        
        # Create initial grouping with larger tolerance
        peak_groups = group_peaks_by_rt(all_peaks, 0.2)  # Start with 0.2 min tolerance
        
        # Filter groups with multiple samples
        multi_sample_groups = [g for g in peak_groups if len(set(p['sample'] for p in g)) > 1]
        
        print(f"[DEBUG] Found {len(multi_sample_groups)} multi-sample groups")
        for i, group in enumerate(multi_sample_groups):
            samples = [p['sample'] for p in group]
            rts = [p['rt'] for p in group]
            print(f"[DEBUG] Group {i+1}: {samples} - RTs: {rts}")
        
        # Always show controls, even if no matches initially
        content = [
            html.H6("📊 Cross-Sample Peak Comparison"),
            html.P(f"Comparing {len(hplc_files)} HPLC samples"),
            
            # RT Tolerance Slider - ALWAYS VISIBLE
            html.Div([
                html.Label("Peak Matching RT Tolerance (±min): "),
                dcc.Slider(
                    id='across-samples-rt-tolerance',
                    min=0.01, max=0.5, step=0.01, value=0.2,  # Start with 0.2
                    marks={0.01: '0.01', 0.1: '0.1', 0.2: '0.2', 0.3: '0.3', 0.5: '0.5'},
                    tooltip={"placement": "bottom", "always_visible": True}
                )
            ], style={'marginBottom': '20px'})
        ]
        
        if not multi_sample_groups:
            content.extend([
                html.Div([
                    html.P("No matching peaks found across different samples with current tolerance."),
                    html.P("Try adjusting the retention time tolerance above."),
                    html.H6("All Peaks by Sample:"),
                    html.Div([
                        html.P("🔸 {}: {}".format(sample, [f"{p['rt']:.3f} min" for p in all_peaks if p['sample'] == sample]))
                        for sample in sorted(set(p['sample'] for p in all_peaks))
                    ])
                ])
            ])
            
            return html.Div(content)
        
        # Create dropdown options for peak groups
        dropdown_options = []
        for i, group in enumerate(multi_sample_groups):
            avg_rt = sum(p['rt'] for p in group) / len(group)
            sample_count = len(set(p['sample'] for p in group))
            sample_names = sorted(set(p['sample'] for p in group))
            
            dropdown_options.append({
                'label': f"Group {i+1}: {avg_rt:.3f} min - Found in {sample_count} samples ({', '.join(sample_names[:3])}{' ...' if len(sample_names) > 3 else ''})",
                'value': i
            })
        
        # Create default comparison table for first group
        # Use stored group selection or default to first group
        group_index = min(stored_group_selection or 0, len(multi_sample_groups) - 1)
        selected_group = multi_sample_groups[group_index]
        comparison_data = []

        print(f"[DEBUG] Using stored group selection: {stored_group_selection}, actual index: {group_index}")


        for peak in selected_group:
            # Helper function to safely convert values
            def safe_format_float(value, decimals=2, default="n.a."):
                try:
                    if value and str(value).lower() != 'n.a.' and str(value).strip() != '':
                        num_val = float(str(value).replace(',', '.'))
                        return f"{num_val:.{decimals}f}" if num_val > 0 else default
                    return default
                except:
                    return default
            
            row_data = {
                'Sample': peak['sample'],
                'Peak': int(peak['peak_no']) if str(peak['peak_no']).isdigit() else peak['peak_no'],
                'RT (min)': f"{peak['rt']:.3f}",
                'Area (mAU·min)': f"{peak['area']:.3f}",
                'Area %': f"{peak['rel_area']:.2f}",
                'Height (mAU)': f"{peak['height']:.0f}",
                'Width (min)': safe_format_float(peak['width'], 3),
                'Resolution': safe_format_float(peak['resolution'], 2),
                'Asymmetry': safe_format_float(peak['asymmetry'], 2),
                'Plates': f"{peak['plates']}" if peak['plates'] > 0 else "n.a."
            }
            comparison_data.append(row_data)
        
        # Define table columns (same as main table)
        table_columns = [
            {"name": "Sample", "id": "Sample"},
            {"name": "Peak", "id": "Peak"},
            {"name": "RT (min)", "id": "RT (min)"},
            {"name": "Area (mAU·min)", "id": "Area (mAU·min)"},
            {"name": "Area %", "id": "Area %"},
            {"name": "Height (mAU)", "id": "Height (mAU)"},
            {"name": "Width (min)", "id": "Width (min)"},
            {"name": "Resolution", "id": "Resolution"},
            {"name": "Asymmetry", "id": "Asymmetry"},
            {"name": "Plates", "id": "Plates"}
        ]
        
        content.extend([
            # Peak Group Selector
            html.Div([
                html.Label("Select Peak Group to Compare: "),
                dcc.Dropdown(
                    id='peak-group-selector',
                    options=dropdown_options,
                    value=min(stored_group_selection, len(dropdown_options) - 1) if dropdown_options else 0,
                    style={'marginTop': '5px'}
                )
            ], style={'marginBottom': '20px'}),
            
            # Comparison Table
            html.Div([
                dash_table.DataTable(
                    id='across-samples-table',
                    data=comparison_data,
                    columns=table_columns,
                    style_table={
                        'overflowX': 'auto', 
                        'overflowY': 'auto',
                        'maxHeight': '400px'
                    },
                    style_cell={'fontSize': '12px', 'padding': '8px', 'textAlign': 'center'},
                    style_header={'backgroundColor': '#e3f2fd', 'fontWeight': 'bold', 'color': '#1565c0'},
                    style_data_conditional=[
                        {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'}
                    ]
                )
            ])
        ])
        
        return html.Div(content)
        
    # Store the selected peak group for persistence
    app.clientside_callback(
        """
        function(value) {
            // Simple pass-through function with safety check
            if (value !== undefined) {
                return value;
            }
            return null;
        }
        """,
        Output('selected-peak-group-store', 'data', allow_duplicate=True),
        [Input('peak-group-selector', 'value')],
        prevent_initial_call=True
    )
    
    # Add sidebar tab switching functionality
    app.clientside_callback(
        """
        function(n_clicks_sample, n_clicks_peak, n_clicks_plot, n_clicks_export) {
            const clientside = window.dash_clientside.clientside;
            if (clientside && typeof clientside.switch_tab === 'function') {
                return clientside.switch_tab(n_clicks_sample, n_clicks_peak, n_clicks_plot, n_clicks_export);
            }
            return '';
        }
        """,
        Output('_sidebar_tab_dummy', 'children'),  # Dummy output that's not used
        [
            Input('sample-tab-btn', 'n_clicks'),
            Input('peak-tab-btn', 'n_clicks'),
            Input('plot-tab-btn', 'n_clicks'),
            Input('export-tab-btn', 'n_clicks')
        ],
        prevent_initial_call=True
    )
    
    # Add HPLC analysis tab switching functionality
    app.clientside_callback(
        """
        function(n_clicks_integration, n_clicks_across, n_clicks_calibration) {
            const clientside = window.dash_clientside.clientside;
            if (clientside && typeof clientside.switch_analysis_tab === 'function') {
                return clientside.switch_analysis_tab(n_clicks_integration, n_clicks_across, n_clicks_calibration);
            }
            return '';
        }
        """,
        Output('_analysis_tab_dummy', 'children'),  # Dummy output that's not used
        [
            Input('integration-tab-btn', 'n_clicks'),
            Input('across-samples-tab-btn', 'n_clicks'),
            Input('calibration-tab-btn', 'n_clicks')
        ],
        prevent_initial_call=True
    )
    
    @app.callback(
        [Output("hplc-analysis-section", "style"),
        Output("integration-table-container", "children", allow_duplicate=True),
        Output("across-samples-container", "children"),
        Output("calibration-container", "children")],
        [Input("selected-layer", "data"),
        Input("stored-peaks", "data")],  # This listens to manual peaks
        [State("active-hplc-tab-store", "data"),
        State("selected-peak-group-store", "data")],
        prevent_initial_call=True
    )
    def update_hplc_analysis_section(selected_layer, manual_peaks, active_tab_type, stored_group_selection):
        """Update HPLC analysis section when file is selected or peaks are detected."""
        print(f"🧪 [HPLC] Processing: {selected_layer}")
        print(f"🧪 [HPLC] Manual peaks: {len(manual_peaks) if manual_peaks else 0}")
        
        if not selected_layer:
            return {"display": "none"}, "", "", ""
        
        filename = selected_layer.split('|')[0]
        file_data = data_manager.get_file_data(filename)
        
        # Check if this is HPLC data
        if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
            return {"display": "none"}, "", "", ""
        
        # Get imported peaks table
        integration_table = file_data.get('integration_table')
        
        # Start with imported peaks
        all_rows = []
        if integration_table is not None and not integration_table.empty:
            for _, row in integration_table.iterrows():
                row_dict = row.to_dict()
                row_dict['source'] = 'imported'
                all_rows.append(row_dict)
        
        # Add manual peaks
        if manual_peaks:
            for i, p in enumerate(manual_peaks, start=1):
                manual_row = {
                    "No.": len(all_rows) + i,  # Continue numbering
                    "Peak Name": f"Manual {i}",
                    "Retention Time": f"{p['apex_x']:.3f}",
                    "Area": f"{p['area']:.3f}",
                    "Height": f"{p['height']:.0f}",
                    "Width": f"{p['width']:.3f}" if 'width' in p else "n.a.",
                    "Plates": "n.a.",
                    "Asymmetry": "n.a.",
                    "Resolution": "n.a.",
                    "source": "manual"
                }
                all_rows.append(manual_row)
        
        # Create DataFrame for combined peaks
        if all_rows:
            combined_df = pd.DataFrame(all_rows)
            
            # Recalculate relative areas based on total area
            total_area = 0
            for row in all_rows:
                try:
                    area_str = str(row.get('Area', '0')).replace(',', '.')
                    area = float(area_str) if area_str and area_str.lower() != 'n.a.' else 0
                    total_area += area
                except:
                    pass
            
            # Add relative area column
            for row in all_rows:
                try:
                    area_str = str(row.get('Area', '0')).replace(',', '.')
                    area = float(area_str) if area_str and area_str.lower() != 'n.a.' else 0
                    row['Relative Area'] = f"{(area / total_area * 100):.2f}" if total_area > 0 else "0.00"
                except:
                    row['Relative Area'] = "0.00"
            
            # Create DataTable for integration results
            integration_content = html.Div([
                html.H6(f"Integration Table - {len(all_rows)} peaks", 
                      style={'marginBottom': '10px', 'color': '#2c3e50'}),
                
                dash_table.DataTable(
                    id='integration-table',
                    data=all_rows,
                    columns=[
                        {"name": "No.", "id": "No."},
                        {"name": "Peak Name", "id": "Peak Name"},
                        {"name": "RT (min)", "id": "Retention Time"},
                        {"name": "Area (mAU·min)", "id": "Area"},
                        {"name": "Area %", "id": "Relative Area"},
                        {"name": "Height (mAU)", "id": "Height"},
                        {"name": "Width (min)", "id": "Width"},
                        {"name": "Resolution", "id": "Resolution"},
                        {"name": "Asymmetry", "id": "Asymmetry"},
                        {"name": "Plates", "id": "Plates"}
                    ],
                    style_table={
                        'overflowX': 'auto', 
                        'overflowY': 'auto',
                        'maxHeight': '400px'
                    },
                    style_cell={'fontSize': '12px', 'padding': '8px', 'textAlign': 'center'},
                    style_header={'backgroundColor': '#e3f2fd', 'fontWeight': 'bold', 'color': '#1565c0'},
                    style_data_conditional=[
                        {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'},
                        {
                            'if': {'filter_query': '{source} = imported'},
                            'backgroundColor': '#e8f5e8',
                            'color': 'black'
                        },
                        {
                            'if': {'filter_query': '{source} = manual'},
                            'backgroundColor': '#fff3cd',
                            'color': 'black'
                        }
                    ],
                    sort_action="native",
                ),
                
                html.Div([
                    html.Small("🟩 Green rows: Imported peaks | 🟨 Yellow rows: Manual peaks", 
                            style={'color': '#666', 'marginTop': '10px'})
                ])
            ])
            
            # Create across samples content
            across_samples_content = create_across_samples_content(data_manager, filename, stored_group_selection)
            
            # Create calibration placeholder
            calibration_content = html.Div([
                html.H6("📊 Calibration & Quantification"),
                html.P("This feature is coming soon."),
                html.Div([
                    html.Ul([
                        html.Li("Standard curve creation"),
                        html.Li("Linear and non-linear regression"),
                        html.Li("Automatic quantification"),
                        html.Li("Export of results")
                    ])
                ], style={'marginTop': '15px'})
            ])
            
            return {"display": "block"}, integration_content, across_samples_content, calibration_content
        
        # No peaks available
        empty_message = html.Div("No peaks detected in this file.")
        return {"display": "block"}, empty_message, empty_message, empty_message




    @app.callback(
        Output('across-samples-table', 'data'),
        [Input('peak-group-selector', 'value'),
        Input('across-samples-rt-tolerance', 'value')],
        [State('selected-layer', 'data')],
        prevent_initial_call=True
    )
    def update_across_samples_table(selected_group_idx, rt_tolerance, selected_layer):
        """Update the across samples comparison table when group selection or RT tolerance changes."""
        if selected_layer is None:
            return []
            
        filename = selected_layer.split('|')[0]
        
        # Extract all peaks from all samples
        all_peaks = []
        
        # Get all HPLC files
        for loaded_filename in data_manager.get_loaded_files():
            file_data = data_manager.get_file_data(loaded_filename)
            if file_data and file_data.get('type') in ['chromatogram', 'chromeleon_bundle']:
                integration_table = file_data.get('integration_table')
                peak_table = file_data.get('peak_table')
                
                if integration_table is not None and len(integration_table) > 0:
                    sample_name = loaded_filename.replace('_UV_VIS_1.txt', '').replace('temp_', '')
                    
                    # Filter out total rows and n.a. rows
                    peaks_only = integration_table[
                        (~integration_table.iloc[:, 0].astype(str).str.contains('Total', case=False, na=False)) &
                        (~integration_table.iloc[:, 0].astype(str).str.contains('n.a.', case=False, na=False)) &
                        (integration_table.iloc[:, 0].notna())
                    ]
                    
                    # Get corresponding peak analysis data
                    peak_analysis = {}
                    if peak_table is not None:
                        for _, peak_row in peak_table.iterrows():
                            peak_no = peak_row.get('No.')
                            if str(peak_no).lower() != 'n.a.' and pd.notna(peak_no):
                                peak_analysis[peak_no] = peak_row
                    
                    for idx, peak_row in peaks_only.iterrows():
                        peak_no = peak_row.get('No.')
                        if str(peak_no).lower() == 'n.a.' or pd.isna(peak_no):
                            continue
                            
                        corresponding_peak = peak_analysis.get(peak_no, {})
                        
                        # More robust RT extraction
                        rt_value = peak_row.get('Retention Time', 0)
                        if pd.isna(rt_value) or str(rt_value).lower() == 'n.a.':
                            continue
                            
                        try:
                            rt = float(str(rt_value).replace(',', '.'))
                            if rt <= 0:
                                continue
                        except:
                            continue
                        
                        peak_data = {
                            'sample': sample_name,
                            'filename': loaded_filename,
                            'is_current': loaded_filename == filename,
                            'peak_no': peak_no,
                            'rt': rt,
                            'area': float(str(peak_row.get('Area', 0)).replace(',', '.')),
                            'height': float(str(peak_row.get('Height', 0)).replace(',', '.')),
                            'rel_area': float(str(peak_row.get('Relative Area', 0)).replace(',', '.')),
                            'width': float(str(corresponding_peak.get('Width (50%)', 0)).replace(',', '.')),
                            'resolution': str(corresponding_peak.get('Resolution (EP)', 'n.a.')),
                            'asymmetry': float(str(corresponding_peak.get('Asymmetry (EP)', 0)).replace(',', '.')) if corresponding_peak.get('Asymmetry (EP)', 'n.a.') != 'n.a.' else 0,
                            'plates': int(float(str(corresponding_peak.get('Plates (EP)', 0)).replace(',', '.'))) if str(corresponding_peak.get('Plates (EP)', 0)).replace(',', '.').replace('.', '').isdigit() else 0
                        }
                        all_peaks.append(peak_data)
        
        # Group peaks by retention time with the current tolerance
        def group_peaks_by_rt(peaks, tolerance=0.1):
            """Group peaks by retention time within tolerance."""
            peaks_sorted = sorted(peaks, key=lambda x: x['rt'])
            groups = []
            
            for peak in peaks_sorted:
                # Find if this peak belongs to an existing group
                assigned = False
                for group in groups:
                    group_rt_avg = sum(p['rt'] for p in group) / len(group)
                    if abs(peak['rt'] - group_rt_avg) <= tolerance:
                        group.append(peak)
                        assigned = True
                        break
                
                if not assigned:
                    groups.append([peak])
            
            return groups
        
        # Create peak groups with current tolerance
        peak_groups = group_peaks_by_rt(all_peaks, rt_tolerance)
        
        # Filter groups with multiple samples
        multi_sample_groups = [g for g in peak_groups if len(set(p['sample'] for p in g)) > 1]
        
        if not multi_sample_groups or selected_group_idx >= len(multi_sample_groups):
            return []  # No valid groups or invalid index
        
        # Get the selected group
        selected_group = multi_sample_groups[selected_group_idx]
        comparison_data = []
        
        # Helper function to safely format float values
        def safe_format_float(value, decimals=2, default="n.a."):
            try:
                if value and str(value).lower() != 'n.a.' and str(value).strip() != '':
                    num_val = float(str(value).replace(',', '.'))
                    return f"{num_val:.{decimals}f}" if num_val > 0 else default
                return default
            except:
                return default
        
        # Create comparison data for the selected group
        for peak in selected_group:
            row_data = {
                'Sample': peak['sample'],
                'Peak': int(peak['peak_no']) if str(peak['peak_no']).isdigit() else peak['peak_no'],
                'RT (min)': f"{peak['rt']:.3f}",
                'Area (mAU·min)': f"{peak['area']:.3f}",
                'Area %': f"{peak['rel_area']:.2f}",
                'Height (mAU)': f"{peak['height']:.0f}",
                'Width (min)': safe_format_float(peak['width'], 3),
                'Resolution': safe_format_float(peak['resolution'], 2),
                'Asymmetry': safe_format_float(peak['asymmetry'], 2),
                'Plates': f"{peak['plates']}" if peak['plates'] > 0 else "n.a."
            }
            comparison_data.append(row_data)
            
        # Store the selected group index for persistence
        # This is done in a clientside callback
        
        return comparison_data
    @app.callback(
        Output("active-hplc-tab-store", "data"),
        [Input("integration-tab-btn", "n_clicks"),
         Input("across-samples-tab-btn", "n_clicks"),
         Input("calibration-tab-btn", "n_clicks")],
        [State("active-hplc-tab-store", "data")],
        prevent_initial_call=True
    )
    def store_active_tab(integration_clicks, across_clicks, calibration_clicks, current_active):
        """Store which HPLC analysis tab is currently active."""
        ctx = callback_context
        
        # Return current active if no triggers
        if not ctx.triggered:
            return current_active or "integration"
        
        try:
            # Find which tab was clicked
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            # Map button IDs to tab names
            if triggered_id == "integration-tab-btn":
                return "integration"
            elif triggered_id == "across-samples-tab-btn":
                return "across-samples"
            elif triggered_id == "calibration-tab-btn":
                return "calibration"
                    
        except Exception as e:
            print(f"[DEBUG] Error in store_active_tab: {e}")
            
        # Fallback to current active or default
        return current_active or "integration"




    @app.callback(
        Output("selected-peak-group-store", "data"),
        [Input('peak-group-selector', 'value')],
        prevent_initial_call=True
    )
    def store_selected_peak_group(selected_group):
        """Store the selected peak group to preserve across file switches."""
        return selected_group or 0


def register_clear_callbacks(app, data_manager):
    """Register the clear feedback callback (separate from main UI updates)."""
    
    @app.callback(
        Output("clear-feedback", "children"),
        Input("clear-data-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_feedback(n_clicks):
        if n_clicks:
            return "✅ Cleared!"
        return ""

def create_single_file_overview(data_manager, filename):
    """Generate detailed metadata card for a single file."""
    entry = data_manager.get_file_data(filename)
    if not entry:
        return html.Div("❌ File data not found.")

    meta = entry.get("metadata", {})
    kind = entry.get("type", "unknown").title().replace("_", " ")
    display_name = filename.replace("_UV_VIS_1.txt", "").replace("temp_", "")

    card = [
        html.H4(display_name, style={'color': '#2c3e50', 'marginBottom': '15px'}),
        html.P([html.Strong("File Type: "), html.Span(kind, style={'color': '#3498db', 'fontWeight': 'bold'})])
    ]

    # Inject into mock manager to reuse existing logic
    class OneFileManager:
        def get_loaded_files(self): return [filename]
        def get_file_data(self, f): return entry if f == filename else None

    return create_data_overview(OneFileManager())[0]

def create_file_list(data_manager):
    """Create a compact file list with delete buttons."""
    loaded_files = data_manager.get_loaded_files()
    if not loaded_files:
        return html.Div("No files loaded", className="no-files-text")
    
    file_items = []
    for fname in loaded_files:
        file_data = data_manager.get_file_data(fname)
        if not file_data:
            continue
            
        # Get file type icon
        file_type = file_data['type']
        icons = {
            'uvvis_csv': '📊',
            'lcms_cdf': '📈', 
            'lcms_bundle': '📦',
            'chromeleon_bundle': '📈',
            'chromatogram': '📉',
            'spectra': '🌊'
        }
        icon = icons.get(file_type, '📄')
        
        # Create shortened display name
        display_name = fname.replace('_UV_VIS_1.txt', '').replace('temp_', '')
        if len(display_name) > 30:
            display_name = display_name[:27] + '...'
            
        # Get metadata for display
        meta = file_data.get("metadata", {})
        date = meta.get('Date', '').split(',')[0] if meta.get('Date') else ''
        file_type_display = file_data['type'].replace('_', '-').upper()
        
        file_items.append(
            html.Div([
                html.Div([
                    html.Span(f"{icon} {display_name}", className="file-name"),
                    html.Div(f"{file_type_display} • {date}", className="file-meta"),
                ], className="file-info"),
                html.Button("×", id={'type': 'delete-file-btn', 'index': fname}, 
                          className="btn-delete-file", title=f"Delete {fname}")
            ], className="file-item")
        )
    
    return html.Div(file_items, className="file-list")
    
def create_data_overview(data_manager):
    """Generate one card per recognised bundle."""
    bundles = data_manager.get_loaded_files()
    if not bundles:
        return "No data loaded."

    def non_empty(obj):
        if obj is None:
            return False
        if hasattr(obj, "empty"):
            return not obj.empty
        if isinstance(obj, (dict, list, tuple, set, str)):
            return bool(obj)
        return bool(obj)

    def tick_with_hint(obj, missing_filename=""):
        if non_empty(obj):
            return "✅"
        else:
            return f"❌ MISSING{f' (upload {missing_filename})' if missing_filename else ''}"

    cards: list = []
    for fname in bundles:
        entry = data_manager.get_file_data(fname)
        if not entry:
            continue

        meta = entry.get("metadata", {})
        kind = entry.get("type", "unknown").title().replace("_", " ")
        chrom = entry.get("data")
        integ = entry.get("integration_table")
        peak = entry.get("peak_table")
        sst  = entry.get("sst_result")

        # Clean display name and extract base name for hints
        display_name = fname.replace("_UV_VIS_1.txt", "").replace("temp_", "")
        base_name = display_name  # This is the base name for file hints

        card = [
            html.H4(display_name),
            html.P(f"Type: {kind}"),
        ]

        # Generic metadata
        if "Wavelength (nm)" in meta:
            card.append(html.P(f"Wavelength: {meta['Wavelength (nm)']} nm"))
        if "Injection Date" in meta:
            card.append(html.P(f"Injection Date: {meta['Injection Date']}"))
        if "Injection Time" in meta:
            card.append(html.P(f"Injection Time: {meta['Injection Time']}"))

        print(f"[DEBUG UI] SST data for {fname}: {sst}")
        print(f"[DEBUG UI] SST non_empty check: {non_empty(sst)}")

        # Chromeleon-bundle specific extras

        if entry["type"] == "chromeleon_bundle":
            card.extend([
                html.P(f"Chromatogram Data: {tick_with_hint(chrom, f'{base_name}_UV_VIS_1.txt')}"),
                html.P(f"SST Result: {tick_with_hint(sst, f'{base_name}_SST.txt')}"),
                html.P(f"Integration Table: {tick_with_hint(integ, f'{base_name}_Integration.txt')}"),
                html.P(f"Peak Analysis Table: {tick_with_hint(peak, f'{base_name}_Peak Analysis.txt')}"),
            ])


            if non_empty(sst):
                card.append(html.Details([
                    html.Summary("🧪 SST Results"),
                    html.Ul([html.Li(f"{k}: {v}") for k, v in sst.items()]),
                ]))


        elif entry["type"] == "uvvis_csv":
            # Extract and clean metadata
            reader_type = meta.get('Reader Type', 'Unknown Reader')
            reader_sn = meta.get('Reader Serial Number', 'Unknown')
            plate_type = meta.get('Plate Type', '96 WELL PLATE')
            read_type = meta.get('Read', 'Absorbance Spectrum')
            
            # Clean date/time
            date_raw = meta.get('Date', '')
            time_raw = meta.get('Time', '')
            date_clean = date_raw.split(',')[0].strip() if date_raw else 'Unknown'
            time_clean = time_raw.split(',')[0].strip() if time_raw else 'Unknown'
            
            # Wavelength info
            wl_range = meta.get('wavelength_range', 'Unknown')
            wl_min = meta.get('wavelength_min', 0)
            wl_max = meta.get('wavelength_max', 0)
            data_points = meta.get('data_points', 0)
            
            # Well info
            filled_wells = meta.get('filled_well_count', 0)
            total_wells = meta.get('total_wells', 0)
            
            # Calculate step size
            step_size = int((wl_max - wl_min) / (data_points - 1)) if data_points > 1 else 10
            
            card.extend([
                # Instrument Information
                html.H5("📋 Instrument Information", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Date: "), f"{date_clean}", html.Br(),
                    html.Strong("Time: "), f"{time_clean}", html.Br(),
                    html.Strong("Reader: "), f"{reader_type}", 
                    f" (SN: {reader_sn})" if reader_sn != 'Unknown' else "", html.Br(),
                    html.Strong("Plate: "), f"{plate_type}", html.Br(),
                    html.Strong("Read Type: "), f"{read_type}"
                ], style={'margin': '5px 0', 'fontSize': '14px'}),
                
                # Measurement Parameters
                html.H5("⚙️ Measurement Parameters", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Range: "), f"{wl_min:.0f}–{wl_max:.0f} nm", html.Br(),
                    html.Strong("Step: "), f"{step_size} nm", html.Br(),
                    html.Strong("Data Points: "), f"{data_points} wavelengths"
                ], style={'margin': '5px 0', 'fontSize': '14px'}),
                
                # Spectrum Data
                html.H5("🧪 Spectrum Data", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Wavelengths: "), f"{data_points} (from {wl_min:.0f} to {wl_max:.0f} nm)", html.Br(),
                    html.Strong("Wells Filled: "), f"{filled_wells}/{total_wells}", html.Br(),
                    html.Strong("Plate Layout: "), f"{plate_type.lower()}"
                ], style={'margin': '5px 0', 'fontSize': '14px'})
            ])
            
            # Show sample of filled wells
            filled_wells_list = meta.get('filled_wells', [])
            if filled_wells_list:
                sample_wells = filled_wells_list[:16]  # Show first 16 wells
                wells_text = ', '.join(sample_wells)
                if len(filled_wells_list) > 16:
                    wells_text += f" ... (+{len(filled_wells_list) - 16} more)"
                
                card.append(html.Details([
                    html.Summary("🔍 Sample Wells Data", style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#34495e'}),
                    html.P(wells_text, style={'fontSize': '12px', 'fontFamily': 'monospace', 'background': '#f8f9fa', 'padding': '8px', 'borderRadius': '4px'})
                ]))
            
            # Show overflow warnings if any
            overflow_count = meta.get('overflow_count', 0)
            if overflow_count > 0:
                overflow_wells = meta.get('overflow_wells', [])
                card.append(html.Details([
                    html.Summary(f"⚠️ Overflow Detected ({overflow_count} wells)", 
                                style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#e74c3c'}),
                    html.P([
                        "Wells with possible saturation (>4.0 AU): ",
                        html.Code(', '.join(overflow_wells[:10]) + ('...' if len(overflow_wells) > 10 else ''),
                                style={'background': '#fff5f5', 'padding': '2px 4px', 'borderRadius': '3px'})
                    ], style={'fontSize': '12px', 'color': '#e74c3c'})
                ]))
            
            # Add software info if available
            software_version = meta.get('Software Version', '')
            if software_version:
                card.append(html.Details([
                    html.Summary("💻 Software Information", style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#7f8c8d'}),
                    html.P(f"Gen5 Software Version: {software_version}", 
                        style={'fontSize': '12px', 'fontStyle': 'italic'})
                ]))

        elif entry["type"] == "lcms_cdf":
            # Get comprehensive metadata
            raw_metadata = meta.get('raw_cdf_data', {})
            
            # Basic info
            sample_name = meta.get('sample_name', 'Unknown Sample')
            detector_name = meta.get('detector_name', 'MS Detector')
            ionization_mode = meta.get('ionization_mode', 'unknown')
            experiment_title = meta.get('experiment_title', '')
            
            # Instrument info
            instrument_name = meta.get('instrument_name', 'Unknown')
            instrument_mfr = meta.get('instrument_mfr', '')
            instrument_model = meta.get('instrument_model', '')
            
            # Analysis parameters
            scan_count = meta.get('scan_count', 0)
            rt_range = meta.get('retention_time_range', 'Unknown')
            mass_range = meta.get('mass_range_str', 'Unknown')
            max_intensity = meta.get('max_intensity', 0)
            
            card.extend([
                # Sample and Experiment Info
                html.H5("🧪 Sample Information", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Sample: "), f"{sample_name}", html.Br(),
                    html.Strong("Experiment: "), f"{experiment_title}" if experiment_title else "Not specified", html.Br(),
                    html.Strong("Ionization Mode: "), 
                    html.Span(f"{ionization_mode.upper()}", 
                            style={'color': '#e74c3c' if ionization_mode == 'negative' else '#27ae60' if ionization_mode == 'positive' else '#7f8c8d',
                                'fontWeight': 'bold'})
                ], style={'margin': '5px 0', 'fontSize': '14px'}),
                
                # Instrument Information
                html.H5("🔬 Instrument Details", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Detector: "), f"{detector_name}", html.Br(),
                    html.Strong("Instrument: "), f"{instrument_name}", html.Br(),
                    html.Strong("Manufacturer: "), f"{instrument_mfr}" if instrument_mfr else "Not specified", html.Br(),
                    html.Strong("Model: "), f"{instrument_model}" if instrument_model else "Not specified"
                ], style={'margin': '5px 0', 'fontSize': '14px'}),
                
                # Analysis Parameters
                html.H5("⚙️ Analysis Parameters", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Retention Time: "), f"{rt_range}", html.Br(),
                    html.Strong("Mass Range: "), f"{mass_range}", html.Br(),
                    html.Strong("Total Scans: "), f"{scan_count}", html.Br(),
                    html.Strong("Max Intensity: "), f"{max_intensity:.0f}" if max_intensity > 0 else "Unknown"
                ], style={'margin': '5px 0', 'fontSize': '14px'}),
                
                # Data Summary
                html.H5("📊 Data Summary", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("TIC Points: "), f"{meta.get('tic_points', 0)}", html.Br(),
                    html.Strong("Data Points: "), f"{meta.get('data_points', 0)}", html.Br(),
                    html.Strong("File Size: "), f"{len(str(raw_metadata))} chars metadata"
                ], style={'margin': '5px 0', 'fontSize': '14px'})
            ])
            
            # CDF Structure Analysis (expandable)
            cdf_dimensions = meta.get('cdf_dimensions', {})
            cdf_variables = meta.get('cdf_variables', {})
            
            if cdf_dimensions or cdf_variables:
                structure_info = []
                
                if cdf_dimensions:
                    structure_info.append(html.H6("📏 CDF Dimensions:"))
                    for dim_name, dim_info in cdf_dimensions.items():
                        size = dim_info.get('size', '?')
                        unlimited = " (unlimited)" if dim_info.get('unlimited') else ""
                        structure_info.append(html.Li(f"{dim_name}: {size}{unlimited}"))
                
                if cdf_variables:
                    structure_info.append(html.H6("📋 Variable Categories:"))
                    for cat_name, var_list in cdf_variables.items():
                        if var_list:
                            structure_info.append(html.Li(f"{cat_name.title()}: {len(var_list)} variables"))
                
                card.append(html.Details([
                    html.Summary("🔍 CDF File Structure", style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#34495e'}),
                    html.Div(structure_info, style={'fontSize': '12px', 'marginLeft': '10px'})
                ]))
            
            # Raw Metadata (expandable, for debugging)
            if raw_metadata:
                metadata_items = []
                for key, value in list(raw_metadata.items())[:20]:  # Show first 20 items
                    if isinstance(value, (str, int, float)):
                        metadata_items.append(html.Li([
                            html.Code(key, style={'background': '#f8f9fa', 'padding': '2px 4px'}),
                            f": {value}"
                        ]))
                
                if len(raw_metadata) > 20:
                    metadata_items.append(html.Li(f"... and {len(raw_metadata) - 20} more fields"))
                
                card.append(html.Details([
                    html.Summary(f"🔧 Raw CDF Metadata ({len(raw_metadata)} fields)", 
                                style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#7f8c8d'}),
                    html.Ul(metadata_items, style={'fontSize': '11px', 'maxHeight': '200px', 'overflow': 'auto'})
                ]))

        # LC-MS Bundle specific display
        elif entry["type"] == "lcms_bundle":
            bundle_data = entry.get("bundle_data", {})
            components = meta.get("components", [])
            
            # Enhanced bundle display with comprehensive metadata
            # Format injection date properly
            injection_raw = meta.get('injection_date_time_stamp', '')
            if injection_raw and len(injection_raw) >= 12 and injection_raw[:12].isdigit():
                from datetime import datetime
                try:
                    dt = datetime.strptime(injection_raw[:12], "%Y%m%d%H%M")
                    injection_formatted = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    injection_formatted = "Unknown"
            else:
                injection_formatted = "Unknown"

            # Format sample ID (truncate if too long)
            sample_id = meta.get('sample_id', 'Unknown')
            if len(sample_id) > 20:
                sample_id = sample_id[:8] + "..."

            volume = meta.get('sample_injection_volume', '?')

            card.extend([
                html.H5("📦 LC-MS Bundle Components", style={'margin': '10px 0 5px 0', 'color': '#2c3e50'}),
                html.P([
                    html.Strong("Sample: "), meta.get('sample_name', 'Unknown'), html.Br(),
                    html.Strong("Sample ID: "), sample_id, html.Br(),
                    html.Strong("Injection: "), injection_formatted, html.Br(),
                    html.Strong("Volume: "), f"{volume} µL", html.Br(),
                    html.Strong("Components: "), ", ".join(components), html.Br(),
                    html.Strong("Files: "), f"{meta.get('file_count', 0)} bundled"
                ], style={'margin': '5px 0', 'fontSize': '14px'})
            ])
            
            # MS Data Details
            ms_components = [c for c in components if c.startswith('MS')]
            if ms_components:
                ms_details = []

                if 'MS+' in components:
                    ms_details.append(html.Li([
                        html.Strong("MS+ (Positive): "),
                        f"{meta.get('ms_positive_scans', 0)} scans, ",
                        f"RT: {meta.get('ms_positive_rt_range', 'Unknown')}, ",
                        f"m/z: {meta.get('ms_positive_mass_range', 'Unknown')}, ",
                        f"Max: {meta.get('ms_positive_max_intensity', 0):,.0f}"
                    ]))
                if 'MS-' in components:
                    ms_details.append(html.Li([
                        html.Strong("MS- (Negative): "),
                        f"{meta.get('ms_negative_scans', 0)} scans, ",
                        f"RT: {meta.get('ms_negative_rt_range', 'Unknown')}, ",
                        f"m/z: {meta.get('ms_negative_mass_range', 'Unknown')}, ",
                        f"Max: {meta.get('ms_negative_max_intensity', 0):,.0f}"
                    ]))

                card.append(html.Details([
                    html.Summary("🔬 Mass Spectrometry Data", style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#e74c3c'}),
                    html.Ul(ms_details)
                ]))
            
            # UV Data Details  
            uv_components = [c for c in components if c.startswith('UV')]
            if uv_components:
                uv_details = []

                if 'UV-A' in components:
                    uv_details.append(html.Li([
                        html.Strong(f"Channel A ({meta.get('uv_a_wavelength', '?')} nm): "),
                        f"{meta.get('uv_a_data_points', 0)} pts, ",
                        f"RT: {meta.get('uv_a_rt_range', 'Unknown')}, ",
                        f"Max: {meta.get('uv_a_max_intensity', 0):.1f} {meta.get('uv_a_unit', 'mAU')}"
                    ]))
                if 'UV-B' in components:
                    uv_details.append(html.Li([
                        html.Strong(f"Channel B ({meta.get('uv_b_wavelength', '?')} nm): "),
                        f"{meta.get('uv_b_data_points', 0)} pts, ",
                        f"RT: {meta.get('uv_b_rt_range', 'Unknown')}, ",
                        f"Max: {meta.get('uv_b_max_intensity', 0):.1f} {meta.get('uv_b_unit', 'mAU')}"
                    ]))

                card.append(html.Details([
                    html.Summary("📊 UV Chromatogram Data", style={'cursor': 'pointer', 'fontWeight': 'bold', 'color': '#3498db'}),
                    html.Ul(uv_details)
                ]))

        cards.append(html.Div(card, className="file-card"))

    return cards




#