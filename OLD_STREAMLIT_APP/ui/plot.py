# ui/plot.py 

import streamlit as st
import plotly.graph_objects as go
import numpy as np
from ui.sidebar import hex_to_rgba
from ui.plot_settings import apply_plot_settings  
from ui.fonts_labels import apply_font_settings
from ui.plot_interactions import make_titles_editable, implement_title_editing_ui
from ui.plot_interactions import capture_legend_position
import json
from urllib.parse import parse_qs
from ui.plot_interactions import capture_title_changes
plotly_events = st.session_state.get('plotly_events')  # optional if using events
capture_legend_position(st.session_state.get("plotly_events", {}))
from lcms.cdf_reader import get_eic
from ui.plot_settings import (
    get_data_bounds, 
    initialize_axis_state,
    capture_zoom_events,
    apply_axis_ranges
)
 

def navigate_to_peak_ms(chrom_id):
    """Navigate to Peak MS tab programmatically"""
    st.session_state[f"active_tab_{chrom_id}"] = "Peak MS"
    
    # Handle query params
    query_params = st.query_params
    active_tabs = {}
    if "active_tabs" in query_params:
        try:
            active_tabs = json.loads(query_params["active_tabs"][0])
        except:
            active_tabs = {}
    
    active_tabs[str(chrom_id)] = "Peak MS"
    update_query_params({"active_tabs": json.dumps(active_tabs)})
    st.rerun()

def navigate_to_extracted_ion_chromatogram(chrom_id):
    """Navigate to Extracted Ion Chromatogram tab programmatically"""
    st.session_state[f"active_tab_{chrom_id}"] = "Extracted Ion Chromatogram"
    
    # Handle query params
    query_params = st.query_params
    active_tabs = {}
    if "active_tabs" in query_params:
        try:
            active_tabs = json.loads(query_params["active_tabs"][0])
        except:
            active_tabs = {}
    
    active_tabs[str(chrom_id)] = "Extracted Ion Chromatogram"
    update_query_params({"active_tabs": json.dumps(active_tabs)})
    st.rerun()

def update_query_params(params):
    """Update query parameters"""
    for key, value in params.items():
        st.query_params[key] = value

def get_current_figure():
    """
    Get the current plotly figure for export.
    
    Returns:
        The plotly figure object or None if not available
    """
    # If you're storing the figure in session state
    if 'current_figure' in st.session_state:
        return st.session_state.current_figure
    
    # Otherwise, recreate the figure
    active_chrom = st.session_state.active_chromatogram
    if active_chrom is None or not st.session_state.chromatograms:
        return None
        
    # This depends on your implementation, but you'll need to recreate
    # the figure that's currently displayed
    from utils.data_processing import process_chromatogram_data
    preprocessed_data = {}
    
    # Process the active chromatogram
    if active_chrom in st.session_state.chromatograms:
        chrom_data = st.session_state.chromatograms[active_chrom]
        if 'data' in chrom_data:
            x = chrom_data['data']['x']
            y = chrom_data['data']['y']
            
            # Apply processing similar to what's done in plot_chromatograms
            from utils.data_processing import apply_smoothing, calculate_baseline
            
            smoothing = st.session_state.smoothing
            y_smooth = apply_smoothing(y, smoothing)
            baseline = calculate_baseline(
                y_smooth,
                iterations=st.session_state.settings['baseline_iterations'],
                percentile=st.session_state.settings['percentile']
            )
            y_corrected = y_smooth - baseline
            
            preprocessed_data[active_chrom] = {
                'x': x,
                'y': y,
                'y_smooth': y_smooth,
                'baseline': baseline,
                'y_corrected': y_corrected
            }
    
    # Recreate the figure
    fig = plot_chromatograms(preprocessed_data, return_fig=True)
    
    return fig

