# File: callbacks/viz_callbacks.py 
import dash
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
from callbacks.baseline_integration_callbacks import _get_chrom_data, exact_crossings


from callbacks.draw_mode_callbacks import register_draw_mode_callbacks

def register_viz_callbacks(app, data_manager):
    """Register visualization-related callbacks with visibility support."""

    # Register draw/zoom tool switching
    register_draw_mode_callbacks(app)
    
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


    @app.callback(
        [Output('ms-plot', 'figure'),
        Output('uv-chromatogram-plot', 'figure', allow_duplicate=True),
        Output('uvvis-plate-plot', 'figure'),
        Output('spectra-plot', 'figure'),
        Output('ms-plot', 'style'),
        Output('uv-chromatogram-plot', 'style'),
        Output('uvvis-plate-plot', 'style'),
        Output('spectra-plot', 'style')],
        [Input('file-selector', 'value'),
        Input('visibility-state', 'data'),
        Input('selected-layer', 'data'),
        Input('baseline-mode', 'data'),
        Input('stored-peaks', 'data'),
        Input('selected-peak-idx', 'data'),
        Input('p-line-visible', 'data'),
        Input('clear-shapes-trigger', 'data'),
        Input('plot-zoom-state', 'data'),
        # PLOT SETTINGS INPUTS
        Input('line-thickness-slider', 'value'),
        Input('plot-layout-options', 'value'),
        Input('grid-options', 'value'),
        Input('x-min-input', 'value'),
        Input('x-max-input', 'value'),
        Input('y-min-input', 'value'),
        Input('y-max-input', 'value'),
        Input('x-axis-label', 'value'),
        Input('y-axis-label', 'value')],
        prevent_initial_call=True
    )
    def update_specialized_plots(selected_value, visibility_state, selected_layer, baseline_mode, 
                            stored_peaks, selected_peak_idx, p_line_visible, clear_shapes_trigger, zoom_state,
                            line_thickness, layout_options, grid_options,
                            x_min, x_max, y_min, y_max, x_label, y_label):
        """Update plots based on dropdown, visibility, and tree selection."""

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
            if not visibility_state.get(item_id, True):
                return False
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

        ms_fig, uv_chrom_fig, uvvis_fig, spectra_fig = empty_fig, empty_fig, empty_fig, empty_fig

        files = data_manager.get_loaded_files()
        if not files:
            hidden = {"display": "none"}
            return ms_fig, uv_chrom_fig, uvvis_fig, spectra_fig, hidden, hidden, hidden, hidden

        active_selection = selected_layer if selected_layer else selected_value
        if not active_selection or not is_visible(active_selection):
            print(f"[DEBUG] No active/visible selection ({active_selection}). Returning empty plots.")
            # Try to find a default chromatogram plot to show
            uv_chrom_fig = create_multi_chromatogram_plot_safe(
                files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels, stored_peaks
            )
            ms_style = {"display": "none"}
            uv_chrom_style = {"display": "block"} if uv_chrom_fig != empty_fig else {"display": "none"}
            uvvis_style = {"display": "none"}
            spectra_style = {"display": "none"}
            return empty_fig, uv_chrom_fig, empty_fig, empty_fig, ms_style, uv_chrom_style, uvvis_style, spectra_style

        # Handle selection and populate appropriate plots
        if '|' in active_selection:
            filename, component = active_selection.split('|', 1)
            file_data = data_manager.get_file_data(filename)

            if file_data and file_data['type'] == 'lcms_bundle':
                bundle_data = file_data.get("bundle_data", {})
                
                # Always show both plots from the SAME bundle
                # Find MS plot
                for comp_type in ['ms_positive', 'ms_negative']:
                    comp_id = f"{filename}|{comp_type}"
                    if bundle_data.get(comp_type) and is_visible(comp_id):
                        ms_fig = create_tic_plot({'data': bundle_data[comp_type]['data'], 'metadata': bundle_data[comp_type]['metadata'], 'type': 'lcms_cdf'})
                        ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                        break

                # Find UV plot
                for comp_type in ['vwd_a', 'vwd_b']:
                    comp_id = f"{filename}|{comp_type}"
                    if bundle_data.get(comp_type) and is_visible(comp_id):
                        if plot_options.get('separate_plots', False):
                            chrom_data = prepare_chromatogram_data_for_plotting(bundle_data[comp_type])
                            uv_chrom_fig = create_separate_plots(chrom_data, plot_options, line_width, axis_range, axis_labels) if chrom_data else create_lcms_uv_plot(bundle_data[comp_type])
                        else:
                            uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp_type])
                        uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                        break
            
            elif file_data and file_data['type'] == 'uvvis_csv':
                uvvis_fig = create_single_well_plot(file_data, component)
                uvvis_fig = apply_plot_settings(uvvis_fig, plot_options, line_width, axis_range, axis_labels)

        elif active_selection:
            file_data = data_manager.get_file_data(active_selection)
            if file_data:
                if file_data['type'] == 'uvvis_csv':
                    uvvis_fig = create_uvvis_plot_with_visibility(file_data, visibility_state, max_wells=5)
                    uvvis_fig = apply_plot_settings(uvvis_fig, plot_options, line_width, axis_range, axis_labels)
                elif file_data['type'] == 'lcms_cdf':
                    ms_fig = create_tic_plot(file_data)
                    ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                elif file_data['type'] in ['chromatogram', 'chromeleon_bundle']:
                    uv_chrom_fig = create_multi_chromatogram_plot_safe(
                        files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels, stored_peaks
                    )
                elif file_data['type'] == 'lcms_bundle':
                    # Default view for bundle: show first of each type
                    bundle_data = file_data.get("bundle_data", {})
                    for comp_type in ['ms_positive', 'ms_negative']:
                        if bundle_data.get(comp_type) and is_visible(f"{active_selection}|{comp_type}"):
                            ms_fig = create_tic_plot({'data': bundle_data[comp_type]['data'], 'metadata': bundle_data[comp_type]['metadata'], 'type': 'lcms_cdf'})
                            ms_fig = apply_plot_settings(ms_fig, plot_options, line_width, axis_range, axis_labels)
                            break
                    for comp_type in ['vwd_a', 'vwd_b']:
                        if bundle_data.get(comp_type) and is_visible(f"{active_selection}|{comp_type}"):
                            uv_chrom_fig = create_lcms_uv_plot(bundle_data[comp_type])
                            uv_chrom_fig = apply_plot_settings(uv_chrom_fig, plot_options, line_width, axis_range, axis_labels)
                            break

        # Determine plot visibility
        ms_style = {"display": "block"} if ms_fig != empty_fig else {"display": "none"}
        uv_chrom_style = {"display": "block"} if uv_chrom_fig != empty_fig else {"display": "none"}
        uvvis_style = {"display": "block"} if uvvis_fig != empty_fig else {"display": "none"}
        spectra_style = {"display": "none"} # Placeholder

        # Set dragmode based on the baseline integration mode - EXACT mini_dash.py logic
        if uv_chrom_fig != empty_fig:
            drag = {"draw": "drawline", "edit": "select", "navigate": "pan", "zoom": "zoom"}[baseline_mode or "navigate"]
            # Apply stored zoom state if available and in zoom mode
            layout_updates = {
                'dragmode': drag,
                'shapes': []  # Always start with empty shapes - EXACT mini_dash.py
            }
            
            # Apply zoom state if available (regardless of current mode)
            if zoom_state:
                print(f"[DEBUG] Applying stored zoom state: {zoom_state}")
                if "xaxis.range[0]" in zoom_state and "xaxis.range[1]" in zoom_state:
                    layout_updates["xaxis"] = layout_updates.get("xaxis", {})
                    layout_updates["xaxis"]["range"] = [zoom_state["xaxis.range[0]"], zoom_state["xaxis.range[1]"]]
                
                if "yaxis.range[0]" in zoom_state and "yaxis.range[1]" in zoom_state:
                    layout_updates["yaxis"] = layout_updates.get("yaxis", {})
                    layout_updates["yaxis"]["range"] = [zoom_state["yaxis.range[0]"], zoom_state["yaxis.range[1]"]]
            
            uv_chrom_fig.update_layout(**layout_updates)

        # ADD BASELINE INTEGRATION OVERLAYS - EXACT MINI_DASH.PY LOGIC
        if uv_chrom_fig != empty_fig and stored_peaks:
            df = _get_chrom_data(data_manager, selected_layer)
            if df is not None:
                shapes = []
                
                # ensure list - EXACT mini_dash.py
                stored_peaks = stored_peaks or []
                
                # draw selected peak's p-line first (so it's shapes[0]) - EXACT mini_dash.py
                if selected_peak_idx is not None and p_line_visible and selected_peak_idx < len(stored_peaks):
                    p = stored_peaks[selected_peak_idx]
                    if 'p_line' in p:
                        (p0, p1) = p["p_line"]
                        shapes.append(go.layout.Shape(type="line",
                                                    x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1],
                                                    line=dict(color="#005F8C", width=3),
                                                    editable=True, layer="above"))

                # iterate peaks and draw - EXACT mini_dash.py
                for i, p in enumerate(stored_peaks):
                    res = p
                    # area fill
                    if 'poly_x' in res and 'poly_y' in res:
                        uv_chrom_fig.add_scatter(x=res["poly_x"], y=res["poly_y"],
                                                fill="toself",
                                                fillcolor="rgba(0,150,200,0.30)",
                                                line=dict(width=0), hoverinfo="skip",
                                                showlegend=False)
                    
                    if 'q1' not in p or 'q2' not in p:
                        continue
                        
                    q1, q2 = res["q1"], res["q2"]

                    # helper dots - EXACT mini_dash.py
                    if i == selected_peak_idx and p_line_visible:     # selected & editing -> q-dots
                        uv_chrom_fig.add_scatter(x=[q1[0], q2[0]], y=[q1[1], q2[1]],
                                                mode="markers",
                                                marker=dict(size=5, symbol="circle", color="#005F8C"),
                                                showlegend=False, hoverinfo="skip")
                        # open p-endpoints
                        if 'p_line' in res:
                            p0, p1 = res["p_line"]
                            uv_chrom_fig.add_scatter(x=[p0[0], p1[0]], y=[p0[1], p1[1]],
                                                    mode="markers",
                                                    marker=dict(size=10, symbol="circle-open", color="#005F8C"),
                                                    showlegend=False, hoverinfo="skip")
                            # dotted q-line for comparison if differs - EXACT mini_dash.py
                            if q1 != p0 or q2 != p1:
                                shapes.append(go.layout.Shape(type="line",
                                                            x0=q1[0], y0=q1[1],
                                                            x1=q2[0], y1=q2[1],
                                                            line=dict(color="#005F8C", width=2, dash="dot"),
                                                            editable=False, layer="above"))
                    else:                         # other peaks -> intersection dots
                        left, right = exact_crossings(q1, q2, df)
                        if left and right:
                            uv_chrom_fig.add_scatter(x=[left[0], right[0]], y=[left[1], right[1]],
                                                    mode="markers",
                                                    marker=dict(size=5, symbol="circle", color="#002B4A"),
                                                    showlegend=False, hoverinfo="skip")

                # Add all shapes to the figure - EXACT mini_dash.py
                if shapes:
                    uv_chrom_fig.update_layout(shapes=shapes)

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

