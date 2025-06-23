# utils/file_upload_handler.py
import streamlit as st
import tempfile
import os
import numpy as np
from scipy.signal import savgol_filter
from data_readers.chromatogram_reader import ChromatogramReader
from utils.toast import show_toast

def process_single_chromatogram(chrom_data, smoothing=8):
    """
    Process a single chromatogram and prepare it for peak detection.
    This is used when a new chromatogram is uploaded to ensure it's
    immediately available in the preprocessed_data structure.
    
    Parameters:
    -----------
    chrom_data : dict
        Dictionary containing chromatogram data
    smoothing : int, optional
        Smoothing window size (default: 8)
        
    Returns:
    --------
    dict
        Dictionary containing processed chromatogram data
    """
    import numpy as np
    from scipy.signal import savgol_filter
    
    # Get raw data
    if 'chromatogram_data' in chrom_data:
        # Data is already in a DataFrame
        df = chrom_data['chromatogram_data']
        x = df["Time (min)"].values
        y = df["Value (mAU)"].values
    elif 'x' in chrom_data and 'y' in chrom_data:
        x = chrom_data['x']
        y = chrom_data['y']
    else:
        print("No valid data found in chromatogram")
        return None
    
    # Safety check for data types
    if not isinstance(x, np.ndarray):
        try:
            x = np.array(x)
        except Exception as e:
            print(f"Error converting x to numpy array: {e}")
            return None
            
    if not isinstance(y, np.ndarray):
        try:
            y = np.array(y)
        except Exception as e:
            print(f"Error converting y to numpy array: {e}")
            return None
    
    # Check if we have any data points
    if len(x) == 0 or len(y) == 0:
        print(f"Chromatogram has no data points.")
        return None
    
    # Smoothing (Savitzky-Golay filter)
    if smoothing > 0:
        # Make sure smoothing window is odd and not too large
        window_size = min(smoothing * 2 + 1, len(y) - 1)
        # Ensure window size is odd
        if window_size % 2 == 0:
            window_size -= 1
            
        if window_size > 2:
            try:
                y_smooth = savgol_filter(y, window_size, 2)
            except Exception as e:
                print(f"Error applying Savitzky-Golay filter: {e}")
                # Fallback if window size is too large
                y_smooth = y
        else:
            y_smooth = y
    else:
        y_smooth = y
        
    # Calculate baseline using a simple alternative that estimates baseline as the 5th percentile in a rolling window
    window_size = max(int(len(y) / 10), 1)  # 10% of the data points or at least 1
    baseline = np.zeros_like(y)
    
    # Calculate a simple baseline approximation for initialization
    for i in range(len(y)):
        start = max(0, i - window_size)
        end = min(len(y), i + window_size + 1)
        window = y_smooth[start:end]
        baseline[i] = np.percentile(window, 5)  # Use 5th percentile as baseline estimate
    
    # Calculate signal after baseline correction
    y_corrected = np.maximum(y_smooth - baseline, 0)  # Ensure non-negative values
    
    # Return processed data
    return {
        'x': x,
        'y': y,
        'y_smooth': y_smooth,
        'baseline': baseline,
        'y_corrected': y_corrected
    }


