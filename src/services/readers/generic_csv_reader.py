"""
Generic CSV Reader for simple tabular data files
"""
import pandas as pd
import os
from typing import Optional, Dict, Any
from .base_reader import BaseReader


class GenericCSVReader(BaseReader):
    """Reader for generic CSV files with simple tabular data."""

    def __init__(self):
        super().__init__()
        self.metadata: Dict[str, Any] = {}

    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        """Load generic CSV file."""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")

            # Try to read the CSV with pandas - handle different line endings
            # lineterminator=None lets pandas auto-detect \n, \r\n, or \r
            self.data = pd.read_csv(path, lineterminator=None)
            
            # Basic validation
            if self.data.empty:
                print(f"⚠️ CSV file is empty: {path}")
                return False
            
            # Store basic metadata
            self.metadata = {
                'file_type': 'generic_csv',
                'file_name': self.file_name,
                'rows': len(self.data),
                'columns': len(self.data.columns),
                'column_names': list(self.data.columns)
            }
            
            print(f"✅ Loaded generic CSV: {len(self.data)} rows × {len(self.data.columns)} columns")
            print(f"   Columns: {list(self.data.columns)}")
            return True

        except Exception as e:
            print(f"❌ Failed to load generic CSV {path}: {e}")
            return False

    def _process_file(self) -> None:
        """Abstract method implementation - not used in this reader."""
        pass  # Data is already processed by pandas

    def get_data(self) -> Optional[pd.DataFrame]:
        """Return the loaded DataFrame."""
        return self.data

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata dictionary."""
        return self.metadata
