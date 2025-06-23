import os
import pandas as pd
from io import StringIO
from data_readers.base_reader import BaseReader

class CSVReader(BaseReader):
    """Reader for CSV chromatogram data files."""

    def __init__(self):
        super().__init__()
        self.wavelength = "Unknown"  # CSV files typically don't have wavelength info

    def _process_file(self):
        """
        Process the CSV file content.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Read CSV file
            df = pd.read_csv(self.file_path)
            
            # Extract filename (without extension) for legend
            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0]
            
            # Assume first column is time, second column is signal
            if len(df.columns) < 2:
                raise ValueError(f"CSV must have at least 2 columns, found {len(df.columns)}")
            
            # Try to detect time and value columns by name
            time_col = None
            value_col = None
            
            for col in df.columns:
                col_lower = col.lower()
                if 'time' in col_lower and time_col is None:
                    time_col = col
                elif any(word in col_lower for word in ['value', 'signal', 'intensity', 'mau', 'absorbance']) and value_col is None:
                    value_col = col
            
            # If no columns found by name, use first two columns
            if time_col is None:
                time_col = df.columns[0]
            if value_col is None:
                value_col = df.columns[1]
            
            # Create standardized DataFrame
            self.data = pd.DataFrame({
                'Time (min)': df[time_col].astype(float),
                'Value (mAU)': df[value_col].astype(float)
            })
            
            if self.data.empty:
                raise ValueError(f"No data found in CSV file: {self.file_path}")
            else:
                print(f"Loaded CSV data from {self.file_name} with {len(self.data)} points.")
                print(f"Time column: {time_col}, Value column: {value_col}")

            return True

        except Exception as e:
            print(f"Error processing CSV file: {e}")
            return False

    def get_wavelength(self):
        """
        Return the wavelength (CSV files don't typically have this).

        Returns:
            str: "Unknown" for CSV files
        """
        return self.wavelength