import re

def convert_german_number(text):
    """Convert German decimal format (comma as decimal separator) to English format."""
    # Handle numbers like 1.234,56 -> 1234.56
    text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
    # Handle simple numbers like 123,45 -> 123.45
    text = re.sub(r'(\d+),(\d+)', r'\1.\2', text)
    return text

# Test with your problematic lines
test_lines = [
    "7,263333\t0,200\t669,219010",
    "7,270000\t0,200\t1.007,712092",
    "7,273333\t0,200\t1.187,171240",
    "7,276667\t0,200\t1.363,998328",
    "7,330000\t0,200\t866,419884"
]

print("Testing German number conversion:")
print("=" * 50)

for i, line in enumerate(test_lines):
    converted = convert_german_number(line)
    print(f"Line {i+1}:")
    print(f"  Original:  {line}")
    print(f"  Converted: {converted}")
    print()

# Test with full text block
full_text = "\n".join(test_lines)
print("Full text conversion:")
print("=" * 30)
print("Before:")
print(full_text)
print("\nAfter:")
converted_full = convert_german_number(full_text)
print(converted_full)

# Test parsing the converted text
print("\n" + "=" * 30)
print("Testing pandas parsing:")
from io import StringIO
import pandas as pd

try:
    df = pd.read_csv(StringIO(converted_full), sep="\t", header=None, names=["Time (min)", "Step (s)", "Value (mAU)"])
    print("✅ Pandas parsing successful!")
    print(f"Shape: {df.shape}")
    print("Data types:")
    print(df.dtypes)
    
    # Try numeric conversion
    df["Time (min)"] = pd.to_numeric(df["Time (min)"], errors="coerce")
    df["Value (mAU)"] = pd.to_numeric(df["Value (mAU)"], errors="coerce")
    
    nan_count = df.isnull().sum().sum()
    print(f"NaN values after numeric conversion: {nan_count}")
    
    if nan_count > 0:
        print("Rows with NaN:")
        print(df[df.isnull().any(axis=1)])
    else:
        print("✅ All numeric conversions successful!")
        
except Exception as e:
    print(f"❌ Pandas parsing failed: {e}")