def add_baseline_peaks_to_figure(fig, filename, stored_peaks, data_manager, row=None, col=None):
    print("[BASELINE PEAKS DEBUG] add_baseline_peaks_to_figure CALLED")
    print(f"[BASELINE PEAKS DEBUG] filename: {filename}, row: {row}, col: {col}")
    """Add filled areas for baseline integration peaks to the figure"""
    if not stored_peaks:
        return fig
        
    try:
        import plotly.graph_objects as go
        import pandas as pd
        import numpy as np
        
        # Get chromatogram data
        file_data = data_manager.get_file_data(filename)
        if not file_data:
            return fig
            
        chromatogram_data = file_data.get('chromatogram_data')
        if chromatogram_data is None:
            return fig
            
        time_col = 'Time (min)'
        intensity_col = 'Value (mAU)'
        if time_col not in chromatogram_data.columns or intensity_col not in chromatogram_data.columns:
            return fig
        
        # Filter peaks by data source with enhanced debugging
        filtered_peaks = []
        print(f"[BASELINE PEAKS] Filtering peaks for {filename} from {len(stored_peaks)} total peaks")
        for i, peak in enumerate(stored_peaks):
            # Check if peak belongs to this data source
            peak_source = peak.get('data_source')
            
            # CRITICAL FIX: Compare the actual filename part without path
            # This ensures we match peaks with their data sources correctly
            import os
            filename_base = os.path.basename(filename) if filename else filename
            peak_source_base = os.path.basename(peak_source) if peak_source else peak_source
            
            is_match = (peak_source == filename) or (peak_source_base == filename_base)
            print(f"[BASELINE PEAKS] Peak {i}: data_source={peak_source}, filename={filename}")
            print(f"[BASELINE PEAKS] Basename comparison: peak_source_base={peak_source_base}, filename_base={filename_base}, match={is_match}")
            
            if is_match or peak_source is None:  # Include peaks without data_source for backward compatibility
                filtered_peaks.append(peak)
                print(f"[BASELINE PEAKS] ✅ Including peak {i} for {filename}")
            else:
                print(f"[BASELINE PEAKS] ❌ Excluding peak {i} with source {peak_source} from {filename}")
        
        print(f"[BASELINE PEAKS] Found {len(filtered_peaks)} peaks for {filename} out of {len(stored_peaks)} total peaks")
        
        # For each stored peak, fill area, draw baseline, THEN always draw q-points and q-line
        for i, peak in enumerate(filtered_peaks):
            q1, q2 = peak.get("q1"), peak.get("q2")
            print(f"[BASELINE PEAKS] Peak {i}: q1={q1}, q2={q2}")
            # 1) area fill under curve
            if 'poly_x' in peak and 'poly_y' in peak:
                scatter_args = dict(
                    x=peak["poly_x"],
                    y=peak["poly_y"],
                    fill="toself",
                    fillcolor="rgba(0,150,200,0.30)",
                    line=dict(width=0),
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"Peak {i+1}"
                )
                
                # Add to specific subplot if row/col provided
                if row is not None and col is not None:
                    fig.add_trace(go.Scatter(**scatter_args), row=row, col=col)
                else:
                    fig.add_scatter(**scatter_args)

            # 2) dashed baseline line (p-line)
            if 'p_line' in peak:
                (p0, p1) = peak["p_line"]
                shape = go.layout.Shape(
                    type="line",
                    x0=p0[0], y0=p0[1], x1=p1[0], y1=p1[1],
                    line=dict(color="#005F8C", width=3),
                    editable=True, layer="above"
                )
                
                # For subplots, we need to adjust the shape coordinates
                if row is not None and col is not None:
                    # Add shape to specific subplot
                    fig.add_shape(shape, row=row, col=col)
                else:
                    fig.add_shape(shape)

            # 3) ALWAYS add the two q-point markers
            q1, q2 = peak.get("q1"), peak.get("q2")
            if q1 and q2:
                scatter_args = dict(
                    x=[q1[0], q2[0]],
                    y=[q1[1], q2[1]],
                    mode='markers',
                    marker=dict(size=8, symbol='circle-open', color='#005F8C'),
                    showlegend=False,
                    hoverinfo='skip',
                    name=f"q-points {i+1}"
                )
                
                # Add to specific subplot if row/col provided
                if row is not None and col is not None:
                    fig.add_trace(go.Scatter(**scatter_args), row=row, col=col)
                else:
                    fig.add_trace(go.Scatter(**scatter_args))

                # 4) ALWAYS add the dashed q-line
                line_args = dict(
                    x=[q1[0], q2[0]],
                    y=[q1[1], q2[1]],
                    mode='lines',
                    line=dict(color='#005F8C', width=2, dash='dot'),
                    showlegend=False,
                    hoverinfo='skip',
                    name=f"q-line {i+1}"
                )
                
                # Add to specific subplot if row/col provided
                if row is not None and col is not None:
                    fig.add_trace(go.Scatter(**line_args), row=row, col=col)
                else:
                    fig.add_trace(go.Scatter(**line_args))

        return fig

    except Exception as e:
        print(f"[BASELINE PEAKS] ❌ Major error: {e}")
        return fig

