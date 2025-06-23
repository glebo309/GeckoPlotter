#utils/peak_deteection.py

import numpy as np
import streamlit as st
from scipy.signal import find_peaks
from scipy.integrate import trapezoid
from config.settings import get_color_from_palette
from utils.color_utils import generate_random_color, hex_to_rgba
import copy


def detect_peak_near_click(x_coord, preprocessed_data, search_radius=0.5, preserve_color=None, chrom_id=None, threshold=None):
    """
    Find the nearest peak to the clicked coordinate.
    
    Parameters:
    -----------
    x_coord : float
        X coordinate (time) of the click or search point
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
    search_radius : float, optional
        Radius to search around the click (default: 0.5)
    preserve_color : dict, optional
        Color info to preserve (for recalculation)
    chrom_id : int, optional
        Chromatogram ID (default: active chromatogram)
    threshold : float, optional
        Height threshold for peak detection (optional)
        
    Returns:
    --------
    dict or None
        Dictionary containing peak information, or None if no peak found
    """

    if chrom_id is None:
        chrom_id = st.session_state.active_chromatogram
        
    # Check if chromatogram exists in preprocessed_data
    if chrom_id not in preprocessed_data:
        return None
        
    # Get processed data for this chromatogram
    x = preprocessed_data[chrom_id]['x']
    y_corrected = preprocessed_data[chrom_id]['y_corrected']
    y_smooth = preprocessed_data[chrom_id]['y_smooth']
    
    # Find index closest to click
    click_idx = np.abs(x - x_coord).argmin()
    
    # Define search window around click
    window_size = int(search_radius / (x[1] - x[0]))
    left_idx = max(0, click_idx - window_size)
    right_idx = min(len(y_corrected) - 1, click_idx + window_size)
    
    # Find the highest peak in the window
    search_window = y_corrected[left_idx:right_idx+1]
    if len(search_window) == 0:
        return None
    
    local_max_idx = np.argmax(search_window)
    peak_idx = left_idx + local_max_idx
    
    # Get peak properties
    peak_height = y_corrected[peak_idx]
    peak_time = x[peak_idx]
    
    # Apply threshold check if specified
    if threshold is not None and peak_height < threshold:
        return None  # Exit immediately if peak doesn't meet threshold
    
    # Determine peak boundaries using a very low slope threshold
    slope_threshold = st.session_state.settings['slope_threshold']
    
    # Look for significant slope change going left
    start_idx = peak_idx
    while start_idx > 0:
        # Calculate slope relative to peak height
        slope = (y_corrected[start_idx] - y_corrected[start_idx-1]) / (x[start_idx] - x[start_idx-1])
        slope_percent = abs(slope / peak_height)
        
        # Stop when slope drops below threshold or signal drops below 1% of peak height
        if slope_percent < slope_threshold or y_corrected[start_idx] < peak_height * 0.01:
            break
        start_idx -= 1
    
    # Look for significant slope change going right
    end_idx = peak_idx
    while end_idx < len(y_corrected) - 1:
        # Calculate slope relative to peak height
        slope = (y_corrected[end_idx] - y_corrected[end_idx+1]) / (x[end_idx+1] - x[end_idx])
        slope_percent = abs(slope / peak_height)
        
        # Stop when slope drops below threshold or signal drops below 1% of peak height
        if slope_percent < slope_threshold or y_corrected[end_idx] < peak_height * 0.01:
            break
        end_idx += 1
    
    # Extend the boundaries to capture more of the peak
    extension = int((end_idx - start_idx) * (st.session_state.settings['extension_factor'] - 1) / 2)
    start_idx = max(0, start_idx - extension)
    end_idx = min(len(y_corrected) - 1, end_idx + extension)
    
    # Calculate width at half height
    half_height = peak_height / 2
    
    # Find left half-height point
    left_hh_idx = peak_idx
    while left_hh_idx > start_idx:
        if y_corrected[left_hh_idx] < half_height:
            # Found point below half height, interpolate
            x1, x2 = x[left_hh_idx], x[left_hh_idx + 1]
            y1, y2 = y_corrected[left_hh_idx], y_corrected[left_hh_idx + 1]
            x_left_hh = x1 + (half_height - y1) * (x2 - x1) / (y2 - y1)
            break
        left_hh_idx -= 1
    else:
        x_left_hh = x[start_idx]
    
    # Find right half-height point
    right_hh_idx = peak_idx
    while right_hh_idx < end_idx:
        if y_corrected[right_hh_idx] < half_height:
            # Found point below half height, interpolate
            x1, x2 = x[right_hh_idx - 1], x[right_hh_idx]
            y1, y2 = y_corrected[right_hh_idx - 1], y_corrected[right_hh_idx]
            x_right_hh = x1 + (half_height - y1) * (x2 - x1) / (y2 - y1)
            break
        right_hh_idx += 1
    else:
        x_right_hh = x[end_idx]
    
    width_hh = abs(x_right_hh - x_left_hh)
    
    # Calculate area by numerical integration
    area = trapezoid(y_corrected[start_idx:end_idx+1], x[start_idx:end_idx+1])
    
    # In detect_peak_near_click, update the color generation part
    if preserve_color is None:
        try:
            # Check if there are existing peaks with similar retention times
            from models.calibration import group_peaks_by_retention_time
            
            # Only run grouping if we already have some peaks
            has_similar_peak = False
            similar_peak_color = None
            
            if hasattr(st.session_state, 'selected_peaks') and st.session_state.selected_peaks:
                # Collect all existing peaks
                existing_peaks = []
                for existing_chrom_id, existing_peaks_list in st.session_state.selected_peaks.items():
                    for existing_peak in existing_peaks_list:
                        existing_peaks.append({
                            'chromatogram_id': existing_chrom_id,
                            'peak': existing_peak,
                            'midpoint': existing_peak['Midpoint (min)']
                        })
                
                # Add this new peak temporarily
                temp_peak = {
                    'chromatogram_id': chrom_id,
                    'peak': {'Midpoint (min)': peak_time},
                    'midpoint': peak_time
                }
                all_peaks = existing_peaks + [temp_peak]
                
                # Get the time window
                time_window = 0.2  # Default
                if 'peak_matching_window' in st.session_state:
                    time_window = st.session_state.peak_matching_window
                
                # Group peaks
                peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
                
                # Find the group containing our new peak
                for group in peak_groups:
                    for peak_info in group:
                        if peak_info == temp_peak:  # Found our peak's group
                            # Check if there are other peaks in this group
                            if len(group) > 1:
                                has_similar_peak = True
                                # Find the first existing peak in this group
                                for other_peak_info in group:
                                    if other_peak_info != temp_peak:
                                        # Get its color
                                        similar_peak = other_peak_info['peak']
                                        if 'color' in similar_peak and 'color_hex' in similar_peak:
                                            similar_peak_color = {
                                                'color': similar_peak['color'],
                                                'color_hex': similar_peak['color_hex'],
                                                'opacity': similar_peak.get('opacity', 0.4)
                                            }
                                        break
                            break
            
            # If we found a similar peak, use its color
            if has_similar_peak and similar_peak_color:
                color_hex = similar_peak_color['color_hex']
                rgba_color = similar_peak_color['color']
                opacity = similar_peak_color['opacity']
            else:
                # Otherwise generate a new color
                import importlib
                colourmaps = importlib.import_module("utils.colourmaps")
                
                # Get current theme from session state
                current_theme = "get_color_from_palette"
                if 'plot_settings' in st.session_state and 'color_palette_function' in st.session_state.plot_settings:
                    current_theme = st.session_state.plot_settings['color_palette_function']
                
                # Get the palette function
                palette_func = getattr(colourmaps, current_theme)
                
                # Generate a color based on peak time
                # Using a formula that creates different colors for different times
                rt_bin = int(peak_time * 5)  # 5 is just a multiplier to create distinct bins
                rgb = palette_func(rt_bin)
                
                # Convert to hex and rgba
                color_hex = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
                rgba_color = f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.4)"
                opacity = 0.4
            
            user_changed_color = False
            
        except Exception as e:
            # Fallback to default colors if there's any error
            print(f"Error generating peak color: {e}")
            color_hex = "#ff4500"  # OrangeRed
            rgba_color = "rgba(255, 69, 0, 0.4)"
            opacity = 0.4
            user_changed_color = False

    else:
        color_hex = preserve_color['color_hex']
        rgba_color = preserve_color['color']
        opacity = preserve_color['opacity']
        user_changed_color = preserve_color['user_changed_color']
    
    # Create peak info
    peak_info = {
        "id": st.session_state.next_peak_id,
        "peak_idx": peak_idx,
        "Midpoint (min)": peak_time,
        "Height (a.u.)": peak_height,
        "Area (a.u.·min)": area,
        "Min Time (min)": x[start_idx],
        "Max Time (min)": x[end_idx],
        "Width (min)": x[end_idx] - x[start_idx],
        "Width at Half-Height (min)": width_hh,
        "Start Index": start_idx,
        "End Index": end_idx,
        "color": rgba_color,
        "color_hex": color_hex,
        "opacity": opacity,
        "user_changed_color": user_changed_color,
        "name": f"Peak {st.session_state.next_peak_id}"  # Add a name field
    }
    
    return peak_info

