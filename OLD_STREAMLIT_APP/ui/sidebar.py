
# ui/sidebar.py  
import streamlit as st
import numpy as np
import copy
from scipy.signal import find_peaks
from models.chromatogram import add_new_chromatogram
from utils.peak_detection import detect_peak_near_click, recalculate_all_peaks
from utils.toast import show_toast
from utils.color_utils import hex_to_rgba, rgba_to_hex  
# ui/sidebar.py  
import copy 



def rgba_to_hex(color_string):
    import re
    # If already hex, return as-is
    if isinstance(color_string, str) and color_string.startswith('#') and len(color_string) == 7:
        return color_string
    # If rgba, convert to hex
    match = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),?.*\)', color_string)
    if match:
        r, g, b = match.groups()
        return '#{:02X}{:02X}{:02X}'.format(int(r), int(g), int(b))
    # fallback
    return '#000000'

def hex_to_rgba(hex_code, alpha=1.0):
    if hex_code.startswith("rgba"):
        return hex_code  # Already in correct format
    hex_code = hex_code.lstrip('#')
    r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b},{alpha})"

def render_sidebar(preprocessed_data, process_uploaded_file):
    """
    Render the sidebar with controls for chromatogram management,
    peak detection, and advanced settings.
    """
    # Create a styled title that looks like a button with JavaScript
    title_container = st.sidebar.container()
    
    # Custom styling for the title with JavaScript click handler 
    title_container.markdown("""
    <style>
    .gecko-title-button {
        font-size: 42px;
        font-weight: 900;
        color: #1c1c1c;
        text-align: center;
        cursor: pointer;
        padding: 1rem 0;
        transition: background 0.2s ease;
        border-radius: 6px;
        border: none;
        outline: none;
        background: transparent;
        width: 100%;
        margin: 0;
    }
    .gecko-title-button:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }
    </style>

    <div class="gecko-title-button" onclick="
        // Set a value in sessionStorage to indicate collapse was clicked
        sessionStorage.setItem('collapse_clicked', 'true');
        // Reload the page to trigger a rerun
        window.location.reload();
    ">
        🦎 GeckoPlotter
    </div>

    <script>
        // Check if we need to trigger the collapse
        if (sessionStorage.getItem('collapse_clicked')) {
            // Clear the flag
            sessionStorage.removeItem('collapse_clicked');
            // Find the hidden button and click it
            setTimeout(function() {
                // Give the page time to load, then find and click the hidden button
                const buttons = window.document.querySelectorAll('button');
                for (let button of buttons) {
                    if (button.innerText === 'COLLAPSE_TRIGGER') {
                        button.click();
                        break;
                    }
                }
            }, 300);
        }
    </script>
    """, unsafe_allow_html=True)
    
    # Hidden button to actually trigger the collapse
    # Hide with CSS instead of using label_visibility
    st.sidebar.markdown("""
    <style>
    /* Hide the collapse trigger button */
    [data-testid="baseButton-secondary"]:has(> div:contains("COLLAPSE_TRIGGER")) {
        display: none;
    }
    </style>
    """, unsafe_allow_html=True)
    
    #if st.sidebar.button("COLLAPSE_TRIGGER", key="collapse_trigger_btn"):
    #    # Set all expanders to closed 
    #    st.session_state.collapse_all = True
    #    show_toast("All sections collapsed", "info")
    #    st.rerun() 

    # Check if we're in collapse mode
    collapse_all = st.session_state.get('collapse_all', False)
    
    # Reset the flag after collapse
    if collapse_all:
        st.session_state.collapse_all = False

    # Check if we have chromatograms loaded
    has_chromatograms = bool(st.session_state.chromatograms)
    active_chrom = st.session_state.active_chromatogram

    # --- 1. UPLOAD DATA (Expanded) ---
    with st.sidebar.expander(
        "Upload Data", 
        expanded=not collapse_all and not has_chromatograms
    ):
        uploaded_files_sidebar = st.file_uploader(
            "",  # no label text
            type=['csv', 'txt', 'cdf'],
            accept_multiple_files=True,
            label_visibility="hidden",
            help="Drag and drop file here. Limit 200MB per file • CSV, TXT, CDF",
            key=f"sidebar_uploader_{len(st.session_state.chromatograms)}"
        )

        if uploaded_files_sidebar:
            files_processed = False
            for uploaded_file in uploaded_files_sidebar:
                file_exists = any(
                    chromatogram_data.get('file_path') == uploaded_file.name
                    for chromatogram_data in st.session_state.chromatograms.values()
                )
                if not file_exists:
                    success = process_uploaded_file(uploaded_file)
                    if success:
                        files_processed = True
                        show_toast(f"File '{uploaded_file.name}' uploaded from sidebar", "success")
            
            # Set upload_expanded to False BEFORE rerun
            if files_processed:
                st.session_state.upload_expanded = False
                st.rerun()


    # --- Check if we have chromatograms loaded ---
    has_chromatograms = bool(st.session_state.chromatograms)
    active_chrom = st.session_state.active_chromatogram






    # --- 2. SAMPLE MANAGEMENT (only if we have chromatograms) ---
    if has_chromatograms:
        with st.sidebar.expander("Sample Management", expanded=not collapse_all and False):
            st.subheader("Samples")

            for chrom_id, chrom_data in st.session_state.chromatograms.items():
                is_active = (chrom_id == st.session_state.active_chromatogram)
                show_rename = st.session_state.get(f"rename_mode_{chrom_id}", False)

                cols = st.columns([0.08, 0.16, 0.44, 0.16, 0.16])

                # Visibility toggle
                visible = cols[0].checkbox("", value=chrom_data["visible"], key=f"visible_{chrom_id}", label_visibility="collapsed")
                st.session_state.chromatograms[chrom_id]["visible"] = visible

                # Color picker
                hex_color = rgba_to_hex(chrom_data["color"])
                new_color = cols[1].color_picker("", value=hex_color, key=f"color_{chrom_id}", label_visibility="collapsed")
                if new_color.lower() != hex_color.lower():
                    chrom_data["color"] = new_color
                    st.rerun()

                # Select chromatogram
                name_display = f"**{chrom_data['name']}**" if is_active else chrom_data["name"]
                if cols[2].button(name_display, key=f"select_{chrom_id}"):
                    st.session_state.active_chromatogram = chrom_id
                    st.rerun()

                # Rename toggle
                if cols[3].button("✏️", key=f"rename_{chrom_id}"):
                    st.session_state[f"rename_mode_{chrom_id}"] = not st.session_state.get(f"rename_mode_{chrom_id}", False)
                    st.rerun()

                # Delete chromatogram
                if cols[4].button("🗑️", key=f"delete_{chrom_id}"):
                    removed_name = chrom_data["name"]
                    del st.session_state.chromatograms[chrom_id]
                    if chrom_id in st.session_state.selected_peaks:
                        del st.session_state.selected_peaks[chrom_id]

                    # Reset active chromatogram safely
                    if st.session_state.chromatograms:
                        st.session_state.active_chromatogram = next(iter(st.session_state.chromatograms.keys()))
                    else:
                        st.session_state.active_chromatogram = None

                    show_toast(f"Removed chromatogram: {removed_name}", "warning")
                    st.rerun()

                # Inline rename input
                if show_rename:
                    new_name = st.text_input("Rename:", value=chrom_data["name"], key=f"rename_input_{chrom_id}")
                    if new_name and new_name != chrom_data["name"]:
                        chrom_data["name"] = new_name
                        st.session_state[f"rename_mode_{chrom_id}"] = False
                        show_toast("Name updated", "success")
                        st.rerun()

    # --- 3. SIGNAL PROCESSING (only if we have chromatograms) ---
    """
    if has_chromatograms:
        with st.sidebar.expander("Signal Processing", expanded=not collapse_all and False):
            st.subheader("Signal Processing")
        
            smoothing = st.slider('Signal smoothing', min_value=0, max_value=15, value=st.session_state.smoothing, step=2)
            if 'previous_smoothing' not in st.session_state:
                st.session_state.previous_smoothing = smoothing
            elif st.session_state.previous_smoothing != smoothing:
                show_toast(f"Signal smoothing set to {smoothing}", "info")
                st.session_state.previous_smoothing = smoothing
            st.session_state.smoothing = smoothing
    """ 




    # --- 5. PLOT SETTINGS (Only show if we have chromatograms) ---
    if has_chromatograms:
        with st.sidebar.expander("Plot Settings", expanded=not collapse_all and False):
            from ui.plot_settings import render_plot_settings
            render_plot_settings()







    # --- 4. PEAK ANALYSIS (only if we have active chromatogram) ---
    # --- 4. PEAK ANALYSIS (only if we have active chromatogram) ---
    if has_chromatograms and active_chrom is not None and active_chrom in preprocessed_data:
        with st.sidebar.expander("Peak Analysis", expanded=not collapse_all and False):
            # --- 4.1 Add peak by time ---
            st.header("Add Peak by Time")
            
            # Info message with icon
            st.info("📌 Hover over a peak to see its time, then enter it here")
            
            # Peak height threshold slider
            if active_chrom not in st.session_state.auto_thresholds:
                # Initialize with default threshold (5% of max)
                max_y = np.max(preprocessed_data[active_chrom]['y_corrected'])
                st.session_state.auto_thresholds[active_chrom] = float(max_y * 0.05)

            # Display the slider with the stored value
            max_value = float(np.max(preprocessed_data[active_chrom]['y_corrected']))
            auto_threshold = st.slider(
                "Peak Height Threshold", 
                min_value=0.0, 
                max_value=max_value, 
                value=st.session_state.auto_thresholds[active_chrom],
                format="%.2f",
                key=f"threshold_{active_chrom}"
            )
            
            # Update stored threshold from the slider
            st.session_state.auto_thresholds[active_chrom] = auto_threshold
            
            # Time coordinate input with side-by-side button
            col1, col2 = st.columns([0.65, 0.35])
            with col1:
                x_coord = st.number_input(
                    "Retention Time (min)", 
                    min_value=float(preprocessed_data[active_chrom]['x'][0]), 
                    max_value=float(preprocessed_data[active_chrom]['x'][-1]), 
                    value=float(5.00),
                    step=0.01,
                    format="%.2f"
                )
            
            with col2:
                # Add vertical alignment to match the number input
                st.markdown("##")  # Small vertical spacer
                if st.button("Add Peak", use_container_width=True):
                    # Get the active chromatogram's threshold
                    threshold = st.session_state.auto_thresholds[active_chrom]
                    
                    # Call detect_peak_near_click with the threshold
                    new_peak = detect_peak_near_click(
                        x_coord, 
                        preprocessed_data, 
                        threshold=threshold
                    )
                    
                    if new_peak:
                        # Check if we already have a peak very close to this one
                        duplicate = False
                        if active_chrom in st.session_state.selected_peaks:
                            for existing_peak in st.session_state.selected_peaks[active_chrom]:
                                if abs(existing_peak['Midpoint (min)'] - new_peak['Midpoint (min)']) < 0.1:
                                    duplicate = True
                                    show_toast(f"Duplicate peak at {new_peak['Midpoint (min)']:.2f} min", "warning")
                                    break
                        
                        if not duplicate:
                            # Initialize the list for this chromatogram if it doesn't exist
                            if active_chrom not in st.session_state.selected_peaks:
                                st.session_state.selected_peaks[active_chrom] = []
                                
                            st.session_state.selected_peaks[active_chrom].append(new_peak)
                            st.session_state.next_peak_id += 1
                            show_toast(f"Peak added at {new_peak['Midpoint (min)']:.2f} min", "success")
                            st.rerun()
                    else:
                        show_toast(f"No peak found above threshold ({threshold:.2f}) at the selected time.", "warning")

            # Add a small spacing
            st.markdown("")

            # --- 4.2 Auto-detect peaks ---
            # Full width button for detecting all peaks in this sample
            if st.button("Detect All Peaks", key="detect_all_peaks_btn", use_container_width=True):
                # Find all peaks above threshold
                y_corrected = preprocessed_data[active_chrom]['y_corrected']
                all_peaks, properties = find_peaks(y_corrected, height=auto_threshold, prominence=auto_threshold*0.2)
                
                # Clear existing peaks for this chromatogram
                st.session_state.selected_peaks[active_chrom] = []
                
                # Add each detected peak
                for peak_idx in all_peaks:
                    x_coord = preprocessed_data[active_chrom]['x'][peak_idx]
                    new_peak = detect_peak_near_click(
                        x_coord, 
                        preprocessed_data, 
                        search_radius=0.2,
                        threshold=auto_threshold
                    )
                    if new_peak:
                        st.session_state.selected_peaks[active_chrom].append(new_peak)
                        st.session_state.next_peak_id += 1

                if st.session_state.selected_peaks[active_chrom]:
                    peak_count = len(st.session_state.selected_peaks[active_chrom])
                    sample_name = st.session_state.chromatograms[active_chrom]['name']
                    show_toast(f"Detected {peak_count} peaks in '{sample_name}'", "success")
                    st.rerun()
                else:
                    show_toast("No peaks detected with current threshold", "warning")

            # Full width button for detecting same peak in all samples
            if st.button("Detect Same Peak in All Samples", key="detect_same_peaks_btn", use_container_width=True):
                # Logic to detect the same peak across all samples
                if active_chrom in st.session_state.selected_peaks and st.session_state.selected_peaks[active_chrom]:
                    # Get the most recently added peak in the active chromatogram
                    latest_peak = st.session_state.selected_peaks[active_chrom][-1]
                    peak_time = latest_peak['Midpoint (min)']
                    
                    # Reasonable time window to search for similar peaks
                    time_window = 0.2  # 0.2 minutes (12 seconds)
                    
                    # Store how many peaks were found
                    peak_count = 0
                    processed_samples = []
                    
                    # For each chromatogram (except the active one that already has the peak)
                    for chrom_id, chrom_data in st.session_state.chromatograms.items():
                        if chrom_id != active_chrom and chrom_data['visible']:
                            # Check if this chromatogram already has a peak at similar time
                            has_similar_peak = False
                            if chrom_id in st.session_state.selected_peaks:
                                for existing_peak in st.session_state.selected_peaks[chrom_id]:
                                    if abs(existing_peak['Midpoint (min)'] - peak_time) < time_window:
                                        has_similar_peak = True
                                        break
                            
                            # If no similar peak, detect one
                            if not has_similar_peak:
                                new_peak = detect_peak_near_click(
                                    peak_time,  # Use same time as reference peak
                                    preprocessed_data,
                                    search_radius=time_window,
                                    chrom_id=chrom_id
                                )
                                
                                if new_peak:
                                    # Initialize the list for this chromatogram if needed
                                    if chrom_id not in st.session_state.selected_peaks:
                                        st.session_state.selected_peaks[chrom_id] = []
                                    
                                    # Add the peak
                                    st.session_state.selected_peaks[chrom_id].append(new_peak)
                                    st.session_state.next_peak_id += 1
                                    peak_count += 1
                                    processed_samples.append(chrom_data['name'])
                    
                    if peak_count > 0:
                        show_toast(f"Detected corresponding peak in {peak_count} other samples", "success", duration=4)
                        st.rerun()
                    else:
                        show_toast("No additional samples found with this peak", "info")
                else:
                    show_toast("Please select or add a peak in the current sample first", "warning")
            
            # Add a small spacing
            st.markdown("")
            
            # MOVED: Integrate to Zero checkbox to the bottom
            # Get the current value from plot_settings
            if 'plot_settings' not in st.session_state:
                st.session_state.plot_settings = {'integrate_zero': True}
                
            integrate_zero = st.checkbox(
                "Integrate to Zero (Baseline)", 
                value=st.session_state.plot_settings.get('integrate_zero', True),
                key=f"integrate_zero_cb_{st.session_state.plot_settings.get('integrate_zero', True)}"
            )
            if integrate_zero != st.session_state.plot_settings.get('integrate_zero', False):
                st.session_state.plot_settings['integrate_zero'] = integrate_zero
                show_toast(f"Integrate to zero {'enabled' if integrate_zero else 'disabled'}", "info")
                st.rerun()

            st.divider()
            
            # --- 4.3 Advanced Peak Detection (with checkbox to toggle) ---
            show_advanced = st.checkbox("Show Advanced Peak Detection Settings", value=False, key="toggle_advanced_peak_settings")
            
            if show_advanced:
                # Add warning about calibration consistency if calibration exists
                if st.session_state.calibration_models:
                    st.warning("⚠️ Note: Changes to these settings will affect peak integration but not existing calibration curves.")
                    
                # Define the callback functions with preprocessed_data
                def update_snr_callback():
                    update_snr(preprocessed_data)
                    
                def update_slope_callback():
                    update_slope(preprocessed_data)
                    
                def update_baseline_iterations_callback():
                    update_baseline_iterations(preprocessed_data)
                    
                def update_percentile_callback():
                    update_percentile(preprocessed_data)
                    
                def update_extension_callback():
                    update_extension(preprocessed_data)
                
                def update_markers_callback():
                    update_markers()
                
                # Add sliders with callbacks
                st.slider('Signal-to-noise ratio', min_value=1.0, max_value=10.0, 
                        value=st.session_state.settings['snr'], step=0.5,
                        key="pa_snr_slider", on_change=update_snr_callback,
                        help="Lower values detect more of the peak (2-3 recommended)")
                
                st.slider('Slope threshold (%)', min_value=0.5, max_value=20.0, 
                        value=st.session_state.settings['slope_threshold'] * 100, step=0.5,
                        key="pa_slope_slider", on_change=update_slope_callback,
                        help="Lower values include more of the peak (1-3% recommended)")
                
                st.slider('Baseline iterations', min_value=10, max_value=200, 
                        value=st.session_state.settings['baseline_iterations'], step=10,
                        key="pa_baseline_slider", on_change=update_baseline_iterations_callback,
                        help="More iterations for better baseline detection (50 recommended)")
                
                st.slider('Baseline percentile', min_value=1, max_value=20, 
                        value=st.session_state.settings['percentile'], step=1,
                        key="pa_percentile_slider", on_change=update_percentile_callback,
                        help="Percentile used for baseline estimation (5 recommended)")
                
                st.slider('Boundary extension factor', min_value=1.0, max_value=3.0, 
                        value=st.session_state.settings['extension_factor'], step=0.1,
                        key="pa_extension_slider", on_change=update_extension_callback,
                        help="How much to extend peak boundaries (1.5-2.0 recommended)")
                

                if st.button("Reset to Default Settings"):
                    # Default settings
                    default_settings = {
                        'snr': 3.0,
                        'slope_threshold': 0.02,
                        'baseline_iterations': 50,
                        'percentile': 5,
                        'extension_factor': 1.5,
                        'show_peak_markers': False
                    }
                    
                    # Store current settings to check if recalculation is needed
                    old_settings = copy.deepcopy(st.session_state.settings)
                    
                    # Update settings
                    st.session_state.settings = default_settings
                    
                    # Update UI controls to match new settings
                    st.session_state.pa_snr_slider = default_settings['snr']
                    st.session_state.pa_slope_slider = default_settings['slope_threshold'] * 100
                    st.session_state.pa_baseline_slider = default_settings['baseline_iterations']
                    st.session_state.pa_percentile_slider = default_settings['percentile']
                    st.session_state.pa_extension_slider = default_settings['extension_factor']
                    st.session_state.pa_marker_checkbox = default_settings['show_peak_markers']
                    
                    # Recalculate peaks with new settings
                    recalculate_all_peaks(preprocessed_data, old_settings)
                    
                    # Show confirmation
                    show_toast("Reset to default peak detection settings", "info")
                    st.rerun()

 



    # --- 7. FONTS & LABELS (Only show if we have chromatograms) ---
    if has_chromatograms:
        with st.sidebar.expander("Fonts & Labels", expanded=not collapse_all and False):
            from ui.fonts_labels import render_fonts_labels
            render_fonts_labels()



    # Find the Export Options section and replace it with:
    # --- 6. EXPORT OPTIONS (Only show if we have chromatograms) ---
    if has_chromatograms:
        with st.sidebar.expander("Export Options", expanded=not collapse_all and False):
            from ui.export_options import render_export_options
            render_export_options()

