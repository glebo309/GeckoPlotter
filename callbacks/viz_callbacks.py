# File: callbacks/viz_callbacks.py 
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate
from dash import callback_context

from plot.lcms import create_tic_plot, create_lcms_uv_plot
from plot.hplc import create_chromatogram_plot, create_chromeleon_bundle_plot
from plot.uvis import create_uvvis_plot, create_single_well_plot
from .upload_callbacks import create_data_overview
from callbacks.plot_settings_callbacks import apply_plot_settings, create_separate_plots
from utils.peak_integration import peak_manager


def register_viz_callbacks(app, data_manager):
    """Register visualization-related callbacks with visibility support."""
    
    # Sample area follows tree selection
    @app.callback(
        Output("data-overview", "children", allow_duplicate=True),
        Input("selected-layer", "data"),
        prevent_initial_call=True
    )
    def update_sample_display_from_tree(selected_layer):
        if not selected_layer:
            return "No data selected."
        
        # Extract filename from tree selection
        filename = selected_layer.split("|")[0]
        if filename not in data_manager.get_loaded_files():
            return "⚠️ File not found."
        
        from .upload_callbacks import create_single_file_overview
        return create_single_file_overview(data_manager, filename)

    # Populate dropdown when files are uploaded
    @app.callback(
        [Output("file-selector", "options", allow_duplicate=True),
        Output("file-selector", "value", allow_duplicate=True)],
        [Input("upload-status", "children")],
        prevent_initial_call=True
    )
    def populate_dropdown_on_upload(upload_status):
        """Populate dropdown when files are uploaded."""
        if not upload_status:
            return [], None
        
        # Default to UV-VIS tab (most common)
        tab_value = "uvvis_csv"
        files = data_manager.get_loaded_files()
        matching_files = []
        
        for fname in files:
            fdata = data_manager.get_file_data(fname)
            if not fdata:
                continue
                
            if fdata.get("type") == tab_value:
                wells_info = f" ({fdata['metadata'].get('filled_well_count', '?')} wells)"
                matching_files.append({"label": f"📊 {fname}{wells_info}", "value": fname})
                filled_wells = fdata["metadata"].get("filled_wells", [])[:10]
                for well in filled_wells:
                    matching_files.append({"label": f"  └─ 🧪 Well {well}", "value": f"{fname}|{well}"})
        
        # If no UV-VIS files, try other types
        if not matching_files:
            for fname in files:
                fdata = data_manager.get_file_data(fname)
                if not fdata:
                    continue
                if fdata.get("type") in ["chromatogram", "chromeleon_bundle"]:
                    display_name = fname.replace("_UV_VIS_1.txt", "")
                    matching_files.append({"label": f"📈 {display_name}", "value": fname})
                    break
                elif fdata.get("type") == "lcms_bundle":
                    matching_files.append({"label": f"📦 {fname.replace('_LCMS_BUNDLE', '')}", "value": fname})
                    break
        
        default_value = matching_files[0]["value"] if matching_files else None
        return matching_files, default_value

    # Handle pill selection and file type switching

    # 1. PILL SWITCH CALLBACK - Master control that overrides tree selection
    @app.callback(
        [Output("file-selector", "options"),
        Output("file-selector", "value"),
        Output("pill-uvvis_csv", "className"),
        Output("pill-chromatogram", "className"), 
        Output("pill-lcms_bundle", "className"),
        Output("pill-spectra", "className"),
        Output("pill-uvvis_csv", "style"),
        Output("pill-chromatogram", "style"), 
        Output("pill-lcms_bundle", "style"),
        Output("pill-spectra", "style"),
        Output("selected-layer", "data", allow_duplicate=True)],  # ADD: Override tree selection
        [Input("pill-uvvis_csv", "n_clicks"),
        Input("pill-chromatogram", "n_clicks"),
        Input("pill-lcms_bundle", "n_clicks"), 
        Input("pill-spectra", "n_clicks"),
        Input("file-list", "children"),
        Input("upload-status", "children")],
        [State("selected-layer", "data")],  # ADD: Current tree selection
        prevent_initial_call=True
    )
    def handle_pills_and_files(uv_clicks, chrom_clicks, lcms_clicks, spec_clicks, file_list, upload_status, current_selection):
        """Handle pill selection as master switches that override tree selection."""
        
        from dash import callback_context
        
        ctx = callback_context
        triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        
        # Check what file types are available
        available_types = set()
        latest_file_type = None
        files = data_manager.get_loaded_files()
        
        # Group files by type and find latest for each type
        files_by_type = {
            "uvvis_csv": [],
            "chromatogram": [],
            "lcms_bundle": [],
            "spectra": []
        }
        
        for fname in files:
            fdata = data_manager.get_file_data(fname)
            if fdata:
                file_type = fdata.get("type")
                if file_type in ["chromatogram", "chromeleon_bundle"]:
                    available_types.add("chromatogram")
                    files_by_type["chromatogram"].append(fname)
                else:
                    available_types.add(file_type)
                    if file_type in files_by_type:
                        files_by_type[file_type].append(fname)
        
        # Determine active tab and target selection
        pill_clicked = False
        if triggered_id and triggered_id.startswith('pill-'):
            pill_clicked = True
            tab_value = triggered_id.replace('pill-', '')
            print(f"[PILL DEBUG] Pill clicked: {tab_value}")
            
            # Find the latest file of the clicked type to override tree selection
            target_files = files_by_type.get(tab_value, [])
            if target_files:
                # Use the last (newest) file of this type
                new_tree_selection = target_files[-1]
                print(f"[PILL DEBUG] Switching tree to: {new_tree_selection}")
            else:
                new_tree_selection = current_selection
        else:
            # Not a pill click - determine tab from upload or current selection
            if upload_status and len(upload_status) > 0:
                # Auto-select based on latest upload
                for msg in reversed(upload_status):
                    if hasattr(msg, 'children') and 'uvvis_csv' in str(msg.children):
                        latest_file_type = "uvvis_csv"
                        break
                    elif hasattr(msg, 'children') and ('LC-MS bundle' in str(msg.children) or 'lcms_bundle' in str(msg.children)):
                        latest_file_type = "lcms_bundle"
                        break
                    elif hasattr(msg, 'children') and ('chromeleon_bundle' in str(msg.children) or 'chromatogram' in str(msg.children)):
                        latest_file_type = "chromatogram"
                        break
            
            if not latest_file_type and files:
                last_file = files[-1]
                fdata = data_manager.get_file_data(last_file)
                if fdata:
                    file_type = fdata.get("type")
                    if file_type in ["chromatogram", "chromeleon_bundle"]:
                        latest_file_type = "chromatogram"
                    else:
                        latest_file_type = file_type
            
            tab_value = latest_file_type if latest_file_type in available_types else (
                "uvvis_csv" if "uvvis_csv" in available_types else 
                list(available_types)[0] if available_types else "uvvis_csv"
            )
            
            # If upload triggered, auto-select the newest file
            if triggered_id == "upload-status" and files:
                new_tree_selection = files[-1]  # Latest uploaded file
                print(f"[PILL DEBUG] Upload triggered, auto-selecting: {new_tree_selection}")
            else:
                new_tree_selection = current_selection
        
        # Update pill styles (show/hide)
        pill_styles = {
            "uvvis_csv": {"display": "flex"} if "uvvis_csv" in available_types else {"display": "none"},
            "chromatogram": {"display": "flex"} if "chromatogram" in available_types else {"display": "none"},
            "lcms_bundle": {"display": "flex"} if "lcms_bundle" in available_types else {"display": "none"},
            "spectra": {"display": "flex"} if "spectra" in available_types else {"display": "none"}
        }
        
        # Update pill classes (active state)
        pill_classes = {
            "uvvis_csv": "nav-pill active" if tab_value == "uvvis_csv" else "nav-pill",
            "chromatogram": "nav-pill active" if tab_value == "chromatogram" else "nav-pill",
            "lcms_bundle": "nav-pill active" if tab_value == "lcms_bundle" else "nav-pill",
            "spectra": "nav-pill active" if tab_value == "spectra" else "nav-pill"
        }
        
        # Get matching files for dropdown
        matching_files = []
        for fname in files:
            fdata = data_manager.get_file_data(fname)
            if not fdata:
                continue
                
            # Handle chromatography types
            if tab_value == "chromatogram" and fdata.get("type") not in ["chromatogram", "chromeleon_bundle"]:
                continue
            elif tab_value != "chromatogram" and fdata.get("type") != tab_value:
                continue
                
            # Build options based on file type
            if tab_value == "uvvis_csv":
                wells_info = f" ({fdata['metadata'].get('filled_well_count', '?')} wells)"
                matching_files.append({"label": f"📊 {fname}{wells_info}", "value": fname})
                filled_wells = fdata["metadata"].get("filled_wells", [])[:10]
                for well in filled_wells:
                    matching_files.append({"label": f"  └─ 🧪 Well {well}", "value": f"{fname}|{well}"})
            
            elif tab_value == "chromatogram":
                if fdata.get("type") == "chromatogram":
                    wl_info = f" ({fdata['metadata'].get('wavelength', '?')} nm)" if fdata['metadata'].get('wavelength') else ""
                    matching_files.append({"label": f"📈 {fname}{wl_info}", "value": fname})
                elif fdata.get("type") == "chromeleon_bundle":
                    display_name = fname.replace("_UV_VIS_1.txt", "")
                    matching_files.append({"label": f"📈 {display_name}", "value": fname})
            
            elif tab_value == "lcms_bundle":
                bundle_data = fdata.get("bundle_data", {})
                matching_files.append({"label": f"📦 {fname.replace('_LCMS_BUNDLE', '')}", "value": fname})
                if bundle_data.get('ms_positive'):
                    matching_files.append({"label": f"  └─ 🔬 MS+", "value": f"{fname}|ms_positive"})
                if bundle_data.get('ms_negative'):
                    matching_files.append({"label": f"  └─ 🔬 MS-", "value": f"{fname}|ms_negative"})
                if bundle_data.get('vwd_a'):
                    wl = bundle_data['vwd_a']['metadata'].get('wavelength', '?')
                    matching_files.append({"label": f"  └─ 📊 UV-A ({wl} nm)", "value": f"{fname}|vwd_a"})
                if bundle_data.get('vwd_b'):
                    wl = bundle_data['vwd_b']['metadata'].get('wavelength', '?')
                    matching_files.append({"label": f"  └─ 📊 UV-B ({wl} nm)", "value": f"{fname}|vwd_b"})
        
        if matching_files:
            if tab_value == "lcms_bundle":
                default_value = next(
                    (item["value"] for item in matching_files if "|" in item["value"]), 
                    matching_files[0]["value"]
                )
            else:
                default_value = matching_files[0]["value"]
        else:
            default_value = None
        
        return (matching_files, default_value,
                pill_classes["uvvis_csv"], pill_classes["chromatogram"],
                pill_classes["lcms_bundle"], pill_classes["spectra"],
                pill_styles["uvvis_csv"], pill_styles["chromatogram"],
                pill_styles["lcms_bundle"], pill_styles["spectra"],
                new_tree_selection)


    # 2. TREE-TO-PILL SYNC CALLBACK - Updates pills when tree selection changes
    @app.callback(
        [Output("pill-uvvis_csv", "className", allow_duplicate=True),
        Output("pill-chromatogram", "className", allow_duplicate=True), 
        Output("pill-lcms_bundle", "className", allow_duplicate=True),
        Output("pill-spectra", "className", allow_duplicate=True)],

        Input("selected-layer", "data"),
        [State("pill-uvvis_csv", "style"),
        State("pill-chromatogram", "style"),
        State("pill-lcms_bundle", "style"),
        State("pill-spectra", "style")],
        prevent_initial_call=True
    )
    def sync_pills_to_tree_selection(selected_layer, uv_style, chrom_style, lcms_style, spec_style):
        """Update pill states when tree selection changes (but don't override tree)."""
        if not selected_layer:
            raise PreventUpdate
        
        # Extract filename and get file type
        filename = selected_layer.split("|")[0]
        file_data = data_manager.get_file_data(filename)
        
        if not file_data:
            raise PreventUpdate
        
        file_type = file_data.get("type")
        
        # Only update if the pill is visible (style has display: flex)
        pill_classes = {
            "uvvis_csv": "nav-pill",
            "chromatogram": "nav-pill",
            "lcms_bundle": "nav-pill", 
            "spectra": "nav-pill"
        }
        
        # Determine which tab should be active and make it active only if visible
        if file_type == "uvvis_csv" and uv_style.get("display") != "none":
            pill_classes["uvvis_csv"] = "nav-pill active"
        elif file_type in ["chromatogram", "chromeleon_bundle"] and chrom_style.get("display") != "none":
            pill_classes["chromatogram"] = "nav-pill active"
        elif file_type == "lcms_bundle" and lcms_style.get("display") != "none":
            pill_classes["lcms_bundle"] = "nav-pill active"
        elif file_type == "spectra" and spec_style.get("display") != "none":
            pill_classes["spectra"] = "nav-pill active"
        
        print(f"[PILL SYNC] Tree selected {file_type}, updating pills: {pill_classes}")
        
        return (pill_classes["uvvis_csv"], pill_classes["chromatogram"],
                pill_classes["lcms_bundle"], pill_classes["spectra"])







    # Replace the main callback in your viz_callbacks.py with this updated version:



    # Replace your entire main callback in viz_callbacks.py with this:

    @app.callback(
        [Output('ms-plot', 'figure'),
        Output('uv-chromatogram-plot', 'figure'), 
        Output('uvvis-plate-plot', 'figure'),
        Output('spectra-plot', 'figure'),
        Output('ms-plot', 'style'),
        Output('uv-chromatogram-plot', 'style'),
        Output('uvvis-plate-plot', 'style'), 
        Output('spectra-plot', 'style')],
        [Input('file-selector', 'value'),
        Input('visibility-state', 'data'),
        Input('selected-layer', 'data'),
        # PLOT SETTINGS INPUTS
        Input('line-thickness-slider', 'value'),
        Input('plot-layout-options', 'value'),
        Input('grid-options', 'value'),
        Input('x-min-input', 'value'),
        Input('x-max-input', 'value'),
        Input('y-min-input', 'value'),
        Input('y-max-input', 'value'),
        Input('x-axis-label', 'value'),
        Input('y-axis-label', 'value')]
    )
    def update_specialized_plots(selected_value, visibility_state, selected_layer,
                                # Plot settings parameters
                                line_thickness, layout_options, grid_options,
                                x_min, x_max, y_min, y_max, x_label, y_label):


        """Update plots based on dropdown, visibility, AND tree selection with plot settings."""
        
        # Import plot settings functions
        from callbacks.plot_settings_callbacks import (
            get_plot_settings_from_inputs, apply_plot_settings, 
            create_separate_plots, prepare_chromatogram_data_for_plotting
        )
        
        # Get plot settings
        line_width, plot_options, axis_range, axis_labels = get_plot_settings_from_inputs(
            line_thickness, layout_options, grid_options, 
            x_min, x_max, y_min, y_max, x_label, y_label
        )
        
        def is_visible(item_id):
            if not visibility_state:
                return True
            
            # Check if item itself is visible
            if not visibility_state.get(item_id, True):
                return False
            
            # Also check if parent bundle is visible (for child items)
            if "|" in item_id:
                parent_id = item_id.split("|")[0]
                if not visibility_state.get(parent_id, True):
                    return False
            
            return True

        empty_fig = go.Figure().add_annotation(
            text="No data available", xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=14, font_color="#999"
        )
        
        # Initialize all plots
        ms_fig = empty_fig
        uv_chrom_fig = empty_fig  
        uvvis_fig = empty_fig
        spectra_fig = empty_fig
        
        files = data_manager.get_loaded_files()
        if not files:
            hidden = {"display": "none"}
            return ms_fig, uv_chrom_fig, uvvis_fig, spectra_fig, hidden, hidden, hidden, hidden
        
        # PRIORITY 1: Use tree selection if available
        active_selection = selected_layer if selected_layer else selected_value
        

        print(f"[DEBUG] Active selection: {active_selection}")
        print(f"[DEBUG] Is visible: {is_visible(active_selection) if active_selection else 'None'}")

        # FIX: If active selection is HIDDEN, show empty plots
        if active_selection and not is_visible(active_selection):
            print(f"[DEBUG] Selection {active_selection} is hidden - showing empty plots")
            return empty_fig, empty_fig, empty_fig, empty_fig, \
                {"display": "none"}, {"display": "none"}, {"display": "none"}, {"display": "none"}

        # Handle selection and populate appropriate plots
        if active_selection and '|' in active_selection:
            filename, component = active_selection.split('|', 1)
            
            if is_visible(active_selection):
                file_data = data_manager.get_file_data(filename)
                
                if file_data and file_data['type'] == 'lcms_bundle':
                    bundle_data = file_data.get("bundle_data", {})
                    component_data = bundle_data.get(component)

                    if component_data:
                        if component.startswith('ms_'):
                            ms_fig = create_tic_plot({
                                'data': component_data['data'],
                                'metadata': component_data['metadata'],
                                'type': 'lcms_cdf'
                            })
                            # Apply plot settings to MS plot
                            ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                            
                        elif component.startswith('vwd_'):
                            # Check if separate plots is enabled for chromatograms
                            if plot_options.get('separate_plots', False):
                                # Prepare data for separate plots
                                chrom_data = prepare_chromatogram_data_for_plotting(component_data)
                                if chrom_data:
                                    uv_chrom_fig = create_separate_plots(chrom_data, plot_options, line_width, axis_range, axis_labels)
                                else:
                                    uv_chrom_fig = create_lcms_uv_plot(component_data)
                                    uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                            else:
                                uv_chrom_fig = create_lcms_uv_plot(component_data)
                                uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                
                elif file_data and file_data['type'] == 'uvvis_csv':
                    uvvis_fig = create_single_well_plot(file_data, component)
                    uvvis_fig = apply_plot_settings(uvvis_fig, plot_options, line_width, axis_range, axis_labels)
        
        elif active_selection:
            if is_visible(active_selection):
                file_data = data_manager.get_file_data(active_selection)
                if file_data:
                    if file_data['type'] == 'uvvis_csv':
                        uvvis_fig = create_uvvis_plot_with_visibility(file_data, visibility_state, max_wells=5)
                        uvvis_fig = apply_plot_settings(uvvis_fig, plot_options, line_width, axis_range, axis_labels)
                        
                    elif file_data['type'] == 'lcms_cdf':
                        ms_fig = create_tic_plot(file_data)
                        ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                        
                    elif file_data['type'] in ['chromatogram', 'chromeleon_bundle']:
                        # NEW: Create multi-file chromatogram plot
                        uv_chrom_fig = create_multi_chromatogram_plot_safe(
                            files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels
                        )
                            
                    elif file_data['type'] == 'lcms_bundle':
                        # When clicking bundle itself, show first available from each type
                        bundle_data = file_data.get("bundle_data", {})
                        
                        # Get first visible MS
                        for comp in ['ms_positive', 'ms_negative']:
                            comp_id = f"{active_selection}|{comp}"
                            if bundle_data.get(comp) and is_visible(comp_id):
                                ms_fig = create_tic_plot({
                                    'data': bundle_data[comp]['data'],
                                    'metadata': bundle_data[comp]['metadata'],
                                    'type': 'lcms_cdf'
                                })
                                ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                                break
                        
                        # Get first visible UV
                        for comp in ['vwd_a', 'vwd_b']:
                            comp_id = f"{active_selection}|{comp}"
                            if bundle_data.get(comp) and is_visible(comp_id):
                                if plot_options.get('separate_plots', False):
                                    # Prepare data for separate plots
                                    chrom_data = prepare_chromatogram_data_for_plotting(bundle_data[comp])
                                    if chrom_data:
                                        uv_chrom_fig = create_separate_plots(chrom_data, plot_options, line_width, axis_range, axis_labels)
                                    else:
                                        uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp])
                                        uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                                else:
                                    uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp])
                                    uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                                break

        # Auto-populate with latest data if plots are empty (MODIFIED FOR MULTI-FILE)
        if ms_fig == empty_fig:
            for fname in reversed(files):
                if not is_visible(fname):
                    continue
                    
                file_data = data_manager.get_file_data(fname)
                if file_data and file_data['type'] in ['lcms_bundle', 'lcms_cdf']:
                    if file_data['type'] == 'lcms_bundle':
                        bundle_data = file_data.get("bundle_data", {})
                        for comp in ['ms_positive', 'ms_negative']:
                            comp_id = f"{fname}|{comp}"
                            if bundle_data.get(comp) and is_visible(comp_id):
                                ms_fig = create_tic_plot({
                                    'data': bundle_data[comp]['data'],
                                    'metadata': bundle_data[comp]['metadata'],
                                    'type': 'lcms_cdf'
                                })
                                ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                                break
                    else:
                        ms_fig = create_tic_plot(file_data)
                        ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                    break

        if uv_chrom_fig == empty_fig:
            # NEW: Auto-populate with multi-file chromatogram plot
            uv_chrom_fig = create_multi_chromatogram_plot_safe(
                files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels
            )

        if uvvis_fig == empty_fig:
            for fname in reversed(files):
                if not is_visible(fname):
                    continue
                    
                file_data = data_manager.get_file_data(fname)
                if file_data and file_data['type'] == 'uvvis_csv':
                    uvvis_fig = create_uvvis_plot_with_visibility(file_data, visibility_state, max_wells=5)
                    uvvis_fig = apply_plot_settings(uvvis_fig, plot_options, line_width, axis_range, axis_labels)
                    break
        
        # Rest of your existing logic for showing/hiding plots remains the same...
        # Show plots based on selected data type - keep same bundle together
        if active_selection and '|' in active_selection:
            filename, component = active_selection.split('|', 1)
            file_data = data_manager.get_file_data(filename)
            
            if file_data and file_data['type'] == 'lcms_bundle':
                # LC-MS Bundle: Always show both plots from SAME bundle
                bundle_data = file_data.get("bundle_data", {})
                
                # Determine selected component type
                selected_is_ms = component.startswith('ms_')
                selected_is_uv = component.startswith('vwd_')
                
                # Update MS plot with visibility check
                if selected_is_ms:
                    if is_visible(active_selection):
                        component_data = bundle_data.get(component)
                        if component_data:
                            ms_fig = create_tic_plot({
                                'data': component_data['data'],
                                'metadata': component_data['metadata'],
                                'type': 'lcms_cdf'
                            })
                            ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                else:
                    # Use first available visible MS from this bundle
                    for comp in ['ms_positive', 'ms_negative']:
                        comp_id = f"{filename}|{comp}"
                        if bundle_data.get(comp) and is_visible(comp_id):
                            ms_fig = create_tic_plot({
                                'data': bundle_data[comp]['data'],
                                'metadata': bundle_data[comp]['metadata'],
                                'type': 'lcms_cdf'
                            })
                            ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                            break
                
                # Update UV plot with visibility check
                if selected_is_uv:
                    if is_visible(active_selection):
                        component_data = bundle_data.get(component)
                        if component_data:
                            if plot_options.get('separate_plots', False):
                                chrom_data = prepare_chromatogram_data_for_plotting(component_data)
                                if chrom_data:
                                    uv_chrom_fig = create_separate_plots(chrom_data, plot_options, line_width, axis_range, axis_labels)
                                else:
                                    uv_chrom_fig = create_lcms_uv_plot(component_data)
                                    uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                            else:
                                uv_chrom_fig = create_lcms_uv_plot(component_data)
                                uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                else:
                    # Use first available visible UV from this bundle
                    for comp in ['vwd_a', 'vwd_b']:
                        comp_id = f"{filename}|{comp}"
                        if bundle_data.get(comp) and is_visible(comp_id):
                            if plot_options.get('separate_plots', False):
                                chrom_data = prepare_chromatogram_data_for_plotting(bundle_data[comp])
                                if chrom_data:
                                    uv_chrom_fig = create_separate_plots(chrom_data, plot_options, line_width, axis_range, axis_labels)
                                else:
                                    uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp])
                                    uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                            else:
                                uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp])
                                uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                            break
                
                # Check if we should hide entire plot sections
                ms_should_show = ms_fig != empty_fig
                uv_should_show = uv_chrom_fig != empty_fig

                # For bundles, hide plot if ALL components of that type are hidden
                ms_components = ['ms_positive', 'ms_negative']
                ms_visible_count = sum(1 for comp in ms_components 
                                    if bundle_data.get(comp) and is_visible(f"{filename}|{comp}"))
                if ms_visible_count == 0 and any(bundle_data.get(comp) for comp in ms_components):
                    ms_should_show = False
                
                uv_components = ['vwd_a', 'vwd_b']
                uv_visible_count = sum(1 for comp in uv_components 
                                    if bundle_data.get(comp) and is_visible(f"{filename}|{comp}"))
                if uv_visible_count == 0 and any(bundle_data.get(comp) for comp in uv_components):
                    uv_should_show = False

                return ms_fig, uv_chrom_fig, empty_fig, empty_fig, \
                    {"display": "block" if ms_should_show else "none"}, \
                    {"display": "block" if uv_should_show else "none"}, \
                    {"display": "none"}, {"display": "none"}

            elif file_data and file_data['type'] == 'uvvis_csv':
                # UV-Vis: Show only plate plot, hide MS
                if not is_visible(active_selection):
                    uvvis_fig = empty_fig
                return empty_fig, empty_fig, uvvis_fig, empty_fig, {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}

        elif active_selection:
            file_data = data_manager.get_file_data(active_selection)
            if file_data:
                if file_data['type'] == 'uvvis_csv':
                    # UV-Vis: Show only plate plot, hide MS
                    if not is_visible(active_selection):
                        uvvis_fig = empty_fig
                    return empty_fig, empty_fig, uvvis_fig, empty_fig, {"display": "none"}, {"display": "none"}, {"display": "block"}, {"display": "none"}
                elif file_data['type'] == 'lcms_cdf':
                    # Standalone MS: Show only MS plot, hide others
                    if not is_visible(active_selection):
                        ms_fig = empty_fig
                    return ms_fig, empty_fig, empty_fig, empty_fig, {"display": "block"}, {"display": "none"}, {"display": "none"}, {"display": "none"}
                elif file_data['type'] in ['chromatogram', 'chromeleon_bundle']:
                    # HPLC: Show only UV chromatogram, HIDE MS
                    if not is_visible(active_selection):
                        uv_chrom_fig = empty_fig
                    return empty_fig, uv_chrom_fig, empty_fig, empty_fig, {"display": "none"}, {"display": "block"}, {"display": "none"}, {"display": "none"}
                elif file_data['type'] == 'lcms_bundle':
                    return ms_fig, uv_chrom_fig, empty_fig, empty_fig, {"display": "block"}, {"display": "block"}, {"display": "none"}, {"display": "none"}

        # Default when nothing selected: show latest available data
        if ms_fig != empty_fig and uv_chrom_fig != empty_fig:
            # If we have both, check if they're from same LC-MS bundle
            for fname in reversed(files):
                if not is_visible(fname):
                    continue
                file_data = data_manager.get_file_data(fname)
                if file_data and file_data['type'] == 'lcms_bundle':
                    # Show both from latest LC-MS bundle
                    return ms_fig, uv_chrom_fig, empty_fig, empty_fig, {"display": "block"}, {"display": "block"}, {"display": "none"}, {"display": "none"}

        # Show individual plots if no bundle context
        ms_style = {"display": "block"} if ms_fig != empty_fig else {"display": "none"}
        uv_chrom_style = {"display": "block"} if uv_chrom_fig != empty_fig else {"display": "none"}
        uvvis_style = {"display": "block"} if uvvis_fig != empty_fig else {"display": "none"}
        spectra_style = {"display": "none"}

        return ms_fig, uv_chrom_fig, uvvis_fig, spectra_fig, ms_style, uv_chrom_style, uvvis_style, spectra_style





