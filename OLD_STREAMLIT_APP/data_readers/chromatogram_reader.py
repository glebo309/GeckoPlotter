import os
import re
import pandas as pd
from io import StringIO
from data_readers.base_reader import BaseReader

class ChromatogramReader(BaseReader):
    """Reader for chromatogram data files."""

    def __init__(self):
        super().__init__()
        self.wavelength = None

    def _process_file(self):
        """
        Process the chromatogram file content.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with open(self.file_path, 'r') as file:
                content = file.read()

            # Extract filename (without extension) for legend
            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0].replace("_UV_VIS_1", "")

            # Extract wavelength information
            wavelength_match = re.search(r"WVL:\s*(\d{3})\s*nm", content)
            if wavelength_match:
                self.wavelength = wavelength_match.group(1)
                print(f"Extracted wavelength: {self.wavelength} nm from {self.file_name}")
            else:
                raise ValueError(f"Wavelength not found in the file: {self.file_path}")

            # Remove everything before 'Raw Data:'
            raw_data_start = content.find("Raw Data:")
            if raw_data_start == -1:
                raise ValueError(f"'Raw Data:' section not found in the file: {self.file_path}")

            raw_data = content[raw_data_start + len("Raw Data:"):].strip()

            # Debug: Show what we're working with
            print("BEFORE replacement:")
            first_few_lines = raw_data.split('\n')[:3]
            for line in first_few_lines:
                print(f"  '{line}'")
            
            # Check if we have the problematic numbers
            if '1.042,436199' in raw_data:
                print("Found problematic number: 1.042,436199")
            
            # Fix European numbers: remove dots (thousands separators), then convert commas to dots (decimal)
            # This handles cases like "1.042,436199" -> "1042,436199" -> "1042.436199"
            raw_data = raw_data.replace(".", "")  # Remove thousands separators first
            raw_data = raw_data.replace(".", "")  # Remove thousands separators first  
            raw_data = raw_data.replace(",", ".")  # Then replace commas with dots for decimal points

            # Debug: Show what we get after replacement
            print("AFTER replacement:")
            first_few_lines = raw_data.split('\n')[:3]
            for line in first_few_lines:
                print(f"  '{line}'")
            
            # Check if replacement worked
            if '1042.436199' in raw_data:
                print("SUCCESS: Found converted number: 1042.436199")
            if '1.042,436199' in raw_data:
                print("ERROR: Still found problematic number: 1.042,436199")

            # Convert raw data to a pandas dataframe
            df = pd.read_csv(StringIO(raw_data), sep="\t")

            # Only keep 'Time (min)' and 'Value (mAU)' columns
            if not {'Time (min)', 'Value (mAU)'}.issubset(df.columns):
                raise ValueError(f"Required columns not found in the file: {self.file_path}")

            self.data = df[['Time (min)', 'Value (mAU)']]

            if self.data.empty:
                raise ValueError(f"No data found in 'Raw Data:' section of the file: {self.file_path}")
            else:
                print(f"Loaded chromatogram data from {self.file_name} with {len(self.data)} points.")

            return True

        except Exception as e:
            print(f"Error processing chromatogram file: {e}")
            return False

    def get_wavelength(self):
        """
        Return the wavelength from the chromatogram data.

        Returns:
            str: The wavelength in nm
        """
        return self.wavelength