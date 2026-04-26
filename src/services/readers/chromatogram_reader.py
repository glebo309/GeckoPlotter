# =============================================================================
# File: services/readers/chromatogram_reader.py
# =============================================================================
import os
import re
import pandas as pd
from io import StringIO
from typing import Optional, Dict, Any
from .base_reader import BaseReader


class ChromatogramReader(BaseReader):
    """Reader for chromatogram data files (TXT format with German number format support)."""

    def __init__(self):
        super().__init__()
        self.wavelength: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

    @staticmethod
    def _convert_german_number(text: str) -> str:
        """Convert German decimal format (comma as decimal separator) to English format."""
        # Handle numbers like 1.234,56 -> 1234.56
        text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
        # Handle simple numbers like 123,45 -> 123.45
        text = re.sub(r'(\d+),(\d+)', r'\1.\2', text)
        return text
    
    def _extract_metadata_from_header(self, header: str) -> None:
        """Extract all metadata from the header section."""
        # Parse key-value pairs from header
        # Format: "Key:\tValue" or "Key\tValue"
        lines = header.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('---'):
                continue
            
            # Try tab-separated key:value format
            if '\t' in line:
                parts = line.split('\t')
                for i in range(0, len(parts)-1, 2):
                    if i+1 < len(parts):
                        key = parts[i].strip().rstrip(':')
                        value = parts[i+1].strip()
                        if key and value:
                            # Clean key for storage
                            clean_key = key.replace(' ', '_').replace('(', '').replace(')', '').replace('.', '').lower()
                            self.metadata[clean_key] = value
            
            # Try colon-separated format
            elif ':' in line and not line.startswith('chrom://'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    clean_key = key.replace(' ', '_').replace('(', '').replace(')', '').replace('.', '').lower()
                    self.metadata[clean_key] = value

    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        """Load and process a chromatogram file."""
        try:
            self.file_path = path
            self.file_name = os.path.splitext(os.path.basename(path))[0].replace("_UV_VIS_1", "")

            # Read file content
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Process the file
            return self._process_file_content(content)

        except Exception as e:
            print(f"Failed to load chromatogram {path}: {e}")
            return False

    def _process_file(self) -> None:
        """Abstract method implementation - not used in this reader."""
        pass  # This reader uses _process_file_content instead

    def _process_file_content(self, content: str) -> bool:
        """Process the chromatogram file content."""
        try:
            # Split metadata from raw data
            if "Raw Data:" not in content:
                raise ValueError("Raw Data section not found in file")

            header_section, raw_data = content.split("Raw Data:", 1)
            
            # Extract ALL metadata from header section
            self._extract_metadata_from_header(header_section)
            
            # Extract wavelength (for backward compatibility)
            wavelength_match = re.search(r"WVL:\s*(\d{3})\s*nm", content)
            if wavelength_match:
                self.wavelength = wavelength_match.group(1)
                if 'wavelength_nm' not in self.metadata:
                    self.metadata['wavelength_nm'] = self.wavelength

            # Convert German decimal format
            raw_data = self._convert_german_number(raw_data)

            # Parse into DataFrame
            df = pd.read_csv(StringIO(raw_data), sep="\t")

            # Validate required columns
            required_cols = ['Time (min)', 'Value (mAU)']
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"Missing required columns. Found: {list(df.columns)}")

            # Convert to numeric and clean data
            df["Time (min)"] = pd.to_numeric(df["Time (min)"], errors="coerce")
            df["Value (mAU)"] = pd.to_numeric(df["Value (mAU)"], errors="coerce")
            df = df.dropna()

            if len(df) == 0:
                raise ValueError("No valid data points found after cleaning")

            # Store the processed data
            self.data = df[required_cols].copy()

            # Update metadata
            self.metadata.update({
                'data_points': len(self.data),
                'time_range': f"{self.data['Time (min)'].min():.2f} - {self.data['Time (min)'].max():.2f} min",
                'value_range': f"{self.data['Value (mAU)'].min():.1f} - {self.data['Value (mAU)'].max():.1f} mAU",
                'file_type': 'chromatogram'
            })

            return True

        except Exception as e:
            print(f"Failed to process chromatogram content: {e}")
            return False

    def get_wavelength(self) -> Optional[str]:
        """Return the wavelength from the chromatogram data."""
        return self.wavelength

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata dictionary."""
        return self.metadata.copy()
