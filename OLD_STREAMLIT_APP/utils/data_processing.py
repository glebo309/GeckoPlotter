#utils/data_processing.py

import numpy as np
import pandas as pd
import streamlit as st
from scipy.signal import savgol_filter

def process_chromatogram_data(chromatograms, smoothing=8):
    """
    Process all chromatogram data with the current settings.
    
    Parameters:
    -----------
    chromatograms : dict
        Dictionary of chromatograms from session state
    smoothing : int
        Smoothing window size (must be odd number)
        
    Returns:
    --------
    dict
        Preprocessed data for each chromatogram
    """
    preprocessed_data = {}
    
    for chrom_id, chromatogram_data in chromatograms.items():
        if 'data' in chromatogram_data:
            # Extract x and y data
            x = chromatogram_data['data']['x']
            y = chromatogram_data['data']['y']
            
            # Apply smoothing
            y_smoothed = apply_smoothing(y, smoothing)
            
            # Calculate baseline
            baseline = calculate_baseline(
                y_smoothed, 
                iterations=st.session_state.settings['baseline_iterations'],
                percentile=st.session_state.settings['percentile']
            )
            
            # Correct baseline
            y_corrected = y_smoothed - baseline
            
            # Store processed data
            preprocessed_data[chrom_id] = {
                'x': x,
                'y': y,
                'y_smoothed': y_smoothed,
                'baseline': baseline,
                'y_corrected': y_corrected
            }
    
    return preprocessed_data

def apply_smoothing(y, window_size):
    """
    Apply Savitzky-Golay smoothing to the signal.
    
    Parameters:
    -----------
    y : array-like
        Input signal
    window_size : int
        Window size for smoothing filter (must be odd)
        
    Returns:
    --------
    array-like
        Smoothed signal
    """
    # Ensure window size is odd
    if window_size % 2 == 0:
        window_size += 1
    
    # Ensure window size is at least 5
    window_size = max(5, window_size)
    
    # Apply Savitzky-Golay filter if possible
    if len(y) > window_size:
        try:
            # For very large window sizes, use a lower polynomial order
            poly_order = min(3, (window_size - 1) // 2)
            y_smoothed = savgol_filter(y, window_size, poly_order)
            return y_smoothed
        except Exception as e:
            print(f"Smoothing error: {e}")
            return y
    else:
        return y

def calculate_baseline(y, iterations=50, percentile=5):
    """
    Calculate the baseline of a signal using an iterative approach.
    
    Parameters:
    -----------
    y : array-like
        Input signal
    iterations : int
        Number of iterations for baseline estimation
    percentile : int
        Percentile to use for baseline estimation
        
    Returns:
    --------
    array-like
        Estimated baseline
    """
    y_modified = y.copy()
    indices = np.arange(len(y))
    
    for _ in range(iterations):
        # Fit a 3rd degree polynomial to the modified signal
        z = np.polyfit(indices, y_modified, 3)
        p = np.poly1d(z)
        fitted = p(indices)
        
        # Calculate residuals
        residuals = y_modified - fitted
        
        # Find points below the percentile (likely to be baseline points)
        threshold = np.percentile(residuals, percentile)
        
        # Replace values above the threshold with the fitted value
        mask = residuals > threshold
        y_modified[mask] = fitted[mask]
    
    # The final modified signal is our baseline estimate
    return y_modified

def process_uploaded_file(uploaded_file):
    """
    Process an uploaded chromatogram file.
    
    Parameters:
    -----------
    uploaded_file : UploadedFile
        Streamlit uploaded file object
    """
    from models.chromatogram import add_new_chromatogram
    
    try:
        # Determine file type by extension
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        if file_extension in ['csv', 'txt']:
            # Read the data based on file type
            if file_extension == 'csv':
                df = pd.read_csv(uploaded_file)
            else:  # txt file
                df = pd.read_csv(uploaded_file, sep='\t')
            
            # Create a new chromatogram
            chrom_id = len(st.session_state.chromatograms) + 1
            chrom_name = add_new_chromatogram()
            
            # Extract x and y columns (assuming first two columns)
            x_col = df.columns[0]
            y_col = df.columns[1]
            
            # Update the chromatogram with actual data
            st.session_state.chromatograms[chrom_id]['data'] = {
                'x': df[x_col].values,
                'y': df[y_col].values
            }
            
            # Update file information
            st.session_state.chromatograms[chrom_id]['file_path'] = uploaded_file.name
            st.session_state.chromatograms[chrom_id]['file_name'] = uploaded_file.name.split('.')[0]
            
            # Set as active chromatogram
            st.session_state.active_chromatogram = chrom_id
            
            return True
    except Exception as e:
        st.error(f"Error processing file: {e}")
        return False