def handle_chromatogram_upload(uploaded_file, preprocessed_data):
    """
    Process an uploaded chromatogram file and add it to the session state.
    
    Parameters:
    -----------
    uploaded_file : streamlit.UploadedFile
        The uploaded file object from Streamlit
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
        
    Returns:
    --------
    bool
        True if file was successfully processed, False otherwise
    """
    import pandas as pd
    import re
    from io import StringIO
    
    # Check if the file has already been uploaded
    for chrom_id, chrom_data in st.session_state.chromatograms.items():
        if chrom_data.get('file_name') == uploaded_file.name:
            show_toast(f"File {uploaded_file.name} has already been uploaded.", "warning")
            return False
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
        # Write the uploaded file content to the temp file
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
    
    try:
        # Read the file content directly and fix European numbers
        with open(tmp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract filename (without extension) for legend
        file_name = os.path.splitext(uploaded_file.name)[0].replace("_UV_VIS_1", "")
        
        # Extract wavelength information
        wavelength_match = re.search(r"WVL:\s*(\d{3})\s*nm", content)
        if wavelength_match:
            wavelength = wavelength_match.group(1)
            print(f"Extracted wavelength: {wavelength} nm from {file_name}")
        else:
            raise ValueError(f"Wavelength not found in the file: {uploaded_file.name}")
        
        # Find the Raw Data section
        raw_data_start = content.find("Raw Data:")
        if raw_data_start == -1:
            raise ValueError(f"'Raw Data:' section not found in the file: {uploaded_file.name}")
        
        raw_data = content[raw_data_start + len("Raw Data:"):].strip()
        
        # Fix European numbers: remove dots (thousands separators), convert commas to dots (decimal)
        raw_data = raw_data.replace(".", "").replace(",", ".")
        
        # Parse with pandas
        df = pd.read_csv(StringIO(raw_data), sep="\t")
        
        # Only keep 'Time (min)' and 'Value (mAU)' columns
        if not {'Time (min)', 'Value (mAU)'}.issubset(df.columns):
            raise ValueError(f"Required columns not found in the file: {uploaded_file.name}")

        df = df[['Time (min)', 'Value (mAU)']]

        if df.empty:
            raise ValueError(f"No data found in 'Raw Data:' section of the file: {uploaded_file.name}")
        else:
            print(f"Loaded chromatogram data from {file_name} with {len(df)} points.")
        
        # Create a new chromatogram ID
        new_id = max(st.session_state.chromatograms.keys()) + 1 if st.session_state.chromatograms else 0
        
        # Debug: Print the first few data points
        print(f"First 5 data points from uploaded file {file_name}:")
        for i in range(min(5, len(df))):
            print(f"  Time: {df['Time (min)'].iloc[i]}, Value: {df['Value (mAU)'].iloc[i]}")
        
        # Get color for this chromatogram
        color = get_color_from_palette(new_id)
        


        # Create a new chromatogram dictionary
        chrom_dict = {
            'name': file_name,
            'file_name': uploaded_file.name,
            'wavelength': wavelength,
            'color': color,
            'visible': True,
            'type': 'hplc',
            'data': {
                'x': df["Time (min)"].values,
                'y': df["Value (mAU)"].values
            },
            'chromatogram_data': df,  # Store the DataFrame directly
            'is_uploaded': True
        }


        # Add to session state
        st.session_state.chromatograms[new_id] = chrom_dict
        
        # Initialize empty peaks list for this chromatogram
        if new_id not in st.session_state.selected_peaks:
            st.session_state.selected_peaks[new_id] = []
        
        # Pre-process this chromatogram to ensure data is available
        # Get smoothing parameter from session state
        smoothing = st.session_state.get('smoothing', 8)
        
        # Process this individual chromatogram and add to preprocessed_data
        processed_data = process_single_chromatogram(chrom_dict, smoothing)
        if processed_data:
            preprocessed_data[new_id] = processed_data
            
            # Initialize auto-threshold if needed (5% of max by default)
            if new_id not in st.session_state.auto_thresholds:
                max_y = float(np.max(processed_data['y_corrected']))
                st.session_state.auto_thresholds[new_id] = max_y * 0.05
            
            # Set as active chromatogram
            st.session_state.active_chromatogram = new_id
            
            show_toast(f"Successfully loaded {file_name}", "success")
            return True
        else:
            show_toast(f"Error processing data in {uploaded_file.name}.", "error")
            return False
            
    except Exception as e:
        show_toast(f"Error processing file {uploaded_file.name}: {str(e)}", "error")
        return False
    finally:
        # Clean up the temporary file
        try:
            os.unlink(tmp_path)
        except:
            pass

def get_color_from_palette(index):
    """
    Get a color from the palette based on index.
    
    Parameters:
    -----------
    index : int
        Index to select color
        
    Returns:
    --------
    str
        Color string for the chromatogram
    """
    # Define a color palette
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]
    
    # Return color based on index (cycling through the palette)
    return colors[index % len(colors)]