# utils/lcms_csv_processor.py

import pandas as pd
import numpy as np
import streamlit as st
from io import StringIO
import os
import random

def process_lcms_csv(file_path, file_name):
    """
    Process an LC-MS CSV file directly without relying on Streamlit's file uploader.
    
    Parameters:
    -----------
    file_path : str
        Path to the temporary file containing the CSV data
    file_name : str
        Original file name
        
    Returns:
    --------
    bool
        True if processing was successful, False otherwise
    """
    try:
        # Read the CSV file
        with open(file_path, 'rb') as f:
            csv_content = f.read()
            
        # Try to decode as UTF-8, fallback to Latin-1
        try:
            csv_text = csv_content.decode('utf-8')
        except UnicodeDecodeError:
            csv_text = csv_content.decode('latin-1')
        
        # Parse the CSV data
        df = pd.read_csv(
            StringIO(csv_text),
            header=None,
            names=["time", "signal"],
            sep=None,  # Auto-detect separator
            engine="python"
        )
        
        # Convert to numeric, ignoring errors
        df = df.apply(pd.to_numeric, errors='coerce')
        
        # Drop any rows with NaN values
        df = df.dropna()
        
        if len(df) == 0:
            st.error("No valid data found in the CSV file. Please check the format.")
            return False
            
        # Extract x and y data
        x = df["time"].values
        y = df["signal"].values
        
        # Generate a random color for this chromatogram
        r = random.randint(0, 255)
        g = random.randint(0, 255) 
        b = random.randint(0, 255)
        color = f"rgba({r}, {g}, {b}, 1)"
        
        # Generate a new chromatogram ID
        chrom_id = max(st.session_state.chromatograms.keys(), default=0) + 1
        
        # Create a clean name without extension
        name = file_name.rsplit('.', 1)[0]
        
        # Add the chromatogram to session state
        st.session_state.chromatograms[chrom_id] = {
            'name': name,
            'visible': True,
            'color': color,
            'type': 'lcms',
            'data': {'x': x, 'y': y},
            'file_path': file_name
        }
        
        # Set as active chromatogram
        st.session_state.active_chromatogram = chrom_id
        
        # Initialize empty peaks list for this chromatogram
        if chrom_id not in st.session_state.selected_peaks:
            st.session_state.selected_peaks[chrom_id] = []
            
        # Clean up temporary file
        try:
            os.unlink(file_path)
        except:
            pass
            
        return True
        
    except Exception as e:
        st.error(f"Error processing LC-MS CSV file: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return False