def add_peak_areas_to_figure(fig, filename, data_manager, row=None, col=None):
    """Add filled area under detected/integrated peaks to the figure"""
    try:
        import numpy as np
        import pandas as pd
        import plotly.graph_objects as go

        print(f"[PEAK DEBUG] Starting peak visualization for: {filename}")

        file_data = data_manager.get_file_data(filename)
        if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
            print(f"[PEAK DEBUG] Skipping {filename} - not a chromatogram file")
            return fig

        # Get chromatogram data
        chromatogram_data = file_data.get('data')
        if chromatogram_data is None:
            chromatogram_data = file_data.get('chromatogram_data')
        
        if chromatogram_data is None:
            print(f"[PEAK DEBUG] No chromatogram data found for {filename}")
            return fig
            
        print(f"[PEAK DEBUG] Chromatogram data shape: {chromatogram_data.shape}")
        print(f"[PEAK DEBUG] Columns: {list(chromatogram_data.columns)}")
        
        # Find time and intensity columns
        time_col = 'Time (min)'
        intensity_col = 'Value (mAU)'  # Use correct column name
        
        if time_col not in chromatogram_data.columns:
            print(f"[PEAK DEBUG] Time column '{time_col}' not found")
            return fig
        if intensity_col not in chromatogram_data.columns:
            print(f"[PEAK DEBUG] Intensity column '{intensity_col}' not found")
            return fig
        
        # Check integration table (imported peaks)
        integration_table = file_data.get('integration_table')
        if integration_table is not None and not integration_table.empty:
            print(f"[PEAK DEBUG] Integration table found: {integration_table.shape}")
            
            # Process each peak in the integration table
            for idx, row in integration_table.iterrows():
                peak_no = row.get('No.', 'N/A')
                rt_raw = row.get('Retention Time', None)
                area_raw = row.get('Area', None)
                height_raw = row.get('Height', None)
                
                # Skip invalid peaks
                if pd.isna(rt_raw) or str(rt_raw).lower() == 'n.a.' or str(peak_no).lower() == 'n.a.':
                    continue
                    
                try:
                    rt = float(str(rt_raw).replace(',', '.'))
                    area = float(str(area_raw).replace(',', '.')) if area_raw else 0
                    height = float(str(height_raw).replace(',', '.')) if height_raw else 0
                    
                    if rt <= 0:
                        continue
                        
                    print(f"[PEAK DEBUG] Processing Peak {peak_no}: RT={rt:.3f}, Area={area:.1f}, Height={height:.1f}")
                    
                    # Reconstruct peak boundaries from chromatogram data
                    peak_area_data = reconstruct_peak_from_rt(chromatogram_data, time_col, intensity_col, rt, height)
                    
                    if peak_area_data:
                        # Add filled area under the peak
                        fig.add_scatter(
                            x=peak_area_data['x'],
                            y=peak_area_data['y'],
                            fill="toself",
                            fillcolor=f"rgba({50 + (idx * 30) % 200}, {100 + (idx * 50) % 150}, {150 + (idx * 40) % 100}, 0.4)",
                            line=dict(width=1, color=f"rgba({50 + (idx * 30) % 200}, {100 + (idx * 50) % 150}, {150 + (idx * 40) % 100}, 0.8)"),
                            hovertemplate=f"<b>Peak {peak_no}</b><br>RT: {rt:.3f} min<br>Area: {area:.1f}<br>Height: {height:.1f}<extra></extra>",
                            showlegend=False,
                            name=f"Peak {peak_no}"
                        )
                        

                        print(f"[PEAK DEBUG] ✅ Added peak area for Peak {peak_no}")
                    else:
                        print(f"[PEAK DEBUG] ❌ Could not reconstruct peak area for Peak {peak_no}")
                        
                except (ValueError, TypeError) as e:
                    print(f"[PEAK DEBUG] ❌ Error processing Peak {peak_no}: {e}")
                    continue
        else:
            print("[PEAK DEBUG] No integration table found")

        # Also check for detected peaks from peak manager (manual peaks)
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
                print(f"[PEAK DEBUG] Detected peaks found (key: {matching_key}): {len(detected_peaks)} peaks")
                for i, peak in enumerate(detected_peaks):
                    rt = peak.get('retention_time', 'N/A')
                    area = peak.get('area', 'N/A')
                    print(f"   Detected Peak {i+1}: RT={rt}, Area={area}")
            else:
                print("[PEAK DEBUG] No detected peaks found")
        
        except ImportError as e:
            print(f"[PEAK DEBUG] Peak integration module not available: {e}")
        except Exception as e:
            print(f"[PEAK DEBUG] ❌ Error in peak manager section: {e}")
            import traceback
            print(f"[PEAK DEBUG] Traceback: {traceback.format_exc()}")

        print("[PEAK DEBUG] ✅ Peak visualization completed")
        
    except Exception as e:
        print(f"[PEAK DEBUG] ❌ Major error in add_peak_areas_to_figure: {e}")
        import traceback
        print(f"[PEAK DEBUG] Traceback: {traceback.format_exc()}")
        
    return fig

