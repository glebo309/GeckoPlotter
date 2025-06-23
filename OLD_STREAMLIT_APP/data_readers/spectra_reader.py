import os
import pandas as pd
from data_readers.base_reader import BaseReader

class SpectraReader(BaseReader):
    """Simple spectrum reader."""

    def __init__(self):
        super().__init__()
        self.peak_wavelength = 0.0
        self.spectrum_names = []  # Add this to store spectrum names
        
    def _process_file(self):
        """
        Process the spectrum file content and extract each spectrum as a separate dataset.
        """
        try:
            # Extract filename
            self.file_name = os.path.splitext(os.path.basename(self.file_path))[0]
            
            # Read the CSV file
            self.data = pd.read_csv(self.file_path)
            
            # Check for 'Wavelength' column
            if 'Wavelength' not in self.data.columns:
                print(f"No Wavelength column in {self.file_path}")
                return False
                
            # Find intensity columns (all non-Wavelength columns)
            intensity_columns = [col for col in self.data.columns if col != 'Wavelength']
            if not intensity_columns:
                print(f"No intensity columns in {self.file_path}")
                return False
                
            # Store all spectrum names
            self.spectrum_names = intensity_columns
            
            # Store wavelength data as X values
            self.wavelength_data = self.data['Wavelength'].values
            
            # Create separate data for each spectrum
            self.spectra_data = {}
            self.peak_wavelengths = {}
            
            for column in intensity_columns:
                # Create a dataset for this spectrum
                spectrum_data = pd.DataFrame({
                    'Wavelength': self.data['Wavelength'],
                    'Intensity': self.data[column]
                })
                
                # Find peak wavelength for this spectrum
                max_idx = spectrum_data['Intensity'].idxmax()
                peak_wavelength = float(spectrum_data.loc[max_idx, 'Wavelength'])
                
                # Store this spectrum and its peak wavelength
                self.spectra_data[column] = spectrum_data
                self.peak_wavelengths[column] = peak_wavelength
                
                print(f"Processed spectrum {column} with peak at {peak_wavelength} nm")
            
            # For backward compatibility, keep self.data as the first spectrum
            if intensity_columns:
                self.data = self.spectra_data[intensity_columns[0]]
                self.peak_wavelength = self.peak_wavelengths[intensity_columns[0]]
            
            print(f"Processed {self.file_name} with {len(self.data)} points")
            print(f"Found {len(intensity_columns)} spectra: {', '.join(intensity_columns)}")
            
            return True
        except Exception as e:
            print(f"Error in spectrum reader: {e}")
            import traceback
            traceback.print_exc()
            # Create minimal valid dataframe
            self.data = pd.DataFrame({
                'Wavelength': [0.0],
                'Intensity': [0.0]
            })
            self.spectra_data = {}
            self.peak_wavelength = 0.0
            self.peak_wavelengths = {}
            self.spectrum_names = []
            return False

    def get_all_spectra(self):
        """Return a dictionary of all spectra data."""
        return self.spectra_data

    def get_spectrum_data(self, spectrum_name):
        """Return data for a specific spectrum."""
        if spectrum_name in self.spectra_data:
            return self.spectra_data[spectrum_name]
        return None

    def get_peak_wavelength_for_spectrum(self, spectrum_name):
        """Return the peak wavelength for a specific spectrum."""
        if spectrum_name in self.peak_wavelengths:
            return self.peak_wavelengths[spectrum_name]
        return 0.0

    def get_spectrum_names(self):
        """Return list of all spectrum names (column names)."""
        return self.spectrum_names

    def get_peak_wavelength(self):
        """Return dictionary of peak wavelengths for all spectra."""
        return self.peak_wavelengths


        """Return the peak wavelength."""
        return self.peak_wavelength
        

        """Return list of all spectrum names (column names)."""
        return self.spectrum_names