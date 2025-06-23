# Initialize the data_readers package
from .base_reader import BaseReader
from .chromatogram_reader import ChromatogramReader
from .spectra_reader import SpectraReader

def get_data_reader(reader_type: str):
    if reader_type.lower() == 'chromatogram':
        return ChromatogramReader()
    elif reader_type.lower() == 'spectrum':
        return SpectraReader()
    else:
        raise ValueError(f"Unknown data reader type: {reader_type}")
