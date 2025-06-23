import streamlit as st
import numpy as np

# Application settings
APP_TITLE = "🔬 Chromatogram Peak Detection"
APP_LAYOUT = "wide"

# Default peak detection settings
DEFAULT_SETTINGS = {
    'snr': 3.0,                # Signal-to-noise ratio
    'slope_threshold': 0.01,   # 1% - much looser for finding more of the peak
    'baseline_iterations': 50, # For baseline detection
    'percentile': 5,           # For baseline estimation
    'extension_factor': 1.5,   # How much to extend peak boundaries
    'show_peak_markers': False # Whether to show peak markers
}

# Color palette for chromatograms and peaks
def get_color_from_palette(index, alpha=1.0):
    """Return a color from a predefined palette based on index"""
    palette = [
        (0, 123, 255),     # Blue
        (220, 53, 69),     # Red
        (40, 167, 69),     # Green
        (255, 193, 7),     # Yellow/amber 
        (111, 66, 193),    # Purple
        (23, 162, 184),    # Teal
        (255, 99, 132),    # Pink
        (54, 162, 235),    # Light blue
        (255, 159, 64),    # Orange
        (75, 192, 192),    # Light green
        (153, 102, 255),   # Lavender
        (231, 233, 237)    # Grey
    ]
    
    color = palette[index % len(palette)]
    return f"rgba({color[0]}, {color[1]}, {color[2]}, {alpha})"

def initialize_session_state():
    """Initialize session state variables if they don't exist."""
    
    # Initialize with one default chromatogram
    if 'chromatograms' not in st.session_state:
        st.session_state.chromatograms = {
            0: {
                'name': 'Sample 1',
                'x': np.linspace(0, 10, 500),
                'y': None,  # Will be generated below
                'color': get_color_from_palette(0),
                'visible': True
            }
        }

    if 'next_peak_id' not in st.session_state:
        st.session_state.next_peak_id = 0

    if 'active_chromatogram' not in st.session_state:
        st.session_state.active_chromatogram = 0

    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "Sample Results"  # or "Peak Results"

    # Initialize advanced settings in session state for persistence
    if 'settings' not in st.session_state:
        st.session_state.settings = DEFAULT_SETTINGS.copy()

    # Initialize calibration data in session state if not present
    if 'calibration_data' not in st.session_state:
        st.session_state.calibration_data = {
            'standards': {},  # Dict to store standard concentrations for peak groups
            'model_type': 'linear',  # Default model type
            'force_zero': False,  # Force through zero option
            'units': 'µg/mL'  # Default units
        }

    # Initialize storage for calibration models
    if 'calibration_models' not in st.session_state:
        st.session_state.calibration_models = {}

    # Store auto-threshold for each chromatogram
    if 'auto_thresholds' not in st.session_state:
        st.session_state.auto_thresholds = {}
        
    # Initialize selected peaks dictionary
    if 'selected_peaks' not in st.session_state:
        st.session_state.selected_peaks = {}  # Dictionary with chromatogram ID as key