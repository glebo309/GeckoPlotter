
# =============================================================================
# File: readers/base_reader.py
class BaseReader:
    """Base class for all data readers."""
    
    def __init__(self):
        self.file_path = None

    def load_file(self, path, extra_files=None):
        """Override this method in subclass."""
        raise NotImplementedError("load_file() must be implemented by the subclass")

    def _process_file(self):
        """Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _process_file")
    
    def get_data(self):
        """Return the processed data."""
        return self.data
    
    def get_file_name(self):
        """Return the file name."""
        return self.file_name