def extract_clean_sample_name(filename):
    """Extract clean sample name from filename."""
    import re
    
    # Remove file extension
    name = filename.replace('_UV_VIS_1.txt', '').replace('.txt', '')
    
    # Try to extract pattern like "1 - 15", "1 - 30", etc.
    pattern = r'(\d+\s*-\s*\d+)'
    match = re.search(pattern, name)
    if match:
        return match.group(1)
    
    # Try to extract pattern like "15min", "30min", etc.
    pattern = r'(\d+min)'
    match = re.search(pattern, name)
    if match:
        return match.group(1)
    
    # Try to extract just numbers at the end
    pattern = r'(\d+)$'
    match = re.search(pattern, name)
    if match:
        return match.group(1)
    
    # If no pattern found, try to remove common prefixes
    # Remove everything before the last underscore if it contains sample info
    if '_' in name:
        parts = name.split('_')
        # Look for the part that seems like sample info
        for part in reversed(parts):
            if any(char.isdigit() for char in part) and len(part) < 20:
                return part
    
    # Fallback: return the filename without extension
    return name

def is_visible_simple(item_id, visibility_state):
    """Simple visibility check."""
    if not visibility_state:
        return True
    return visibility_state.get(item_id, True)

def register_plotly_resize_callbacks(app):
    """Don't interfere with the existing resize.js functionality."""
    
    # SIMPLE: Don't add any callbacks that might interfere with resize.js
    # Your resize.js should handle all the resize functionality
    pass

