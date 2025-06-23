# app.py

import streamlit as st
import numpy as np
import pandas as pd
from io import StringIO
from config.settings import initialize_session_state, APP_TITLE, APP_LAYOUT
from models.chromatogram import generate_sample_chromatograms, add_new_chromatogram
from utils.data_processing import (
    process_chromatogram_data,
    apply_smoothing,
    calculate_baseline
)
from ui.sidebar import render_sidebar
from ui.plot import plot_chromatograms
from ui.samples_view import render_sample_results, edit_peak_properties
from ui.peaks_view import render_peak_results
from ui.calibration_ui import render_calibration_tabs
from utils.toast import init_toast_container, render_toasts, show_toast
from ui.calibration_ui import render_calibration_setup, render_calibration_curves, render_export_import
from lcms.lcms_view import render_lcms_view
from data_readers.chromatogram_reader import ChromatogramReader
from utils.file_upload_handler import handle_chromatogram_upload


import streamlit.components.v1 as components




def process_uploaded_file_wrapper(uploaded_file):
    """
    Router function that handles different file types appropriately.
    """
    file_extension = uploaded_file.name.lower().split('.')[-1]
    
    if file_extension == 'cdf':
        # Handle LC-MS CDF files (original logic)
        try:
            from lcms.cdf_reader import load_cdf
            rt, tic, tmp_path = load_cdf(uploaded_file)

            color = f"rgba({np.random.randint(256)}, {np.random.randint(256)}, {np.random.randint(256)},1)"
            chrom_id = len(st.session_state.chromatograms) + 1

            st.session_state.chromatograms[chrom_id] = {
                'name': uploaded_file.name.rsplit('.', 1)[0],
                'visible': True,
                'color': color,
                'type': 'lcms',  
                'data': {'x': rt, 'y': tic},
                'file_path': tmp_path
            }
            st.session_state.active_chromatogram = chrom_id
            return True
        except Exception as e:
            st.error(f"Error processing CDF file: {e}")
            return False
            
    elif file_extension == 'csv':
        # Handle CSV files using CSVReader
        try:
            from data_readers.csv_reader import CSVReader
            import tempfile
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name
            
            try:
                # Use CSVReader
                reader = CSVReader()
                reader.file_path = tmp_path
                
                if not reader._process_file():
                    st.error(f"Could not process CSV file: {uploaded_file.name}")
                    return False
                
                # Get the processed data
                df = reader.get_data()
                wavelength = reader.get_wavelength()
                
                x = df["Time (min)"].values
                y = df["Value (mAU)"].values
                
                color = f"rgba({np.random.randint(256)}, {np.random.randint(256)}, {np.random.randint(256)},1)"
                chrom_id = len(st.session_state.chromatograms) + 1

                st.session_state.chromatograms[chrom_id] = {
                    'name': reader.file_name,
                    'visible': True,
                    'color': color,
                    'type': 'hplc',
                    'data': {'x': x, 'y': y},
                    'file_path': uploaded_file.name,
                    'wavelength': wavelength
                }
                st.session_state.active_chromatogram = chrom_id
                
                print(f"CSVReader processed {len(df)} points from {uploaded_file.name}")
                return True
                
            finally:
                # Clean up temp file
                import os
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            st.error(f"Error processing CSV file: {e}")
            return False


    elif file_extension == 'txt':
        # Handle HPLC text files using ChromatogramReader
        preprocessed_data = {}
        for chrom_id, chromatogram_data in st.session_state.chromatograms.items():
            if 'data' in chromatogram_data:
                x = chromatogram_data['data']['x']
                y = chromatogram_data['data']['y']
                y_smooth = apply_smoothing(y, st.session_state.smoothing)
                baseline = calculate_baseline(
                    y_smooth,
                    iterations=st.session_state.settings['baseline_iterations'],
                    percentile=st.session_state.settings['percentile']
                )
                y_corrected = y_smooth - baseline
                preprocessed_data[chrom_id] = {
                    'x': x,
                    'y': y,
                    'y_smooth': y_smooth,
                    'baseline': baseline,
                    'y_corrected': y_corrected
                }
        
        return handle_chromatogram_upload(uploaded_file, preprocessed_data)
    
    else:
        st.error(f"Unsupported file type: {file_extension}")
        return False


