
# =============================================================================
# File: services/readers/base_reader.py
# =============================================================================
from typing import Any, Optional, Dict, List
from abc import ABC, abstractmethod


class BaseReader(ABC):
    """Base class for all data readers in GeckoPlotter."""

    def __init__(self):
        self.file_path: Optional[str] = None
        self.file_name: Optional[str] = None
        self.data: Optional[Any] = None

    @abstractmethod
    def load_file(self, path: str, extra_files: Optional[List[str]] = None) -> bool:
        """Load and process a file. Override this method in subclass.

        Args:
            path: Path to the main file
            extra_files: Optional list of additional files (for multi-file formats)

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def _process_file(self) -> None:
        """Process the loaded file data. Override in subclasses."""
        pass

    def get_data(self) -> Optional[Any]:
        """Return the processed data."""
        return self.data

    def get_file_name(self) -> Optional[str]:
        """Return the file name."""
        return self.file_name

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata about the loaded file."""
        return {
            'file_path': self.file_path,
            'file_name': self.file_name,
            'data_type': type(self.data).__name__ if self.data is not None else None
        }
