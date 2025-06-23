# File: ___inspect_csv.py

import pandas as pd

csv_path = "simple-real.csv"

with open(csv_path, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f.readlines()]

# Detect header line (with "Wavelength")
header_idx = -1
for i, line in enumerate(lines):
    if "Wavelength" in line:
        header_idx = i
        break

if header_idx == -1:
    raise ValueError("No 'Wavelength' header found.")

# Print metadata section
print("🔎 METADATA SECTION\n")
for i in range(header_idx):
    if "," in lines[i]:
        key, val = lines[i].split(",", 1)
        print(f"{key.strip()}: {val.strip()}")
print("\n" + "="*60)

# Read as DataFrame from header line onward
try:
    df = pd.read_csv(csv_path, skiprows=header_idx)
    print(f"📈 DATA STARTING FROM ROW {header_idx}:\n")
    print(df.to_string(index=False))
except Exception as e:
    print(f"⚠️ Failed to load data section: {e}")
