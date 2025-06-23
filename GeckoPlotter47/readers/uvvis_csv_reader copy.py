# File: readers/uvvis_csv_reader.py
import os
import pandas as pd
import numpy as np
from .base_reader import BaseReader

class UVVISCSVReader(BaseReader):
    """Reader for UV-VIS spectrometer CSV data files."""

    def __init__(self):
        super().__init__()
        self.wavelength_column = None
        self.intensity_columns = []
        self.metadata = {}
        self.overflow_points = {}

    def _process_file(self):
        """Process the UV-VIS CSV file content."""
        try:
            # Read all lines from the file
            with open(self.file_path, 'r') as f:
                lines = [line.strip() for line in f.readlines()]

            # Extract filename for legend
            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0]

            # Find the header row (typically contains "Wavelength")
            header_row_idx = -1
            for i, line in enumerate(lines):
                if "Wavelength" in line:
                    header_row_idx = i
                    break

            if header_row_idx == -1:
                raise ValueError("Could not find 'Wavelength' column in the file. Is this a valid UV-VIS spectrometer data file?")

            # Extract metadata from lines before the header
            for i in range(header_row_idx):
                if lines[i] and ',' in lines[i]:
                    parts = lines[i].split(',', 1)
                    if parts[0].strip():
                        self.metadata[parts[0].strip()] = parts[1].strip()

            # Parse the header row
            headers = lines[header_row_idx].split(',')
            
            # Find the wavelength column (should be first)
            wavelength_idx = -1
            for i, header in enumerate(headers):
                if header.strip() == "Wavelength":
                    wavelength_idx = i
                    break

            if wavelength_idx == -1:
                raise ValueError("Could not find 'Wavelength' column in the header row.")

            self.wavelength_column = wavelength_idx

            # Identify intensity columns that are non-empty in the first data row
            self.intensity_columns = []

            # Find first valid data line
            first_data_idx = header_row_idx + 1
            while first_data_idx < len(lines) and not lines[first_data_idx].strip():
                first_data_idx += 1

            if first_data_idx >= len(lines):
                raise ValueError("No valid data rows found below header.")

            first_data_row = lines[first_data_idx].split(',')

            # Only keep columns with non-empty value in first data row
            for i in range(wavelength_idx + 1, len(headers)):
                col_name = headers[i].strip()
                if i < len(first_data_row) and first_data_row[i].strip():  # non-empty
                    self.intensity_columns.append(col_name)



            if not self.intensity_columns:
                raise ValueError("No intensity columns found in the file.")

            # Read data rows (rows after the header that have a valid wavelength)
            data_rows = []
            wavelengths = []
            
            for i in range(header_row_idx + 1, len(lines)):
                row = lines[i].split(',')
                if len(row) > wavelength_idx and self._is_valid_wavelength(row[wavelength_idx]):
                    data_rows.append(row)
                    wavelengths.append(float(row[wavelength_idx]))

            if not data_rows:
                raise ValueError("No valid data rows found in the file.")

            # Create DataFrame
            df_data = {'Wavelength (nm)': wavelengths}
            
            # Process each intensity column
            for col_idx, col_name in enumerate(self.intensity_columns):
                actual_col_idx = wavelength_idx + 1 + col_idx
                intensities = []
                overflow_count = 0
                
                for row in data_rows:
                    if len(row) > actual_col_idx:
                        value_str = row[actual_col_idx].strip()
                        try:
                            # Try to convert to float
                            intensity = float(value_str) if value_str else np.nan
                            intensities.append(intensity)
                        except ValueError:
                            # Handle overflow values (non-numeric strings)
                            intensities.append(np.nan)
                            overflow_count += 1
                    else:
                        intensities.append(np.nan)
                
                df_data[col_name] = intensities
                if overflow_count > 0:
                    self.overflow_points[col_name] = overflow_count

            self.data = pd.DataFrame(df_data)

            if self.data.empty:
                raise ValueError("No data found in the file.")

            print(f"Loaded UV-VIS data from {self.file_name} with {len(self.data)} wavelength points.")
            print(f"Intensity columns: {', '.join(self.intensity_columns)}")
            
            if self.overflow_points:
                for col, count in self.overflow_points.items():
                    print(f"Warning: {count} overflow points found in column '{col}'")

            return True

        except Exception as e:
            print(f"Error processing UV-VIS CSV file: {e}")
            return False

    def _is_valid_wavelength(self, value_str):
        """Check if a string represents a valid wavelength (numeric)."""
        try:
            float(value_str.strip())
            return True
        except (ValueError, AttributeError):
            return False

    def get_intensity_columns(self):
        """Return list of intensity column names."""
        return self.intensity_columns

    def get_metadata(self):
        """Return metadata dictionary."""
        return self.metadata

    def get_overflow_info(self):
        """Return information about overflow points."""
        return self.overflow_points

    def get_wavelength_range(self):
        """Return the wavelength range (min, max)."""
        if self.data is not None and not self.data.empty:
            wl_col = 'Wavelength (nm)'
            return (self.data[wl_col].min(), self.data[wl_col].max())
        return None, None

    def get_column_data(self, column_name):
        """Get data for a specific intensity column."""
        if self.data is not None and column_name in self.data.columns:
            return self.data[['Wavelength (nm)', column_name]].dropna()
        return None