def debug_peak_keys(data_manager):
    """Debug function to find where detected peaks are actually stored"""
    
    try:
        from utils.peak_integration import peak_manager
        
        print(f"\n=== PEAK KEY DEBUG ===")
        print(f"All keys in peak_manager.detected_peaks: {list(peak_manager.detected_peaks.keys())}")
        
        # Check each key and show what's in it
        for key, peaks in peak_manager.detected_peaks.items():
            print(f"Key: '{key}' -> {len(peaks)} peaks")
            for i, peak in enumerate(peaks[:2]):  # Show first 2 peaks
                print(f"  Peak {i+1}: RT={peak.get('retention_time', 'N/A')}, Area={peak.get('area', 'N/A')}")
        
        # Check loaded files
        files = data_manager.get_loaded_files()
        print(f"Loaded files: {files}")
        
        # Check if there's a pattern we're missing
        filename = files[0] if files else None
        if filename:
            print(f"Looking for peaks for file: '{filename}'")
            
            # Try various key combinations
            possible_keys = [
                filename,
                filename.replace('\\', '/'),
                filename.split('/')[-1] if '/' in filename else filename,
                filename.split('\\')[-1] if '\\' in filename else filename,
                filename.replace('_UV_VIS_1.txt', ''),
                filename.replace('.txt', ''),
                filename.replace('_UV_VIS_1.txt', '').replace('.txt', ''),
                # Try without extension
                filename.rsplit('.', 1)[0] if '.' in filename else filename,
                # Try base name patterns
                filename.split('_')[0] if '_' in filename else filename,
            ]
            
            print(f"Trying these keys: {possible_keys}")
            
            found_key = None
            for key in possible_keys:
                if key in peak_manager.detected_peaks and peak_manager.detected_peaks[key]:
                    found_key = key
                    peaks = peak_manager.detected_peaks[key]
                    print(f"✅ FOUND PEAKS with key: '{key}' -> {len(peaks)} peaks")
                    break
            
            if not found_key:
                print("❌ No peaks found with any key variation")
                
                # Maybe check if the detected peaks are stored under a different attribute
                print("Checking peak_manager attributes:")
                for attr in dir(peak_manager):
                    if 'peak' in attr.lower() and not attr.startswith('_'):
                        value = getattr(peak_manager, attr)
                        if hasattr(value, '__len__') and len(value) > 0:
                            print(f"  {attr}: {type(value)} with {len(value)} items")
        
        print("=== END PEAK KEY DEBUG ===\n")
        
    except ImportError as e:
        print(f"❌ Peak integration module not available: {e}")
    except Exception as e:
        print(f"❌ Error in peak key debug: {e}")

