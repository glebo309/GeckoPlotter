# File: readers/lcms_vwd_cdf_reader.py
import netCDF4 as nc
import numpy as np
import pandas as pd
import os
from .base_reader import BaseReader

class LCMSVWDCDFReader(BaseReader):
    """Handle Agilent VWD (Variable Wavelength Detector) CDF files"""
    
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.chromatogram_data = None
        self.wavelength = None
        self.detector_info = {}
        self.data_points = 0
        
    def load_file(self, path, extra_files=None):
        """Load VWD CDF file with metadata extraction"""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")
            
            print(f"\n{'='*80}")
            print(f"📊 VWD CDF ANALYSIS: {self.file_name}")
            print(f"{'='*80}")
            
            # Open CDF file and extract data
            with nc.Dataset(path, 'r') as data:
                # Show file structure
                self._show_file_structure(data)
                
                # Extract metadata
                self._extract_metadata(data)
                
                # Extract chromatogram data
                self._extract_chromatogram_data(data)
            
            print(f"\n✅ VWD Analysis complete: {self.data_points} points, {self.wavelength}nm")
            print(f"{'='*80}\n")
            
            return True
            
        except Exception as e:
            print(f"❌ VWD CDF analysis error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _show_file_structure(self, data):
        """Show basic file structure"""
        print(f"📊 VWD File Structure:")
        print(f"   Dimensions: {len(data.dimensions)}")
        print(f"   Variables: {len(data.variables)}")
        
        # Check for expected VWD variables
        key_vars = ['ordinate_values', 'raw_data_retention', 'actual_sampling_interval']
        found_vars = [v for v in key_vars if v in data.variables]
        missing_vars = [v for v in key_vars if v not in data.variables]
        
        if found_vars:
            print(f"   ✅ Found key variables: {found_vars}")
        if missing_vars:
            print(f"   ❌ Missing variables: {missing_vars}")
    
    def _extract_metadata(self, data):
        """Extract comprehensive metadata from VWD CDF file"""
        print(f"\n📋 Extracting Comprehensive VWD Metadata:")
        
        # Extract ALL global attributes
        global_attrs = {}
        for attr in data.ncattrs():
            value = getattr(data, attr)
            if isinstance(value, bytes):
                value = value.decode('utf-8').strip()
            self.metadata[attr] = value
            global_attrs[attr] = value
        
        print(f"   ✅ Found {len(global_attrs)} global attributes")
        
        # Extract specific important fields
        important_fields = {
            'detector_name': 'Detector',
            'sample_name': 'Sample',
            'sample_id': 'Sample ID',
            'injection_date_time_stamp': 'Injection Time',
            'sample_injection_volume': 'Injection Volume',
            'sample_type': 'Sample Type',
            'sample_amount': 'Sample Amount',
            'operator_name': 'Operator',
            'company_method_name': 'Method',
            'experiment_title': 'Experiment',
            'dataset_date_time_stamp': 'Dataset Time',
            'detection_method_name': 'Detection Method',
            'retention_unit': 'Retention Unit',
            'detector_unit': 'Detector Unit',
            'separation_experiment_type': 'Separation Type',
            'source_file_reference': 'Source File',
            'peak_processing_method_name': 'Peak Method',
            'peak_processing_date_time_stamp': 'Peak Processing Time'
        }
        
        for field, display_name in important_fields.items():
            if field in self.metadata and self.metadata[field]:
                value = self.metadata[field]
                print(f"   📝 {display_name}: {value}")
        
        # Extract wavelength and channel from detector name
        if 'detector_name' in self.metadata:
            detector_info = self.metadata['detector_name']
            print(f"   🔬 Detector: {detector_info}")
            
            # Extract wavelength
            if 'Wavelength=' in detector_info:
                wl_match = detector_info.split('Wavelength=')[1].split(' ')[0]
                self.wavelength = int(wl_match)
                print(f"   🌊 Wavelength: {self.wavelength} nm")
            
            # Extract channel (more robust detection)
            if 'VWD1A' in detector_info or detector_info.endswith('A'):
                self.detector_info['channel'] = 'A'
                print(f"   📊 Channel: A")
            elif 'VWD1B' in detector_info or detector_info.endswith('B'):
                self.detector_info['channel'] = 'B'
                print(f"   📊 Channel: B")
            else:
                # Fallback: try to extract from filename
                if hasattr(self, 'file_name'):
                    if 'VWD1A' in self.file_name or '_A.' in self.file_name:
                        self.detector_info['channel'] = 'A'
                    elif 'VWD1B' in self.file_name or '_B.' in self.file_name:
                        self.detector_info['channel'] = 'B'
                    else:
                        self.detector_info['channel'] = 'Unknown'
                else:
                    self.detector_info['channel'] = 'Unknown'
                print(f"   📊 Channel: {self.detector_info['channel']} (from filename)")
            
            # Store detector settings
            if ',' in detector_info:
                parts = detector_info.split(',')
                self.detector_info['detector_id'] = parts[0].strip()
                if len(parts) > 1:
                    self.detector_info['detector_settings'] = parts[1].strip()


        # Store detector unit
        if 'detector_unit' in self.metadata:
            self.detector_info['unit'] = self.metadata['detector_unit']
        
        # Extract peak information if available
        peak_vars = ['peak_retention_time', 'peak_area', 'peak_height', 'peak_width', 
                    'peak_start_time', 'peak_end_time', 'peak_area_percent', 'peak_height_percent']
        
        peak_data = {}
        for var_name in peak_vars:
            if var_name in data.variables:
                try:
                    var_data = data.variables[var_name][:]
                    if len(var_data) > 0:
                        peak_data[var_name] = var_data
                        print(f"   📊 Found {var_name}: {len(var_data)} peaks")
                except:
                    pass
        
        if peak_data:
            self.metadata['peak_count'] = len(next(iter(peak_data.values())))
            self.metadata['has_peak_data'] = True
        else:
            self.metadata['peak_count'] = 0
            self.metadata['has_peak_data'] = False
        
        # Extract chromatogram parameters
        if 'actual_run_time_length' in data.variables:
            try:
                run_time = float(data.variables['actual_run_time_length'][:])
                self.metadata['run_time_seconds'] = run_time
                self.metadata['run_time_minutes'] = run_time / 60.0
                print(f"   ⏱️ Run time: {run_time/60:.2f} minutes")
            except:
                pass
        
        if 'actual_sampling_interval' in data.variables:
            try:
                interval = float(data.variables['actual_sampling_interval'][:])
                self.metadata['sampling_interval'] = interval
                self.metadata['sampling_rate_hz'] = 1.0 / interval if interval > 0 else 0
                print(f"   📏 Sampling interval: {interval:.3f} seconds")
            except:
                pass
        
        if 'actual_delay_time' in data.variables:
            try:
                delay = float(data.variables['actual_delay_time'][:])
                self.metadata['delay_time'] = delay
                print(f"   ⏳ Delay time: {delay:.1f} seconds")
            except:
                pass
        
        # Extract detector limits
        if 'detector_minimum_value' in data.variables:
            try:
                self.detector_info['min_value'] = float(data.variables['detector_minimum_value'][:])
                print(f"   📉 Detector min: {self.detector_info['min_value']} mAU")
            except:
                pass
        
        if 'detector_maximum_value' in data.variables:
            try:
                self.detector_info['max_value'] = float(data.variables['detector_maximum_value'][:])
                print(f"   📈 Detector max: {self.detector_info['max_value']} mAU")
            except:
                pass
        
        print(f"   ✅ Extracted {len(self.metadata)} metadata fields total")


    def _extract_chromatogram_data(self, data):
        """Extract UV chromatogram data"""
        print(f"\n📈 Extracting UV Chromatogram Data:")
        
        try:
            # Get intensity values
            intensity = data.variables["ordinate_values"][:]
            
            # Get retention time
            if "raw_data_retention" in data.variables:
                rt_seconds = data.variables["raw_data_retention"][:]
                
                # Check if retention time is valid
                if np.all(rt_seconds == 0.0):
                    print(f"   ⚠️ Retention time array is all zeros, reconstructing...")
                    # Reconstruct from sampling interval
                    if "actual_sampling_interval" in data.variables:
                        interval = float(data.variables["actual_sampling_interval"][:])
                        rt_seconds = np.arange(len(intensity)) * interval
                        print(f"   ✅ Reconstructed RT using sampling interval: {interval:.3f}s")
                    else:
                        # Default to 0.4s interval (common for UV detectors)
                        interval = 0.4
                        rt_seconds = np.arange(len(intensity)) * interval
                        print(f"   ⚠️ Using default sampling interval: {interval}s")
            else:
                # No retention time variable, reconstruct
                if "actual_sampling_interval" in data.variables:
                    interval = float(data.variables["actual_sampling_interval"][:])
                else:
                    interval = 0.4  # default
                rt_seconds = np.arange(len(intensity)) * interval
                print(f"   ⚠️ No retention time data, using sampling interval: {interval}s")
            
            # Convert to minutes
            rt_minutes = rt_seconds / 60.0
            
            # Create chromatogram DataFrame
            self.chromatogram_data = pd.DataFrame({
                'Time (min)': rt_minutes,
                'Intensity (mAU)': intensity
            })
            
            self.data_points = len(self.chromatogram_data)
            
            # Get detector limits
            if "detector_minimum_value" in data.variables:
                self.detector_info['min_value'] = float(data.variables["detector_minimum_value"][:])
            if "detector_maximum_value" in data.variables:
                self.detector_info['max_value'] = float(data.variables["detector_maximum_value"][:])
            
            # Report success
            print(f"   ✅ UV chromatogram extracted: {self.data_points} points")
            print(f"   🕒 Time: {rt_minutes.min():.2f} - {rt_minutes.max():.2f} min")
            print(f"   📊 Intensity: {intensity.min():.1f} - {intensity.max():.1f} mAU")
            if self.wavelength:
                print(f"   🌊 Wavelength: {self.wavelength} nm")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Extraction error: {e}")
            return False
    
    # Required BaseReader methods
    def get_data(self):
        """Return the chromatogram data"""
        return self.chromatogram_data
    
    def get_file_name(self):
        """Return display filename"""
        return getattr(self, 'file_name', 'Unknown VWD CDF')
    
    def get_metadata(self):
        """Return processed metadata"""
        processed_metadata = self.metadata.copy()
        processed_metadata.update({
            'wavelength': self.wavelength,
            'detector_channel': self.detector_info.get('channel', 'Unknown'),
            'detector_unit': self.detector_info.get('unit', 'mAU'),
            'data_points': self.data_points
        })
        
        # Add chromatogram info if data exists
        if self.chromatogram_data is not None and not self.chromatogram_data.empty:
            time_data = self.chromatogram_data['Time (min)']
            intensity_data = self.chromatogram_data['Intensity (mAU)']
            
            processed_metadata['retention_time_min'] = float(time_data.min())
            processed_metadata['retention_time_max'] = float(time_data.max())
            processed_metadata['retention_time_range'] = f"{time_data.min():.2f}-{time_data.max():.2f} min"
            processed_metadata['intensity_min'] = float(intensity_data.min())
            processed_metadata['intensity_max'] = float(intensity_data.max())
            processed_metadata['max_intensity'] = float(intensity_data.max())
        
        return processed_metadata
    
    # VWD specific methods
    def get_wavelength(self):
        """Return detection wavelength"""
        return self.wavelength
    
    def get_channel(self):
        """Return detector channel (A or B)"""
        return self.detector_info.get('channel', 'Unknown')
    
    def get_detector_info(self):
        """Return detector information"""
        return {
            'name': self.metadata.get('detector_name', 'VWD'),
            'channel': self.get_channel(),
            'wavelength': self.wavelength,
            'unit': self.detector_info.get('unit', 'mAU'),
            'is_uv': True
        }
    
    def is_uv_data(self):
        """Check if this file contains UV data"""
        return True
    
    def get_max_absorbance(self):
        """Get maximum absorbance value"""
        if self.chromatogram_data is not None and not self.chromatogram_data.empty:
            return float(self.chromatogram_data['Intensity (mAU)'].max())
        return 0
    
    def print_full_analysis(self):
        """Print comprehensive analysis summary"""
        print(f"\n📋 COMPREHENSIVE VWD CDF ANALYSIS SUMMARY")
        print(f"{'='*60}")
        
        # File information
        print(f"📁 File: {self.get_file_name()}")
        print(f"📂 Path: {getattr(self, 'file_path', 'Unknown')}")
        
        # Detector info
        print(f"🔬 Detector: {self.metadata.get('detector_name', 'Unknown')}")
        print(f"📊 Channel: {self.get_channel()}")
        print(f"🌊 Wavelength: {self.wavelength} nm")
        print(f"📏 Units: {self.detector_info.get('unit', 'mAU')}")
        
        # Chromatogram info
        if self.chromatogram_data is not None and not self.chromatogram_data.empty:
            rt_min, rt_max = self.chromatogram_data['Time (min)'].min(), self.chromatogram_data['Time (min)'].max()
            print(f"🕒 Retention Time: {rt_min:.2f} - {rt_max:.2f} min")
            print(f"📊 Data Points: {len(self.chromatogram_data)}")
            
            # Intensity info
            intensity = self.chromatogram_data['Intensity (mAU)']
            print(f"📈 Intensity Range: {intensity.min():.1f} - {intensity.max():.1f} mAU")
        else:
            print(f"📊 Chromatogram Data: Not available")
        
        # Sample information
        print(f"\n🧪 Sample Information:")
        print(f"   Sample Name: {self.metadata.get('sample_name', 'Unknown')}")
        print(f"   Injection Volume: {self.metadata.get('sample_injection_volume', 'Unknown')} µL")
        print(f"   Injection Time: {self.metadata.get('injection_date_time_stamp', 'Unknown')}")
        
        # Metadata summary
        print(f"\n📋 Metadata Summary:")
        print(f"   Total metadata fields: {len(self.metadata)}")
        
        print(f"{'='*60}")
        print(f"✅ VWD Analysis Summary Complete\n")