import netCDF4 as nc
import os
import numpy as np

def explore_cdf_file(file_path):
    """
    Thoroughly explore a CDF file to check for MS data and analyze the structure.
    
    Parameters:
    file_path (str): Path to the CDF file
    """
    print(f"\nExploring file: {file_path}")
    print("-" * 80)
    
    try:
        # Open the CDF file
        data = nc.Dataset(file_path, 'r')
        
        # Get basic file information
        print("File Information:")
        if 'experiment_title' in data.variables:
            print(f"Experiment: {data.variables['experiment_title'][0].decode('utf-8')}")
        if 'sample_name' in data.variables:
            print(f"Sample: {data.variables['sample_name'][0].decode('utf-8')}")
        if 'detector_name' in data.variables:
            print(f"Detector: {data.variables['detector_name'][0].decode('utf-8')}")
        if 'separation_experiment_type' in data.variables:
            print(f"Experiment Type: {data.variables['separation_experiment_type'][0].decode('utf-8')}")
        
        # Check for dimensions
        print("\nDimensions:")
        for dim_name, dim in data.dimensions.items():
            print(f"- {dim_name}: {len(dim)}")
        
        # List all variables with their shapes and a sample of data
        print("\nVariables:")
        for var_name, var in data.variables.items():
            shape_str = str(var.shape)
            data_type = str(var.dtype)
            
            # Print basic variable info
            print(f"- {var_name}: shape={shape_str}, type={data_type}")
            
            # Try to print a sample of data (first few elements)
            try:
                if len(var.shape) == 0:
                    value = var[()]
                    if isinstance(value, bytes):
                        value = value.decode('utf-8')
                    print(f"  Value: {value}")
                elif var.shape[0] < 10:
                    for i in range(var.shape[0]):
                        value = var[i]
                        if isinstance(value, bytes):
                            value = value.decode('utf-8')
                        print(f"  [{i}]: {value}")
                else:
                    # Just print the first few elements
                    sample = var[:5]
                    if sample.dtype.kind == 'S':  # String type
                        sample = [s.decode('utf-8') for s in sample]
                    print(f"  Sample: {sample}...")
            except:
                print(f"  Could not display sample data")
        
        # Look specifically for MS-related variables
        print("\nLooking for Mass Spectrometry Data:")
        ms_related_vars = [
            'mass_values', 'm/z', 'mass_range', 'mass_spectral_data', 'ms_data',
            'mass', 'masses', 'mass_spectra', 'spectral_data', 'ms1_spectra'
        ]
        
        potential_ms_vars = []
        for var_name in data.variables:
            # Check for exact matches in the standard MS variable names
            if var_name.lower() in [v.lower() for v in ms_related_vars]:
                potential_ms_vars.append(var_name)
            # Check if variable name contains key MS-related terms
            elif any(term in var_name.lower() for term in ['mass', 'ms', 'm/z', 'spectral']):
                potential_ms_vars.append(var_name)
        
        if potential_ms_vars:
            print(f"Potentially MS-related variables found:")
            for var_name in potential_ms_vars:
                print(f"- {var_name}: shape={data.variables[var_name].shape}")
        else:
            print("No obvious MS-related variables found.")
        
        # Look for MS data based on detector name
        if 'detector_name' in data.variables:
            detector = data.variables['detector_name'][0].decode('utf-8')
            if 'MS' in detector or 'TIC' in detector:
                print(f"\nThis appears to be a mass spectrometry file based on detector name: {detector}")
                
                # For TIC data, the chromatogram is likely the Total Ion Current
                if 'ordinate_values' in data.variables:
                    print("This file contains TIC (Total Ion Current) data.")
                    
                    # Check if there's information about the scan ranges or mass ranges
                    mass_range_vars = [v for v in data.variables if 'range' in v.lower()]
                    if mass_range_vars:
                        print("Potential mass range information in variables:")
                        for var in mass_range_vars:
                            print(f"- {var}")
                    
                    # Check if individual mass spectra are stored
                    # In some CDF formats, a set of variables like 'mass_spectrum_1', 'mass_spectrum_2', etc. might exist
                    spectrum_vars = [v for v in data.variables if 'spectrum' in v.lower() or 'spectra' in v.lower()]
                    if spectrum_vars:
                        print("Potential individual mass spectra in variables:")
                        for var in spectrum_vars:
                            print(f"- {var}")
        
        # Close the file
        data.close()
        print("-" * 80)
        
    except Exception as e:
        print(f"Error exploring file: {e}")
        import traceback
        traceback.print_exc()

# List all CDF files in the current directory
cdf_files = [f for f in os.listdir() if f.endswith('.cdf')]

if __name__ == "__main__":
    if not cdf_files:
        print("No CDF files found in the current directory.")
    else:
        print(f"Found {len(cdf_files)} CDF files in the current directory.")
        
        # Explore each file
        for file_name in cdf_files:
            explore_cdf_file(file_name)
        
        print("\nSummary:")
        print(f"Analyzed {len(cdf_files)} CDF files.")
        print("To extract and plot specific data from these files, we need to identify which")
        print("variables contain the chromatogram and mass spectral data.")