def reconstruct_peak_from_rt(chromatogram_data, time_col, intensity_col, target_rt, peak_height):
    """
    Professional peak reconstruction using derivative analysis and proper baseline.
    """
    try:
        import numpy as np
        from scipy.signal import savgol_filter
        from scipy.interpolate import interp1d
        
        time_data = chromatogram_data[time_col].values
        intensity_data = chromatogram_data[intensity_col].values
        
        # Find index closest to target RT
        rt_idx = np.argmin(np.abs(time_data - target_rt))
        
        # Smooth data and calculate first derivative
        window = min(21, len(intensity_data) // 10)
        if window % 2 == 0:
            window += 1
        
        smoothed = savgol_filter(intensity_data, window, 3)
        first_deriv = np.gradient(smoothed)
        
        # Find peak boundaries using derivative zero-crossings
        # Left boundary: where derivative changes from negative to positive before peak
        left_idx = rt_idx
        for i in range(rt_idx, max(0, rt_idx - 200), -1):
            if i > 0 and first_deriv[i-1] < 0 and first_deriv[i] >= 0:
                # Found inflection point (valley)
                left_idx = i
                break
            elif i > 0 and smoothed[i] < smoothed[i-1] * 0.01:
                # Or reached near-zero baseline
                left_idx = i
                break
        
        # Right boundary: where derivative changes from negative to positive after peak  
        right_idx = rt_idx
        for i in range(rt_idx, min(len(intensity_data) - 1, rt_idx + 200)):
            if i < len(first_deriv) - 1 and first_deriv[i] < 0 and first_deriv[i+1] >= 0:
                # Found inflection point (valley)
                right_idx = i
                break
            elif i < len(smoothed) - 1 and smoothed[i] < smoothed[i+1] * 0.01:
                # Or reached near-zero baseline
                right_idx = i
                break
        
        # Extract peak region
        peak_times = time_data[left_idx:right_idx+1]
        peak_intensities = intensity_data[left_idx:right_idx+1]
        
        if len(peak_times) < 3:
            return None
        
        # Professional baseline: straight line from start to end of peak
        baseline_start = peak_intensities[0]
        baseline_end = peak_intensities[-1]
        
        # Create baseline points
        baseline_y = np.linspace(baseline_start, baseline_end, len(peak_times))
        
        # Create filled area coordinates
        x_coords = []
        y_coords = []
        
        # Add peak curve points
        x_coords.extend(peak_times)
        y_coords.extend(peak_intensities)
        
        # Add baseline points in reverse order to close polygon
        # Ensure baseline never goes above the curve
        for i in range(len(peak_times)-1, -1, -1):
            x_coords.append(peak_times[i])
            # Baseline should never exceed the actual intensity
            y_coords.append(min(baseline_y[i], peak_intensities[i]))

        # Close the polygon
        x_coords.append(peak_times[0])
        y_coords.append(peak_intensities[0])
        
        print(f"[RECONSTRUCT] Peak: RT {target_rt:.3f}, boundaries [{peak_times[0]:.3f}, {peak_times[-1]:.3f}]")
        
        return {
            'x': x_coords,
            'y': y_coords
        }
        
    except Exception as e:
        print(f"[RECONSTRUCT] Error: {e}")
        # Fallback to simple method
        try:
            time_data = chromatogram_data[time_col].values
            intensity_data = chromatogram_data[intensity_col].values
            rt_idx = np.argmin(np.abs(time_data - target_rt))
            
            # Simple peak width estimation
            half_height = intensity_data[rt_idx] / 2
            
            # Find points at half height
            left_idx = rt_idx
            for i in range(rt_idx, 0, -1):
                if intensity_data[i] < half_height:
                    left_idx = max(0, i - 5)
                    break
                    
            right_idx = rt_idx  
            for i in range(rt_idx, len(intensity_data)):
                if intensity_data[i] < half_height:
                    right_idx = min(len(intensity_data) - 1, i + 5)
                    break
            
            peak_times = time_data[left_idx:right_idx+1]
            peak_intensities = intensity_data[left_idx:right_idx+1]
            
            # Simple baseline
            baseline_y = np.linspace(peak_intensities[0], peak_intensities[-1], len(peak_times))
            
            x_coords = list(peak_times) + list(peak_times[::-1]) + [peak_times[0]]
            y_coords = list(peak_intensities) + list(baseline_y[::-1]) + [peak_intensities[0]]
            
            return {'x': x_coords, 'y': y_coords}
            
        except:
            return None

def auto_detect_peaks(chromatogram_data, time_col='Time (min)', intensity_col='Value (mAU)', 
                     min_height=10, min_distance=0.1, prominence=0.1):
    """
    Automatic peak detection using scipy's find_peaks with HPLC-specific parameters.
    
    Args:
        chromatogram_data: DataFrame with chromatogram
        time_col: Name of time column
        intensity_col: Name of intensity column  
        min_height: Minimum peak height (mAU)
        min_distance: Minimum distance between peaks (minutes)
        prominence: Minimum prominence (relative to neighbors)
    
    Returns:
        List of detected peaks with RT, height, boundaries
    """
    try:
        from scipy.signal import find_peaks, peak_widths, savgol_filter
        import numpy as np
        
        time_data = chromatogram_data[time_col].values
        intensity_data = chromatogram_data[intensity_col].values
        
        # Smooth data first
        window = min(21, len(intensity_data) // 50)
        if window % 2 == 0:
            window += 1
        smoothed = savgol_filter(intensity_data, window, 3)
        
        # Convert min_distance from minutes to indices
        time_step = np.mean(np.diff(time_data))
        distance_indices = int(min_distance / time_step)
        
        # Find peaks
        peaks, properties = find_peaks(smoothed, 
                                     height=min_height,
                                     distance=distance_indices,
                                     prominence=prominence * np.max(smoothed))
        
        # Get peak widths at half height
        widths, width_heights, left_ips, right_ips = peak_widths(smoothed, peaks, rel_height=0.5)
        
        detected_peaks = []
        for i, peak_idx in enumerate(peaks):
            # Convert indices to time
            rt = time_data[peak_idx]
            height = intensity_data[peak_idx]
            
            # Get boundaries from width calculation
            left_idx = int(left_ips[i])
            right_idx = int(right_ips[i])
            
            detected_peaks.append({
                'peak_no': i + 1,
                'retention_time': rt,
                'height': height,
                'left_idx': left_idx,
                'right_idx': right_idx,
                'left_time': time_data[left_idx],
                'right_time': time_data[right_idx],
                'width': time_data[right_idx] - time_data[left_idx]
            })
        
        return detected_peaks
        
    except ImportError:
        print("[AUTO DETECT] scipy not available, using simple detection")
        # Simple fallback detection
        return []

def create_multi_chromatogram_plot_safe(files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels, stored_peaks=None):
    # Determine gridline visibility from plot_options
    show_grid = False
    if plot_options and isinstance(plot_options, dict):
        show_grid = 'show_grid' in plot_options.get('options', [])

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
        return create_separate_chromatogram_subplots_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks)
    else:
        return create_overlay_chromatogram_plot_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks)

