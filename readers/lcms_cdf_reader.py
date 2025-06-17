# File: readers/lcms_cdf_reader.py - CLEAN CONSOLIDATED VERSION
import netCDF4 as nc
import numpy as np
import pandas as pd
import os
from .base_reader import BaseReader

class LCMSCDFReader(BaseReader):
    """Handle Agilent CDF files with comprehensive metadata extraction"""
    
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.instrument_info = {}
        self.ionization_mode = None
        self.tic_data = None
        self.mass_range = (0, 0)
        self.scan_count = 0
        
    def load_file(self, path, extra_files=None):
        """Load CDF file with comprehensive metadata extraction"""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")
            
            print(f"\n{'='*80}")
            print(f"🔍 CDF ANALYSIS: {self.file_name}")
            print(f"{'='*80}")
            
            # Open CDF file and extract data
            with nc.Dataset(path, 'r') as data:
                # Show what we're working with
                self._show_file_structure(data)
                
                # Extract metadata
                self._extract_metadata(data)
                
                # Detect ionization mode
                self._detect_ionization_mode(data)
                
                # Extract TIC data using your working variable names
                self._extract_tic_data(data)
            
            print(f"\n✅ Analysis complete: {self.scan_count} scans, {self.ionization_mode} mode")
            print(f"{'='*80}\n")
            
            return True
            
        except Exception as e:
            print(f"❌ CDF analysis error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _show_file_structure(self, data):
        """Show basic file structure"""
        print(f"📊 File Structure:")
        print(f"   Dimensions: {len(data.dimensions)}")
        print(f"   Variables: {len(data.variables)}")
        
        # Show key variables we expect
        key_vars = ['scan_acquisition_time', 'total_intensity', 'mass_range_min', 'mass_range_max']
        found_vars = [v for v in key_vars if v in data.variables]
        missing_vars = [v for v in key_vars if v not in data.variables]
        
        if found_vars:
            print(f"   ✅ Found key variables: {found_vars}")
        if missing_vars:
            print(f"   ❌ Missing variables: {missing_vars}")
    
    def _extract_metadata(self, data):
        """Extract metadata from global attributes and instrument variables"""
        print(f"\n📋 Extracting Metadata:")
        
        # Extract global attributes (these work from your inspection)
        global_count = 0
        try:
            for attr in data.ncattrs():
                value = getattr(data, attr)
                if isinstance(value, bytes):
                    value = value.decode('utf-8').strip()
                self.metadata[f'global_{attr}'] = value
                global_count += 1
                
                # Check for specific important attributes
                if attr == 'test_ionization_polarity':
                    print(f"   ⚡ Ionization: {value}")
                elif attr in ['experiment_type', 'dataset_origin']:
                    print(f"   📝 {attr}: {value}")
        except Exception as e:
            print(f"   ⚠️ Global attributes error: {e}")
        
        # Extract instrument info from string variables
        instrument_vars = ['instrument_name', 'instrument_mfr', 'instrument_model', 'instrument_serial_no']
        instrument_count = 0
        
        for var_name in instrument_vars:
            try:
                if var_name in data.variables:
                    var_data = data.variables[var_name]
                    # Convert character array to string
                    if var_data.dtype.kind == 'S':
                        chars = var_data[:]
                        if len(chars.shape) == 2:
                            string_val = ''.join([chr(c) for c in chars[0] if c != 0]).strip()
                        else:
                            string_val = chars.tobytes().decode('utf-8').strip('\x00')
                        
                        if string_val:
                            self.instrument_info[var_name] = string_val
                            self.metadata[var_name] = string_val
                            instrument_count += 1
                            print(f"   🔬 {var_name}: {string_val}")
            except Exception as e:
                print(f"   ⚠️ {var_name} extraction error: {e}")
        
        print(f"   ✅ Extracted {global_count} global attributes, {instrument_count} instrument fields")
    

    def _detect_ionization_mode(self, data):
        """Robust ionization mode detection based on metadata and clean filename parsing"""
        print(f"\n⚡ Detecting Ionization Mode:")

        # Try metadata first
        mode_from_meta = None
        if hasattr(data, 'test_ionization_polarity'):
            polarity = getattr(data, 'test_ionization_polarity')
            if isinstance(polarity, bytes):
                polarity = polarity.decode('utf-8')
            if 'positive' in polarity.lower():
                mode_from_meta = 'positive'
            elif 'negative' in polarity.lower():
                mode_from_meta = 'negative'
            print(f"   📦 Metadata polarity: {mode_from_meta}")

        # Then try filename-based detection (strict)
        mode_from_name = None
        if " +tic" in self.file_name.lower():
            mode_from_name = "positive"
        elif " -tic" in self.file_name.lower():
            mode_from_name = "negative"
        print(f"   🧾 Filename polarity: {mode_from_name}")

        # Resolve
        if mode_from_meta and mode_from_name:
            if mode_from_meta != mode_from_name:
                print(f"   ⚠️ Conflict detected — trusting filename!")
            self.ionization_mode = mode_from_name
        elif mode_from_name:
            self.ionization_mode = mode_from_name
        elif mode_from_meta:
            self.ionization_mode = mode_from_meta
        else:
            self.ionization_mode = "unknown"

        print(f"   ✅ Ionization Mode: {self.ionization_mode.upper()}")



    def _extract_tic_data(self, data):
        """Extract TIC data using your working variable names"""
        print(f"\n📊 Extracting TIC Data:")
        
        try:
            # Use the exact variable names from your working inspection
            scan_times = data.variables["scan_acquisition_time"][:]
            total_intensity = data.variables["total_intensity"][:]
            mass_range_min = data.variables["mass_range_min"][:]
            mass_range_max = data.variables["mass_range_max"][:]
            
            # Convert scan times from seconds to minutes
            scan_times_min = scan_times / 60.0
            
            # Create TIC DataFrame
            self.tic_data = pd.DataFrame({
                'Time (min)': scan_times_min,
                'Intensity': total_intensity
            })
            
            self.scan_count = len(scan_times)
            
            # Get overall mass range
            self.mass_range = (float(mass_range_min.min()), float(mass_range_max.max()))
            
            # Report success
            print(f"   ✅ TIC extracted: {len(self.tic_data)} points")
            print(f"   🕒 Time: {scan_times_min.min():.2f} - {scan_times_min.max():.2f} min")
            print(f"   📈 Intensity: {total_intensity.min():.0f} - {total_intensity.max():.0f}")
            print(f"   ⚖️ Mass: {self.mass_range[0]:.1f} - {self.mass_range[1]:.1f} m/z")
            
            return True
            
        except KeyError as e:
            print(f"   ❌ Missing variable: {e}")
            print(f"   🔍 Available variables: {list(data.variables.keys())[:10]}...")
            return False
            
        except Exception as e:
            print(f"   ❌ Extraction error: {e}")
            return False
    
    # Required BaseReader methods
    def get_data(self):
        """Return the TIC data"""
        return self.tic_data
    
    def get_file_name(self):
        """Return display filename"""
        return getattr(self, 'file_name', 'Unknown CDF')
    

    def get_metadata(self):
        """Return processed metadata for LC-MS CDF files"""
        processed_metadata = self.metadata.copy()
        
        # Add LC-MS specific fields
        processed_metadata.update({
            'ionization_mode': self.ionization_mode,
            'scan_count': self.scan_count,
            'detector_name': self.metadata.get('detector_name', 'MS Detector'),
            'data_points': len(self.tic_data) if self.tic_data is not None else 0
        })
        
        # Add retention time info if TIC data exists
        if self.tic_data is not None and not self.tic_data.empty:
            time_data = self.tic_data['Time (min)']
            intensity_data = self.tic_data['Intensity']
            processed_metadata['retention_time_min'] = float(time_data.min())
            processed_metadata['retention_time_max'] = float(time_data.max())
            processed_metadata['retention_time_range'] = f"{time_data.min():.2f}-{time_data.max():.2f} min"
            processed_metadata['max_intensity'] = float(intensity_data.max())
        
        # Add mass range info
        if self.mass_range != (0, 0):
            processed_metadata['mass_range_min'] = self.mass_range[0]
            processed_metadata['mass_range_max'] = self.mass_range[1]
            processed_metadata['mass_range_str'] = f"{self.mass_range[0]:.0f}-{self.mass_range[1]:.0f} m/z"
        
        return processed_metadata


    # LC-MS specific methods
    def get_ionization_mode(self):
        """Return ionization mode"""
        return self.ionization_mode
    
    def get_scan_count(self):
        """Return number of scans"""
        return self.scan_count
    
    def get_mass_range(self):
        """Return (min_mz, max_mz) tuple"""
        return self.mass_range
    
    def get_retention_time_range(self):
        """Return (min_time, max_time) in minutes"""
        if self.tic_data is not None and not self.tic_data.empty:
            times = self.tic_data['Time (min)']
            return times.min(), times.max()
        return 0, 0
    
    def get_raw_metadata(self):
        """Return all raw metadata for debugging"""
        return self.metadata

    # Also add these missing methods that data_manager.py expects:

    def get_detector_info(self):
        """Return detector information"""
        return {
            'name': self.metadata.get('detector_name', 'MS Detector'),
            'is_ms': True
        }

    def get_instrument_info(self):
        """Return instrument information"""
        return self.instrument_info

    def is_ms_data(self):
        """Check if this file contains MS data"""
        return True

    def get_max_intensity(self):
        """Get maximum intensity in TIC"""
        if self.tic_data is not None and not self.tic_data.empty:
            return float(self.tic_data['Intensity'].max())
        return 0
    
    def print_full_analysis(self):
        """Print comprehensive analysis summary for debugging/logging"""
        print(f"\n📋 COMPREHENSIVE LC-MS CDF ANALYSIS SUMMARY")
        print(f"{'='*60}")
        
        # File information
        print(f"📁 File: {self.get_file_name()}")
        print(f"📂 Path: {getattr(self, 'file_path', 'Unknown')}")
        
        # Ionization and scan info
        print(f"⚡ Ionization Mode: {self.ionization_mode.upper()}")
        print(f"🔬 Total Scans: {self.scan_count}")
        
        # Mass range
        if self.mass_range != (0, 0):
            print(f"⚖️ Mass Range: {self.mass_range[0]:.1f} - {self.mass_range[1]:.1f} m/z")
        else:
            print(f"⚖️ Mass Range: Unknown")
        
        # Retention time info
        if self.tic_data is not None and not self.tic_data.empty:
            rt_min, rt_max = self.get_retention_time_range()
            print(f"🕒 Retention Time: {rt_min:.2f} - {rt_max:.2f} min")
            print(f"📊 TIC Data Points: {len(self.tic_data)}")
            
            # Intensity info
            max_intensity = self.get_max_intensity()
            min_intensity = float(self.tic_data['Intensity'].min())
            print(f"📈 Intensity Range: {min_intensity:.0f} - {max_intensity:.0f}")
        else:
            print(f"📊 TIC Data: Not available")
        
        # Instrument information
        if self.instrument_info:
            print(f"\n🔬 Instrument Information:")
            for key, value in self.instrument_info.items():
                clean_key = key.replace('instrument_', '').replace('_', ' ').title()
                print(f"   {clean_key}: {value}")
        else:
            print(f"🔬 Instrument Information: Not available")
        
        # Metadata summary
        print(f"\n📋 Metadata Summary:")
        print(f"   Total metadata fields: {len(self.metadata)}")
        print(f"   Global attributes: {len([k for k in self.metadata.keys() if k.startswith('global_')])}")
        print(f"   Instrument fields: {len(self.instrument_info)}")
        
        # Key metadata fields
        important_fields = ['global_dataset_origin', 'global_experiment_type', 'global_test_ionization_polarity']
        for field in important_fields:
            if field in self.metadata and self.metadata[field]:
                clean_field = field.replace('global_', '').replace('_', ' ').title()
                print(f"   {clean_field}: {self.metadata[field]}")
        
        print(f"{'='*60}")
        print(f"✅ Analysis Summary Complete\n")