def add_peak_areas_to_figure(fig, filename, data_manager):
    """Add filled area under detected/integrated peaks to the figure (full area under curve, not just trapezoid)"""

    try:
        from utils.peak_integration import peak_manager
        import numpy as np
        import pandas as pd
        import plotly.graph_objects as go

        print(f"[PEAK DEBUG] Starting peak visualization for: {filename}")

        file_data = data_manager.get_file_data(filename)
        if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
            print(f"[PEAK DEBUG] Skipping {filename} - not a chromatogram file")
            return fig

        chromatogram_data = file_data.get('data')
        if chromatogram_data is None or chromatogram_data.empty:
            print(f"[PEAK DEBUG] No chromatogram data for {filename}")
            return fig

        # Find time and intensity columns
        time_col = 'Time (min)'
        intensity_cols = [col for col in chromatogram_data.columns if col != time_col]
        if not intensity_cols:
            print(f"[PEAK DEBUG] No intensity columns found in {filename}")
            return fig

        intensity_col = intensity_cols[0]
        x_data = chromatogram_data[time_col].values
        y_data = chromatogram_data[intensity_col].values

        print(f"[PEAK DEBUG] Data shape: x={len(x_data)}, y={len(y_data)}")
        peaks_added = 0

        # === 1. Integration Table Peaks (imported) ===
        integration_table = file_data.get('integration_table')
        if integration_table is not None and not integration_table.empty:
            print(f"[PEAK DEBUG] Processing integration table with {len(integration_table)} rows")

            for i, row in integration_table.iterrows():
                try:
                    peak_no = str(row.get('No.', '')).strip().lower()
                    if peak_no in ['total', 'n.a.', ''] or 'total' in peak_no:
                        continue

                    rt = float(str(row.get('Retention Time', 0)).replace(',', '.'))


                    # 1- pull limits from Chromeleon table
                    raw_start = row.get('Start Time')
                    raw_end   = row.get('End Time')

                    if raw_start not in [None, '', 'n.a.', 'N/A'] and raw_end not in [None, '', 'n.a.', 'N/A']:
                        # valid numeric strings → float
                        start_time = float(str(raw_start).replace(',', '.'))
                        end_time   = float(str(raw_end).replace(',',  '.'))

                        # bad export?  keep them sane
                        if end_time <= start_time:   # fallback if wrong order
                            start_time, end_time = end_time, start_time
                    else:
                        # 2- fallback: width(50 %) or default
                        width = 0.15
                        w50 = row.get('Width (50%)')
                        if w50 not in [None, '', 'n.a.', 'N/A']:
                            try:
                                width = float(str(w50).replace(',', '.')) * 3   # enlarge a bit
                            except Exception:
                                width = 0.15





                    start_time = rt - width / 2
                    end_time = rt + width / 2

                    start_idx = np.abs(x_data - start_time).argmin()
                    end_idx = np.abs(x_data - end_time).argmin()

                    if start_idx >= end_idx:
                        center_idx = np.abs(x_data - rt).argmin()
                        start_idx = max(0, center_idx - 20)
                        end_idx = min(len(x_data)-1, center_idx + 20)

                    px = x_data[start_idx:end_idx+1]
                    py = y_data[start_idx:end_idx+1]

                    if len(px) < 2:
                        continue

                    # --- FILL TO BASELINE (full area under curve) ---
                    fill_x = np.concatenate([px, [px[-1], px[0]]])
                    fill_y = np.concatenate([py, [0, 0]])

                    fig.add_trace(go.Scatter(
                        x=fill_x,
                        y=fill_y,
                        fill='toself',
                        fillcolor='rgba(0,255,0,0.3)',
                        line=dict(width=0),
                        name=f'Imported Peak {peak_no}',
                        showlegend=False,
                        legendgroup='imported_peaks',
                        hovertemplate=f'<b>Imported Peak {peak_no}</b><br>RT: {rt:.3f} min<br>Area: {area_str}<extra></extra>',
                        mode='lines'
                    ))
                    peaks_added += 1
                    print(f"[PEAK DEBUG] ✅ Added imported peak {peak_no} at RT={rt:.3f}")

                except Exception as e:
                    print(f"[PEAK DEBUG] ❌ Error with imported peak {i}: {e}")
                    continue
        else:
            print(f"[PEAK DEBUG] No integration table found")

        # === 2. DETECTED PEAKS ===
        print(f"[PEAK DEBUG] Searching for detected peaks...")

        # Try various key variations for detected peaks
        possible_keys = [
            filename,
            filename.replace('\\', '/'),
            filename.split('/')[-1] if '/' in filename else filename,
            filename.split('\\')[-1] if '\\' in filename else filename,
            filename.replace('_UV_VIS_1.txt', ''),
            filename.replace('.txt', ''),
            filename.replace('_UV_VIS_1.txt', '').replace('.txt', ''),
            filename.rsplit('.', 1)[0] if '.' in filename else filename,
        ]
        possible_keys = list(set([k for k in possible_keys if k]))

        detected_peaks = []
        matching_key = None

        for key in possible_keys:
            if key in peak_manager.detected_peaks and peak_manager.detected_peaks[key]:
                detected_peaks = peak_manager.detected_peaks[key]
                matching_key = key
                print(f"[PEAK DEBUG] ✅ FOUND detected peaks with key: '{key}' -> {len(detected_peaks)} peaks")
                break

        # --- Add detected peaks as full-area polygons ---
        if detected_peaks:
            for i, peak in enumerate(detected_peaks):
                try:
                    rt = float(peak.get('Retention Time', 0))
                    start_idx = peak.get('start_idx')
                    end_idx = peak.get('end_idx')

                    if start_idx is None or end_idx is None:
                        start = float(peak.get('Start Time', rt - 0.05))
                        end = float(peak.get('End Time', rt + 0.05))
                        start_idx = np.abs(x_data - start).argmin()
                        end_idx = np.abs(x_data - end).argmin()

                    px = x_data[start_idx:end_idx+1]
                    py = y_data[start_idx:end_idx+1]
                    if len(px) < 2:
                        continue

                    # --- FILL TO BASELINE (full area under curve) ---
                    fill_x = np.concatenate([px, [px[-1], px[0]]])
                    fill_y = np.concatenate([py, [0, 0]])

                    actual_area = peak.get('Area', 0)

                    fig.add_trace(go.Scatter(
                        x=fill_x,
                        y=fill_y,
                        fill='toself',
                        fillcolor='rgba(255,165,0,0.3)',
                        line=dict(width=0),
                        name=f"Peak {peak.get('No.', i+1)}",
                        showlegend=False,
                        legendgroup='detected_peaks',
                        hovertemplate=f'<b>Peak {peak.get("No.", i+1)}</b><br>RT: {rt:.3f} min<br>Area: {actual_area:.2f}<extra></extra>',
                        mode='lines'
                    ))
                    peaks_added += 1
                    print(f"[PEAK VIZ] Added detected peak {peak.get('No.', i+1)} at RT={rt:.3f}, Area={actual_area:.2f}")

                except Exception as e:
                    print(f"[PEAK DEBUG] ❌ Error with detected peak {i}: {e}")
                    continue
        else:
            print(f"[PEAK DEBUG] ❌ No detected peaks found")

        print(f"[PEAK DEBUG] ✅ Total peaks added to plot: {peaks_added}")

    except Exception as e:
        print(f"[PEAK DEBUG] ❌ Major error: {e}")
        import traceback
        print(f"[PEAK DEBUG] Traceback: {traceback.format_exc()}")

    return fig


