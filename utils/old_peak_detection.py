# utils/peak_detection.py - Enhanced with Integration

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.integrate import trapezoid
import copy
import plotly.graph_objects as go
from typing import Dict, List, Tuple, Optional

class PeakDetectionSettings:
    """Settings for peak detection and integration."""
    def __init__(self):
        self.snr = 3.0
        self.slope_threshold = 0.02
        self.baseline_iterations = 50
        self.percentile = 5
        self.extension_factor = 1.5
        self.show_peak_markers = True
        self.integration_method = 'trapezoid'  # 'trapezoid' or 'simpson'
        self.baseline_correction = True

class PeakIntegrationManager:
    """Manages peak integration for HPLC data with compatibility to Chromeleon imports."""
    
    def __init__(self):
        self.detected_peaks = {}  # Store detected peaks by filename
        self.imported_peaks = {}  # Store imported Chromeleon peaks
        self.peak_colors = {}     # Store consistent colors for peaks
        self.color_index = 0
        
    def clear_peaks(self, filename=None):
        """Clear peaks for a specific file or all files."""
        if filename:
            self.detected_peaks.pop(filename, None)
            self.peak_colors.pop(filename, None)
        else:
            self.detected_peaks.clear()
            self.imported_peaks.clear()
            self.peak_colors.clear()
        
    def add_imported_peaks(self, filename, integration_table, peak_table=None):
        """Add peaks from Chromeleon integration table."""
        if integration_table is None or integration_table.empty:
            return
            
        imported_peaks = []
        for _, row in integration_table.iterrows():
            # Skip total rows
            peak_no = str(row.get('No.', row.get('No', ''))).strip()
            if peak_no.lower() in ['total', 'n.a.', ''] or pd.isna(peak_no):
                continue
                
            # Convert German decimal format
            rt = self._convert_german_float(row.get('Retention Time', 0))
            area = self._convert_german_float(row.get('Area', 0))
            height = self._convert_german_float(row.get('Height', 0))
            rel_area = self._convert_german_float(row.get('Relative Area', 0))
            
            if rt <= 0:  # Skip invalid peaks
                continue
                
            # Find corresponding peak analysis data if available
            peak_analysis = {}
            if peak_table is not None:
                for _, p_row in peak_table.iterrows():
                    if str(p_row.get('No.', '')).strip() == peak_no:
                        peak_analysis = p_row.to_dict()
                        break
            
            # Create peak object compatible with detected peaks
            peak = {
                'peak_no': int(peak_no) if peak_no.isdigit() else peak_no,
                'retention_time': rt,
                'height': height,
                'area': area,
                'relative_area': rel_area,
                'start_time': rt - 0.1,  # Estimate from RT
                'end_time': rt + 0.1,    # Estimate from RT
                'width': self._convert_german_float(peak_analysis.get('Width (50%)', 0.2)),
                'width_half_height': self._convert_german_float(peak_analysis.get('Width (50%)', 0.2)),
                'resolution': peak_analysis.get('Resolution (EP)', 'n.a.'),
                'asymmetry': self._convert_german_float(peak_analysis.get('Asymmetry (EP)', 1.0)),
                'plates': int(self._convert_german_float(peak_analysis.get('Plates (EP)', 0))),
                'type': peak_analysis.get('Type', 'Unknown'),
                'source': 'imported',
                'color_hex': self._get_consistent_color(filename, peak_no),
                'color_rgba': None  # Will be set when needed
            }
            
            # Set RGBA color
            peak['color_rgba'] = self._hex_to_rgba(peak['color_hex'], 0.3)
            imported_peaks.append(peak)
            
        self.imported_peaks[filename] = imported_peaks
        print(f"[PEAK] Added {len(imported_peaks)} imported peaks for {filename}")
        
    def detect_peak_at_time(self, filename, data, retention_time, threshold=None, settings=None):
        """Detect a single peak at specified retention time."""
        if settings is None:
            settings = PeakDetectionSettings()
            
        peak = detect_peak_near_click(retention_time, data, threshold=threshold, settings=settings)
        if peak:
            peak['source'] = 'detected'
            peak['peak_no'] = self._get_next_peak_number(filename)
            peak['color_hex'] = self._get_consistent_color(filename, peak['peak_no'])
            peak['color_rgba'] = self._hex_to_rgba(peak['color_hex'], 0.3)
            
            # Add to detected peaks
            if filename not in self.detected_peaks:
                self.detected_peaks[filename] = []
            self.detected_peaks[filename].append(peak)
            
            print(f"[PEAK] Detected peak {peak['peak_no']} at {retention_time:.3f} min")
            return peak
        return None
        
    def detect_all_peaks_auto(self, filename, data, threshold=None, settings=None):
        """Automatically detect all peaks in the data."""
        if settings is None:
            settings = PeakDetectionSettings()
            
        peaks = detect_all_peaks(data, threshold=threshold, settings=settings)
        if peaks:
            for peak in peaks:
                peak['source'] = 'detected'
                peak['peak_no'] = self._get_next_peak_number(filename)
                peak['color_hex'] = self._get_consistent_color(filename, peak['peak_no'])
                peak['color_rgba'] = self._hex_to_rgba(peak['color_hex'], 0.3)
                
            # Add to detected peaks
            if filename not in self.detected_peaks:
                self.detected_peaks[filename] = []
            self.detected_peaks[filename].extend(peaks)
            
            print(f"[PEAK] Auto-detected {len(peaks)} peaks for {filename}")
            return peaks
        return []
        
    def get_all_peaks(self, filename):
        """Get all peaks (imported + detected) for a filename."""
        all_peaks = []
        
        # Add imported peaks
        if filename in self.imported_peaks:
            all_peaks.extend(self.imported_peaks[filename])
            
        # Add detected peaks
        if filename in self.detected_peaks:
            all_peaks.extend(self.detected_peaks[filename])
            
        # Sort by retention time
        all_peaks.sort(key=lambda p: p['retention_time'])
        return all_peaks
        
    def create_combined_table(self, filename):
        """Create a combined integration table with imported and detected peaks."""
        all_peaks = self.get_all_peaks(filename)
        if not all_peaks:
            return None
            
        table_data = []
        for peak in all_peaks:
            row = {
                'No.': peak['peak_no'],
                'Source': peak['source'].title(),
                'Retention Time (min)': f"{peak['retention_time']:.3f}",
                'Height (mAU)': f"{peak['height']:.1f}",
                'Area (mAU·min)': f"{peak['area']:.3f}",
                'Area %': f"{peak.get('relative_area', 0):.2f}",
                'Width (min)': f"{peak.get('width_half_height', 0):.3f}",
                'Resolution': peak.get('resolution', 'n.a.'),
                'Asymmetry': f"{peak.get('asymmetry', 1.0):.2f}",
                'Plates': peak.get('plates', 0) or 0
            }
            table_data.append(row)
            
        return pd.DataFrame(table_data)
        
    def create_peak_traces(self, filename, data=None):
        """Create plotly traces for peak visualization."""
        all_peaks = self.get_all_peaks(filename)
        if not all_peaks or data is None:
            return []
            
        traces = []
        
        # Extract data arrays
        if isinstance(data, dict):
            x_data = np.array(data['x'])
            y_data = np.array(data['y'])
        elif hasattr(data, 'index') and hasattr(data, 'values'):
            x_data = data.index.values
            y_data = data.values
        else:
            return traces
            
        for peak in all_peaks:
            rt = peak['retention_time']
            
            # Find closest data point
            idx = np.abs(x_data - rt).argmin()
            peak_x = x_data[idx]
            peak_y = y_data[idx]
            
            # Peak marker
            marker_trace = go.Scatter(
                x=[peak_x],
                y=[peak_y],
                mode='markers',
                marker=dict(
                    symbol='triangle-up',
                    size=10,
                    color=peak['color_hex'],
                    line=dict(width=1, color='black')
                ),
                name=f"Peak {peak['peak_no']} ({peak['source']})",
                hovertemplate=(
                    f"<b>Peak {peak['peak_no']}</b> ({peak['source']})<br>"
                    f"RT: {peak['retention_time']:.3f} min<br>"
                    f"Height: {peak['height']:.1f} mAU<br>"
                    f"Area: {peak['area']:.3f} mAU·min<br>"
                    f"Area %: {peak.get('relative_area', 0):.2f}%<br>"
                    "<extra></extra>"
                ),
                showlegend=False
            )
            traces.append(marker_trace)
            
            # Integration area (if we have start/end times)
            if 'start_time' in peak and 'end_time' in peak:
                start_idx = np.abs(x_data - peak['start_time']).argmin()
                end_idx = np.abs(x_data - peak['end_time']).argmin()
                
                if start_idx < end_idx:
                    area_x = x_data[start_idx:end_idx+1]
                    area_y = y_data[start_idx:end_idx+1]
                    
                    area_trace = go.Scatter(
                        x=area_x,
                        y=area_y,
                        fill='tonexty',
                        fillcolor=peak['color_rgba'],
                        line=dict(width=0),
                        name=f"Peak {peak['peak_no']} Integration",
                        hoverinfo='skip',
                        showlegend=False
                    )
                    traces.append(area_trace)
                    
        return traces
        
    def _convert_german_float(self, value):
        """Convert German decimal format to float."""
        if pd.isna(value):
            return 0.0
        try:
            str_val = str(value).replace(',', '.')
            return float(str_val)
        except (ValueError, TypeError):
            return 0.0
            
    def _get_next_peak_number(self, filename):
        """Get the next peak number for detected peaks."""
        all_peaks = self.get_all_peaks(filename)
        if not all_peaks:
            return 1
            
        max_no = 0
        for peak in all_peaks:
            try:
                peak_no = int(peak['peak_no'])
                max_no = max(max_no, peak_no)
            except (ValueError, TypeError):
                pass
                
        return max_no + 1
        
    def _get_consistent_color(self, filename, peak_no):
        """Get consistent color for a peak."""
        key = f"{filename}_{peak_no}"
        if key not in self.peak_colors:
            colors = [
                '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
                '#1abc9c', '#e67e22', '#34495e', '#f1c40f', '#e91e63'
            ]
            self.peak_colors[key] = colors[self.color_index % len(colors)]
            self.color_index += 1
        return self.peak_colors[key]
        
    def _hex_to_rgba(self, hex_color, alpha=0.3):
        """Convert hex color to rgba."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"

# Global peak manager instance
peak_manager = PeakIntegrationManager()

def detect_peak_near_click(x_coord, data, search_radius=0.5, threshold=None, settings=None):
    """Enhanced version of your existing function."""
    if settings is None:
        settings = PeakDetectionSettings()
    
    if not data or 'x' not in data or 'y' not in data:
        return None
        
    x = np.array(data['x'])
    y = np.array(data['y'])
    
    # Find index closest to click
    click_idx = np.abs(x - x_coord).argmin()
    
    # Define search window around click
    if len(x) > 1:
        dx = x[1] - x[0]
        window_size = int(search_radius / dx)
    else:
        window_size = 1
    
    left_idx = max(0, click_idx - window_size)
    right_idx = min(len(y) - 1, click_idx + window_size)
    
    # Find the highest peak in the window
    search_window = y[left_idx:right_idx+1]
    if len(search_window) == 0:
        return None
    
    local_max_idx = np.argmax(search_window)
    peak_idx = left_idx + local_max_idx
    
    # Get peak properties
    peak_height = y[peak_idx]
    peak_time = x[peak_idx]
    
    # Apply threshold check if specified
    if threshold is not None and peak_height < threshold:
        return None
    
    # Determine peak boundaries using slope threshold
    slope_threshold = settings.slope_threshold
    
    # Look for significant slope change going left
    start_idx = peak_idx
    while start_idx > 0:
        if len(x) > start_idx:
            slope = (y[start_idx] - y[start_idx-1]) / (x[start_idx] - x[start_idx-1])
            slope_percent = abs(slope / peak_height) if peak_height > 0 else 0
            
            if slope_percent < slope_threshold or y[start_idx] < peak_height * 0.01:
                break
        start_idx -= 1
    
    # Look for significant slope change going right
    end_idx = peak_idx
    while end_idx < len(y) - 1:
        if len(x) > end_idx + 1:
            slope = (y[end_idx] - y[end_idx+1]) / (x[end_idx+1] - x[end_idx])
            slope_percent = abs(slope / peak_height) if peak_height > 0 else 0
            
            if slope_percent < slope_threshold or y[end_idx] < peak_height * 0.01:
                break
        end_idx += 1
    
    # Extend the boundaries
    extension = int((end_idx - start_idx) * (settings.extension_factor - 1) / 2)
    start_idx = max(0, start_idx - extension)
    end_idx = min(len(y) - 1, end_idx + extension)
    
    # Calculate width at half height
    half_height = peak_height / 2
    
    # Find left half-height point
    left_hh_idx = peak_idx
    while left_hh_idx > start_idx and y[left_hh_idx] >= half_height:
        left_hh_idx -= 1
    
    # Find right half-height point  
    right_hh_idx = peak_idx
    while right_hh_idx < end_idx and y[right_hh_idx] >= half_height:
        right_hh_idx += 1
    
    # Interpolate for more accurate half-height points
    if left_hh_idx < len(x) - 1 and left_hh_idx >= 0:
        x_left_hh = x[left_hh_idx]
        if y[left_hh_idx] < half_height < y[left_hh_idx + 1]:
            x1, x2 = x[left_hh_idx], x[left_hh_idx + 1]
            y1, y2 = y[left_hh_idx], y[left_hh_idx + 1]
            if y2 != y1:
                x_left_hh = x1 + (half_height - y1) * (x2 - x1) / (y2 - y1)
    else:
        x_left_hh = x[start_idx]
    
    if right_hh_idx < len(x) and right_hh_idx > 0:
        x_right_hh = x[right_hh_idx]
        if y[right_hh_idx] < half_height < y[right_hh_idx - 1]:
            x1, x2 = x[right_hh_idx - 1], x[right_hh_idx]
            y1, y2 = y[right_hh_idx - 1], y[right_hh_idx]
            if y2 != y1:
                x_right_hh = x1 + (half_height - y1) * (x2 - x1) / (y2 - y1)
    else:
        x_right_hh = x[end_idx]
    
    width_hh = abs(x_right_hh - x_left_hh)
    
    # Calculate area by numerical integration
    if end_idx > start_idx:
        area = trapezoid(y[start_idx:end_idx+1], x[start_idx:end_idx+1])
    else:
        area = 0
    
    # Create peak info
    peak_info = {
        "peak_idx": peak_idx,
        "retention_time": peak_time,
        "height": peak_height,
        "area": area,
        "start_time": x[start_idx],
        "end_time": x[end_idx],
        "width": x[end_idx] - x[start_idx],
        "width_half_height": width_hh,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "relative_area": 0.0,  # Will be calculated later
        "asymmetry": 1.0,      # Default value
        "plates": 0,           # Default value
        "resolution": 'n.a.'   # Default value
    }
    
    return peak_info

def detect_all_peaks(data, threshold=None, settings=None):
    """Enhanced version of your existing function."""
    if settings is None:
        settings = PeakDetectionSettings()
    
    if not data or 'y' not in data:
        return []
    
    y = np.array(data['y'])
    
    # Set default threshold if not provided
    if threshold is None:
        threshold = np.max(y) * 0.05
    
    # Find all peaks above threshold
    peak_indices, properties = find_peaks(y, height=threshold, prominence=threshold*0.2)
    
    # Create a list to hold all peaks
    peaks = []
    
    # Add each detected peak
    for peak_idx in peak_indices:
        if 'x' in data and len(data['x']) > peak_idx:
            x_coord = data['x'][peak_idx]
            new_peak = detect_peak_near_click(x_coord, data, search_radius=0.2, threshold=threshold, settings=settings)
            if new_peak:
                peaks.append(new_peak)
    
    return peaks

def generate_peak_color(retention_time):
    """Generate a color based on retention time."""
    import colorsys
    
    # Convert retention time to a hue (0-1)
    hue = (retention_time * 0.1) % 1.0
    # Use high saturation and medium lightness
    r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
    
    # Convert to hex
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def hex_to_rgba(hex_color, alpha=1.0):
    """Convert hex color to rgba string."""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16) 
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"