# END OF FILE - Clean ending after last function

    # (Note: gridline state is now handled consistently in both sub-functions)


def apply_consistent_axis_styling(fig, show_horizontal_grid=False, show_vertical_grid=False, row=None, col=None):
    """
    Apply consistent axis styling to plotly figures with control over gridline visibility.
    
    Args:
        fig: Plotly figure to style
        show_horizontal_grid: Whether to show horizontal gridlines
        show_vertical_grid: Whether to show vertical gridlines
        row: Optional row index for subplot
        col: Optional column index for subplot
        
    Returns:
        Styled Plotly figure
    """
    axis_style = dict(
        linewidth=1,
        linecolor='black',
        mirror=True,
        ticks='outside',
        tickwidth=1,
        ticklen=5,
        tickcolor='black',
        showline=True,
        zeroline=False
    )
    x_style = axis_style.copy()
    x_style.update({
        'showgrid': show_vertical_grid,
        'gridwidth': 1,
        'gridcolor': 'rgba(128,128,128,0.3)',
    })
    y_style = axis_style.copy()
    y_style.update({
        'showgrid': show_horizontal_grid,
        'gridwidth': 1,
        'gridcolor': 'rgba(128,128,128,0.3)',
    })
    if row is not None and col is not None:
        fig.update_xaxes(**x_style, row=row, col=col)
        fig.update_yaxes(**y_style, row=row, col=col)
    else:
        fig.update_xaxes(**x_style)
        fig.update_yaxes(**y_style)
    return fig


