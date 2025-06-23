# lcms/cdf_reader.py

import netCDF4 as nc
import numpy as np
import tempfile
from netCDF4 import Dataset

def load_cdf(uploaded_file):
    # Save uploaded file to temp file so netCDF4 can read it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".cdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    with nc.Dataset(tmp_path, 'r') as ds:
        rt = ds.variables['scan_acquisition_time'][:] / 60
        tic = ds.variables['total_intensity'][:]
    
    return rt, tic, tmp_path

def get_mass_spectrum(file_path, scan_index):
    with nc.Dataset(file_path, 'r') as ds:
        scan_indices = ds.variables['scan_index'][:]
        point_counts = ds.variables['point_count'][:]
        start_idx = scan_indices[scan_index]
        if scan_index < len(scan_indices) - 1:
            end_idx = scan_indices[scan_index + 1]
        else:
            end_idx = start_idx + point_counts[scan_index]
        mz = ds.variables['mass_values'][start_idx:end_idx]
        intensity = ds.variables['intensity_values'][start_idx:end_idx]
    return mz, intensity


# lcms/cdf_reader.py
from netCDF4 import Dataset
import numpy as np

def get_eic(cdf_path, mz_target, tol=0.5):
    from netCDF4 import Dataset
    import numpy as np
    ds = Dataset(cdf_path, "r")
    mzs = ds.variables['mass_values'][:]         # flattened
    ints = ds.variables['intensity_values'][:]    # flattened
    scan_idx = ds.variables['scan_index'][:]          # start indices
    counts = ds.variables['point_count'][:]         # lengths per scan
    scan_time = ds.variables['scan_acquisition_time'][:] / 60.0  # Convert to minutes

    eic = []
    for s, c in zip(scan_idx, counts):
        slice_mz = mzs[s:s+c]
        slice_int = ints[s:s+c]
        mask = np.abs(slice_mz - mz_target) <= tol
        eic.append(slice_int[mask].sum())
    return scan_time, np.array(eic)