def update_snr(preprocessed_data):
    old_settings = copy.deepcopy(st.session_state.settings)
    st.session_state.settings['snr'] = st.session_state.pa_snr_slider  # Updated key name
    
    # Add warning if calibration exists
    if st.session_state.calibration_models:
        show_toast("Changed SNR setting - consider recalibrating", "warning", duration=4)
    else:
        show_toast(f"Signal-to-noise ratio set to {st.session_state.pa_snr_slider}", "info")
    
    recalculate_all_peaks(preprocessed_data, old_settings)
    
def update_slope(preprocessed_data):
    old_settings = copy.deepcopy(st.session_state.settings)
    st.session_state.settings['slope_threshold'] = st.session_state.pa_slope_slider / 100  # Updated key name
    
    # Add warning if calibration exists
    if st.session_state.calibration_models:
        show_toast("Changed slope threshold - consider recalibrating", "warning", duration=4)
    else:
        show_toast(f"Slope threshold set to {st.session_state.pa_slope_slider}%", "info")
    
    recalculate_all_peaks(preprocessed_data, old_settings)
    
def update_baseline_iterations(preprocessed_data):
    old_settings = copy.deepcopy(st.session_state.settings)
    st.session_state.settings['baseline_iterations'] = st.session_state.pa_baseline_slider  # Updated key name
    
    # Add warning if calibration exists
    if st.session_state.calibration_models:
        show_toast("Changed baseline iterations - consider recalibrating", "warning", duration=4)
    else:
        show_toast(f"Baseline iterations set to {st.session_state.pa_baseline_slider}", "info")
    
    # Will trigger rerun which will recalculate baseline and peaks
    
