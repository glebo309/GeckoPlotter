# =============================================================================
# File: debug_chromatogram_reader.py
import os
import re
import pandas as pd
from io import StringIO
from .base_reader import BaseReader

class ChromatogramReader(BaseReader):
    """Reader for chromatogram data files with enhanced debugging."""

    def __init__(self):
        super().__init__()
        self.wavelength = None

    @staticmethod
    def convert_german_number(text):
        """Convert German decimal format (comma as decimal separator) to English format."""
        print(f"[DEBUG] Input text length: {len(text)} characters")
        
        # Show a sample of problematic lines before conversion
        lines = text.strip().split('\n')
        problematic_lines = [line for line in lines if '.' in line and ',' in line and line.count('.') > 0]
        if problematic_lines:
            print(f"[DEBUG] Found {len(problematic_lines)} lines with thousand separators")
            for i, line in enumerate(problematic_lines[:3]):  # Show first 3 examples
                print(f"[DEBUG] Example {i+1}: {line}")
        
        # Handle numbers like 1.234,56 -> 1234.56
        original_text = text
        text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
        
        # Handle simple numbers like 123,45 -> 123.45
        text = re.sub(r'(\d+),(\d+)', r'\1.\2', text)
        
        # Show if any changes were made
        if text != original_text:
            print(f"[DEBUG] German number conversion applied successfully")
            # Show sample of converted lines
            converted_lines = text.strip().split('\n')
            for i, (orig, conv) in enumerate(zip(lines, converted_lines)):
                if orig != conv and i < 3:  # Show first 3 differences
                    print(f"[DEBUG] Conversion {i+1}: '{orig}' -> '{conv}'")
        else:
            print(f"[DEBUG] No German number conversion needed")
            
        return text

    def _process_file(self):
        """Process the chromatogram file content with enhanced debugging."""
        try:
            print(f"[DEBUG] Reading file: {self.file_path}")
            with open(self.file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0].replace("_UV_VIS_1", "")
            self.metadata = {}
            print(f"[DEBUG] File name: {self.file_name}")

            # Extract wavelength
            wavelength_match = re.search(r"WVL:\s*(\d{3})\s*nm", content)
            if wavelength_match:
                self.wavelength = wavelength_match.group(1)
                self.metadata['Wavelength (nm)'] = self.wavelength
                print(f"[DEBUG] 📊 Extracted wavelength: {self.wavelength} nm from {self.file_name}")

            # Split metadata from raw data
            if "Raw Data:" not in content:
                raise ValueError(f"'Raw Data:' section not found in the file: {self.file_path}")

            meta, raw_data = content.split("Raw Data:")
            print(f"[DEBUG] Raw data section length: {len(raw_data)} characters")
            
            # Show first few lines of raw data before conversion
            raw_lines = raw_data.strip().split('\n')[:5]
            print(f"[DEBUG] First 5 lines of raw data:")
            for i, line in enumerate(raw_lines):
                print(f"[DEBUG] Line {i+1}: '{line}'")
            
            # Convert German decimal format
            print(f"[DEBUG] Converting German number format...")
            raw_data = self.convert_german_number(raw_data)
            
            # Show first few lines after conversion
            converted_lines = raw_data.strip().split('\n')[:5]
            print(f"[DEBUG] First 5 lines after conversion:")
            for i, line in enumerate(converted_lines):
                print(f"[DEBUG] Converted line {i+1}: '{line}'")

            # Try to parse into DataFrame
            print(f"[DEBUG] Parsing into DataFrame...")
            try:
                df = pd.read_csv(StringIO(raw_data), sep="\t")
                print(f"[DEBUG] DataFrame created successfully with shape: {df.shape}")
                print(f"[DEBUG] Columns: {list(df.columns)}")
            except Exception as parse_error:
                print(f"[ERROR] Failed to parse DataFrame: {parse_error}")
                # Try to save the problematic data to debug
                with open(f"debug_raw_data_{self.file_name}.txt", "w") as debug_file:
                    debug_file.write(raw_data)
                print(f"[DEBUG] Saved raw data to debug_raw_data_{self.file_name}.txt for inspection")
                return False
            
            # Check for expected columns
            if 'Time (min)' not in df.columns or 'Value (mAU)' not in df.columns:
                print(f"[ERROR] Expected columns not found. Available columns: {list(df.columns)}")
                print(f"[DEBUG] First few rows of DataFrame:")
                print(df.head())
                return False

            # Show data types before conversion
            print(f"[DEBUG] Data types before numeric conversion:")
            print(df.dtypes)

            # Clean data
            df["Time (min)"] = pd.to_numeric(df["Time (min)"], errors="coerce")
            df["Value (mAU)"] = pd.to_numeric(df["Value (mAU)"], errors="coerce")
            
            # Check for NaN values
            nan_count = df.isnull().sum().sum()
            if nan_count > 0:
                print(f"[WARNING] Found {nan_count} NaN values after numeric conversion")
                # Show some examples of rows that became NaN
                nan_rows = df[df.isnull().any(axis=1)]
                if not nan_rows.empty:
                    print(f"[DEBUG] Examples of rows with NaN values:")
                    print(nan_rows.head())
            
            df = df.dropna()
            print(f"[DEBUG] After dropping NaN: {df.shape}")

            self.data = df[["Time (min)", "Value (mAU)"]]

            print(f"[DEBUG] ✅ Loaded {len(self.data)} points from {self.file_name}, range: {self.data['Value (mAU)'].min():.1f} to {self.data['Value (mAU)'].max():.1f} mAU")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to load chromatogram: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_metadata(self):
        """Return metadata dictionary."""
        return self.metadata

    def get_wavelength(self):
        """Return the wavelength from the chromatogram data."""
        return self.wavelength