def create_multi_chromatogram_plot_safe(files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels):
    """
    COMPLETE REPLACEMENT - Create multi-chromatogram plots with working peak visualization
    """
    
    # Get all visible chromatogram files
    visible_chrom_files = []
    for filename in files:
        if not is_visible_simple(filename, visibility_state):
            continue
            
        file_data = data_manager.get_file_data(filename)
        if file_data and file_data.get('type') in ['chromatogram', 'chromeleon_bundle']:
            visible_chrom_files.append(filename)
    
    print(f"[MULTI-CHROM] Found {len(visible_chrom_files)} visible chromatogram files: {visible_chrom_files}")
    
    if not visible_chrom_files:
        return go.Figure().add_annotation(
            text="No visible chromatogram files", xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=14, font_color="#999"
        )
    
    # Check if separate plots is enabled
    if plot_options.get('separate_plots', False):
        return create_separate_chromatogram_subplots_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels)
    else:
        return create_overlay_chromatogram_plot_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels)

def create_separate_chromatogram_subplots_fixed(visible_files, data_manager, plot_options, line_width, axis_range, axis_labels):
    """
    COMPLETE REPLACEMENT - Create separate subplots with peak visualization
    """
    
    from plotly.subplots import make_subplots
    from plot.hplc import create_chromatogram_plot, create_chromeleon_bundle_plot
    
    n_plots = len(visible_files)
    if n_plots == 0:
        return go.Figure()
    
    # Create subplots
    fig = make_subplots(
        rows=n_plots, 
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[1] * n_plots
    )
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    # Check settings
    show_legend = plot_options.get('show_legend', True) if plot_options else True
    show_horizontal_grid = plot_options.get('horizontal_grid', False) if plot_options else False
    show_vertical_grid = plot_options.get('vertical_grid', False) if plot_options else False
    
    for i, filename in enumerate(visible_files):
        file_data = data_manager.get_file_data(filename)
        if not file_data:
            continue
        
        try:
            if file_data['type'] == 'chromatogram':
                temp_fig = create_chromatogram_plot(file_data)
            else:
                temp_fig = create_chromeleon_bundle_plot(file_data)
            
            if temp_fig and temp_fig.data:
                main_trace = temp_fig.data[0]
                
                clean_name = extract_clean_sample_name(filename)
                metadata = file_data.get('metadata', {})
                wavelength = metadata.get('wavelength') or metadata.get('Wavelength (nm)')
                
                if wavelength:
                    legend_name = f"{clean_name} (λ={wavelength}nm)"
                else:
                    legend_name = clean_name
                
                new_trace = go.Scatter(
                    x=main_trace.x,
                    y=main_trace.y,
                    mode='lines',
                    name=legend_name,
                    line=dict(width=line_width, color=colors[i % len(colors)]),
                    showlegend=False,
                    hovertemplate=f'<b>{clean_name}</b><br>' +
                                'RT: %{x:.2f} min<br>' +
                                'Signal: %{y:.1f} mAU<br>' +
                                '<extra></extra>'
                )
                fig.add_trace(new_trace, row=i+1, col=1)
                
                if show_legend:
                    subplot_height = 1.0 / n_plots
                    subplot_top = 1 - (i * subplot_height)
                    spacing_offset = 0.08 * (i / n_plots) if i > 0 else 0
                    legend_y = subplot_top - spacing_offset - 0.01
                    
                    fig.add_annotation(
                        text=f'<span style="color:{colors[i % len(colors)]}">{legend_name}</span>',
                        x=0.99,
                        y=legend_y,
                        xref="paper",
                        yref="paper",
                        xanchor="right",
                        yanchor="top",
                        showarrow=False,
                        bgcolor='rgba(255,255,255,0.95)',
                        bordercolor='rgba(0,0,0,0.2)',
                        borderwidth=1,
                        borderpad=4,
                        font=dict(size=10)
                    )
        
        except Exception as e:
            print(f"[ERROR] Failed to add {filename} to subplot: {e}")
            continue
    
    # Layout
    fig.update_layout(
        title_text=f"📈 Chromatograms - Separate Views ({n_plots} samples)",
        template='plotly_white',
        showlegend=False,
        uirevision='chromatogram_view'
    )
    
    # Get axis labels from user input or defaults
    x_label = axis_labels.get('x_label', 'Retention Time (min)') if axis_labels else 'Retention Time (min)'
    y_label = axis_labels.get('y_label', 'Signal Intensity (mAU)') if axis_labels else 'Signal Intensity (mAU)'
    
    # Calculate appropriate number of y-ticks based on subplot count
    if n_plots >= 4:
        nticks = 4
    elif n_plots == 3:
        nticks = 5
    else:
        nticks = 6
    
    # Apply consistent axis styling to ALL subplots
    for i in range(1, n_plots + 1):
        # X-axis - only label on bottom
        fig.update_xaxes(
            title=dict(text=x_label, font=dict(size=12)) if i == n_plots else None,
            linewidth=1,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=1,
            ticklen=5,
            showgrid=show_vertical_grid,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.3)',
            row=i, col=1
        )
        
        # Y-axis - FORCE consistent tick count on ALL subplots
        fig.update_yaxes(
            title="",  # No individual titles, use central label
            linewidth=1,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=1,
            ticklen=5,
            showgrid=show_horizontal_grid,
            gridwidth=1,
            gridcolor='rgba(128,128,128,0.3)',
            nticks=nticks,  # SAME tick count for ALL
            tickmode='auto',  # Let Plotly choose nice values
            row=i, col=1
        )
    
    # Central Y-axis label with consistent font
    fig.add_annotation(
        text=y_label,
        x=-0.05,
        y=0.5,
        xref="paper",
        yref="paper",
        textangle=-90,
        xanchor="center",
        yanchor="middle",
        showarrow=False,
        font=dict(size=12, color="black")
    )
    
    # Apply user axis ranges
    if axis_range and not axis_range.get('auto_range', True):
        for i in range(1, n_plots + 1):
            if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
                fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']], row=i, col=1)
            
            if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
                fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']], row=i, col=1)

    # Add peak areas to all subplots
    for filename in visible_files:
        print(f"[SEPARATE PLOTS] Adding peak areas for: {filename}")
        fig = add_peak_areas_to_figure(fig, filename, data_manager)
    
    return fig