def plot_chromatograms(preprocessed_data, return_fig=False):
    """
    Plot chromatograms with peaks and baselines.
    
    Args:
        preprocessed_data: Dictionary of preprocessed chromatogram data
        return_fig: If True, return the figure instead of displaying it
        
    Returns:
        The plotly figure object if return_fig is True
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from ui.plot_settings import apply_plot_settings
    from ui.fonts_labels import apply_font_settings

    fig_ms = None

    # NEW SMART AXIS CODE - ADD THESE 5 LINES:
    # NEW SMART AXIS CODE WITH DEBUG
    print("📊 plot_chromatograms: Starting smart axis setup")
    data_bounds = get_data_bounds(preprocessed_data)
    print(f"📊 Data bounds calculated: {data_bounds}")
    
    initialize_axis_state(data_bounds)
    print("📊 Axis state initialized")
    
    plotly_events = st.session_state.get('plotly_events', {})
    print(f"📊 Plotly events from session: {plotly_events}")
    
    capture_zoom_events(plotly_events)
    capture_title_changes(plotly_events)
    print("📊 Zoom and title events captured")

    # Check if we should use separate plots
    use_separate_plots = st.session_state.get('plot_settings', {}).get('separate_plots', False)
    
    # Count visible chromatograms for subplots
    visible_chroms = [chrom_id for chrom_id, chrom_data in st.session_state.chromatograms.items() 
                     if chrom_data['visible'] and chrom_id in preprocessed_data]
    
    # Get plot config for labels
    plot_config = st.session_state.get('plot_config', {
        'title': 'Chromatogram Analysis',
        'xaxis_title': 'Time (min)',
        'yaxis_title': 'Signal (a.u.)',
    })
    
    # Get font settings
    font_settings = st.session_state.get('font_settings', {
        'title_fs': 18,
        'axis_fs': 18,
        'legend_fs': 18,
        'tick_fs': 18,
    })
    
    # Preserve current zoom if available
    x_range = None
    y_range = None



    # Create figure - either single plot or subplots
    if use_separate_plots and len(visible_chroms) > 0:
        # Create subplots without subplot titles - we'll use traces in reruninstead
        fig = make_subplots(
            rows=len(visible_chroms), 
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05 / max(1, len(visible_chroms) - 1)  # Adjust spacing based on number of plots
        )
        
        # Common layout configuration for subplots
        fig.update_layout(
            title=plot_config.get('title', 'Chromatogram Analysis'),
            showlegend=st.session_state.get('plot_settings', {}).get('show_legend', True),
            # Use a single y-axis title for all subplots
            yaxis_title=None,  # Remove individual y-axis titles
            height=st.session_state.get('plot_settings', {}).get('plot_height', 500) * 
                   (0.5 + 0.5 * len(visible_chroms)),  # Scale height with number of subplots
            # Ensure legend has enough space at the top
            margin=dict(t=100, b=40, l=60, r=120)
        )
        
        # Add a single y-axis title that spans all subplots
        fig.add_annotation(
            x=-0.1,  # Position to the left of the plots
            y=0.5,   # Middle of the figure
            xref="paper",
            yref="paper",
            text=plot_config.get('yaxis_title', 'Signal (a.u.)'),
            textangle=-90,
            showarrow=False,
            font=dict(size=font_settings.get('axis_fs', 18))
        )
        
        # Add an x-axis title only to the bottom subplot
        if len(visible_chroms) > 0:
            fig.update_xaxes(
                title=plot_config.get('xaxis_title', 'Time (min)'),
                title_font=dict(size=font_settings.get('axis_fs', 18)),
                row=len(visible_chroms),
                col=1
            )
    else:
        # Single plot for all chromatograms
        fig = go.Figure()
        
        # Configure layout for single plot
        fig.update_layout(
            title=plot_config.get('title', 'Chromatogram'),
            xaxis_title=plot_config.get('xaxis_title', 'Time (min)'),
            yaxis_title=plot_config.get('yaxis_title', 'Signal (a.u.)'),
            showlegend=st.session_state.get('plot_settings', {}).get('show_legend', True)
        )
    
    # Get plotting settings
    use_smooth = st.session_state.get('plot_settings', {}).get('smooth_lines', True)
    integrate_zero = st.session_state.get('plot_settings', {}).get('integrate_zero', True)
    show_legend = st.session_state.get('plot_settings', {}).get('show_legend', True)
    
    # Plot chromatograms
    fig_ms = None  # <-- declare outside so we can access it later
    for idx, chrom_id in enumerate(visible_chroms):
        chrom_data = st.session_state.chromatograms[chrom_id]
        proc_data = preprocessed_data[chrom_id] 






#############################





        if chrom_data.get('type') == 'lcms':
            from lcms.cdf_reader import get_mass_spectrum, get_eic
            from lcms.ms_plotter import plot_mass_spectrum, plot_extracted_ion_chromatogram
            
            file_path = chrom_data['file_path']
            



            # 1. ——— TIC slider + vertical line ———
    # 1. ——— TIC slider + vertical line ———
# 1. ——— TIC slider + vertical line ———
            scan_count = len(proc_data['x'])
            default_scan = int(np.argmax(proc_data['y']))

            # PRE-CACHE HACK: Load all MS data at once (one-time cost)
            if f"ms_cache_{chrom_id}" not in st.session_state:
                # Show loading toast
                from utils.toast import show_toast
                show_toast(f"Loading MS data for {chrom_data['name']}...", "info", duration=1)
                
                # Create a placeholder for progress updates
                progress_placeholder = st.empty()
                
                ms_cache = {}
                total_scans = len(range(0, scan_count, 10))
                
                # Only cache every 10th scan to save memory but still be responsive  
                for idx, i in enumerate(range(0, scan_count, 10)):
                    try:
                        # Update progress
                        progress = (idx + 1) / total_scans
                        progress_placeholder.progress(progress, f"Caching scan {i}/{scan_count-1}")
                        
                        mz, intensity = get_mass_spectrum(file_path, i)
                        ms_cache[i] = (mz, intensity)
                    except:
                        pass
                
                # Clear progress bar
                progress_placeholder.empty()
                
                # Store cache
                st.session_state[f"ms_cache_{chrom_id}"] = ms_cache
                

            # Initialize AFTER caching to avoid conflicts
            if f"scan_idx_{chrom_id}" not in st.session_state:
                st.session_state[f"scan_idx_{chrom_id}"] = default_scan

            # Simple slider - DON'T use session state as value, let it be independent
            scan_idx = st.slider(
                "Scan Index",
                0, scan_count - 1,
                value=default_scan,  # Use default_scan directly, not from session state
                step=10,  # Jump by 10s since we cached every 10th
                key=f"cached_scan_{chrom_id}"
            )

            # Always update session state with slider value (no comparison needed)
            st.session_state[f"scan_idx_{chrom_id}"] = scan_idx
            scan_rt = proc_data['x'][scan_idx]

            # Show current values
            #st.write(f"**Scan {scan_idx}** at **{scan_rt:.2f} min** (Step: 10 scans)")

            # 2. ——— MS1 at chosen scan ———







            # 2. ——— MS1 at chosen scan ———
            ##############################
            # 2. ——— MS1 at chosen scan ———
            mz, inten = get_mass_spectrum(file_path, scan_idx)
            fig_ms, cfg = plot_mass_spectrum(mz, inten)

            # Ensure the y-axis is correctly labeled for MS
            fig_ms.update_layout(
                yaxis_title="Relative Abundance (%)"
            )

            st.plotly_chart(fig_ms, use_container_width=True, config=cfg, key=f"ms1_{chrom_id}")

            # store for later use
            st.session_state.mass_spectra = st.session_state.get('mass_spectra', {})
            st.session_state.mass_spectra[chrom_id] = (mz, inten)
            
            # 3. ——— TIC Chromatogram (create and display a TIC figure right here) ———
            
            # Create a temporary TIC figure to display here
            tic_fig = go.Figure()
            
            # Use the same styling as the main figure
            y_to_plot = proc_data['y_smooth'] if use_smooth else proc_data['y']
            
            # Add the main chromatogram trace
            tic_fig.add_trace(go.Scatter(
                x=proc_data['x'], 
                y=y_to_plot, 
                mode="lines", 
                name=chrom_data['name'],
                line=dict(color=chrom_data['color'], width=1.5)
            ))
            
            # Add the scan line 
            # Add the scan line 
            tic_fig.add_vline(
                 x=scan_rt,
                 line=dict(color=chrom_data['color'], width=2, dash='dot'),
                 annotation_text="Scan",
                 annotation_position="top left"
             )
            # Add baseline if integrate_zero is enabled
            if integrate_zero:
                tic_fig.add_trace(go.Scatter(
                    x=proc_data['x'], 
                    y=proc_data['baseline'], 
                    mode="lines", 
                    name=f"{chrom_data['name']} Baseline",
                    line=dict(color=chrom_data['color'], width=1, dash="dash"),
                    showlegend=False
                ))
                
            # Add peaks - with showlegend=False
            if chrom_id in st.session_state.selected_peaks:
                for peak in st.session_state.selected_peaks[chrom_id]:
                    # Add peak area if available
                    if 'Start Index' in peak and 'End Index' in peak:
                        start_idx = peak['Start Index']
                        end_idx = peak['End Index']
                        
                        # Add fill for peak area
                        x_fill = proc_data['x'][start_idx:end_idx+1]
                        y_fill = y_to_plot[start_idx:end_idx+1]
                        
                        # *** use the per-peak RGBA stored in peak['color'] ***
                        peak_rgba = peak.get('color',
                                            # fallback if somehow not set yet:
                                            hex_to_rgba(chrom_data['color'], 0.4))

                        tic_fig.add_trace(go.Scatter(
                            x=x_fill,
                            y=y_fill,
                            fill='tozeroy',
                            fillcolor=peak_rgba,
                            line=dict(color=peak_rgba, width=1),
                            name=peak.get('name', f"Peak {peak['id']}"),
                            showlegend=False
                        ))

                        
                    # Add peak marker if enabled
                    if st.session_state.settings['show_peak_markers'] and 'peak_idx' in peak:
                        peak_idx = peak['peak_idx']
                        tic_fig.add_trace(go.Scatter(
                            x=[proc_data['x'][peak_idx]], 
                            y=[proc_data['y_smooth'][peak_idx]], 
                            mode="markers", 
                            marker=dict(color="red", size=10, symbol="x"),
                            name=f"{peak.get('name', f'Peak {peak["id"]}')} Max",
                            showlegend=False
                        ))
            

            # Apply the same styling as the main figure
            tic_fig.update_layout(
                title="TIC Chromatogram",  # Add the title here
                xaxis_title="Retention Time (min)",
                yaxis_title="Intensity (a.u.)",
                showlegend=show_legend,
                margin=dict(l=50, r=50, t=50, b=50)
            )
                        
            # Apply the same grid settings
            tic_fig.update_xaxes(showgrid=st.session_state.get('plot_settings', {}).get('vertical_grid', False))
            tic_fig.update_yaxes(showgrid=st.session_state.get('plot_settings', {}).get('horizontal_grid', False))
            
            # Apply plot settings and font settings
            if 'apply_plot_settings' in globals():
                tic_fig = apply_plot_settings(tic_fig)
            if 'apply_font_settings' in globals():
                tic_fig = apply_font_settings(tic_fig)
            
            # Display the TIC chromatogram right here
            st.plotly_chart(tic_fig, use_container_width=True, key=f"tic_chrom_{chrom_id}")
            
            # First, store the active tab in session state 
            if f"active_tab_{chrom_id}" not in st.session_state:
                st.session_state[f"active_tab_{chrom_id}"] = "Peak MS" 

            # 4. ——— Tabs: Peak MS | Extracted Ion Chromatogram ———
            # Get the query parameters for tab state
            query_params = st.query_params

            # Initialize active tabs from query params or default
            active_tabs = {}
            if "active_tabs" in query_params:
                try:
                    active_tabs = json.loads(query_params["active_tabs"][0])
                except:
                    active_tabs = {}

            # Function to update query parameters
            def update_query_params(params):
                for key, value in params.items():
                    st.query_params[key] = value

            # Get current active tab from query parameters
            current_active_tab = active_tabs.get(str(chrom_id), "Peak MS")

            # Create the tabs
            tab1, tab2 = st.tabs(["Peak MS", "Extracted Ion Chromatogram"])

            # Inside the Peak MS tab
            with tab1:
                if current_active_tab == "Peak MS":
                    # Peak MS tab content
                    peaks = st.session_state.selected_peaks.get(chrom_id, [])
                    if peaks:
                        # build user‐friendly labels
                        peak_labels = [
                            f"{p.get('name', f'Peak {p['id']}')} @ {proc_data['x'][p['peak_idx']]:.2f} min"
                            for p in peaks
                        ]
                        choice = st.selectbox("Select peak to view", peak_labels, key=f"peak_select_{chrom_id}")

                        # find the dict for the chosen label
                        idx = peak_labels.index(choice)
                        sel_peak = peaks[idx]
                        mz2, inten2 = get_mass_spectrum(file_path, sel_peak['peak_idx'])
                        fig_p, cfg_p = plot_mass_spectrum(
                            mz2, inten2,
                            color=chrom_data['color'],
                            name=sel_peak.get('name', "")
                        )
                        st.plotly_chart(fig_p, use_container_width=True, config=cfg_p)

                    else:
                        st.info("No peaks selected yet. …")
                        


            # Inside the Extracted Ion Chromatogram tab

            # Inside the Extracted Ion Chromatogram tab
            # Inside the Extracted Ion Chromatogram tab
            with tab2:
                # Import datetime at the top
                import datetime
                
                # Parameters row (full width)
                param_col1, param_col2 = st.columns(2)
                
                with param_col1:
                    mz_val = st.number_input(
                        "m/z for XIC", value=441.0, step=0.1,
                        key=f"xic_mz_{chrom_id}"
                    )
                
                with param_col2:
                    mz_tol = st.number_input(
                        "m/z Tolerance (±)", 
                        min_value=0.01, 
                        max_value=1.0, 
                        value=1.0, 
                        step=0.01,
                        key=f"mz_tol_{chrom_id}",
                        help="Width of m/z window to extract ion chromatogram"
                    )
                
                # Default ms_window value (will be used before UI element is created)
                ms_window = 10.0
                
                # Store analysis parameters in session state for documentation
                if f"analysis_params_{chrom_id}" not in st.session_state:
                    st.session_state[f"analysis_params_{chrom_id}"] = {}
                
                # Update parameters
                st.session_state[f"analysis_params_{chrom_id}"].update({
                    "mz_value": float(mz_val),
                    "mz_tolerance": float(mz_tol),
                    "ms_window": float(ms_window),
                    "file_name": chrom_data.get('name', ''),
                    "export_timestamp": datetime.datetime.now().isoformat()
                })
                
                # Get data for XIC
                rt_eic, int_eic = get_eic(file_path, mz_val, tol=mz_tol)
                
                # Find peak apex for default display
                apex_idx = np.argmax(int_eic)
                scan_rt = rt_eic[apex_idx]
                
                # Find the scan index in the original data
                full_scan_idx = np.argmin(np.abs(proc_data['x'] - scan_rt))
                
                # Helper function to get peak bounds
                def get_peak_bounds(rt, intensity, peak_idx, threshold=0.1):
                    """Find start and end indices of a peak based on threshold percentage of max height"""
                    max_intensity = intensity[peak_idx]
                    threshold_value = max_intensity * threshold
                    
                    # Find start index (going backward from apex)
                    start_idx = peak_idx
                    for i in range(peak_idx, 0, -1):
                        if intensity[i] < threshold_value:
                            start_idx = i + 1
                            break
                    
                    # Find end index (going forward from apex)
                    end_idx = peak_idx
                    for i in range(peak_idx, len(intensity)-1):
                        if intensity[i] < threshold_value:
                            end_idx = i - 1
                            break
                    
                    return start_idx, end_idx
                
                # Get peak bounds at 10% of max height
                start_idx, end_idx = get_peak_bounds(rt_eic, int_eic, apex_idx, threshold=0.1)
                
                # Calculate peak width properly
                peak_width = rt_eic[end_idx] - rt_eic[start_idx] if end_idx > start_idx else 0.0
                
                # Store peak information for documentation
                st.session_state[f"analysis_params_{chrom_id}"].update({
                    "peak_apex_rt": float(scan_rt),
                    "peak_start_rt": float(rt_eic[start_idx]),
                    "peak_end_rt": float(rt_eic[end_idx]),
                    "peak_max_intensity": float(int_eic[apex_idx]),
                    "peak_width": float(peak_width)
                })
                
                # Two equal columns for the plots
                col1, col2 = st.columns(2)
                
                with col1:
                    # Plot the XIC with fixed height
                    fig_eic, cfg_eic = plot_extracted_ion_chromatogram(
                        rt=rt_eic,
                        intensity=int_eic,
                        mz_value=mz_val
                    )
                    
                    # Update layout for consistent size
                    fig_eic.update_layout(
                        height=400,
                        margin=dict(l=50, r=50, t=60, b=50)  # Consistent margins
                    )
                    
                    # Add vertical line at apex
                    fig_eic.add_vline(
                        x=scan_rt,
                        line=dict(color='red', width=2, dash='dot'),
                        annotation_text="Peak Max",
                        annotation_position="top"
                    )
                    
                    # Add shading for peak bounds
                    fig_eic.add_shape(
                        type="rect",
                        x0=rt_eic[start_idx],
                        x1=rt_eic[end_idx],
                        y0=0,
                        y1=int_eic[apex_idx],
                        fillcolor="rgba(255, 0, 0, 0.1)",
                        line=dict(width=0),
                    )
                    
                    st.plotly_chart(fig_eic, use_container_width=True, config=cfg_eic, key=f"xic_plot_{chrom_id}")
                    
                    # Extracted Ion Details under the XIC plot
                    st.markdown("### Extracted Ion Details")
                    
                    # Show details stacked vertically
                    st.markdown(f"**m/z Value:** {mz_val:.4f} ± {mz_tol:.4f}")
                    st.markdown(f"**Max Intensity:** {int_eic[apex_idx]:.2e}")
                    st.markdown(f"**RT at Max:** {scan_rt:.2f} min")
                    st.markdown(f"**Peak Width:** {peak_width:.2f} min")

                # Second column: MS plots and controls
                with col2:
                    # Initialize default visualization mode
                    ms_window = st.session_state.get(f"analysis_params_{chrom_id}", {}).get("ms_window", 10.0)

                    if f"viz_mode_{chrom_id}" not in st.session_state:
                        st.session_state[f"viz_mode_{chrom_id}"] = "Apex Only"
                        
                    viz_mode = st.session_state[f"viz_mode_{chrom_id}"]
                    
                    # Convert to boolean flags for processing
                    apex_only = (viz_mode == "Apex Only")
                    avg_peak = (viz_mode == "Average Across Peak")
                    bg_subtract = (viz_mode == "Background Subtraction")
                    enable_click = (viz_mode == "Interactive Selection")
                    
                    # Get MS window slider value FIRST (but don't display it yet)
                    # This is the key change - we get the value but don't render the slider yet
                    if f"ms_window_{chrom_id}" not in st.session_state:
                        st.session_state[f"ms_window_{chrom_id}"] = ms_window
                    ms_window = st.session_state[f"ms_window_{chrom_id}"]
                    
                    # Update session state - this happens before plot creation
                    if f"analysis_params_{chrom_id}" not in st.session_state:
                        st.session_state[f"analysis_params_{chrom_id}"] = {}
                    st.session_state[f"analysis_params_{chrom_id}"]["ms_window"] = float(ms_window)
                    
                    # Flag for interactive mode to show instructions
                    if enable_click:
                        # Small message for interactive mode
                        st.caption("Click on the chromatogram to select a scan")
                        
                        # Handle clicks (simulated for now)
                        # In a real implementation, you'd capture click events
                        # For now, just default to apex
                        clicked_rt = scan_rt
                        clicked_scan_idx = apex_idx
                        
                        # Get selected scan
                        selected_scan_idx = np.argmin(np.abs(proc_data['x'] - rt_eic[clicked_scan_idx]))
                        mz_viz, int_viz = get_mass_spectrum(file_path, selected_scan_idx)
                        viz_title = f"MS at RT={rt_eic[clicked_scan_idx]:.2f} min (selected)"
                        
                        # Record selection
                        st.session_state[f"analysis_params_{chrom_id}"]["selected_scan_rt"] = float(rt_eic[clicked_scan_idx])
                        
                    elif avg_peak or bg_subtract:
                        # Get all scan indices within peak bounds
                        peak_scan_indices = []
                        for i in range(start_idx, end_idx+1):
                            rt = rt_eic[i]
                            scan_idx = np.argmin(np.abs(proc_data['x'] - rt))
                            peak_scan_indices.append(scan_idx)
                        
                        # Skip if no peak detected
                        if not peak_scan_indices:
                            st.warning("No clear peak detected. Using apex scan instead.")
                            mz_viz, int_viz = get_mass_spectrum(file_path, full_scan_idx)
                            viz_title = f"MS at RT={scan_rt:.2f} min (peak apex)"
                        else:
                            # Collect all m/z values from scans in peak
                            all_mz = []
                            all_intensity = []
                            for scan_idx in peak_scan_indices:
                                mz, intensity = get_mass_spectrum(file_path, scan_idx)
                                all_mz.extend(mz)
                                all_intensity.extend(intensity)
                            
                            # Create binned mass spectrum
                            mz_min = max(0, mz_val - ms_window)
                            mz_max = mz_val + ms_window
                            bin_size = 0.01  # m/z bin size
                            bins = np.arange(mz_min, mz_max + bin_size, bin_size)
                            binned_intensity = np.zeros(len(bins)-1)
                            
                            # Assign intensities to bins
                            for mz, intensity in zip(all_mz, all_intensity):
                                if mz_min <= mz <= mz_max:
                                    bin_idx = int((mz - mz_min) / bin_size)
                                    if 0 <= bin_idx < len(binned_intensity):
                                        binned_intensity[bin_idx] += intensity
                            
                            # Get bin centers for x-axis
                            bin_centers = bins[:-1] + bin_size/2
                            
                            # Apply background subtraction if selected
                            if bg_subtract:
                                # Get background scan indices (before and after peak)
                                bg_before = max(0, start_idx - 3)
                                bg_after = min(len(rt_eic)-1, end_idx + 3)
                                bg_scan_indices = []
                                
                                # Before peak
                                for i in range(bg_before, start_idx):
                                    rt = rt_eic[i]
                                    scan_idx = np.argmin(np.abs(proc_data['x'] - rt))
                                    bg_scan_indices.append(scan_idx)
                                
                                # After peak
                                for i in range(end_idx+1, bg_after+1):
                                    rt = rt_eic[i]
                                    scan_idx = np.argmin(np.abs(proc_data['x'] - rt))
                                    bg_scan_indices.append(scan_idx)
                                
                                # Skip if no background scans
                                if not bg_scan_indices:
                                    st.warning("Not enough background scans. Using average without subtraction.")
                                    viz_title = f"Average MS across peak (RT={rt_eic[start_idx]:.2f}-{rt_eic[end_idx]:.2f} min)"
                                    mz_viz, int_viz = bin_centers, binned_intensity
                                else:
                                    # Get background m/z values
                                    bg_mz = []
                                    bg_intensity = []
                                    for scan_idx in bg_scan_indices:
                                        mz, intensity = get_mass_spectrum(file_path, scan_idx)
                                        bg_mz.extend(mz)
                                        bg_intensity.extend(intensity)
                                    
                                    # Bin background data
                                    bg_binned_intensity = np.zeros(len(bins)-1)
                                    for mz, intensity in zip(bg_mz, bg_intensity):
                                        if mz_min <= mz <= mz_max:
                                            bin_idx = int((mz - mz_min) / bin_size)
                                            if 0 <= bin_idx < len(bg_binned_intensity):
                                                bg_binned_intensity[bin_idx] += intensity
                                    
                                    # Normalize by number of scans
                                    if len(bg_scan_indices) > 0:
                                        bg_binned_intensity = bg_binned_intensity / len(bg_scan_indices) * len(peak_scan_indices)
                                    
                                    # Subtract background
                                    binned_intensity = binned_intensity - bg_binned_intensity
                                    binned_intensity[binned_intensity < 0] = 0  # No negative values
                                    
                                    viz_title = f"Background-subtracted MS (RT={rt_eic[start_idx]:.2f}-{rt_eic[end_idx]:.2f} min)"
                                    mz_viz, int_viz = bin_centers, binned_intensity
                            else:
                                viz_title = f"Average MS across peak (RT={rt_eic[start_idx]:.2f}-{rt_eic[end_idx]:.2f} min)"
                                mz_viz, int_viz = bin_centers, binned_intensity
                    else:
                        # Default: apex only
                        mz_peak, int_peak = get_mass_spectrum(file_path, full_scan_idx)
                        
                        # Filter to only show window around the target m/z
                        mask = np.abs(mz_peak - mz_val) <= ms_window
                        mz_viz = mz_peak[mask]
                        int_viz = int_peak[mask]
                        viz_title = f"MS at RT={scan_rt:.2f} min (peak apex)"
                    
                    # Create MS plot with fixed height to match XIC
                    fig_ms_peak, cfg_ms_peak = plot_mass_spectrum(
                        mz_viz, int_viz,
                        color='#ff7f0e',
                        name=viz_title,
                    )
                    fig_ms_peak.update_layout(
                        height=400,
                        margin=dict(l=50, r=50, t=60, b=50),
                        yaxis_title="Relative Abundance (%)"  # Force correct label for MS
                    )
                    fig_ms_peak.add_vline(
                        x=mz_val,
                        line=dict(color='red', width=2, dash='dot'),
                        annotation_text=f"m/z = {mz_val:.2f}",
                        annotation_position="top"
                    )
                    st.plotly_chart(fig_ms_peak, use_container_width=True, config=cfg_ms_peak)

                    # NOW we display the slider visually, but use value from earlier
                    ms_window_new = st.slider(
                        "MS Display Window (±m/z)",
                        min_value=1.0,
                        max_value=50.0,
                        value=ms_window,
                        step=1.0,
                        key=f"ms_window_ui_{chrom_id}",  # Different key for UI element
                        help="Width of m/z window to display in mass spectrum"
                    )
                    
                    # Check if slider changed and update session state
                    if ms_window_new != ms_window:
                        st.session_state[f"ms_window_{chrom_id}"] = ms_window_new
                        st.rerun()  # Trigger rerun to update the plot with new window

                    # Update session state
                    st.session_state[f"analysis_params_{chrom_id}"]["ms_window"] = float(ms_window)

                    # MS Display Mode: single mutually exclusive control with context help
                    st.markdown("### MS Display Mode")

                    # Define help texts for each mode correctly using triple quotes
                    apex_help = (
                        """
                        Shows mass spectrum at the peak apex (highest intensity point). Best for clean, well-resolved peaks
                        with high signal-to-noise ratio. Provides the most direct representation of the compound's mass spectrum
                        at its highest concentration.
                        """
                    )
                    avg_help = (
                        """
                        Combines mass spectra across the entire chromatographic peak. Improves signal-to-noise ratio for
                        low-abundance compounds. Particularly useful for noisy data or when working with samples near the
                        detection limit.
                        """
                    )
                    bg_help = (
                        """
                        Averages mass spectra across the peak and subtracts background. Best for samples with chemical noise,
                        column bleed, or co-eluting contaminants. The algorithm uses scans before and after the peak to estimate
                        background contribution.
                        """
                    )
                    interactive_help = (
                        """
                        Click on any point in the chromatogram to see its spectrum. Useful for exploring co-eluting compounds
                        or examining peak purity across the elition profile. Particularly valuable for complex samples with
                        overlapping peaks.
                        """
                    )

                    help_texts = {
                        "Apex Only": apex_help,
                        "Average Across Peak": avg_help,
                        "Background Subtraction": bg_help,
                        "Interactive Selection": interactive_help
                    }

                    modes = [
                        "Apex Only",
                        "Average Across Peak",
                        "Background Subtraction",
                        "Interactive Selection"
                    ]
                    viz_mode = st.radio(
                        "",
                        modes,
                        index=modes.index(st.session_state.get(f"viz_mode_{chrom_id}", "Apex Only")),
                        key=f"viz_mode_{chrom_id}",
                        horizontal=True
                    )

                    # Display context-specific helper text
                    st.caption(help_texts.get(viz_mode, ""))

                    # Update boolean flags based on selection
                    apex_only = (viz_mode == "Apex Only")
                    avg_peak = (viz_mode == "Average Across Peak")
                    bg_subtract = (viz_mode == "Background Subtraction")
                    enable_click = (viz_mode == "Interactive Selection")
                
                # Add CSS to hide the button

#############
        proc_data = preprocessed_data[chrom_id]
        
        # Choose data to plot based on smoothing setting
        y_to_plot = proc_data['y_smooth'] if use_smooth else proc_data['y']
        
        # For separate plots, use subplot, otherwise use main figure
        if use_separate_plots:
            # Current subplot row index (1-based)
            row_idx = idx + 1
            
            # Add the main chromatogram trace to the appropriate subplot
            fig.add_trace(go.Scatter(
                x=proc_data['x'], 
                y=y_to_plot, 
                mode="lines", 
                name=chrom_data['name'],
                line=dict(color=chrom_data['color'], width=1.5),
                showlegend=show_legend  # Use the global legend setting - Show in legend!
            ), row=row_idx, col=1)
            
            # Add baseline if integrate_zero is enabled
            if integrate_zero:
                fig.add_trace(go.Scatter(
                    x=proc_data['x'], 
                    y=proc_data['baseline'], 
                    mode="lines", 
                    name=f"{chrom_data['name']} Baseline",
                    line=dict(color=chrom_data['color'], width=1, dash="dash"),
                    showlegend=False  # Don't show baselines in legend
                ), row=row_idx, col=1)
            
            # Add peaks
            if chrom_id in st.session_state.selected_peaks:
                for peak in st.session_state.selected_peaks[chrom_id]:
                    # Add peak area if available
                    if 'Start Index' in peak and 'End Index' in peak:
                        start_idx = peak['Start Index']
                        end_idx = peak['End Index']
                        
                        # Add fill for peak area
                        x_fill = proc_data['x'][start_idx:end_idx+1]
                        y_fill = y_to_plot[start_idx:end_idx+1]
                        
                        # For separate plots
                        peak_color = peak.get('color', hex_to_rgba(chrom_data['color'], 0.4))
                        line_color = chrom_data['color']  

                        fig.add_trace(go.Scatter(
                            x=x_fill, 
                            y=y_fill, 
                            fill='tozeroy', 
                            fillcolor=peak_color, 
                            line=dict(color=line_color, width=1),  
                            name=peak.get('name', f"Peak {peak['id']}"),
                            showlegend=False
                        ), row=row_idx, col=1)


                    if st.session_state.settings['show_peak_markers'] and 'peak_idx' in peak:
                        peak_idx = peak['peak_idx']
                        fig.add_trace(go.Scatter(
                            x=[proc_data['x'][peak_idx]], 
                            y=[proc_data['y_smooth'][peak_idx]], 
                            mode="markers", 
                            marker=dict(color="red", size=10, symbol="x"),
                            name=f"{peak.get('name', f'Peak {peak["id"]}')} Max",
                            showlegend=False
                        ), row=row_idx, col=1)
        else:
            # For combined plot - add everything to the main figure
            # Add the main chromatogram trace
            fig.add_trace(go.Scatter(
                x=proc_data['x'], 
                y=y_to_plot, 
                mode="lines", 
                name=chrom_data['name'],
                line=dict(color=chrom_data['color'], width=1.5),
                showlegend=show_legend
            ))
            
            # Add baseline if integrate_zero is enabled
            if integrate_zero:
                fig.add_trace(go.Scatter(
                    x=proc_data['x'], 
                    y=proc_data['baseline'], 
                    mode="lines", 
                    name=f"{chrom_data['name']} Baseline",
                    line=dict(color=chrom_data['color'], width=1, dash="dash"),
                    showlegend=False
                ))
            
            # Add peaks - with showlegend=False
            if chrom_id in st.session_state.selected_peaks:
                for peak in st.session_state.selected_peaks[chrom_id]:
                    # Add peak area if available
                    if 'Start Index' in peak and 'End Index' in peak:
                        start_idx = peak['Start Index']
                        end_idx = peak['End Index']
                        
                        # Add fill for peak area
                        x_fill = proc_data['x'][start_idx:end_idx+1]
                        y_fill = y_to_plot[start_idx:end_idx+1]
                        
                        peak_color = peak.get('color', hex_to_rgba(chrom_data['color'], 0.4))
                        peak_line_color = hex_to_rgba(peak.get('hex_color', chrom_data['color']), 1.0)
                        line_color = chrom_data['color']  # Use the chromatogram's color

                        fig.add_trace(go.Scatter(
                            x=x_fill, 
                            y=y_fill, 
                            fill='tozeroy', 
                            fillcolor=peak_color,  # Use peak's color
                            line=dict(color=line_color, width=1),  # Use peak's line color
                            name=peak.get('name', f"Peak {peak['id']}"),
                            showlegend=False
                        ))
                        
                    # Add peak marker if enabled
                    if st.session_state.settings['show_peak_markers'] and 'peak_idx' in peak:
                        peak_idx = peak['peak_idx']
                        fig.add_trace(go.Scatter(
                            x=[proc_data['x'][peak_idx]], 
                            y=[proc_data['y_smooth'][peak_idx]], 
                            mode="markers", 
                            marker=dict(color="red", size=10, symbol="x"),
                            name=f"{peak.get('name', f'Peak {peak["id"]}')} Max",
                            showlegend=False
                        ))



    # Make legend more flexible and draggable
    # Update layout with better legend and title


    # Add title as a separate annotation
    fig.add_annotation(
        text=plot_config.get('title', 'Chromatogram Analysis'),
        x=0.05,
        y=1.02,
        xref="paper",
        yref="paper",
        font=dict(size=font_settings.get('title_fs', 24)),
        showarrow=False,
        xanchor="center",
        yanchor="bottom"
    )

    
    # Apply plot settings
    from ui.plot_settings import apply_plot_settings
    fig = apply_plot_settings(fig)

# REPLACE WITH:

    # NEW: Apply smart axis ranges with debug
    print("📊 About to apply axis ranges to figure")
    apply_axis_ranges(fig, plotly_events)
    print("📊 Finished applying axis ranges")


    # Apply font settings
    from ui.fonts_labels import apply_font_settings
    fig = apply_font_settings(fig)




    
    # Make sure grid is really off if set to False
    horizontal_grid = st.session_state.get('plot_settings', {}).get('horizontal_grid', False)
    vertical_grid   = st.session_state.get('plot_settings', {}).get('vertical_grid',   False)
    
    # Add consistent grid settings across all subplots
    if use_separate_plots:
        for i in range(1, len(visible_chroms) + 1):
            fig.update_xaxes(showgrid=vertical_grid,   row=i, col=1)
            fig.update_yaxes(showgrid=horizontal_grid, row=i, col=1)
    else:
        fig.update_xaxes(showgrid=vertical_grid)
        fig.update_yaxes(showgrid=horizontal_grid)
    

    # Store for possible export
    st.session_state.current_figure = fig

    # Get saved legend position with strong defaults
    legend_pos = st.session_state.get('plot_config', {}).get('legend_position', {'x': 0.99, 'y': 0.9})


    # Apply ONLY legend settings to avoid disrupting other layout aspects
    fig.update_layout( title=dict(text=""))  # Empty title to avoid duplication

    # Print debug info (optional, remove when working)
    print(f"Setting legend position to x={legend_pos['x']}, y={legend_pos['y']}")




    if return_fig:
        return fig



    else:
        # For LCMS files, we've already displayed a dedicated TIC chromatogram,
        # so don't display the main figure again
        if not any(st.session_state.chromatograms.get(chrom_id, {}).get('type') == 'lcms' 
                for chrom_id in visible_chroms):
            # ——— Editable Main Chromatogram ———
            fig, cfg = make_titles_editable(fig)
            
            # Add ability to drag the legend

            cfg.update({
                'editable': True,
                'showAxisDragHandles': True,
                'showTips': True,
                'displayModeBar': True,
                'modeBarButtonsToAdd': ['drawline', 'drawopenpath', 'eraseshape'],
                'toImageButtonOptions': {
                    'format': 'png', 
                    'filename': 'chromatogram',
                    'height': 800,
                    'width': 1200,
                    'scale': 2
                }
            })
        

            # Skip displaying the TIC header a second time if we've already shown it
            if st.session_state.get('suppress_tic_header', False):
                st.session_state.pop('suppress_tic_header', None)
            else:
                st.subheader("Chromatogram Analysis")
            


            st.plotly_chart(
                fig,
                use_container_width=True,
                config=cfg,
                key="chrom_main"
            )

def add_peak_to_plot(fig, peak, proc_data, chrom_data):
    """
    Add a peak to an existing plot.
    
    Parameters:
    -----------
    fig : plotly.graph_objects.Figure
        Figure to add the peak to
    peak : dict
        Peak information dictionary
    proc_data : dict
        Processed data for the chromatogram
    chrom_data : dict
        Chromatogram information
        
    Returns:
    --------
    None
    """
    start_idx = peak['Start Index']
    end_idx = peak['End Index']
    peak_idx = peak['peak_idx']
    
    # Add fill for the peak area with the peak's color
    x_fill = proc_data['x'][start_idx:end_idx+1]
    y_fill = proc_data['y_smooth'][start_idx:end_idx+1]
    

    peak_color = peak.get('color', hex_to_rgba(chrom_data['color'], 0.4))
    peak_line_color = hex_to_rgba(peak.get('hex_color', chrom_data['color']), 1.0)
    line_color = chrom_data['color']  # Use the chromatogram's color


    fig.add_trace(go.Scatter(
        x=x_fill, 
        y=y_fill, 
        fill='tozeroy', 
        fillcolor=peak_color,  # Use peak's color
        line=dict(color=line_color, width=1),  # Use peak's line color
        name=peak.get('name', f"Peak {peak['id']}"),
        showlegend=False
    ))
    
    # Add peak marker (optional)
    if st.session_state.settings['show_peak_markers']:
        fig.add_trace(go.Scatter(
            x=[proc_data['x'][peak_idx]], 
            y=[proc_data['y_smooth'][peak_idx]], 
            mode="markers", 
            marker=dict(color="red", size=10, symbol="x"),
            name=f"{peak.get('name', f'Peak {peak['id']}')} Max",
            showlegend=False
        ))
    
    # Add vertical lines at boundaries
    fig.add_shape(
        type="line",
        x0=proc_data['x'][start_idx], y0=0, 
        x1=proc_data['x'][start_idx], y1=proc_data['y_smooth'][peak_idx],
        fillcolor=hex_to_rgba(chrom_data['color'], 0.3),
        line=dict(color=hex_to_rgba(chrom_data['color'], 1.0), width=1)
    )
    
    fig.add_shape(
        type="line",
        x0=proc_data['x'][end_idx], y0=0, 
        x1=proc_data['x'][end_idx], y1=proc_data['y_smooth'][peak_idx],
        fillcolor=hex_to_rgba(chrom_data['color'], 0.3),
        line=dict(color=hex_to_rgba(chrom_data['color'], 1.0), width=1)
    )

def plot_calibration_curve(x_data, y_data, sample_names, x_curve, y_curve, 
                          current_points=None, model_info=None, units='µg/mL'):
    """
    Create a calibration curve plot with larger fonts for better readability.
    """
    import plotly.graph_objects as go
    import numpy as np
    
    # Create plot
    fig = go.Figure()
    
    # Add calibration standard data points
    if len(x_data) > 0 and len(y_data) > 0:
        fig.add_trace(go.Scatter(
            x=x_data,
            y=y_data,
            mode='markers',
            name='Calibration Standards',
            marker=dict(color='blue', size=12),  # Slightly larger markers
            customdata=sample_names,
            hovertemplate='Concentration: %{x:.2f} ' + units + 
                          '<br>Area: %{y:.2f} a.u.·min<br>Sample: %{customdata}<extra></extra>'
        ))
    
    # Add the calibration curve
    if len(x_curve) > 0 and len(y_curve) > 0:
        fig.add_trace(go.Scatter(
            x=x_curve,
            y=y_curve,
            mode='lines',
            name='Calibration Curve',
            line=dict(color='red', width=3),  # Thicker line
            hovertemplate='Concentration: %{x:.2f} ' + units + 
                          '<br>Predicted Area: %{y:.2f} a.u.·min<extra></extra>'
        ))
    
    # Add current samples to the plot if provided
    if current_points and 'areas' in current_points and 'concentrations' in current_points:
        if len(current_points['concentrations']) > 0 and len(current_points['areas']) > 0:
            fig.add_trace(go.Scatter(
                x=current_points['concentrations'],
                y=current_points['areas'],
                mode='markers',
                name='Current Samples',
                marker=dict(color='green', size=12, symbol='diamond'),  # Larger markers
                customdata=current_points.get('sample_names', ['']*len(current_points['areas'])),
                hovertemplate='Calculated Concentration: %{x:.2f} ' + units + 
                            '<br>Area: %{y:.2f} a.u.·min<br>Sample: %{customdata}<extra></extra>'
            ))
    
    # Calculate ranges that include zero and all data points
    all_x = []
    if len(x_data) > 0:
        all_x.extend(x_data)
    if len(x_curve) > 0:
        all_x.extend(x_curve)
    if current_points and 'concentrations' in current_points and len(current_points['concentrations']) > 0:
        all_x.extend(current_points['concentrations'])
        
    all_y = []
    if len(y_data) > 0:
        all_y.extend(y_data)
    if len(y_curve) > 0:
        all_y.extend(y_curve)
    if current_points and 'areas' in current_points and len(current_points['areas']) > 0:
        all_y.extend(current_points['areas'])
    
    # Set ranges with origin included
    x_min = 0
    x_max = max(all_x) * 1.05 if all_x else 1
    y_min = 0
    y_max = max(all_y) * 1.05 if all_y else 1
    
    # Define font sizes
    title_font_size = 30        # Plot title
    axis_title_font_size = 24   # X and Y axis titles
    tick_font_size = 20         # Tick labels
    legend_font_size = 18       # Legend text
    formula_font_size = 20      # Formula annotation
    
    # Set title with model name if available
    title = "Calibration Curve"
    if model_info and 'name' in model_info:
        title += f": {model_info['name']}"
    

    # Add annotation for formula and R²
    if model_info:
        formula_text = model_info.get('formula', "")
        r_squared = model_info.get('r_squared', 0)
        std_error = model_info.get('std_error', 0)
        
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.02, y=0.98,
            text=f"{formula_text}<br>R² = {r_squared:.4f}<br>Std Error = {std_error:.4g}",
            showarrow=False,
            font=dict(size=formula_font_size),
            align="left",
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="black",
            borderwidth=1,
            borderpad=4
        )
    
    return fig

def render_chromatogram_view(preprocessed_data):
    """
    Render the chromatogram view tab.
    
    Parameters:
    -----------
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
    
    Returns:
    --------
    None
    """
    # Plot controls
    controls_col1, controls_col2 = st.columns([1, 1])
    
    with controls_col1:
        # Toggle baseline visibility
        show_baseline = st.checkbox(
            "Show Baseline", 
            value=st.session_state.get('show_baseline', False),
            key="show_baseline_cb"
        )
        if 'show_baseline' not in st.session_state or st.session_state.show_baseline != show_baseline:
            st.session_state.show_baseline = show_baseline
            # No need to rerun as checkbox state changes are handled by Streamlit
    
    with controls_col2:
        # Other plot controls can be added here
        plot_height = st.slider(
            "Plot Height", 
            min_value=300, 
            max_value=1000, 
            value=st.session_state.get('plot_height', 500),
            key="plot_height_slider"
        )
        if 'plot_height' not in st.session_state or st.session_state.plot_height != plot_height:
            st.session_state.plot_height = plot_height
    
    # Plot the chromatograms
    plot_chromatograms(preprocessed_data)
    
    # Optional: Add download options
    with st.expander("Export Options"):
        col1, col2 = st.columns(2)
        
        with col1:
            export_format = st.selectbox(
                "Export Format",
                options=["PNG", "SVG", "CSV"],
                index=0,
                key="export_format_select"
            )
        
        with col2:
            if st.button("Export", key="export_button"):
                if export_format == "CSV":
                    # Logic for CSV export
                    st.success("CSV export would happen here")
                    from utils.toast import show_toast
                    show_toast("Data exported as CSV", "success")
                else:
                    # Logic for image export
                    st.info(f"Use the plotly export tools to save as {export_format}")
                    from utils.toast import show_toast
                    show_toast(f"Use plot toolbar to export as {export_format}", "info")

def plot_residuals(x_data, y_data, predict_area, sample_names=None, units='µg/mL'):
    """
    Create a residuals plot for a calibration curve with larger fonts.
    
    Parameters:
    -----------
    x_data : array-like
        Concentration values
    y_data : array-like
        Measured area values
    predict_area : function
        Function to predict area from concentration
    sample_names : list, optional
        Names of samples (default: None)
    units : str, optional
        Concentration units (default: 'µg/mL')
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The residuals plot figure
    """
    import plotly.graph_objects as go
    import numpy as np
    
    # Calculate predicted values and residuals
    y_pred = np.array([predict_area(x) for x in x_data])
    residuals = y_data - y_pred
    
    # Create plot
    fig = go.Figure()
    
    # Add residuals as scatter points
    fig.add_trace(go.Scatter(
        x=x_data,
        y=residuals,
        mode='markers',
        name='Residuals',
        marker=dict(color='blue', size=12),  # Larger markers
        customdata=sample_names if sample_names else [f"Standard {i+1}" for i in range(len(x_data))],
        hovertemplate='Concentration: %{x:.2f} ' + units + 
                       '<br>Residual: %{y:.2f} a.u.·min<br>Sample: %{customdata}<extra></extra>'
    ))
    
    # Add zero line
    fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=max(x_data) * 1.05 if len(x_data) > 0 else 1,
        y1=0,
        line=dict(color="red", width=3, dash="dash"),  # Thicker zero line
    )
    
    # Calculate axis ranges
    x_min = 0  # Start from zero for concentration
    x_max = max(x_data) * 1.05 if len(x_data) > 0 else 1
    
    # For y-axis, include zero and the full range of residuals
    if len(residuals) > 0:
        y_min = min(0, min(residuals)) - abs(min(residuals)) * 0.05
        y_max = max(0, max(residuals)) + abs(max(residuals)) * 0.05
    else:
        y_min = -0.1
        y_max = 0.1
    
    # Define font sizes - same as in calibration plot
    title_font_size = 30
    axis_title_font_size = 24
    tick_font_size = 20
    legend_font_size = 18
    
    # Update layout with larger fonts
    fig.update_layout(
        title=dict(
            text="Residuals Plot",
            font=dict(size=title_font_size)
        ),
        xaxis=dict(
            title=dict(
                text=f"Concentration ({units})",
                font=dict(size=axis_title_font_size)
            ),
            tickfont=dict(size=tick_font_size),
            range=[x_min, x_max],
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='gray'
        ),
        yaxis=dict(
            title=dict(
                text="Residual (Measured - Predicted)",
                font=dict(size=axis_title_font_size)
            ),
            tickfont=dict(size=tick_font_size),
            range=[y_min, y_max],
            zeroline=True,
            zerolinewidth=2,
            zerolinecolor='gray'
        ),
        hovermode="closest",
        legend=dict(
            font=dict(size=legend_font_size)
        ),
        margin=dict(t=100, l=100, b=100, r=40),  # More margin for larger fonts
        height=600,  # Taller plot
        width=800    # Wider plot
    )
    
    return fig