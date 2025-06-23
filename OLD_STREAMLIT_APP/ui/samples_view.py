# ui/samples_view.py
import streamlit as st
import pandas as pd

def render_sample_results(active_chrom, preprocessed_data):
    """
    Render the Sample Results view showing peaks for the active chromatogram.
    
    Parameters:
    -----------
    active_chrom : int
        ID of the active chromatogram
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
        
    Returns:
    --------
    None
    """
    # Show peaks only for the active chromatogram
    if active_chrom in st.session_state.selected_peaks and len(st.session_state.selected_peaks[active_chrom]) > 0:
        st.header(f"Sample Results: {st.session_state.chromatograms[active_chrom]['name']}", divider=True)
        
        # Create a clean version of the DataFrame for display (active sample-focused)
        sample_results = []
        
        # Calculate total area for this chromatogram
        total_area = sum(p.get('Area (a.u.·min)', 0) for p in st.session_state.selected_peaks[active_chrom])
        
        # Get available calibration models for quantification
        available_calibrations = {}
        if 'calibration_models' in st.session_state:
            available_calibrations = st.session_state.calibration_models
        
        for peak in st.session_state.selected_peaks[active_chrom]:
            # Basic peak properties
            result_row = {
                "Peak Name": peak.get('name', f"Peak {peak['id']}"),
                "Peak ID": peak['id'],
                "Midpoint (min)": peak['Midpoint (min)'],
                "Height (a.u.)": peak['Height (a.u.)'],
                "Area (a.u.·min)": peak['Area (a.u.·min)'],
                "Area %": (peak['Area (a.u.·min)'] / total_area) * 100 if total_area > 0 else 0,
                "Width (min)": peak['Width (min)'],
                "Width at Half-Height (min)": peak['Width at Half-Height (min)']
            }
            
            # Check if there's a calibration for this peak
            matching_cal = None
            for cal_id, cal_model in available_calibrations.items():
                if abs(peak['Midpoint (min)'] - cal_model['rt']) < 0.2:  # Within 0.2 min
                    matching_cal = cal_model
                    break
            
            # Add quantification if calibration exists
            if matching_cal:
                # Calculate concentration
                concentration = matching_cal['predict_concentration'](peak['Area (a.u.·min)'])
                
                # Add to results
                result_row["Calibration"] = matching_cal['name']
                result_row[f"Concentration ({matching_cal['units']})"] = concentration
            
            sample_results.append(result_row)
        
        if sample_results:
            df = pd.DataFrame(sample_results)
            st.dataframe(df)
            
    else:
        st.info(f"No peaks found for {st.session_state.chromatograms[active_chrom]['name']}. Use the sidebar to add peaks.")

def edit_peak_properties():
    """
    Render the peak properties editor that allows editing names, colors, etc.
    """
    if any(len(peaks) > 0 for peaks in st.session_state.selected_peaks.values()):
        with st.container():  # ✅ replace expander
            st.markdown("### Peak Properties")  # ✅ add visible title

            all_peaks = []
            for chrom_id, peaks in st.session_state.selected_peaks.items():
                for peak in peaks:
                    peak_with_chrom = peak.copy()
                    peak_with_chrom['chromatogram_id'] = chrom_id
                    all_peaks.append(peak_with_chrom)
            all_peaks.sort(key=lambda p: p['id'])

            if all_peaks:
                tab_labels = [f"{p.get('name', f'Peak {p['id']}')}" for p in all_peaks]
                peak_tabs = st.tabs(tab_labels)

                for i, (peak, tab) in enumerate(zip(all_peaks, peak_tabs)):
                    with tab:
                        chrom_id = peak['chromatogram_id']
                        chrom_name = st.session_state.chromatograms[chrom_id]['name']

                        col1, col2 = st.columns([1, 1])

                        with col1:
                            st.write(f"**Sample:** {chrom_name}")
                            st.write(f"**Midpoint:** {peak['Midpoint (min)']:.2f} min")
                            st.write(f"**Height:** {peak['Height (a.u.)']:.1f} a.u.")
                            st.write(f"**Width:** {peak['Width (min)']:.4f} min")
                            st.write(f"**Width at Half-Height:** {peak['Width at Half-Height (min)']:.4f} min")

                            new_peak_name = st.text_input(
                                "Peak Name",
                                value=peak.get('name', f"Peak {peak['id']}"),
                                key=f"name_{peak['id']}_{chrom_id}"
                            )
                            if new_peak_name != peak.get('name', f"Peak {peak['id']}"):
                                for p in st.session_state.selected_peaks[chrom_id]:
                                    if p['id'] == peak['id']:
                                        p['name'] = new_peak_name
                                        break
                                st.session_state.force_redraw = True

                            color_hex = st.color_picker(
                                "Fill Color",
                                peak.get('color_hex', "#ff6384"),
                                key=f"color_picker_{peak['id']}_{chrom_id}"
                            )
                            opacity = st.slider(
                                "Fill Opacity",
                                min_value=0.0,
                                max_value=1.0,
                                value=peak.get('opacity', 0.4),
                                step=0.1,
                                key=f"opacity_{peak['id']}_{chrom_id}"
                            )
                            r = int(color_hex[1:3], 16)
                            g = int(color_hex[3:5], 16)
                            b = int(color_hex[5:7], 16)
                            rgba_color = f"rgba({r}, {g}, {b}, {opacity})"
                            if rgba_color != peak.get('color', "") or color_hex != peak.get('color_hex', ""):
                                for p in st.session_state.selected_peaks[chrom_id]:
                                    if p['id'] == peak['id']:
                                        p['color'] = rgba_color
                                        p['color_hex'] = color_hex
                                        p['opacity'] = opacity
                                        p['user_changed_color'] = True
                                        break
                                st.session_state.force_redraw = True

                        with col2:
                            st.write(f"**Boundaries:** {peak['Min Time (min)']:.2f} – {peak['Max Time (min)']:.2f} min")
                            area = peak.get('Area (a.u.·min)', 0)
                            st.metric("Area", f"{area:.2f} a.u.·min")
                            if chrom_id in st.session_state.selected_peaks:
                                total_area = sum(p.get('Area (a.u.·min)', 0) for p in st.session_state.selected_peaks[chrom_id])
                                if total_area > 0:
                                    percent = (area / total_area) * 100
                                    st.metric("% of Total", f"{percent:.1f}%")

                            if st.button(f"Delete Peak", key=f"delete_{peak['id']}_{chrom_id}"):
                                for idx, p in enumerate(st.session_state.selected_peaks[chrom_id]):
                                    if p['id'] == peak['id']:
                                        st.session_state.selected_peaks[chrom_id].pop(idx)
                                        break
                                st.success(f"Peak removed")
                                st.session_state.force_redraw = True