def create_overlay_chromatogram_plot_fixed(visible_files, data_manager, plot_options, line_width, axis_range, axis_labels):
    """
    COMPLETE REPLACEMENT - Create overlay plot with peak visualization
    """
    
    fig = go.Figure()
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    show_legend = plot_options.get('show_legend', True) if plot_options else True
    show_horizontal_grid = plot_options.get('horizontal_grid', False) if plot_options else False
    show_vertical_grid = plot_options.get('vertical_grid', False) if plot_options else False
    
    for i, filename in enumerate(visible_files):
        file_data = data_manager.get_file_data(filename)
        if not file_data:
            continue
        
        try:
            if file_data['type'] == 'chromatogram':
                temp_fig = create_chromatogram_plot(file_data)
            else:
                temp_fig = create_chromeleon_bundle_plot(file_data)
            
            if temp_fig and temp_fig.data:
                main_trace = temp_fig.data[0]
                
                clean_name = extract_clean_sample_name(filename)
                metadata = file_data.get('metadata', {})
                wavelength = metadata.get('wavelength') or metadata.get('Wavelength (nm)')
                
                if wavelength:
                    legend_name = f"{clean_name} (λ={wavelength}nm)"
                else:
                    legend_name = clean_name
                
                new_trace = go.Scatter(
                    x=main_trace.x,
                    y=main_trace.y,
                    mode='lines',
                    name=legend_name,
                    line=dict(
                        width=line_width,
                        color=colors[i % len(colors)]
                    ),
                    showlegend=show_legend,
                    hovertemplate=f'<b>{clean_name}</b><br>' +
                                'RT: %{x:.2f} min<br>' +
                                'Signal: %{y:.1f} mAU<br>' +
                                '<extra></extra>'
                )
                fig.add_trace(new_trace)
        
        except Exception as e:
            print(f"[ERROR] Failed to add {filename}: {e}")
            continue
    
    # Get axis labels from user input
    x_label = axis_labels.get('x_label', 'Time (min)') if axis_labels else 'Time (min)'
    y_label = axis_labels.get('y_label', 'Signal Intensity') if axis_labels else 'Signal Intensity'
    
    # Layout
    fig.update_layout(
        title="Multi-Sample - HPLC Chromatograms",
        xaxis_title=x_label,
        yaxis_title=y_label,
        template='plotly_white',
        showlegend=show_legend,
        legend=dict(
            x=0.99,
            y=0.99,
            xanchor='right', 
            yanchor='top',
            bgcolor='rgba(255,255,255,0.95)',
            bordercolor='rgba(0,0,0,0.2)',
            borderwidth=1
        ) if show_legend else dict(),
        uirevision='chromatogram_view'
    )
    
    fig.update_xaxes(
        linewidth=1,
        linecolor='black',
        mirror=True,
        ticks='outside',
        tickwidth=1,
        ticklen=5,
        showgrid=show_vertical_grid,
        gridwidth=1,
        gridcolor='rgba(128,128,128,0.3)',
    )
    
    fig.update_yaxes(
        linewidth=1,
        linecolor='black',
        mirror=True,
        ticks='outside',
        tickwidth=1,
        ticklen=5,
        showgrid=show_horizontal_grid,
        gridwidth=1,
        gridcolor='rgba(128,128,128,0.3)',
    )
    
    # Apply user axis ranges
    if axis_range and not axis_range.get('auto_range', True):
        if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
            fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']])
        
        if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
            fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']])
    
    # Add peak areas
    for filename in visible_files:
        print(f"[OVERLAY] Adding peak areas for: {filename}")
        fig = add_peak_areas_to_figure(fig, filename, data_manager)
    
    return fig

