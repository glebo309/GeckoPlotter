import pandas as pd

def read_sec_file_robust(file_path):
    """
    Robust SEC file reader that handles files starting with 0xFF
    """
    
    # Read as binary
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()
    
    print(f"File size: {len(raw_bytes)} bytes")
    print(f"First 10 bytes (hex): {' '.join(f'{b:02x}' for b in raw_bytes[:10])}")
    
    # Check for specific byte patterns
    if raw_bytes[0] == 0xFF:
        if raw_bytes[1] == 0xFE:
            print("Detected: UTF-16 LE with BOM")
            # Skip BOM and decode
            text = raw_bytes[2:].decode('utf-16-le')
        else:
            print("File starts with 0xFF - attempting various decodings")
            # Try skipping first byte
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text = raw_bytes[1:].decode(encoding)
                    print(f"Successfully decoded by skipping first byte and using {encoding}")
                    break
                except:
                    continue
            else:
                # If all else fails, replace problematic bytes
                text = raw_bytes.decode('latin-1', errors='replace')
                print("Decoded with latin-1 and error replacement")
    else:
        # Standard decoding
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'utf-16']:
            try:
                text = raw_bytes.decode(encoding)
                print(f"Successfully decoded with {encoding}")
                break
            except:
                continue
    
    # Parse the content
    lines = text.strip().split('\n')
    
    # Clean CSV output
    output_lines = ['Volume_ml,UV_mAU,Conductivity_mS_cm,Conc_B_percent,Injection,Run_Log,Fraction,UV_Baseline_mAU']
    
    # Skip header lines and process data
    for i, line in enumerate(lines[3:], start=3):
        cells = line.strip().split('\t')
        
        if len(cells) >= 14:
            try:
                # Parse with safe defaults
                volume = float(cells[0]) if cells[0].strip() else 0
                uv = float(cells[1]) if cells[1].strip() else 0
                cond = float(cells[3]) if cells[3].strip() else 0
                conc = float(cells[5]) if cells[5].strip() else 0
                
                # String fields
                injection = cells[7].strip('"') if len(cells) > 7 else ''
                run_log = cells[9].strip('"') if len(cells) > 9 else ''
                fraction = cells[11].strip('"') if len(cells) > 11 else ''
                
                # Baseline
                baseline = float(cells[13]) if len(cells) > 13 and cells[13].strip() else 0
                
                # Create CSV line
                csv_line = f"{volume},{uv},{cond},{conc},{injection},{run_log},{fraction},{baseline}"
                output_lines.append(csv_line)
                
            except ValueError as e:
                print(f"Skipping line {i}: {e}")
                continue
    
    print(f"\nProcessed {len(output_lines)-1} data rows")
    
    # Create DataFrame
    df = pd.read_csv(pd.io.common.StringIO('\n'.join(output_lines)))
    
    return df, output_lines

# Usage example
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python read_sec.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    try:
        df, csv_lines = read_sec_file_robust(file_path)
        
        # Save clean CSV
        output_path = file_path.rsplit('.', 1)[0] + '_clean.csv'
        with open(output_path, 'w') as f:
            f.write('\n'.join(csv_lines))
        
        print(f"\nClean CSV saved to: {output_path}")
        print("\nData summary:")
        print(df.describe())
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
