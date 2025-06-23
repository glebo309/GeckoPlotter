# models/chromatogram.py

import streamlit as st
import numpy as np
import pandas as pd
from config.settings import get_color_from_palette

class Chromatogram:

    def __init__(self, chrom_id, name, x=None, y=None, color=None, visible=True):

        self.chrom_id = chrom_id
        self.name = name
        self.x = x
        self.y = y
        self.color = color if color else get_color_from_palette(chrom_id)
        self.visible = visible
    
    def generate_synthetic_data(self):

        # Generate time values from 0 to 10 minutes
        self.x = np.linspace(0, 10, 3000)
        
        # Create baseline with some noise
        baseline = 0.1 * np.random.randn(len(self.x))
        
        # Initialize signal array
        self.y = np.zeros_like(self.x) + baseline
        
        # Add peaks at random positions for testing
        num_peaks = np.random.randint(2, 6)
        for _ in range(num_peaks):
            # Random peak parameters
            peak_pos = np.random.uniform(0.5, 9.5)
            peak_height = np.random.uniform(0.5, 1.0)
            peak_width = np.random.uniform(0.05, 0.2)
            
            # Add Gaussian peak
            self.y += peak_height * np.exp(-((self.x - peak_pos) / peak_width) ** 2)
        
        return self.x, self.y
    
    def to_dict(self):

        return {
            'chrom_id': self.chrom_id,
            'name': self.name,
            'x': self.x,
            'y': self.y,
            'color': self.color,
            'visible': self.visible
        }
    
    @classmethod
    def from_dict(cls, chrom_id, chrom_dict):

        return cls(
            chrom_id=chrom_id,
            name=chrom_dict['name'],
            x=chrom_dict['x'],
            y=chrom_dict['y'],
            color=chrom_dict['color'],
            visible=chrom_dict['visible']
        )

def initialize_session_state():
    """Initialize session state variables if they don't exist."""
    
    # Initialize chromatograms dictionary - EMPTY by default
    if 'chromatograms' not in st.session_state:
        st.session_state.chromatograms = {}  # Start with empty dictionary, no default chromatogram

    if 'next_peak_id' not in st.session_state:
        st.session_state.next_peak_id = 0

    if 'active_chromatogram' not in st.session_state:
        st.session_state.active_chromatogram = None

    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "Sample Results"  # Options: "Sample Results", "Peak Results", "Calibration & Quantification"

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

def add_new_chromatogram(name=None):

    # Generate new ID
    new_id = max(st.session_state.chromatograms.keys()) + 1 if st.session_state.chromatograms else 0
    
    # Generate name if not provided
    if name is None:
        name = f"Sample {new_id + 1}"
    
    # Create new chromatogram
    new_chrom = Chromatogram(
        chrom_id=new_id,
        name=name,
        color=get_color_from_palette(new_id),
        visible=True
    )
    
    # Add to session state
    st.session_state.chromatograms[new_id] = new_chrom.to_dict()
    
    # Initialize empty peaks list for this chromatogram
    if new_id not in st.session_state.selected_peaks:
        st.session_state.selected_peaks[new_id] = []
    
    # Set as active chromatogram
    st.session_state.active_chromatogram = new_id
    
    return new_id

def generate_sample_chromatograms():

    # Simply return without generating any sample data
    return