def debug_peak_visualization(filename, data_manager):
    """
    COMPLETE REPLACEMENT - Debug function to check why peaks aren't showing up
    """
    
    print(f"\n=== DEBUGGING PEAK VISUALIZATION FOR {filename} ===")
    
    # 1. Check file data
    file_data = data_manager.get_file_data(filename)
    if not file_data:
        print("❌ No file data found")
        return
    
    print(f"✅ File type: {file_data.get('type')}")
    
    # 2. Check chromatogram data
    chromatogram_data = file_data.get('data')
    if chromatogram_data is None or chromatogram_data.empty:
        print("❌ No chromatogram data")
        return
    
    print(f"✅ Chromatogram shape: {chromatogram_data.shape}")
    print(f"✅ Columns: {list(chromatogram_data.columns)}")
    
    # Check for standard time/intensity columns
    time_col = 'Time (min)'
    intensity_cols = [col for col in chromatogram_data.columns if col != time_col]
    print(f"✅ Time column: {time_col}")
    print(f"✅ Intensity columns: {intensity_cols}")
    
    # 3. Check integration table (imported peaks)
    integration_table = file_data.get('integration_table')
    if integration_table is not None and not integration_table.empty:
        print(f"✅ Integration table found: {integration_table.shape}")
        print("📊 Integration table peaks:")
        for idx, row in integration_table.iterrows():
            rt = row.get('Retention Time', 'N/A')
            area = row.get('Area', 'N/A')
            height = row.get('Height', 'N/A')
            peak_no = row.get('No.', 'N/A')
            print(f"   Peak {peak_no}: RT={rt}, Area={area}, Height={height}")
    else:
        print("❌ No integration table found")
    
    # 4. Check detected peaks from peak manager
    try:
        from utils.peak_integration import peak_manager
        
        # Try different possible keys for the file
        possible_keys = [
            filename,
            filename.replace('\\', '/'),
            filename.split('/')[-1],
            filename.replace('_UV_VIS_1.txt', '').replace('.txt', ''),
        ]
        
        detected_peaks = []
        matching_key = None
        
        for key in possible_keys:
            if key in peak_manager.detected_peaks:
                detected_peaks = peak_manager.detected_peaks[key]
                matching_key = key
                break
        
        if detected_peaks:
            print(f"✅ Detected peaks found (key: {matching_key}): {len(detected_peaks)} peaks")
            for i, peak in enumerate(detected_peaks):
                rt = peak.get('retention_time', 'N/A')
                area = peak.get('area', 'N/A')
                print(f"   Detected Peak {i+1}: RT={rt}, Area={area}")
        else:
            print("❌ No detected peaks found")
            print(f"   Available keys in peak_manager: {list(peak_manager.detected_peaks.keys())}")
    
    except ImportError as e:
        print(f"❌ Peak integration module not available: {e}")
    
    # 5. Data range check
    if chromatogram_data is not None and intensity_cols:
        time_range = (chromatogram_data[time_col].min(), chromatogram_data[time_col].max())
        intensity_range = (chromatogram_data[intensity_cols[0]].min(), chromatogram_data[intensity_cols[0]].max())
        print(f"📏 Time range: {time_range}")
        print(f"📏 Intensity range: {intensity_range}")
    
    print("=== END DEBUG ===\n")

def debug_peak_data(filename, data_manager):
    """Debug function to check peak data before visualization."""
    try:
        from utils.peak_integration import peak_manager
        
        # Get file data
        file_data = data_manager.get_file_data(filename)
        if not file_data:
            print(f"[DEBUG] No file data found for {filename}")
            return
            
        print(f"[DEBUG] File data type: {file_data.get('type')}")
        
        # Check chromatogram data
        chromatogram_data = file_data.get('data')
        if chromatogram_data is not None:
            print(f"[DEBUG] Chromatogram data shape: {chromatogram_data.shape}")
            print(f"[DEBUG] Columns: {list(chromatogram_data.columns)}")
        
        # Check detected peaks
        detected_peaks = peak_manager.detected_peaks.get(filename, [])
        print(f"[DEBUG] Detected peaks count: {len(detected_peaks)}")
        for i, peak in enumerate(detected_peaks[:3]):  # Show first 3
            print(f"[DEBUG] Peak {i+1}: {peak}")
        
        # Check integration table
        integration_table = file_data.get('integration_table')
        if integration_table is not None:
            print(f"[DEBUG] Integration table shape: {integration_table.shape}")
            print(f"[DEBUG] Integration table columns: {list(integration_table.columns)}")
            print(f"[DEBUG] First few rows:")
            print(integration_table.head())
        
    except Exception as e:
        print(f"[DEBUG] Error in debug_peak_data: {e}")
        import traceback
        print(f"[DEBUG] Full traceback: {traceback.format_exc()}")