def apply_scientific_styling(fig, show_legend=True, title=None, show_x_grid=False, show_y_grid=False):
    """
    Apply scientific publication-quality styling to a figure with gridline control.
    
    Args:
        fig: Plotly figure to style
        show_legend: Whether to show the legend
        title: Optional title for the figure
        show_x_grid: Whether to show vertical gridlines
        show_y_grid: Whether to show horizontal gridlines
        
    Returns:
        Styled Plotly figure
    """
    # Base styling
    fig.update_layout(
        template='plotly_white',
        showlegend=show_legend,
        legend=dict(x=1.02, y=1, xanchor='left', yanchor='top'),
        font=dict(family='Arial', size=12),
        margin=dict(l=60, r=60, t=50, b=50),
    )
    
    if title:
        fig.update_layout(title=title)
    
    # Apply consistent axis styling with gridline control
    fig = apply_consistent_axis_styling(fig, show_horizontal_grid=show_y_grid, show_vertical_grid=show_x_grid)
    
    return fig


def create_separate_chromatogram_subplots_fixed(visible_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks=None, zoom_state=None):
    # Determine gridline visibility from plot_options
    show_grid = False
    if plot_options and isinstance(plot_options, dict):
        show_grid = 'show_grid' in plot_options.get('options', [])

    """
    COMPLETE REPLACEMENT - Create separate subplots with peak visualization
    """
    
    from plotly.subplots import make_subplots
    from plot.hplc import create_chromatogram_plot, create_chromeleon_bundle_plot
    
    n_plots = len(visible_files)
    if n_plots == 0:
        return go.Figure().add_annotation(
            text="No visible chromatogram files", xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=14, font_color="#999"
        )
    
    # Create subplots
    fig = make_subplots(rows=n_plots, cols=1, shared_xaxes=True, vertical_spacing=0.02)
    
    # Extract plot options
    show_legend = 'show_legend' in plot_options.get('options', []) if plot_options else True
    
    # Get axis labels
    x_label = axis_labels.get('x', 'Time (min)') if axis_labels else 'Time (min)'
    y_label = axis_labels.get('y', 'Absorbance (mAU)') if axis_labels else 'Absorbance (mAU)'
    
    # Add each chromatogram as a separate subplot
    for i, filename in enumerate(visible_files, 1):
        file_data = data_manager.get_file_data(filename)
        if not file_data:
            continue
            
        data = file_data.get('data')
        if data is None or data.empty:
            continue
            
        # Determine column names
        time_col = 'Time (min)'
        intensity_col = None
        for col in data.columns:
            if 'Intensity' in col or 'Value' in col:
                intensity_col = col
                break
        
        if not intensity_col:
            continue
            
        # Add trace
        clean_name = extract_clean_sample_name(filename)
        fig.add_trace(
            go.Scatter(
                x=data[time_col],
                y=data[intensity_col],
                mode='lines',
                name=clean_name,
                line=dict(width=line_width or 1.5)
            ),
            row=i, col=1
        )
        
        # Peak areas will be added later in a separate loop
        
    # Set figure height based on number of plots
    height_per_plot = 250
    total_height = max(500, n_plots * height_per_plot)
    

    # Update layout
    fig.update_layout(
        showlegend=show_legend,
        template='plotly_white',
        margin=dict(l=60, r=60, t=50, b=50),
        legend=dict(x=1.02, y=1, xanchor='left', yanchor='top'),
        autosize=True  # Enable responsive sizing
)
    # Add y-axis title
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
    
    # Apply user axis ranges OR maintain current zoom if available
    # Apply user axis ranges OR maintain current zoom if available
    from dash import callback_context
    ctx = callback_context

    # Try to get zoom state from the plot_zoom_state Store
    zoom_state = None
    for input_item in ctx.inputs_list:
        if 'plot-zoom-state.data' in str(input_item):
            zoom_state = input_item.get('value')
            break

    # Apply ranges
    for i in range(1, n_plots + 1):
        if zoom_state and 'xaxis.range[0]' in zoom_state and 'xaxis.range[1]' in zoom_state:
            # Use stored zoom state
            fig.update_xaxes(range=[zoom_state['xaxis.range[0]'], zoom_state['xaxis.range[1]']], row=i, col=1)
            if 'yaxis.range[0]' in zoom_state and 'yaxis.range[1]' in zoom_state:
                fig.update_yaxes(range=[zoom_state['yaxis.range[0]'], zoom_state['yaxis.range[1]']], row=i, col=1)
        elif axis_range and not axis_range.get('auto_range', True):
            # Use manual settings
            if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
                fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']], row=i, col=1)
            
            if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
                fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']], row=i, col=1)



    # Add peak areas to all subplots with proper row/col indexing
    for i, filename in enumerate(visible_files, 1):
        print(f"[SEPARATE PLOTS] Adding peak areas for: {filename} in subplot {i}")
        # Add detected peaks from peak_manager
        fig = add_peak_areas_to_figure(fig, filename, data_manager, row=i, col=1)
        
        # Add baseline integration peaks if available
        print(f"[SEPARATE DEBUG] stored_peaks type: {type(stored_peaks)}, value: {stored_peaks}")
        if stored_peaks:
            print(f"[SEPARATE DEBUG] Calling add_baseline_peaks_to_figure with {len(stored_peaks)} peaks for {filename} in subplot {i}")
            fig = add_baseline_peaks_to_figure(fig, filename, stored_peaks, data_manager, row=i, col=1)
        else:
            print(f"[SEPARATE DEBUG] No stored_peaks to add for {filename}")
    
    # Apply scientific styling with grid control
    fig = apply_scientific_styling(fig, show_legend=show_legend, title=None, show_x_grid=show_grid, show_y_grid=show_grid)
    
    return fig


