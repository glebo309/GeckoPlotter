#!/usr/bin/env python3
"""
Test script to debug integration parsing
Run this with your actual integration file to see what's happening
"""

import pandas as pd
from io import StringIO
import re

def convert_german_number(text):
    """Convert German decimal format to English format."""
    print(f"[DEBUG] Converting German numbers...")
    
    original_text = text
    
    # Handle numbers like 1.234,56 -> 1234.56
    text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
    
    # Handle simple numbers like 123,45 -> 123.45
    text = re.sub(r'\b(\d+),(\d+)\b', r'\1.\2', text)
    
    # Handle numbers in table cells
    text = re.sub(r'\t(\d+),(\d+)\t', r'\t\1.\2\t', text)
    text = re.sub(r'\t(\d+),(\d+)$', r'\t\1.\2', text, flags=re.MULTILINE)
    text = re.sub(r'^(\d+),(\d+)\t', r'\1.\2\t', text, flags=re.MULTILINE)
    
    if text != original_text:
        print(f"[DEBUG] German number conversion applied")
    
    return text

def parse_integration_table(text):
    """Parse integration table from text."""
    try:
        if "Integration Results" not in text:
            print("❌ 'Integration Results' not found")
            return None

        # Split at Integration Results
        section = text.split("Integration Results")[1]
        print(f"✅ Found Integration Results section ({len(section)} chars)")
        
        # Apply German number conversion
        section = convert_german_number(section)
        
        lines = section.strip().split('\n')
        print(f"📋 Processing {len(lines)} lines")
        
        # Show all lines for debugging
        print("\n🔍 All lines in section:")
        for i, line in enumerate(lines):
            print(f"  {i:2d}: '{line}'")
        
        # Find header line
        header_line = None
        header_idx = -1
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            if any(kw in line for kw in ["No.", "Peak Name", "Retention Time", "Area", "Height"]):
                header_line = line
                header_idx = i
                print(f"\n📊 Found header at line {i}: '{line}'")
                break
        
        if not header_line:
            print("❌ No header found")
            return None
        
        # Find data lines
        data_lines = []
        for i in range(header_idx + 1, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            
            # Skip units line
            parts = [p.strip() for p in line.split('\t')]
            is_units = all(p in ['', 'min', 'mAU', 'mAU*min', '%', 'n.a.'] for p in parts if p)
            
            if is_units:
                print(f"⏭️  Skipping units line {i}: '{line}'")
                continue
            
            # Skip total line
            if 'Total:' in line or 'Total' in parts[0]:
                print(f"⏭️  Skipping total line {i}: '{line}'")
                continue
            
            data_lines.append(line)
            print(f"📈 Data line {i}: '{line}'")
        
        if not data_lines:
            print("❌ No data lines found")
            return None
        
        # Create CSV content
        csv_lines = [header_line] + data_lines
        csv_content = '\n'.join(csv_lines)
        
        print(f"\n📄 Final CSV content:")
        print(csv_content)
        
        # Parse with pandas
        df = pd.read_csv(StringIO(csv_content), sep="\t")
        df.columns = [col.strip() for col in df.columns]
        df = df.dropna(how="all", axis=1)
        df = df.dropna(how="all", axis=0)
        
        print(f"\n✅ Successfully parsed table:")
        print(f"   Shape: {df.shape}")
        print(f"   Columns: {list(df.columns)}")
        print(f"\n📊 Data preview:")
        print(df.to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

# Test with your file
if __name__ == "__main__":
    # Read your integration file
    with open("1 - 15_Integration.txt", "r", encoding="utf-8") as f:
        content = f.read()
    
    print("🧪 Testing integration table parsing...")
    result = parse_integration_table(content)
    
    if result is not None:
        print("\n🎉 Success! Table parsed correctly.")
    else:
        print("\n💥 Failed to parse table.")