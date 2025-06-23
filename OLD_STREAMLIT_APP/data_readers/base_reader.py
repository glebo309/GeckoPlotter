
import os


class BaseReader:
    """Base class for all data readers in GeckoPlotter."""

    def __init__(self):
        self.file_path = None
        self.file_name = None
        self.data = None

    def read_file(self, file_path):
        """
        Read the file and process its content.

        Args:
            file_path (str): Path to the file to be read

        Returns:
            bool: True if successful, False otherwise
        """
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        return self._process_file()

    def _process_file(self):
        """
        Process the file content. Should be implemented by subclasses.

        Returns:
            bool: True if successful, False otherwise
        """
        raise NotImplementedError("Subclasses must implement _process_file()")

    def get_data(self):
        """
        Return the processed data.

        Returns:
            object: The processed data
        """
        return self.data
