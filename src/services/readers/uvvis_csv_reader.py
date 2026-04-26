# =============================================================================
# File: services/readers/uvvis_csv_reader.py
# =============================================================================
import pandas as pd
import os
from typing import Optional, Dict, Any, List, Tuple
from .base_reader import BaseReader


class UVVISCSVReader(BaseReader):
    """Reader for UV-Vis CSV files from Synergy H1 plate readers."""

    def __init__(self):
        super().__init__()
        self.metadata: Dict[str, Any] = {}
        self.intensity_columns: List[str] = []
        self.wavelength_range: Tuple[Optional[float], Optional[float]] = (None, None)

    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        """Load UV-Vis CSV file."""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")

            # Find header row
            header_idx = self._find_header_row(path)
            if header_idx == -1:
                raise ValueError("No 'Wavelength' header found in CSV file")

            # Parse metadata
            self._parse_metadata(path, header_idx)

            # Load data
            self.data = pd.read_csv(path, skiprows=header_idx)

            # Process data
            self._process_data()
            self._extract_intensity_columns()

            # Calculate wavelength range
            self._calculate_wavelength_range()

            return True

        except Exception as e:
            print(f"Failed to load UV-Vis CSV {path}: {e}")
            return False

    def _process_file(self) -> None:
        """Abstract method implementation - not used in this reader."""
        pass  # This reader processes data differently

    def _find_header_row(self, path: str) -> int:
        """Find the row containing 'Wavelength' header."""
        with open(path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if "Wavelength" in line:
                    return i
        return -1

    def _parse_metadata(self, path: str, header_idx: int) -> None:
        """Parse metadata from lines before header."""
        self.metadata = {}

        with open(path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]

        for line in lines[:header_idx]:
            if not line or line.count(',') < 1:
                continue

            parts = line.split(',', 1)
            if len(parts) >= 2:
                key = parts[0].strip().rstrip(':')
                value = parts[1].strip().rstrip(',').strip()

                if key and value:
                    self.metadata[key] = value

        # Add computed metadata
        if 'Date' in self.metadata and 'Time' in self.metadata:
            self.metadata['DateTime'] = f"{self.metadata['Date']} {self.metadata['Time']}"

        self.metadata['Data Type'] = 'UV-Vis Spectrum'

    def _process_data(self) -> None:
        """Clean and process the data DataFrame."""
        # Remove empty columns
        self.data = self.data.dropna(axis=1, how='all')

        # Remove unnamed columns
        cols_to_keep = [col for col in self.data.columns
                       if not col.startswith('Unnamed:') and col.strip()]
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
    def _extract_intensity_columns(self) -> None:
        """Extract well column names (intensity columns)."""
        self.intensity_columns = [col for col in self.data.columns
                                if col != 'Wavelength' and col.strip()]

    def _calculate_wavelength_range(self) -> None:
        """Calculate wavelength range."""
        if 'Wavelength' in self.data.columns:
            wl_col = self.data['Wavelength'].dropna()
            if len(wl_col) > 0:
                self.wavelength_range = (wl_col.min(), wl_col.max())

    def get_intensity_columns(self) -> List[str]:
        """Return list of well/intensity column names."""
        return self.intensity_columns.copy()

    def get_wavelength_range(self) -> Tuple[Optional[float], Optional[float]]:
        """Return (min_wavelength, max_wavelength) tuple."""
        return self.wavelength_range

    def get_well_data(self, well_name: str) -> Optional[pd.DataFrame]:
        """Get absorbance spectrum for a specific well."""
        if well_name in self.intensity_columns and 'Wavelength' in self.data.columns:
            return self.data[['Wavelength', well_name]].dropna()
        return None

    def get_filled_wells(self) -> List[str]:
        """Return list of wells that contain data."""
        filled_wells = []
        for col in self.intensity_columns:
            if col in self.data.columns:
                values = self.data[col].dropna()
                if len(values) > 0 and (values > 0.001).any():
                    filled_wells.append(col)
        return filled_wells

    def get_column_data(self, column_name: str) -> Optional[pd.DataFrame]:
        """Get wavelength and absorbance data for a specific well/column."""
        if self.data is None or 'Wavelength' not in self.data.columns:
            return None

        if column_name not in self.data.columns:
            return None

        result = self.data[['Wavelength', column_name]].copy()
        result = result.dropna()

        # Rename columns for consistency
        result = result.rename(columns={
            'Wavelength': 'Wavelength (nm)',
            column_name: column_name
        })

        return result

    def get_available_columns(self) -> List[str]:
        """Get list of available intensity columns."""
        return self.intensity_columns.copy()

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the loaded data."""
        if self.data is None:
            return {}

        metadata = self.metadata.copy()
        metadata.update({
            'file_type': 'uvvis_csv',
            'data_points': len(self.data),
            'wavelength_range': (self.data['Wavelength'].min(), self.data['Wavelength'].max()),
            'intensity_columns': self.get_intensity_columns(),
            'filled_wells': self.get_filled_wells(),
        })
        
        metadata['filled_well_count'] = len(metadata['filled_wells'])
        metadata['total_wells'] = len(metadata['intensity_columns'])
        
        return metadata
