# utils/peak_integration.py
import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from scipy.integrate import trapezoid
from typing import Dict, List, Tuple, Optional
import plotly.graph_objects as go
from scipy.integrate import simpson 
from scipy import signal, optimize
from scipy.ndimage import gaussian_filter1d


class PeakIntegrationManager:
    """Manage peak detection and integration for HPLC chromatograms"""
    

    def _find_peak_boundaries_advanced(self, x: np.ndarray, y: np.ndarray, peak_idx: int) -> Tuple[int, int]:
        """Find peak boundaries using second derivative and valley detection"""
        
        # Smooth data for better derivative calculation
        y_smooth = gaussian_filter1d(y, sigma=2)
        
        # Calculate derivatives
        dy = np.gradient(y_smooth)
        d2y = np.gradient(dy)
        
        # Method 1: Find inflection points (where second derivative changes sign)
        inflection_points = np.where(np.diff(np.sign(d2y)))[0]
        
        # Find valleys (local minima)
        valleys, _ = signal.find_peaks(-y, prominence=np.std(y)*0.1)
        
        # Combine both methods
        left_candidates = np.concatenate([
            inflection_points[inflection_points < peak_idx],
            valleys[valleys < peak_idx]
        ])
        
        right_candidates = np.concatenate([
            inflection_points[inflection_points > peak_idx],
            valleys[valleys > peak_idx]
        ])
        
        # Choose the closest valid boundary
        if len(left_candidates) > 0:
            start_idx = left_candidates[np.argmax(left_candidates)]
        else:
            start_idx = max(0, peak_idx - 30)
            
        if len(right_candidates) > 0:
            end_idx = right_candidates[np.argmin(right_candidates)]
        else:
            end_idx = min(len(y) - 1, peak_idx + 30)
        
        return start_idx, end_idx

    def calculate_baseline(self, x: np.ndarray, y: np.ndarray, start_idx: int, end_idx: int, method: str = 'perpendicular') -> np.ndarray:
        """Calculate baseline using different methods"""
        
        if method == 'perpendicular':
            # Straight line from start to end
            baseline = np.linspace(y[start_idx], y[end_idx], end_idx - start_idx + 1)
            
        elif method == 'valley':
            # Horizontal line at minimum between boundaries
            baseline = np.full(end_idx - start_idx + 1, min(y[start_idx], y[end_idx]))
            
        elif method == 'tangent':
            # Tangent skim for overlapping peaks
            window = 5
            
            # Fit lines at boundaries
            left_fit = np.polyfit(x[max(0, start_idx-window):start_idx+window], 
                                y[max(0, start_idx-window):start_idx+window], 1)
            right_fit = np.polyfit(x[end_idx-window:min(len(x), end_idx+window)], 
                                y[end_idx-window:min(len(x), end_idx+window)], 1)
            
            # Find intersection
            m1, b1 = left_fit
            m2, b2 = right_fit
            
            if abs(m1 - m2) > 1e-10:
                x_intersect = (b2 - b1) / (m1 - m2)
                baseline = np.zeros(end_idx - start_idx + 1)
                
                for i, xi in enumerate(x[start_idx:end_idx+1]):
                    if xi <= x_intersect:
                        baseline[i] = m1 * xi + b1
                    else:
                        baseline[i] = m2 * xi + b2
            else:
                baseline = np.linspace(y[start_idx], y[end_idx], end_idx - start_idx + 1)
                
        return baseline

    def _calculate_peak_properties(self, x: np.ndarray, y: np.ndarray, peak_idx: int, 
                                start_idx: int, end_idx: int, filename: str) -> Dict:
        """Calculate comprehensive peak properties"""
        peak_height = y[peak_idx]
        peak_time = x[peak_idx]
        
        # CRITICAL: Integration to y=0
        # Extract the peak segment
        y_segment = y[start_idx:end_idx+1]
        x_segment = x[start_idx:end_idx+1]
        
        # Calculate area using trapezoid rule - this integrates the ENTIRE area under the curve to y=0
        area = trapezoid(y_segment, x_segment)
        
        # Debug: verify what we're integrating
        print(f"[INTEGRATION] Peak at RT={peak_time:.3f}: integrating {len(x_segment)} points from y={min(y_segment):.1f} to y={max(y_segment):.1f}")
        print(f"[INTEGRATION] Calculated area: {area:.2f}")
        
        # Calculate width at half height
        half_height = peak_height / 2
        width_hh = self._calculate_width_at_height(x, y, peak_idx, start_idx, end_idx, half_height)
        
        # Count total peaks for proper numbering
        total_peak_count = 0
        if filename in self.detected_peaks:
            total_peak_count = len(self.detected_peaks[filename])
        
        peak_no = total_peak_count + 1
        
        peak_info = {
            'No.': peak_no,
            'Peak Name': f'Peak {peak_no}',
            'Retention Time': peak_time,
            'Area': area,
            'Height': peak_height,
            'Relative Area': 100.0,  # Will be updated later
            'Relative Height': 0.0,
            'Amount': 'n.a.',
            'Width (50%)': width_hh,
            'Start Time': x[start_idx],
            'End Time': x[end_idx],
            'Width (min)': x[end_idx] - x[start_idx],
            'Type': 'BB',
            'Resolution (EP)': 'n.a.',
            'Asymmetry (EP)': self._calculate_asymmetry(x, y, peak_idx, start_idx, end_idx),
            'Plates (EP)': self._calculate_theoretical_plates(peak_time, width_hh),
            'source': 'detected',
            'peak_idx': int(peak_idx),
            'start_idx': int(start_idx),
            'end_idx': int(end_idx),
            'filename': filename
        }
        
        return peak_info

    def update_settings(self, **kwargs):
        """Update detection settings"""
        for key, value in kwargs.items():
            if key in self.settings:
                self.settings[key] = value
                print(f"[PEAK] Updated {key} = {value}")
        
        # Add new settings if not present
        if 'integration_method' not in self.settings:
            self.settings['integration_method'] = 'perpendicular'
        if 'baseline_method' not in self.settings:
            self.settings['baseline_method'] = 'perpendicular'

    def __init__(self):
        self.detected_peaks = {}  # Store user-detected peaks by filename
        self.settings = {
            'slope_threshold': 0.02,
            'extension_factor': 1.2,
            'search_radius': 0.5,
            'height_threshold_percent': 5.0,
            'baseline_correction': True
        }
    
    def detect_peak_at_time(self, chromatogram_data: pd.DataFrame, retention_time: float, 
                          filename: str, height_threshold: float = None) -> Optional[Dict]:
        """
        Detect a peak near the specified retention time
        
        Args:
            chromatogram_data: DataFrame with 'Time (min)' and intensity columns
            retention_time: Target retention time in minutes
            filename: Source filename for tracking
            height_threshold: Minimum peak height (auto if None)
            
        Returns:
            Peak dictionary or None if no peak found
        """
        try:
            # Check if peak already exists near this time
            if filename in self.detected_peaks:
                for existing_peak in self.detected_peaks[filename]:
                    if abs(existing_peak['Retention Time'] - retention_time) < 0.05:  # Within 0.05 min
                        print(f"[PEAK] Peak already exists at {retention_time:.3f} min")
                        return existing_peak

            # Extract time and intensity data
            time_col = 'Time (min)'
            intensity_cols = [col for col in chromatogram_data.columns if col != time_col]
            if not intensity_cols:
                print(f"[PEAK] No intensity columns found")
                return None
                
            intensity_col = intensity_cols[0]  # Use first intensity column
            
            x = chromatogram_data[time_col].values
            y = chromatogram_data[intensity_col].values
            
            if len(x) == 0 or len(y) == 0:
                return None
            
            # Find closest index to target time
            target_idx = np.abs(x - retention_time).argmin()
            
            # Define search window
            search_radius = self.settings['search_radius']
            if len(x) > 1:
                dx = x[1] - x[0]
                window_size = max(1, int(search_radius / dx))
            else:
                window_size = 1
            
            left_idx = max(0, target_idx - window_size)
            right_idx = min(len(y) - 1, target_idx + window_size)
            
            # Find highest point in search window
            search_window = y[left_idx:right_idx+1]
            if len(search_window) == 0:
                return None
                
            local_max_idx = np.argmax(search_window)
            peak_idx = left_idx + local_max_idx
            
            peak_height = y[peak_idx]
            peak_time = x[peak_idx]
            
            # Apply height threshold
            if height_threshold is None:
                height_threshold = np.max(y) * (self.settings['height_threshold_percent'] / 100.0)
            
            if peak_height < height_threshold:
                print(f"[PEAK] Peak at {peak_time:.3f} min too small: {peak_height:.1f} < {height_threshold:.1f}")
                return None
            
            # Find peak boundaries
            start_idx, end_idx = self._find_peak_boundaries(x, y, peak_idx)
            
            # Calculate peak properties
            peak_info = self._calculate_peak_properties(x, y, peak_idx, start_idx, end_idx, filename)
            
            # Store the detected peak
            if filename not in self.detected_peaks:
                self.detected_peaks[filename] = []
            
            self.detected_peaks[filename].append(peak_info)
            print(f"[PEAK STORE] Stored peak under key: '{filename}' - Total keys: {list(self.detected_peaks.keys())}")
            print(f"[PEAK] ✅ Detected peak at {peak_time:.3f} min, height: {peak_height:.1f}, area: {peak_info['Area']:.2f}")

            return peak_info
            
        except Exception as e:
            print(f"[PEAK] Error detecting peak: {e}")
            return None
    
    def _find_peak_boundaries(self, x: np.ndarray, y: np.ndarray, peak_idx: int) -> Tuple[int, int]:
        """Find peak boundaries - use advanced method if enabled"""
        
        if self.settings.get('use_advanced_boundaries', False):
            return self._find_peak_boundaries_advanced(x, y, peak_idx)
        
        # Your existing derivative approach code...

        # Calculate first derivative
        dy = np.gradient(y)
        
        # Find inflection points (where derivative changes sign)
        # Left boundary: where slope changes from positive to negative before peak
        start_idx = 0
        for i in range(peak_idx, 0, -1):
            if i < len(dy) - 1:
                # Look for where derivative crosses zero (inflection point)
                if dy[i] < 0 and dy[i-1] >= 0:
                    start_idx = i
                    break
                # Or where signal reaches near baseline
                if y[i] < y[peak_idx] * 0.01:
                    start_idx = i
                    break
        
        # Right boundary: where slope changes from negative to positive after peak
        end_idx = len(y) - 1
        for i in range(peak_idx, len(y) - 1):
            if i < len(dy) - 1:
                # Look for where derivative crosses zero
                if dy[i] < 0 and dy[i+1] >= 0:
                    end_idx = i
                    break
                # Or where signal reaches near baseline
                if y[i] < y[peak_idx] * 0.01:
                    end_idx = i
                    break
        
        # Ensure we have reasonable boundaries
        if end_idx - start_idx < 3:
            start_idx = max(0, peak_idx - 20)
            end_idx = min(len(y) - 1, peak_idx + 20)
        
        return start_idx, end_idx

    def _calculate_width_at_height(self, x: np.ndarray, y: np.ndarray, peak_idx: int,
                                 start_idx: int, end_idx: int, target_height: float) -> float:
        """Calculate peak width at specified height using interpolation"""
        try:
            # Find left crossing point
            left_x = x[start_idx]
            for i in range(peak_idx, start_idx, -1):
                if i > 0 and y[i-1] <= target_height <= y[i]:
                    # Interpolate
                    x1, x2 = x[i-1], x[i]
                    y1, y2 = y[i-1], y[i]
                    if y2 != y1:
                        left_x = x1 + (target_height - y1) * (x2 - x1) / (y2 - y1)
                    break
            
            # Find right crossing point
            right_x = x[end_idx]
            for i in range(peak_idx, end_idx):
                if i < len(y) - 1 and y[i] >= target_height >= y[i+1]:
                    # Interpolate
                    x1, x2 = x[i], x[i+1]
                    y1, y2 = y[i], y[i+1]
                    if y2 != y1:
                        right_x = x1 + (target_height - y1) * (x2 - x1) / (y2 - y1)
                    break
            
            return abs(right_x - left_x)
            
        except Exception:
            return 0.1  # Fallback width
    
    def _calculate_asymmetry(self, x: np.ndarray, y: np.ndarray, peak_idx: int,
                           start_idx: int, end_idx: int) -> float:
        """Calculate peak asymmetry factor"""
        try:
            peak_height = y[peak_idx]
            ten_percent_height = peak_height * 0.1
            
            # Find width at 10% height
            width_10 = self._calculate_width_at_height(x, y, peak_idx, start_idx, end_idx, ten_percent_height)
            width_50 = self._calculate_width_at_height(x, y, peak_idx, start_idx, end_idx, peak_height * 0.5)
            
            if width_50 > 0:
                return width_10 / width_50
            return 1.0
            
        except Exception:
            return 1.0
    
    def _calculate_theoretical_plates(self, retention_time: float, width_hh: float) -> int:
        """Calculate number of theoretical plates"""
        try:
            if width_hh > 0 and retention_time > 0:
                plates = 5.54 * (retention_time / width_hh) ** 2
                return int(plates)
            return 0
        except Exception:
            return 0

    def auto_detect_peaks(self, chromatogram_data: pd.DataFrame, filename: str,
                        height_threshold: float = None, min_distance: int = 10) -> List[Dict]:
        """
        Automatically detect all significant peaks in chromatogram
        """
        try:
            time_col = 'Time (min)'
            intensity_cols = [col for col in chromatogram_data.columns if col != time_col]
            if not intensity_cols:
                return []
                
            intensity_col = intensity_cols[0]
            x = chromatogram_data[time_col].values
            y = chromatogram_data[intensity_col].values
            
            if height_threshold is None:
                height_threshold = np.max(y) * (self.settings['height_threshold_percent'] / 100.0)
            
            # Get imported peaks to avoid duplicates
            imported_peaks = []
            try:
                # Access the data manager to get integration table
                import __main__
                if hasattr(__main__, 'data_manager'):
                    file_data = __main__.data_manager.get_file_data(filename)
                    if file_data and 'integration_table' in file_data:
                        integration_table = file_data['integration_table']
                        if integration_table is not None and not integration_table.empty:
                            for _, row in integration_table.iterrows():
                                rt = float(str(row.get('Retention Time', 0)).replace(',', '.'))
                                if rt > 0:
                                    imported_peaks.append(rt)
            except:
                pass
            
            # Clear existing peaks for this file first
            self.detected_peaks[filename] = []
            
            # Use scipy to find peaks
            peak_indices, properties = find_peaks(
                y, 
                height=height_threshold,
                distance=min_distance,
                prominence=height_threshold * 0.1
            )
            
            print(f"[PEAK] Found {len(peak_indices)} peak candidates")
            
            # Process each peak
            detected_count = 0
            for i, peak_idx in enumerate(peak_indices):
                retention_time = x[peak_idx]
                
                # Skip if too close to an imported peak
                skip_peak = False
                for imported_rt in imported_peaks:
                    if abs(retention_time - imported_rt) < 0.1:  # Within 0.1 min
                        print(f"[PEAK] Skipping peak at {retention_time:.3f} - already imported")
                        skip_peak = True
                        break
                
                if skip_peak:
                    continue
                
                # Find boundaries and calculate properties
                start_idx, end_idx = self._find_peak_boundaries(x, y, peak_idx)
                
                peak_height = y[peak_idx]
                peak_time = x[peak_idx]
                
                # Calculate area to y=0
                y_segment = y[start_idx:end_idx+1]
                x_segment = x[start_idx:end_idx+1]
                area = trapezoid(y_segment, x_segment)
                
                # Calculate other properties
                half_height = peak_height / 2
                width_hh = self._calculate_width_at_height(x, y, peak_idx, start_idx, end_idx, half_height)
                
                # Peak number is based on detected count
                detected_count += 1
                peak_no = detected_count
                
                peak_info = {
                    'No.': peak_no,
                    'Peak Name': f'Peak {peak_no}',
                    'Retention Time': peak_time,
                    'Area': area,
                    'Height': peak_height,
                    'Relative Area': 100.0,
                    'Relative Height': 0.0,
                    'Amount': 'n.a.',
                    'Width (50%)': width_hh,
                    'Start Time': x[start_idx],
                    'End Time': x[end_idx],
                    'Width (min)': x[end_idx] - x[start_idx],
                    'Type': 'BB',
                    'Resolution (EP)': 'n.a.',
                    'Asymmetry (EP)': self._calculate_asymmetry(x, y, peak_idx, start_idx, end_idx),
                    'Plates (EP)': self._calculate_theoretical_plates(peak_time, width_hh),
                    'source': 'detected',
                    'peak_idx': peak_idx,
                    'start_idx': start_idx,
                    'end_idx': end_idx,
                    'filename': filename
                }
                
                self.detected_peaks[filename].append(peak_info)
            
            # Update relative areas
            self._update_relative_areas(filename)
            
            print(f"[PEAK] Successfully detected {len(self.detected_peaks[filename])} new peaks")
            return self.detected_peaks[filename]
            
        except Exception as e:
            print(f"[PEAK] Error in auto-detection: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _update_relative_areas(self, filename: str):
        """Update relative area percentages for all peaks in a file"""
        if filename not in self.detected_peaks or not self.detected_peaks[filename]:
            return
        
        # Calculate total area
        total_area = sum(peak['Area'] for peak in self.detected_peaks[filename])
        
        if total_area > 0:
            for peak in self.detected_peaks[filename]:
                peak['Relative Area'] = (peak['Area'] / total_area) * 100.0
    
    def get_combined_integration_table(self, filename: str, imported_table: pd.DataFrame = None) -> pd.DataFrame:
        """
        Combine imported peaks with detected peaks into unified table
        """
        try:
            combined_peaks = []
            
            # Add imported peaks first
            if imported_table is not None and not imported_table.empty:
                for idx, row in imported_table.iterrows():
                    peak_dict = row.to_dict()
                    peak_dict['source'] = 'imported'
                    # Ensure No. is an integer
                    if 'No.' in peak_dict:
                        try:
                            peak_dict['No.'] = int(float(str(peak_dict['No.']).replace(',', '.')))
                        except:
                            peak_dict['No.'] = idx + 1
                    combined_peaks.append(peak_dict)
            
            # Add detected peaks
            if filename in self.detected_peaks:
                for peak in self.detected_peaks[filename]:
                    peak_copy = {}
                    for key, value in peak.items():
                        # Skip any non-serializable fields
                        if key in ['baseline']:
                            continue
                        # Ensure indices are integers
                        if key in ['peak_idx', 'start_idx', 'end_idx', 'No.']:
                            peak_copy[key] = int(value) if value is not None else 0
                        else:
                            peak_copy[key] = value
                    peak_copy['source'] = 'detected'
                    combined_peaks.append(peak_copy)
            
            if not combined_peaks:
                return pd.DataFrame()
            
            # Create combined DataFrame
            df = pd.DataFrame(combined_peaks)
            
            # Sort by retention time and renumber
            if 'Retention Time' in df.columns:
                df = df.sort_values('Retention Time').reset_index(drop=True)
                # Renumber all peaks sequentially
                df['No.'] = range(1, len(df) + 1)
            
            return df
            
        except Exception as e:
            print(f"[PEAK] Error combining tables: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    def clear_detected_peaks(self, filename: str = None):
        """Clear detected peaks for file or all files"""
        if filename:
            if filename in self.detected_peaks:
                del self.detected_peaks[filename]
                print(f"[PEAK] Cleared detected peaks for {filename}")
        else:
            self.detected_peaks.clear()
            print(f"[PEAK] Cleared all detected peaks")
    
    def get_peak_markers_for_plot(self, filename: str) -> List[Dict]:
        """
        Get peak markers for plotting
        
        Returns:
            List of peak marker dictionaries for Plotly
        """
        markers = []
        
        if filename in self.detected_peaks:
            for peak in self.detected_peaks[filename]:
                markers.append({
                    'x': peak['Retention Time'],
                    'y': peak['Height'],
                    'name': peak['Peak Name'],
                    'area': peak['Area'],
                    'width': peak.get('Width (50%)', 0),
                    'start_time': peak.get('Start Time', 0),
                    'end_time': peak.get('End Time', 0),
                    'source': 'detected'
                })
        
        return markers
    
    def update_settings(self, **kwargs):
        """Update detection settings"""
        for key, value in kwargs.items():
            if key in self.settings:
                self.settings[key] = value
                print(f"[PEAK] Updated {key} = {value}")


# Global instance
peak_manager = PeakIntegrationManager()