def apply_scientific_styling(fig, show_legend=True, title=None):
    """Apply JACS-style scientific publication formatting to any Plotly figure."""
    
    # SCIENTIFIC COLOR PALETTE - Colorblind safe and professional
    scientific_colors = [
        '#1f77b4',  # Professional blue
        '#ff7f0e',  # Orange
        '#2ca02c',  # Green  
        '#d62728',  # Red
        '#9467bd',  # Purple
        '#8c564b',  # Brown
        '#e377c2',  # Pink
        '#7f7f7f',  # Grey
        '#bcbd22',  # Olive
        '#17becf'   # Cyan
    ]
    
    # Update traces with scientific line styling
    for i, trace in enumerate(fig.data):
        if hasattr(trace, 'line'):
            trace.line.width = 1.8  # Professional line width (1.5-2px)
            trace.line.color = scientific_colors[i % len(scientific_colors)]
    
    fig.update_layout(
        # CLEAN WHITE BACKGROUND
        plot_bgcolor='white',
        paper_bgcolor='white',
        
        # PROFESSIONAL FONTS - Consistent sans-serif
        font=dict(
            family="Arial, Helvetica, sans-serif",  # Professional font stack
            size=11,  # Base font size
            color="black"
        ),
        
        # TITLE STYLING (if provided)
        title=dict(
            text=title,
            font=dict(size=14, color="black"),
            x=0.5,  # Center title
            xanchor='center'
        ) if title else None,
        
        # LEGEND - Inside plot, professional styling
        showlegend=show_legend,
        legend=dict(
            x=0.98,  # Top right inside plot
            y=0.98,
            xanchor='right',
            yanchor='top',
            bgcolor='rgba(255,255,255,0.95)',  # Slightly transparent white
            bordercolor='rgba(128,128,128,0.5)',  # Subtle grey border
            borderwidth=0.8,  # Thin border
            font=dict(size=10),  # Slightly smaller than axis labels
            itemsizing='constant',  # Consistent marker sizes
            itemclick=False,  # Prevent accidental hiding
            itemdoubleclick=False
        ) if show_legend else dict(),
        
        # MARGINS - Adequate whitespace for publication
        margin=dict(l=70, r=40, t=50, b=60)
    )
    
    # X-AXIS SCIENTIFIC FORMATTING
    fig.update_xaxes(
        # AXIS LINE - Thin, professional
        linewidth=1.2,
        linecolor='black',
        mirror=False,  # Only bottom axis line
        
        # TICKS - Small, uniform, inward pointing
        ticks='inside',
        tickwidth=1,
        ticklen=4,
        tickcolor='black',
        
        # TICK LABELS - Professional formatting
        tickfont=dict(size=10, color='black'),
        tickformat='.1f',  # One decimal place, no trailing zeros
        
        # GRID LINES - Faint, dashed
        showgrid=True,
        gridwidth=0.5,
        gridcolor='rgba(128,128,128,0.2)',  # Very light grey
        griddash='dot',  # Dotted grid lines
        
        # AXIS LABEL - Italicized variables, upright units
        title=dict(
            font=dict(size=12, color='black'),
            standoff=15  # Space from tick labels
        )
    )
    
    # Y-AXIS SCIENTIFIC FORMATTING  
    fig.update_yaxes(
        # AXIS LINE - Thin, professional
        linewidth=1.2,
        linecolor='black',
        mirror=False,  # Only left axis line
        
        # TICKS - Small, uniform, inward pointing
        ticks='inside',
        tickwidth=1,
        ticklen=4,
        tickcolor='black',
        
        # TICK LABELS - Professional formatting
        tickfont=dict(size=10, color='black'),
        tickformat='.0f',  # No decimals for intensity values
        
        # GRID LINES - Faint, dashed
        showgrid=True,
        gridwidth=0.5,
        gridcolor='rgba(128,128,128,0.2)',  # Very light grey
        griddash='dot',  # Dotted grid lines
        
        # AXIS LABEL - Italicized variables, upright units
        title=dict(
            font=dict(size=12, color='black'),
            standoff=15  # Space from tick labels
        )
    )
    
    return fig

def format_scientific_axis_labels(x_label=None, y_label=None):
    """Format axis labels with proper scientific typography."""
    
    # Default scientific labels with italic variables and upright units
    if not x_label:
        x_label = "<i>t</i> (min)"  # Italic 't' for time variable, upright units
    
    if not y_label:
        y_label = "Signal Intensity (mAU)"  # Upright units
    
    return x_label, y_label

def create_publication_ready_legend_annotations(traces_data, n_plots, colors, show_legend=True):
    """Create individual legend annotations for subplots in scientific style."""
    annotations = []
    
    if not show_legend:
        return annotations
    
    for i, (sample_name, color) in enumerate(zip(traces_data, colors)):
        # Calculate subplot position
        subplot_y_start = 1 - (i / n_plots)
        legend_y = subplot_y_start - 0.03  # Position near top of each subplot
        
        annotations.append(
            dict(
                text=f'<span style="color:{color}; font-size:10px">{sample_name}</span>',
                x=0.02,  # Inside plot area
                y=legend_y,
                xref="paper",
                yref="paper",
                xanchor="left",
                yanchor="top",
                showarrow=False,
                bgcolor='rgba(255,255,255,0.9)',  # Semi-transparent background
                bordercolor='rgba(128,128,128,0.3)',  # Subtle border
                borderwidth=0.5,
                font=dict(size=10, family="Arial, Helvetica, sans-serif")
            )
        )
    
    return annotations

def apply_consistent_axis_styling(fig, show_horizontal_grid=False, show_vertical_grid=False, row=None, col=None):
    """Apply EXACTLY the same axis styling to both overlay and separate plots."""
    
    # IDENTICAL axis styling for consistency
    axis_style = dict(
        linewidth=1,
        linecolor='black',
        mirror=True,  # Complete box - all four sides
        ticks='outside',
        tickwidth=1,
        ticklen=5,
        tickcolor='black',
        showline=True,
        zeroline=False
    )
    
    # X-axis styling
    x_style = axis_style.copy()
    x_style.update({
        'showgrid': show_vertical_grid,
        'gridwidth': 1,
        'gridcolor': 'rgba(128,128,128,0.3)',
    })
    
    # Y-axis styling  
    y_style = axis_style.copy()
    y_style.update({
        'showgrid': show_horizontal_grid,
        'gridwidth': 1,
        'gridcolor': 'rgba(128,128,128,0.3)',
    })
    
    if row is not None and col is not None:
        # For subplots
        fig.update_xaxes(**x_style, row=row, col=col)
        fig.update_yaxes(**y_style, row=row, col=col)
    else:
        # For single plots
        fig.update_xaxes(**x_style)
        fig.update_yaxes(**y_style)
    
    return fig



def create_uvvis_plot_with_visibility(file_data, visibility_state, max_wells=5):
    """Create UV-Vis plot but only include visible wells."""
    if not visibility_state:
        return create_uvvis_plot(file_data, max_wells=max_wells)
    
    # Filter wells based on visibility
    filename = file_data.get('filename', 'unknown')
    filled_wells = file_data['metadata'].get('filled_wells', [])
    
    visible_wells = []
    for well in filled_wells:
        well_id = f"{filename}|{well}"
        if visibility_state.get(well_id, True):
            visible_wells.append(well)
    
    if not visible_wells:
        return go.Figure().add_annotation(
            text="All wells hidden", xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=14, font_color="#999"
        )
    
    # Create modified file_data with only visible wells
    modified_file_data = file_data.copy()
    modified_file_data['metadata'] = file_data['metadata'].copy()
    modified_file_data['metadata']['filled_wells'] = visible_wells[:max_wells]
    
    return create_uvvis_plot(modified_file_data, max_wells=max_wells)