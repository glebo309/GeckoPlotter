# File: readers/spectra_reader.py
import os
import re
import pandas as pd
from io import StringIO
from .base_reader import BaseReader

class SpectraReader(BaseReader):
    """Reader for spectral data files."""

    def __init__(self):
        super().__init__()
        self.time_point = None


    def _process_file(self):
        """Process the spectral data file content."""
        try:
            with open(self.file_path, 'r') as file:
                content = file.read()

            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0]
            self.metadata = {}

            # Time point
            time_match = re.search(r"Time:\s*(\d+\.\d+)\s*min", content)
            if time_match:
                self.time_point = time_match.group(1)
                self.metadata['Time (min)'] = self.time_point

            # Extract all header metadata (before 'Spectral Data:')
            header_part = content.split("Spectral Data:")[0]
            for line in header_part.strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    self.metadata[key.strip()] = value.strip()

            raw_data_start = content.find("Spectral Data:")
            if raw_data_start == -1:
                raise ValueError(f"'Spectral Data:' not found in {self.file_path}")

            raw_data = content[raw_data_start + len("Spectral Data:"):].strip()
            raw_data = raw_data.replace(",", ".")

            df = pd.read_csv(StringIO(raw_data), sep="\t")
            if not {'Wavelength (nm)', 'Absorbance'}.issubset(df.columns):
                raise ValueError("Required columns missing")
            self.data = df[['Wavelength (nm)', 'Absorbance']]
            return True

        except Exception as e:
            print(f"Error processing spectral file: {e}")
            return False

    def get_metadata(self):
        return self.metadata


    def get_time_point(self):
        """Return the time point of the spectrum."""
        return self.time_point
