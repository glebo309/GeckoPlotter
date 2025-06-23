# ui/direct_parser.py

import streamlit as st
import pandas as pd
import numpy as np
from io import StringIO
import os
import tempfile
import random

def render_direct_input_parser():
    """
    Provide a direct text input option for pasting LC-MS data.
    This is a simple fallback that will work with any version of Streamlit.
    """
    st.write("### Direct LC-MS Data Input")
    st.info("Copy and paste your LC-MS data directly here. The data should have two columns: time and signal values.")
    
    # Text area for pasting data
    data_text = st.text_area(
        "Paste your LC-MS data here (time and signal values, separated by spaces, commas, or tabs):",
        height=200
    )
    
    # File name input
    file_name = st.text_input("Enter a name for this dataset:", "LC-MS_Dataset")
    
    # Process button
    if st.button("Process LC-MS Data"):
        if not data_text.strip():
            st.error("Please paste some data first.")
            return None
            
        try:
            # Convert the pasted text to a CSV format
            processed_text = []
            for line in data_text.strip().split('\n'):
                # Skip empty lines or header-like lines
                if not line.strip() or any(keyword in line.lower() for keyword in ['time', 'signal', 'header', 'column']):
                    continue
                    
                # Clean up the line
                line = line.strip().replace(',', ' ').replace('\t', ' ')
                
                # Extract numbers from the line
                parts = [part for part in line.split() if part.strip()]
                if len(parts) >= 2:  # Need at least two values
                    processed_text.append(f"{parts[0]},{parts[1]}")
            
            # Create a CSV string
            csv_text = "\n".join(processed_text)
            
            if not csv_text:
                st.error("No valid data found. Please check your input format.")
                return None
                
            # Parse the CSV data
            df = pd.read_csv(
                StringIO(csv_text),
                header=None,
                names=["time", "signal"]
            )
            
            # Convert to numeric, ignoring errors
            df = df.apply(pd.to_numeric, errors='coerce')
            
            # Drop any rows with NaN values
            df = df.dropna()
            
            if len(df) == 0:
                st.error("No valid data found after parsing. Please check your input format.")
                return None
                
            # Show a preview of the data
            st.write("Data preview:")
            st.write(df.head())
                
            # Extract x and y data
            x = df["time"].values
            y = df["signal"].values
            
            # Create a temporary file for compatibility with the existing processor
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as temp_file:
                df.to_csv(temp_file, index=False)
                temp_path = temp_file.name
            
            # Return file info
            return {
                "name": f"{file_name}.csv",
                "path": temp_path,
                "size": os.path.getsize(temp_path)
            }
            
        except Exception as e:
            st.error(f"Error processing LC-MS data: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            return None
            
    return None

def process_lcms_from_direct_input(file_info):
    """
    Process LC-MS data from direct input and add it to the chromatograms.
    
    Parameters:
    -----------
    file_info : dict
        Dictionary containing file information
        
    Returns:
    --------
    bool
        True if processing was successful, False otherwise
    """
    try:
        # Read the CSV file
        df = pd.read_csv(file_info["path"])
        
        # Extract x and y data
        x = df["time"].values
        y = df["signal"].values
        
        # Generate a random color
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        color = f"rgba({r}, {g}, {b}, 1)"
        
        # Generate a new chromatogram ID
        chrom_id = max(st.session_state.chromatograms.keys(), default=0) + 1
        
        # Create a clean name without extension
        name = file_info["name"].rsplit('.', 1)[0]
        
        # Add the chromatogram to session state
        st.session_state.chromatograms[chrom_id] = {
            'name': name,
            'visible': True,
            'color': color,
            'type': 'lcms',
            'data': {'x': x, 'y': y},
            'file_path': file_info["name"]
        }
        
        # Set as active chromatogram
        st.session_state.active_chromatogram = chrom_id
        
        # Initialize empty peaks list for this chromatogram
        if chrom_id not in st.session_state.selected_peaks:
            st.session_state.selected_peaks[chrom_id] = []
            
        # Clean up temporary file
        try:
            os.unlink(file_info["path"])
        except:
            pass
            
        return True
        
    except Exception as e:
        st.error(f"Error processing LC-MS data: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return False