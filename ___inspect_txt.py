from pprint import pprint
import pandas as pd
import re

txt_path = "1 - 15_UV_VIS_1.txt"

with open(txt_path, "r", encoding="utf-8") as f:
    content = f.read()

# --- Split metadata from raw data
if "Raw Data:" not in content:
    raise ValueError("No 'Raw Data:' found.")

meta, raw = content.split("Raw Data:")

# --- Convert German decimal format
def convert_german_number(text):
    text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
    text = re.sub(r'(\d+),(\d+)', r'\1.\2', text)
    return text

raw = convert_german_number(raw)

# --- Load DataFrame
from io import StringIO
df = pd.read_csv(StringIO(raw), sep="\t")

# --- Plot
import matplotlib.pyplot as plt

plt.plot(df['Time (min)'], df['Value (mAU)'])
plt.xlabel("Time (min)")
plt.ylabel("Absorbance (mAU)")
plt.title("Chromatogram")
plt.grid(True)
plt.show()
