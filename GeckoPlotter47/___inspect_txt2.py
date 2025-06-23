from pprint import pprint
import pandas as pd
import re
from io import StringIO

# --- File path ---
txt_path = "1 - 15_UV_VIS_1.txt"

with open(txt_path, "r", encoding="utf-8") as f:
    content = f.read()

# --- Split metadata from raw data ---
if "Raw Data:" not in content:
    raise ValueError("No 'Raw Data:' found.")

meta, raw_data = content.split("Raw Data:")

# --- Process data and check format consistency ---
special_cases = []
anomalies = []
fixed_lines = []

for idx, line in enumerate(raw_data.strip().splitlines(), start=1):
    parts = line.strip().split("\t")
    if len(parts) != 3:
        anomalies.append((idx, line, "Incorrect number of columns"))
        continue

    original = parts[2]

    # Fix commas in all parts
    for i in range(3):
        if ',' in parts[i]:
            parts[i] = re.sub(r'(?<=\d)\.(?=\d{3}(,|\s|$))', '', parts[i])
            parts[i] = parts[i].replace(',', '.')

    # Record transformed Value
    if original != parts[2]:
        special_cases.append((idx, original, parts[2]))

    try:
        float(parts[0])
        float(parts[2])
        fixed_lines.append("\t".join(parts))
    except ValueError:
        anomalies.append((idx, line, "Non-numeric data"))

processed_data = "\n".join(fixed_lines)

# --- Load into DataFrame ---
df = pd.read_csv(StringIO(processed_data), sep="\t", header=None, names=["Time (min)", "Step (s)", "Value (mAU)"])

# --- Convert to numeric and drop bad rows ---
df["Time (min)"] = pd.to_numeric(df["Time (min)"], errors="coerce")
df["Value (mAU)"] = pd.to_numeric(df["Value (mAU)"], errors="coerce")
df = df.dropna()

# --- Output only special-cases ---
print("\n\U0001F4CC Transformed locale-style number lines only:")
for idx, orig, trans in special_cases:
    print(f"Line {idx}: '{orig}'  →  '{trans}'")

# --- Pretty print anomalies ---
if anomalies:
    print("\n❗ Detected anomalies:")
    for anomaly in anomalies:
        print(f"Line {anomaly[0]}: {anomaly[2]} - '{anomaly[1]}'")
else:
    print("\n✅ No anomalies detected.")