def create_overlay_chromatogram_plot_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks=None):
    """
    Overlay all chromatograms in a single plot, with gridline toggle and peak visualization.
    """
    import plotly.graph_objects as go
    fig = go.Figure()

    # Determine gridline visibility from plot_options
    show_grid = False
    show_legend = True
    if plot_options and isinstance(plot_options, dict):
        show_grid = 'show_grid' in plot_options.get('options', [])
        show_legend = 'show_legend' in plot_options.get('options', [])

    x_label = axis_labels.get('x', 'Time (min)') if axis_labels else 'Time (min)'
    y_label = axis_labels.get('y', 'Absorbance (mAU)') if axis_labels else 'Absorbance (mAU)'

    # Overlay all visible chromatograms
    for filename in visible_chrom_files:
        file_data = data_manager.get_file_data(filename)
        if not file_data or file_data.get('type') not in ['chromatogram', 'chromeleon_bundle']:
            continue
        data = file_data.get('data')
        if data is None or data.empty:
            continue
        time_col = 'Time (min)'
        # Intensity column detection (robust)
        intensity_col = None
        for col in data.columns:
            if 'Intensity' in col or 'Value' in col:
                intensity_col = col
                break
        if not intensity_col:
            continue
        fig.add_trace(go.Scatter(
            x=data[time_col],
            y=data[intensity_col],
            mode='lines',
            name=filename,
            line=dict(width=line_width or 2)
        ))

        # Add legacy peak areas (peak_manager)
        fig = add_peak_areas_to_figure(fig, filename, data_manager)
        # Add baseline integration peaks if available
        if stored_peaks:
            fig = add_baseline_peaks_to_figure(fig, filename, stored_peaks, data_manager)

    # Axis labels
    fig.update_layout(
        xaxis_title=x_label,
        yaxis_title=y_label,
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=show_legend,
        legend=dict(x=1.02, y=1, xanchor='left', yanchor='top')
    )

    # Apply axis ranges if specified
    if axis_range and not axis_range.get('auto_range', True):
        if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
            fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']])
        if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
            fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']])

    # Apply scientific styling with grid control
    fig = apply_scientific_styling(fig, show_legend=show_legend, title=None, show_x_grid=show_grid, show_y_grid=show_grid)

    return fig

    # Determine gridline visibility from plot_options
    show_grid = False
    if plot_options and isinstance(plot_options, dict):
        show_grid = 'show_grid' in plot_options.get('options', [])

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
                        bordercolor='rgba(128,128,128,0.3)',
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
            showgrid=show_grid,
            gridwidth=1 if show_grid else 0,
            gridcolor='rgba(128,128,128,0.3)' if show_grid else 'rgba(0,0,0,0)',
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

    # Add peak areas to all subplots with proper row/col indexing
    for i, filename in enumerate(visible_files, 1):
        print(f"[SEPARATE PLOTS] Adding peak areas for: {filename} in subplot {i}")
        # Add detected peaks from peak_manager
        fig = add_peak_areas_to_figure(fig, filename, data_manager, row=i, col=1)
        
        # Add baseline integration peaks if available
        print(f"[SEPARATE DEBUG] stored_peaks type: {type(stored_peaks)}, value: {stored_peaks}")
        if stored_peaks:
            print(f"[SEPARATE DEBUG] Calling add_baseline_peaks_to_figure with {len(stored_peaks)} peaks for {filename} in subplot {i}")
            fig = add_baseline_peaks_to_figure(fig, filename, stored_peaks, data_manager, row=i, col=1)
        else:
            print(f"[SEPARATE DEBUG] No stored_peaks to add for {filename}")
    
    # Apply scientific publication styling with grid control
    fig = apply_scientific_styling(fig, show_legend=show_legend, title=None, show_x_grid=show_grid, show_y_grid=show_grid)
    
    return fig

def create_multi_chromatogram_plot_safe(files, data_manager, visibility_state, plot_options, line_width, axis_range, axis_labels, stored_peaks=None):
    # Determine gridline visibility from plot_options
    show_grid = False
    if plot_options and isinstance(plot_options, dict):
        show_grid = 'show_grid' in plot_options.get('options', [])

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
        return create_separate_chromatogram_subplots_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks)
    else:
        return create_overlay_chromatogram_plot_fixed(visible_chrom_files, data_manager, plot_options, line_width, axis_range, axis_labels, stored_peaks)

# END OF FILE - Clean ending after last function

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