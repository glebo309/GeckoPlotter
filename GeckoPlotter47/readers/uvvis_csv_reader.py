import pandas as pd
import os
from .base_reader import BaseReader

class UVVISCSVReader(BaseReader):
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.intensity_columns = []
        self.overflow_info = {}
        self.wavelength_range = (None, None)
        
    def load_file(self, path, extra_files=None):
        """Load Synergy H1 UV-Vis CSV file"""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")
            
            print(f"[DEBUG] 📊 UVVISCSVReader loading: {self.file_name}")
            
            # Read the raw file to analyze structure
            with open(path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()]
            
            # Find the header row with "Wavelength"
            header_idx = -1
            for i, line in enumerate(lines):
                if "Wavelength" in line:
                    header_idx = i
                    print(f"[DEBUG] 🔍 Found 'Wavelength' header at row {header_idx}")
                    break
            
            if header_idx == -1:
                raise ValueError("No 'Wavelength' header found in CSV file")
            
            # Parse metadata section (everything before header)
            self._parse_metadata(lines[:header_idx])
            print(f"[DEBUG] 📋 Parsed {len(self.metadata)} metadata fields")
            
            # Load data section using pandas
            self.data = pd.read_csv(path, skiprows=header_idx)
            print(f"[DEBUG] 📈 Loaded data shape: {self.data.shape}")
            print(f"[DEBUG] 🏷️ Data columns: {list(self.data.columns)}")
            
            # Clean up the data
            self._process_data()
            
            # Extract intensity columns (well columns)
            self._extract_intensity_columns()
            
            # Calculate wavelength range
            if 'Wavelength' in self.data.columns:
                wl_col = self.data['Wavelength'].dropna()
                self.wavelength_range = (wl_col.min(), wl_col.max())
                print(f"[DEBUG] 🌊 Wavelength range: {self.wavelength_range[0]:.0f}-{self.wavelength_range[1]:.0f} nm")
            
            print(f"[DEBUG] ✅ Successfully loaded UV-Vis CSV with {len(self.intensity_columns)} wells")
            return True
            
        except Exception as e:
            print(f"[DEBUG] ❌ UVVISCSVReader error: {e}")
            return False
    

    def _parse_metadata(self, metadata_lines):
        """Parse the metadata section from Synergy H1 format"""
        self.metadata = {}
        
        for line in metadata_lines:
            if not line or line.count(',') < 1:
                continue
                
            # Split on first comma only
            parts = line.split(',', 1)
            if len(parts) >= 2:
                key = parts[0].strip().rstrip(':')
                value = parts[1].strip()
                
                # Clean up value - remove trailing commas and extra whitespace
                # Synergy files have lots of trailing commas for empty columns
                value = value.rstrip(',').strip()
                
                # Skip empty keys or values
                if key and value and key != '' and value != '' and value != ',':
                    # Special handling for common keys
                    if key == "Reader Type:":
                        key = "Reader Type"  # Remove colon for consistency
                    elif key == "Reader Serial Number:":
                        key = "Reader Serial Number"
                    elif key == "Software Version":
                        # Keep as is
                        pass
                    
                    self.metadata[key] = value
                    print(f"[DEBUG] Metadata: '{key}' = '{value}'")  # Debug output
        
        # Add some computed metadata
        if 'Date' in self.metadata and 'Time' in self.metadata:
            date_clean = self.metadata['Date'].split(',')[0].strip()  # Take first part before commas
            time_clean = self.metadata['Time'].split(',')[0].strip()  # Take first part before commas
            self.metadata['DateTime'] = f"{date_clean} {time_clean}"
            self.metadata['Date'] = date_clean  # Clean up the date field
            self.metadata['Time'] = time_clean  # Clean up the time field
        
        # Mark as absorbance spectrum
        self.metadata['Data Type'] = 'Absorbance Spectrum'
        
        print(f"[DEBUG] 📋 Final metadata extracted: {list(self.metadata.keys())}")




    def _process_data(self):
        """Clean and process the data DataFrame"""
        # Remove completely empty columns
        self.data = self.data.dropna(axis=1, how='all')
        
        # Remove unnamed/empty columns
        cols_to_keep = []
        for col in self.data.columns:
            if not col.startswith('Unnamed:') and col.strip() != '':
                cols_to_keep.append(col)
        
        self.data = self.data[cols_to_keep]
        
        # Convert wavelength to numeric
        if 'Wavelength' in self.data.columns:
            self.data['Wavelength'] = pd.to_numeric(self.data['Wavelength'], errors='coerce')
        
        # Convert intensity columns to numeric
        for col in self.data.columns:
            if col != 'Wavelength':
                self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
        
        # Remove rows where wavelength is NaN
        if 'Wavelength' in self.data.columns:
            self.data = self.data.dropna(subset=['Wavelength'])
        
        print(f"[DEBUG] 🧹 Cleaned data shape: {self.data.shape}")
    
    def _extract_intensity_columns(self):
        """Extract well column names (intensity columns)"""
        self.intensity_columns = []
        
        for col in self.data.columns:
            if col != 'Wavelength' and col.strip() != '':
                self.intensity_columns.append(col)
        
        print(f"[DEBUG] 🧪 Found {len(self.intensity_columns)} wells: {self.intensity_columns[:10]}{'...' if len(self.intensity_columns) > 10 else ''}")
        
        # Check for overflow (values > 4.0 typically indicate saturation)
        self.overflow_info = {}
        for col in self.intensity_columns:
            if col in self.data.columns:
                max_val = self.data[col].max()
                if pd.notna(max_val) and max_val > 4.0:
                    self.overflow_info[col] = f"Max: {max_val:.3f} (possible overflow)"
        
        if self.overflow_info:
            print(f"[DEBUG] ⚠️ Possible overflow detected in {len(self.overflow_info)} wells")
    
    # Required BaseReader methods
    def get_data(self):
        """Return the main DataFrame"""
        return self.data
    
    def get_file_name(self):
        """Return display filename"""
        return getattr(self, 'file_name', 'Unknown UV-Vis CSV')
    
    def get_metadata(self):
        """Return metadata dictionary"""
        return self.metadata
    
    # UV-Vis specific methods
    def get_intensity_columns(self):
        """Return list of well/intensity column names"""
        return self.intensity_columns
    
    def get_overflow_info(self):
        """Return overflow information"""
        return self.overflow_info
    
    def get_wavelength_range(self):
        """Return (min_wavelength, max_wavelength) tuple"""
        return self.wavelength_range
    
    def get_well_data(self, well_name):
        """Get absorbance spectrum for a specific well"""
        if well_name in self.intensity_columns and 'Wavelength' in self.data.columns:
            return self.data[['Wavelength', well_name]].dropna()
        return None
    
    def get_filled_wells(self):

        """Return list of wells that contain data (non-zero values)"""
        filled_wells = []
        for col in self.intensity_columns:
            if col in self.data.columns:
                # Check if well has any non-zero, non-NaN values
                values = self.data[col].dropna()
                if len(values) > 0 and (values > 0.001).any():  # Threshold for "filled"
                    filled_wells.append(col)
        return filled_wells
    


    # Add these methods to your UVVISCSVReader class in readers/uvvis_csv_reader.py

    def get_column_data(self, column_name):
        """Get wavelength and absorbance data for a specific well/column"""
        if self.data is None or 'Wavelength' not in self.data.columns:
            return None
        
        if column_name not in self.data.columns:
            print(f"[DEBUG] Column '{column_name}' not found in data")
            return None
        
        # Return DataFrame with wavelength and the specific column
        result = self.data[['Wavelength', column_name]].copy()
        result = result.dropna()  # Remove NaN values
        
        # Rename columns for consistency with viz callback expectations
        result = result.rename(columns={
            'Wavelength': 'Wavelength (nm)',
            column_name: column_name
        })
        
        print(f"[DEBUG] Returning column data for '{column_name}': {len(result)} points")
        return result

    def get_available_columns(self):
        """Get list of available intensity columns for dropdown selection"""
        return self.intensity_columns

    def get_column_preview_data(self, max_columns=10):
        """Get preview data for first few columns - useful for dropdown options"""
        if not self.intensity_columns:
            return []
        
        preview_columns = self.intensity_columns[:max_columns]
        preview_data = []
        
        for col in preview_columns:
            if col in self.data.columns:
                # Get some stats for this column
                values = self.data[col].dropna()
                if len(values) > 0:
                    max_val = values.max()
                    mean_val = values.mean()
                    preview_data.append({
                        'column': col,
                        'max_absorbance': max_val,
                        'mean_absorbance': mean_val,
                        'has_data': max_val > 0.001  # Consider filled if max > threshold
                    })
        
        return preview_data