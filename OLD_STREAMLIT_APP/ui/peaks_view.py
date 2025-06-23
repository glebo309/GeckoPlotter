# ui/peaks_view.py


import streamlit as st
import pandas as pd
from models.calibration import group_peaks_by_retention_time
from ui.sidebar import hex_to_rgba, rgba_to_hex

def render_peak_results(preprocessed_data):
    """
    Render the Peak Results view for comparing peaks across samples.
    
    Parameters:
    -----------
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
        
    Returns:
    --------
    None
    """
    if any(len(peaks) > 0 for peaks in st.session_state.selected_peaks.values()):
        st.header("Compare Across Samples", divider=True)
        
        # Store previous time window value 
        prev_time_window = st.session_state.get('peak_matching_window', 0.2)
        
        # Set a time window for matching peaks (in minutes)
        time_window = st.slider(
            "Peak Matching Time Window (min)", 
            min_value=0.05, 
            max_value=1.0, 
            value=prev_time_window,
            step=0.05,
            help="Peaks with midpoints closer than this value will be considered the same compound across samples"
        )

        # Store the window value in session state
        st.session_state.peak_matching_window = time_window

        # Check if the slider changed and needs to trigger recoloring
        if prev_time_window != time_window:
            # Flag that we need to update peak colors
            if 'selected_peaks' in st.session_state and st.session_state.selected_peaks:
                # Use explicitly imported function from top of file
                import importlib
                
                try:
                    # Get the current color palette function
                    colourmaps = importlib.import_module("utils.colourmaps")
                    palette_name = st.session_state.plot_settings.get('color_palette_function', 'get_color_from_palette')
                    palette_func = getattr(colourmaps, palette_name)
                    
                    # Collect all peaks for grouping
                    all_peaks = []
                    for chrom_id, peaks in st.session_state.selected_peaks.items():
                        for peak in peaks:
                            peak_info = {
                                'chromatogram_id': chrom_id,
                                'peak': peak,
                                'midpoint': peak['Midpoint (min)']
                            }
                            all_peaks.append(peak_info)
                    
                    # Group peaks using the updated time window
                    from models.calibration import group_peaks_by_retention_time as gpbrt
                    peak_groups = gpbrt(all_peaks, time_window)
                    
                    # Update colors based on the new grouping
                    for group_idx, group in enumerate(peak_groups):
                        # Calculate color for this group - use a prime number distribution
                        color_idx = (group_idx * 17) % 50
                        rgb = palette_func(color_idx)
                        
                        # Get hex color
                        if rgb is None:
                            hex_color = "#888888"  # Fallback color
                        else:
                            r, g, b = rgb
                            hex_color = f"#{r:02X}{g:02X}{b:02X}"
                        
                        # Apply this color to all peaks in the group
                        for peak_info in group:
                            peak = peak_info['peak']
                            opacity = peak.get('opacity', 0.4)
                            peak['hex_color'] = hex_color
                            peak['color'] = hex_to_rgba(hex_color, opacity)
                    
                    # Force plot redraw
                    st.session_state['force_redraw'] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating peak colors: {e}")

        # Collect all peaks from all chromatograms
        all_peaks = []
        for chrom_id, peaks in st.session_state.selected_peaks.items():
            for peak in peaks:
                peak_info = {
                    'chromatogram_id': chrom_id,
                    'chromatogram_name': st.session_state.chromatograms[chrom_id]['name'],
                    'peak_id': peak['id'],
                    'peak_name': peak.get('name', f"Peak {peak['id']}"),
                    'midpoint': peak['Midpoint (min)'],
                    'height': peak['Height (a.u.)'],
                    'area': peak['Area (a.u.·min)'],
                    'width': peak['Width (min)'],
                    'width_hh': peak['Width at Half-Height (min)']
                }
                all_peaks.append(peak_info)
        
        # Use a different name to prevent any confusion with imports
        from models.calibration import group_peaks_by_retention_time as gpbrt
        peak_groups = gpbrt(all_peaks, time_window)
        
        # Rest of your function...









        # Group peaks by retention time
        peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
        
        # Filter out groups with only one peak (no comparison possible)
        comparison_groups = [group for group in peak_groups if len(group) > 1]
        single_peaks = [group[0] for group in peak_groups if len(group) == 1]
        
        # Display a selector for the peak groups
        if comparison_groups:
            # Create a readable name for each peak group
            group_names = []
            for i, group in enumerate(comparison_groups):
                avg_time = sum(p['midpoint'] for p in group) / len(group)
                samples = sorted(set(p['chromatogram_name'] for p in group))
                samples_str = ', '.join(samples)
                group_names.append(f"Group {i+1}: {avg_time:.2f} min - Found in {len(group)} samples ({samples_str})")
            
            # Let user select which group to compare
            selected_group_idx = st.selectbox(
                "Select Peak Group to Compare",
                options=range(len(comparison_groups)),
                format_func=lambda i: group_names[i]
            )
            
            selected_group = comparison_groups[selected_group_idx]
            
            # Get all chromatogram IDs that have samples
            all_chrom_ids = sorted(st.session_state.chromatograms.keys())
            
            # Create comparison table
            comparison_data = []
            
            # Get available calibration models for quantification
            available_calibrations = {}
            if 'calibration_models' in st.session_state:
                available_calibrations = st.session_state.calibration_models
            
            # Check if there's a calibration for this peak group
            matching_cal = None
            for cal_id, cal_model in available_calibrations.items():
                if abs(selected_group[0]['midpoint'] - cal_model['rt']) < 0.2:  # Within 0.2 min
                    matching_cal = cal_model
                    break
            
            for chrom_id in all_chrom_ids:
                if chrom_id not in st.session_state.chromatograms:
                    continue
                
                chrom_name = st.session_state.chromatograms[chrom_id]['name']
                
                # Find a peak from this chromatogram in the selected group
                matching_peak = next((p for p in selected_group if p['chromatogram_id'] == chrom_id), None)
                
                if matching_peak:
                    # Calculate the total area for this chromatogram for percentage
                    total_area = sum(p.get('area', 0) for p in all_peaks if p['chromatogram_id'] == chrom_id)
                    
                    comparison_row = {
                        "Sample": chrom_name,
                        "Peak Name": matching_peak['peak_name'],
                        "Midpoint (min)": matching_peak['midpoint'],
                        "Height (a.u.)": matching_peak['height'],
                        "Area (a.u.·min)": matching_peak['area'],
                        "Area %": (matching_peak['area'] / total_area) * 100 if total_area > 0 else 0,
                        "Width (min)": matching_peak['width'],
                        "Width at Half-Height (min)": matching_peak['width_hh']
                    }
                    
                    # Add quantification if calibration exists
                    if matching_cal:
                        # Calculate concentration
                        concentration = matching_cal['predict_concentration'](matching_peak['area'])
                        
                        # Add to comparison data
                        comparison_row["Calibration"] = matching_cal['name']
                        comparison_row[f"Concentration ({matching_cal['units']})"] = concentration
                    
                    comparison_data.append(comparison_row)
                else:
                    # Add an empty row for this chromatogram
                    comparison_row = {
                        "Sample": chrom_name,
                        "Peak Name": "Not detected",
                        "Midpoint (min)": None,
                        "Height (a.u.)": None,
                        "Area (a.u.·min)": None,
                        "Area %": None,
                        "Width (min)": None,
                        "Width at Half-Height (min)": None
                    }
                    
                    # Add placeholder for calibration info
                    if matching_cal:
                        comparison_row["Calibration"] = matching_cal['name']
                        comparison_row[f"Concentration ({matching_cal['units']})"] = None
                    
                    comparison_data.append(comparison_row)
            
            if comparison_data:
                # Display the data
                df = pd.DataFrame(comparison_data)
                st.dataframe(df)
                
                # Add download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label=f"Download Comparison for Group {selected_group_idx+1} as CSV",
                    data=csv,
                    file_name=f"peak_group_{selected_group_idx+1}_comparison.csv",
                    mime="text/csv",
                )
        
        else:
            st.info("No matching peaks found across different samples. Try adjusting the time window or adding more peaks.")
            if single_peaks:
                st.write(f"Found {len(single_peaks)} peaks that only appear in one sample.")
                
                # Show the single peaks
                single_data = []
                for peak in single_peaks:
                    single_data.append({
                        "Sample": peak['chromatogram_name'],
                        "Peak Name": peak['peak_name'],
                        "Midpoint (min)": peak['midpoint']
                    })
                
                st.dataframe(pd.DataFrame(single_data))
    else:
        st.info("No peaks detected yet. Add peaks using the sidebar controls to compare them across samples.")