def main():

    st.set_page_config(
        page_icon="🦎",
        layout="wide"
    )
    render_toasts()

    toast_container = init_toast_container()

    from ui.plot_interactions import implement_title_editing_ui
    implement_title_editing_ui()

    # --- Initialize session state ---
    for key, default in {
        'chromatograms': {},
        'active_chromatogram': None,
        'selected_peaks': {},
        'next_peak_id': 1,
        'auto_thresholds': {},
        'calibration_models': {},
        'calibration_data': {
            'model_type': 'linear',
            'force_zero': False,
            'units': 'µg/mL',
            'standards': {}
        },
        'settings': {
            'snr': 3.0,
            'slope_threshold': 0.02,
            'baseline_iterations': 50,
            'percentile': 5,
            'extension_factor': 1.5,
            'show_peak_markers': False
        },
        'smoothing': 8,
        'view_mode': "Sample Results"
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # --- Title ---


    # --- If no data uploaded yet, show upload prompt ---
    if not st.session_state.chromatograms:
        st.markdown("""
        ## Welcome to GeckoPlotter.

        Analyze HPLC, LC–MS, UV–Vis — and soon genomics & protein structures — all in one place.

        🌈 **Visualize** your curves  
        ⚖️ **Quantify** peaks in seconds  
        🔗 **Interact** with your data in real time  

        Ready to get started?  
        • Drag & drop your files into the **sidebar**  
        • Enjoy fast, easy insights!
        """)

    if 'plot_settings' not in st.session_state:
        st.session_state.plot_settings = {
            'line_thickness': 1.5,
            'smooth_lines': True,
            'integrate_zero': False,
            'show_legend': True,
            'horizontal_grid': False,
            'vertical_grid': False,
            'plot_width': 800,
            'plot_height': 500
        }



    # --- Compute preprocessed_data ---
    preprocessed_data = {}
    for chrom_id, chromatogram_data in st.session_state.chromatograms.items():
        if 'data' in chromatogram_data:
            x = chromatogram_data['data']['x']
            y = chromatogram_data['data']['y']
            y_smooth = apply_smoothing(y, st.session_state.smoothing)
            baseline = calculate_baseline(
                y_smooth,
                iterations=st.session_state.settings['baseline_iterations'],
                percentile=st.session_state.settings['percentile']
            )
            y_corrected = y_smooth - baseline
            preprocessed_data[chrom_id] = {
                'x': x,
                'y': y,
                'y_smooth': y_smooth,
                'baseline': baseline,
                'y_corrected': y_corrected
            }

    # --- NOW render the sidebar ONCE ---
    render_sidebar(preprocessed_data, process_uploaded_file_wrapper)



    # --- If still no data, stop ---
    if not st.session_state.chromatograms:
        return

    # --- Plot ---
    plot_chromatograms(preprocessed_data)


    # --- Tabs ---
    # Check if we have any peaks detected
    # --- Tabs ---
    # Check if we have any peaks detected
    has_peaks = any(chrom_id in st.session_state.selected_peaks and len(st.session_state.selected_peaks[chrom_id]) > 0 
                for chrom_id in st.session_state.chromatograms)

    if st.session_state.chromatograms and has_peaks:  # Only show tabs if chromatograms are loaded AND peaks are detected
        tab1, tab2 = st.tabs(["Sample Results", "Compound Analysis"])
        
        with tab1:
            st.session_state.view_mode = "Sample Results"
            active_chrom = st.session_state.active_chromatogram
            
            if active_chrom:
                # We know there are peaks since we check has_peaks above
                render_sample_results(active_chrom, preprocessed_data)
        
        with tab2:
            st.session_state.view_mode = "Compound Analysis"
            render_peak_results(preprocessed_data)

    elif st.session_state.chromatograms:
        # Only show the hint for HPLC (not LC–MS) when no peaks are detected
        active = st.session_state.active_chromatogram
        chroms = st.session_state.chromatograms
        has_peaks = any(
            chrom_id in st.session_state.selected_peaks and st.session_state.selected_peaks[chrom_id]
            for chrom_id in chroms
        )
        if not has_peaks and active and chroms[active].get('type') == 'hplc':
            st.info("👆 Use the 'Peak Analysis' section in the sidebar to detect peaks.")


    # --- Peak editor ---
    has_peaks = any(chrom_id in st.session_state.selected_peaks and len(st.session_state.selected_peaks[chrom_id]) > 0 
                for chrom_id in st.session_state.chromatograms)

    if has_peaks:
        with st.expander("Peak Properties", expanded=False):
            edit_peak_properties()

    # --- Calibration ---
    if has_peaks:
        # Make Calibration collapsible
        with st.expander("Calibration & Quantification", expanded=False):
            cal_tabs = st.tabs(["Calibration Setup", "Calibration Curves", "Export/Import"])
            with cal_tabs[0]:
                render_calibration_setup()
            with cal_tabs[1]:
                render_calibration_curves()
            with cal_tabs[2]:
                render_export_import()

    # --- Reports ---

    if has_peaks:
        # Make Reports collapsible
        with st.expander("Reports", expanded=False):
            # Add download button for each chromatogram with peaks
            for chrom_id in st.session_state.chromatograms:
                if chrom_id in st.session_state.selected_peaks and len(st.session_state.selected_peaks[chrom_id]) > 0:
                    # Create data for download
                    active_chrom = chrom_id
                    sample_results = []
                    
                    # Total area for this chromatogram for percentage
                    total_area = sum(p.get('Area (a.u.·min)', 0) for p in st.session_state.selected_peaks[chrom_id])
                    
                    for peak in st.session_state.selected_peaks[chrom_id]:
                        # Create a row for this peak
                        result_row = {
                            "Peak Name": peak.get('name', f"Peak {peak['id']}"),
                            "Peak ID": peak['id'],
                            "Midpoint (min)": peak['Midpoint (min)'],
                            "Height (a.u.)": peak.get('Height (a.u.)', 0),
                            "Area (a.u.·min)": peak.get('Area (a.u.·min)', 0),
                            "Area %": (peak.get('Area (a.u.·min)', 0) / total_area) * 100 if total_area > 0 else 0,
                            "Width (min)": peak.get('Width (min)', 0),
                            "Width at Half-Height (min)": peak.get('Width at Half-Height (min)', 0)
                        }
                        
                        # Add to results
                        sample_results.append(result_row)
                    
                    # Create DataFrame for download - add a unique key for each button
                    if sample_results:
                        df = pd.DataFrame(sample_results)
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label=f"Download Results for {st.session_state.chromatograms[chrom_id]['name']} as CSV",
                            data=csv,
                            file_name=f"sample_{chrom_id}_results.csv",
                            mime="text/csv",
                            key=f"download_results_{chrom_id}"  # Add this unique key
                        )
            
            # Then the generate report button
            if st.button("Generate Report"):
                show_toast("Report generation would happen here.", "success")