def detect_all_peaks(preprocessed_data, chrom_id, threshold=None):


    """
    Detect all peaks in a chromatogram above a threshold.
    
    Parameters:
    -----------
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
    chrom_id : int
        Chromatogram ID
    threshold : float, optional
        Threshold for peak detection (default: auto-threshold for the chromatogram)
        
    Returns:
    --------
    list
        List of peak dictionaries
    """
    # Get threshold for this chromatogram
    if threshold is None:
        if chrom_id in st.session_state.auto_thresholds:
            threshold = st.session_state.auto_thresholds[chrom_id]
        else:
            # Default to 5% of max
            max_y = np.max(preprocessed_data[chrom_id]['y_corrected'])
            threshold = max_y * 0.05
    
    # Find all peaks above threshold
    y_corrected = preprocessed_data[chrom_id]['y_corrected']
    peak_indices, properties = find_peaks(y_corrected, height=threshold)
    
    # Create a list to hold all peaks
    peaks = []
    
    # Add each detected peak
    temp_next_peak_id = st.session_state.next_peak_id
    for peak_idx in peak_indices:
        x_coord = preprocessed_data[chrom_id]['x'][peak_idx]
        new_peak = detect_peak_near_click(x_coord, preprocessed_data, search_radius=0.2, chrom_id=chrom_id)
        if new_peak:
            peaks.append(new_peak)
            st.session_state.next_peak_id += 1
    

    return peaks


    """
    Recalculate all peaks with current settings while preserving colors.
    
    Parameters:
    -----------
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
    old_settings : dict, optional
        Previous settings for comparison
        
    Returns:
    --------
    None
    """
    for chrom_id, peaks in st.session_state.selected_peaks.items():
        if peaks:
            # Store the original peaks
            original_peaks = peaks.copy()
            
            # Clear peaks and reuse the IDs
            temp_next_peak_id = st.session_state.next_peak_id
            st.session_state.selected_peaks[chrom_id] = []
            
            # Add recalculated peaks while preserving colors and names
            for peak in original_peaks:
                x_coord = peak['Midpoint (min)']
                
                # Extract color info to preserve it
                color_info = {
                    'color': peak['color'],
                    'color_hex': peak['color_hex'],
                    'opacity': peak['opacity'],
                    'user_changed_color': peak.get('user_changed_color', False)
                }
                
                # Detect peak with preserved color
                new_peak = detect_peak_near_click(
                    x_coord, 
                    preprocessed_data,
                    preserve_color=color_info, 
                    chrom_id=chrom_id
                )
                
                if new_peak:
                    # Keep the original ID and name
                    new_peak['id'] = peak['id']
                    new_peak['name'] = peak.get('name', f"Peak {peak['id']}")
                    st.session_state.selected_peaks[chrom_id].append(new_peak)
            
            # Restore the next_peak_id
            st.session_state.next_peak_id = temp_next_peak_id

