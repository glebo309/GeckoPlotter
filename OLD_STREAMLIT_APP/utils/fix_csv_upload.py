# fix_csv_upload.py

import streamlit as st
import os
import tempfile

def fix_csv_upload(original_file):
    """
    Fix for the CSV upload issue by handling file extension case sensitivity.
    
    This function creates a temporary file with a properly formatted extension
    that Streamlit will accept.
    
    Parameters:
    -----------
    original_file : streamlit.UploadedFile
        The original file uploaded by the user
        
    Returns:
    --------
    streamlit.UploadedFile
        A modified file object with the proper extension
    """
    if original_file is None:
        return None
        
    # Check if this is a CSV file with uppercase extension
    filename = original_file.name
    base, ext = os.path.splitext(filename)
    
    # If extension is .CSV, create a temporary file with lowercase extension
    if ext.upper() == '.CSV' and ext != '.csv':
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp_file:
            temp_file.write(original_file.getbuffer())
            temp_path = temp_file.name
            
        # Create a new UploadedFile-like object with the correct extension
        class FixedUploadedFile:
            def __init__(self, orig_file, path):
                self.name = orig_file.name.replace(ext, '.csv')
                self._path = path
                self._buffer = None
                self.type = orig_file.type
                self.size = orig_file.size
            
            def read(self, size=-1):
                with open(self._path, 'rb') as f:
                    return f.read(size)
                    
            def getbuffer(self):
                if self._buffer is None:
                    with open(self._path, 'rb') as f:
                        self._buffer = f.read()
                return self._buffer
                
            def seek(self, offset):
                # This is handled differently since we're using a file path now
                pass
                
        return FixedUploadedFile(original_file, temp_path)
    
    # Otherwise, return the original file unchanged
    return original_file