# File: ___inspect_cdf.py
from netCDF4 import Dataset
import numpy as np
import sys
import os

cdf_path = sys.argv[1] if len(sys.argv) > 1 else "LCMS-2025-05-06 14-22-39+02-00-04_MS1 -TIC SCAN ESI Frag=135V Gain=1-0_spectra.cdf"  # ← or hardcode for now

if not os.path.exists(cdf_path):
    print(f"❌ File not found: {cdf_path}")
    sys.exit(1)

try:
    ds = Dataset(cdf_path, "r")
except Exception as e:
    print(f"❌ Failed to open CDF file: {e}")
    sys.exit(1)

print(f"📂 Inspecting: {cdf_path}\n")

# --- General Metadata ---
print("🔎 METADATA\n")
for attr in ds.ncattrs():
    print(f"{attr}: {getattr(ds, attr)}")

# --- Variables ---
print("\n📦 VARIABLES\n")
for var in ds.variables:
    print(f"• {var}: shape={ds.variables[var].shape}, dtype={ds.variables[var].dtype}")

# --- Detect Content Type ---
varnames = ds.variables.keys()

print("\n" + "="*60)

if "scan_acquisition_time" in varnames:
    print("🧪 MS SCAN DATA DETECTED")
    try:
        times = ds.variables["scan_acquisition_time"][:]
        tics = ds.variables["total_intensity"][:]
        mz_min = ds.variables["mass_range_min"][:]
        mz_max = ds.variables["mass_range_max"][:]

        print(f"🕓 Total scans: {len(times)}")
        print(f"⏱️ First 5 scan times (min): {times[:5] / 60.0}")
        print(f"📊 TIC range: {min(tics):.1f} – {max(tics):.1f}")
        print(f"🔬 m/z range per scan: {mz_min[0]:.1f} – {mz_max[0]:.1f}")
    except Exception as e:
        print(f"⚠️ Error reading MS scan data: {e}")


elif "raw_data_retention" in varnames and "ordinate_values" in varnames:
    print("📈 VWD TRACE DETECTED")
    try:
        intensity = ds.variables["ordinate_values"][:]
        try:
            rt = ds.variables["raw_data_retention"][:]
            if np.all(rt == 0.0):
                raise ValueError("Invalid retention time")
        except:
            interval = ds.variables["actual_sampling_interval"][:]
            rt = np.arange(len(intensity)) * interval
            print(f"⚠️ Retention time missing — reconstructed from sampling interval ({interval:.3f}s)")
        
        print(f"📊 Points: {len(rt)}")
        print(f"⏱️ Retention time range: {rt[0]:.2f} – {rt[-1]:.2f} sec")
        print(f"📉 Intensity range: {min(intensity):.1f} – {max(intensity):.1f} mAU")
    except Exception as e:
        print(f"⚠️ Error reading VWD data: {e}")



else:
    print("❌ Unknown or unsupported CDF structure.")

ds.close()
