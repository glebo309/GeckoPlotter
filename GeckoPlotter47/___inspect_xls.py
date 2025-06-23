# File: xls_reader.py

import pandas as pd

xls_path = "1 - 15.xls"

# Load the Excel file
xls = pd.ExcelFile(xls_path)

print(f"📄 Found sheets: {xls.sheet_names}\n")

# Print everything from all sheets
for sheet_name in xls.sheet_names:
    print(f"\n--- SHEET: {sheet_name} ---\n")
    try:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        print(df.to_string(index=False, header=False))
    except Exception as e:
        print(f"⚠️ Failed to load sheet '{sheet_name}': {e}")