def render_peak_analysis(preprocessed_data):
    # you can just delegate to render_peak_results for now
    render_peak_results(preprocessed_data)


def edit_peak_properties():
    active = st.session_state.active_chromatogram
    base_rgba = st.session_state.chromatograms[active]['color']
    # strip alpha → #RRGGBB
    base_hex = rgba_to_hex(base_rgba)

    peaks = st.session_state.selected_peaks.get(active, [])
    for peak in peaks:
        st.markdown(f"---\n### Peak {peak['id']} Properties")
        col1, col2 = st.columns([0.6, 0.4])

        # ensure defaults exist
        peak.setdefault('hex_color', base_hex)
        peak.setdefault('opacity', 0.4)

        with col1:
            new_hex = st.color_picker(
                "Peak colour",
                value=peak['hex_color'],
                key=f"peak_hex_{active}_{peak['id']}"
            )
        with col2:
            new_op = st.slider(
                "Opacity",
                min_value=0.0, max_value=1.0, step=0.05,
                value=peak['opacity'],
                key=f"peak_op_{active}_{peak['id']}"
            )

        # write back into the peak dict
        peak['hex_color'] = new_hex
        peak['opacity']   = new_op
        # recombine into full rgba for plotting
        peak['color']     = hex_to_rgba(new_hex, new_op)