def recalculate_all_peaks(preprocessed_data, old_settings=None):
    """
    Recalculate all peaks with current settings while preserving colors.
    
    Parameters:
    -----------
    preprocessed_data : dict
        Dictionary containing processed chromatogram data
    old_settings : dict, optional
        Previous settings for comparison
        
    Returns:
    --------
    None
    """
    for chrom_id, peaks in st.session_state.selected_peaks.items():
        if peaks and chrom_id in preprocessed_data:  # Make sure the chromatogram ID exists in preprocessed_data
            # Store the original peaks
            original_peaks = copy.deepcopy(peaks)
            
            # Clear peaks and reuse the IDs
            temp_next_peak_id = st.session_state.next_peak_id
            st.session_state.selected_peaks[chrom_id] = []
            
            # Add recalculated peaks while preserving colors and names
            for peak in original_peaks:
                x_coord = peak['Midpoint (min)']
                
                # Extract color info to preserve it
                color_info = {
                    'color': peak['color'],
                    'color_hex': peak['color_hex'],
                    'opacity': peak['opacity'],
                    'user_changed_color': peak.get('user_changed_color', False)
                }
                
                # Detect peak with preserved color
                new_peak = detect_peak_near_click(
                    x_coord, 
                    preprocessed_data,
                    preserve_color=color_info, 
                    chrom_id=chrom_id
                )
                
                if new_peak:
                    # Keep the original ID and name
                    new_peak['id'] = peak['id']
                    new_peak['name'] = peak.get('name', f"Peak {peak['id']}")
                    st.session_state.selected_peaks[chrom_id].append(new_peak)
            
            # Restore the next_peak_id
            st.session_state.next_peak_id = temp_next_peak_id