def render_chromatogram_view(preprocessed_data):
    """
    Render the chromatogram view tab with plot, baseline toggle,
    result selector, and peak editor.
    """
    # Baseline toggle (above plot)
    st.checkbox("Show Baseline", value=st.session_state.get('show_baseline', False), key='show_baseline_cb')
    st.session_state.show_baseline = st.session_state.show_baseline_cb

    # Plot chromatograms
    if preprocessed_data:
        plot_chromatograms(preprocessed_data)
    else:
        st.info("No data to display.")

    # 👇 Move this below the plot
    st.markdown("---")
    view_mode = st.radio(
        "View Results As:",
        options=["Sample Results", "Peak Analysis"],
        index=0 if st.session_state.get("view_mode", "Sample Results") == "Sample Results" else 1,
        horizontal=True,
        key="view_mode"
    )
    st.session_state["view_mode"] = view_mode

    # Optional: peak editor
    if any(len(peaks) > 0 for peaks in st.session_state.selected_peaks.values()):
        with st.expander("Peak Properties", expanded=False):
            edit_peak_properties()

def render_reports(preprocessed_data):
    """
    Render the reports tab (local stub).
    """
    st.header("Reports")
    st.info("Reporting features will be implemented soon.")
    if st.button("Generate Report"):
        show_toast("Report generation would happen here.", "success")

if __name__ == "__main__":
    main()