def update_percentile(preprocessed_data):
    old_settings = copy.deepcopy(st.session_state.settings)
    st.session_state.settings['percentile'] = st.session_state.pa_percentile_slider  # Updated key name
    
    # Add warning if calibration exists
    if st.session_state.calibration_models:
        show_toast("Changed baseline percentile - consider recalibrating", "warning", duration=4)
    else:
        show_toast(f"Baseline percentile set to {st.session_state.pa_percentile_slider}", "info")
    
    recalculate_all_peaks(preprocessed_data, old_settings)
    
def update_extension(preprocessed_data):
    old_settings = copy.deepcopy(st.session_state.settings)
    st.session_state.settings['extension_factor'] = st.session_state.pa_extension_slider  # Updated key name
    
    # Add warning if calibration exists
    if st.session_state.calibration_models:
        show_toast("Changed boundary extension - consider recalibrating", "warning", duration=4)
    else:
        show_toast(f"Boundary extension set to {st.session_state.pa_extension_slider}", "info")
    
    recalculate_all_peaks(preprocessed_data, old_settings)

def update_markers():
    st.session_state.settings['show_peak_markers'] = st.session_state.pa_marker_checkbox  # Updated key name
    status = "enabled" if st.session_state.pa_marker_checkbox else "disabled"
    show_toast(f"Peak markers {status}", "info")

def render_peak_selection_controls(preprocessed_data, active_chrom):
    """Backward compatibility function - no longer used"""
    pass

def render_peak_detection_controls(preprocessed_data, active_chrom):
    """Backward compatibility function - no longer used"""
    pass

def render_advanced_settings(preprocessed_data):
    """Backward compatibility function - no longer used"""
    pass

def generate_random_color():
    """Generate a random HEX color."""
    import random
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    return f"#{r:02X}{g:02X}{b:02X}"