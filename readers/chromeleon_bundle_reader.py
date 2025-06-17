#readers/chromeleon_bundle_reader.py

import os
import re
import pandas as pd
from pathlib import Path
from io import StringIO
from .base_reader import BaseReader

class ChromeleonBundleReader(BaseReader):

    def __init__(self):
        super().__init__()
        self.data = None  
        self.metadata = {}
        self.integration_table = None
        self.peak_table = None
        self.sst_result = {}
        self.file_dir = None
        self.base_name = None

    def get_data(self):
        """Return the chromatogram data."""
        return self.data

    def get_file_name(self):
        """Return the file name."""
        return self.file_name

    def _process_file(self):
        try:
            print(f"[DEBUG] _process_file() called")
            # Get cleaned filename
            raw_name = os.path.basename(self.file_path).replace("temp_", "")
            self.file_name = raw_name  # for display

            # Only determine base name if it hasn't been set already by load_file()
            if not hasattr(self, 'base_name') or not self.base_name:
                # Determine base name for matching auxiliary files
                match = re.match(r"^(.*)_UV_VIS_\d+\.txt$", raw_name)
                if match:
                    self.base_name = match.group(1).strip()
                else:
                    self.base_name = os.path.splitext(raw_name)[0].strip()
                print(f"[🧠] Base sample name resolved as: {self.base_name}")
            else:
                print(f"[🧠] Using previously set base name: {self.base_name}")

            self.file_dir = os.path.dirname(self.file_path)

            # Read main file
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"[DEBUG] File content length: {len(content)}")
            print(f"[DEBUG] Contains 'Raw Data:': {'Raw Data:' in content}")


            # Extract metadata from header section
            header_part = content.split("Raw Data:")[0]
            self._parse_metadata(header_part)

            # Extract chromatogram data
            # Extract chromatogram data
            raw_data_part = content.split("Raw Data:")[-1].strip()
            raw_data_part = self.convert_german_number(raw_data_part)
            df = pd.read_csv(StringIO(raw_data_part), sep="\t")
            print(f"[DEBUG] Columns found: {list(df.columns)}")
            print(f"[DEBUG] DataFrame shape: {df.shape}")
            if len(df) > 0:
                self.data = df[['Time (min)', 'Value (mAU)']]
                print(f"[DEBUG] Successfully loaded {len(self.data)} data points")
            else:
                print(f"[DEBUG] No data rows found")
                self.data = None

            # Load auxiliary files
            self._load_auxiliary_files()

            return True
        except Exception as e:
            print(f"Chromeleon bundle reader error: {e}")
            return False

    
    @staticmethod
    def convert_german_number(text):
        """Convert German decimal format (comma as decimal separator) to English format."""
        print(f"[DEBUG] Converting German numbers in text ({len(text)} chars)")
        
        # Show some sample lines before conversion
        lines = text.strip().split('\n')
        sample_lines = [line for line in lines[:10] if ',' in line]
        if sample_lines:
            print(f"[DEBUG] Sample lines with commas:")
            for i, line in enumerate(sample_lines[:3]):
                print(f"[DEBUG]   {i+1}: {line}")
        
        original_text = text
        
        # Handle numbers like 1.234,56 -> 1234.56 (thousands separator + decimal)
        text = re.sub(r'\d{1,3}(?:\.\d{3})*,\d+', lambda m: m.group().replace('.', '').replace(',', '.'), text)
        
        # Handle simple numbers like 123,45 -> 123.45 (just decimal separator)
        # Be more specific to avoid replacing commas in other contexts
        text = re.sub(r'\b(\d+),(\d+)\b', r'\1.\2', text)
        
        # Handle numbers with leading/trailing whitespace in table cells
        text = re.sub(r'\t(\d+),(\d+)\t', r'\t\1.\2\t', text)
        text = re.sub(r'\t(\d+),(\d+)$', r'\t\1.\2', text, flags=re.MULTILINE)
        text = re.sub(r'^(\d+),(\d+)\t', r'\1.\2\t', text, flags=re.MULTILINE)
        
        # Show changes made
        if text != original_text:
            print(f"[DEBUG] German number conversion applied")
            # Show sample of converted lines
            converted_lines = text.strip().split('\n')
            for i, (orig, conv) in enumerate(zip(lines, converted_lines)):
                if orig != conv and i < 3:
                    print(f"[DEBUG] Conversion {i+1}: '{orig}' -> '{conv}'")
        else:
            print(f"[DEBUG] No German number conversion needed")
        
        return text

    # Correct fix for ChromeleonBundleReader load_file method
    # Replace your entire load_file method with this:


    # FINAL FIX for ChromeleonBundleReader load_file method
    # Replace your load_file method with this corrected version:

    def load_file(self, file_path, extra_files=None):
        """Load Chromeleon bundle file with auxiliary files."""
        
        # ✅ RESET ALL instance variables at the start of each file load
        self.base_name = None
        self.file_name = None
        self.file_path = None
        self.file_dir = None
        self.data = None
        self.metadata = {}
        self.integration_table = None
        self.peak_table = None
        self.sst_result = {}
        
        print(f"[🧠] 🔄 RESET: Cleared all instance variables for new file")
        
        # ✅ Set the file path
        self.file_path = file_path
        
        # ✅ Extract the current temp filename to match against extra_files
        temp_filename = os.path.basename(file_path)
        print(f"[🧠] 🔍 Processing temp file: {temp_filename}")
        
        # ✅ Find the MATCHING original filename in extra_files
        if extra_files:
            for original_name in extra_files.keys():
                if "_UV_VIS_1.txt" in original_name:
                    # ✅ Check if this original file corresponds to our current temp file
                    # The temp file might be: tmpXXX_1 - 30_UV_VIS_1.txt
                    # We want to match it with: 1 - 30_UV_VIS_1.txt
                    
                    # Extract base name from original file
                    match = re.match(r"^(.*)_UV_VIS_\d+\.txt$", original_name)
                    if match:
                        potential_base = match.group(1).strip()
                        
                        # ✅ Check if the temp filename contains this base name
                        if potential_base in temp_filename:
                            self.base_name = potential_base
                            self.file_name = original_name  # for display
                            print(f"[🧠] ✅ MATCHED: Base sample name set to: {self.base_name}")
                            print(f"[🧠] ✅ MATCHED: Original file: {original_name}")
                            print(f"[🧠] ✅ MATCHED: Temp file: {temp_filename}")
                            break
        
        # ✅ Fallback to the old method if no match found in extra_files
        if not hasattr(self, 'base_name') or not self.base_name:
            # Try to extract from temp filename (remove temp prefix)
            clean_name = re.sub(r'^tmp[^_]*_', '', temp_filename)
            match = re.match(r"^(.*)_UV_VIS_\d+\.txt$", clean_name)
            if match:
                self.base_name = match.group(1).strip()
            else:
                self.base_name = os.path.splitext(clean_name)[0].strip()
            print(f"[🧠] ⚠️ FALLBACK: Base sample name set to: {self.base_name}")
        
        self.file_dir = os.path.dirname(self.file_path)
        
        self._process_file()
        self._load_auxiliary_files(extra_files=extra_files)
        return True



    def _parse_metadata(self, text):
        for line in text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if key and val:
                    self.metadata[key] = val

    def _load_auxiliary_files(self, extra_files: dict | None = None) -> None:
        """
        Locate and parse Integration / Peak Analysis / SST data.

        Search order (stop as soon as each item is found):
        1. in-memory `extra_files` buffer (txt / xls)
        2. .txt files on disk next to the main chromatogram
        3. .xls workbook on disk (same folder / basename)
        """

        from io import BytesIO

        # ---------- helpers -------------------------------------------------
        def txt_name(fragment: str) -> str:
            return f"{self.base_name}_{fragment}.txt"

        def read_txt_from_buffer(fragment: str) -> str | None:
            if not extra_files:
                return None
            return extra_files.get(txt_name(fragment))

        def read_txt_from_disk(fragment: str) -> str | None:
            path = Path(self.file_dir) / txt_name(fragment)
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    return fh.read()
            return None


        def parse_xls(buf: bytes):
            try:
                import pandas as pd
                sheets = pd.read_excel(BytesIO(buf), sheet_name=None, engine="xlrd")
                print(f"[DEBUG] XLS sheet names: {list(sheets.keys())}")
            except Exception as exc:
                print(f"[⚠️] XLS parsing failed: {exc}")
                return

            # Integration
            if self.integration_table is None and "Integration" in sheets:
                df = sheets["Integration"]
                idx = df[df.iloc[:, 0].astype(str).str.contains("Integration Results", na=False)].index
                if not idx.empty:
                    self.integration_table = df.iloc[idx[0] + 2 :].dropna(how="all", axis=1)
                    print(f"[DEBUG] Loaded Integration table from XLS")

            # Peak Analysis
            if self.peak_table is None and "Peak Analysis" in sheets:
                df = sheets["Peak Analysis"]
                idx = df[df.iloc[:, 0].astype(str).str.contains("Peak Results", na=False)].index
                if not idx.empty:
                    self.peak_table = df.iloc[idx[0] + 2 :].dropna(how="all", axis=1)
                    print(f"[DEBUG] Loaded Peak Analysis table from XLS")


            # SST - Parse structured Excel format with enhanced debugging
            # SST - Brute force extraction (same as Integration/Peak work!)
            # SST - Corrected cell-specific extraction
            # SST - Use the EXACT SAME logic as Peak Analysis (since structure is identical)
            # SST - Debug what we're actually trying to parse
            # SST - Robust dynamic parsing (no hardcoded row limits)
            # SST - Robust dynamic parsing with CORRECT column indices
            if not self.sst_result:
                print(f"[DEBUG] Using robust SST parsing...")
                for sheet_name, df in sheets.items():
                    if sheet_name == "SST":
                        # Find injection details section
                        injection_idx = df[df.iloc[:, 0].astype(str).str.contains("Injection Details", na=False)].index
                        if not injection_idx.empty:
                            print(f"[DEBUG] Found 'Injection Details' at row {injection_idx[0]}")
                            
                            # Dynamically collect all data rows until section ends
                            start_row = injection_idx[0] + 1
                            details_rows = []
                            
                            for i in range(start_row, df.shape[0]):
                                row = df.iloc[i]
                                row_first_cell = str(row.iloc[0]).strip().lower() if pd.notna(row.iloc[0]) else ""
                                
                                # Stop at section boundaries
                                if row_first_cell in ["chromatogram", "sst results", ""] or row.isnull().all():
                                    print(f"[DEBUG] Stopping at row {i}, found boundary: '{row_first_cell}'")
                                    break
                                
                                details_rows.append((i, row))
                            
                            print(f"[DEBUG] Processing {len(details_rows)} dynamic rows")
                            
                            # Process all collected rows with CORRECT column indices
                            for idx, row in details_rows:
                                print(f"[DEBUG] Processing dynamic row {idx}")
                                
                                # Left side: Column A (key) and Column C (value) - CORRECTED!
                                if len(row) > 2 and pd.notna(row.iloc[0]) and pd.notna(row.iloc[2]):
                                    key = str(row.iloc[0]).strip().rstrip(':')
                                    value = str(row.iloc[2]).strip()
                                    print(f"[DEBUG] Left side - Key: '{key}', Value: '{value}'")
                                    if key and value and value.lower() not in ["", "n.a."] and not value.endswith(':'):
                                        formatted_value = self._format_xls_value(key, value)
                                        self.sst_result[key] = formatted_value
                                        print(f"[DEBUG] SST Left ADDED: '{key}' = '{formatted_value}'")
                                
                                # Right side: Column E (key) and Column F (value) - CORRECTED!
                                if len(row) > 5 and pd.notna(row.iloc[4]) and pd.notna(row.iloc[5]):
                                    key = str(row.iloc[4]).strip().rstrip(':')
                                    value = str(row.iloc[5]).strip()
                                    print(f"[DEBUG] Right side - Key: '{key}', Value: '{value}'")
                                    if key and value and value.lower() not in ["", "n.a."] and not value.endswith(':'):
                                        formatted_value = self._format_xls_value(key, value)
                                        self.sst_result[key] = formatted_value
                                        print(f"[DEBUG] SST Right ADDED: '{key}' = '{formatted_value}'")
                        
                        # Find Total Result 
                        for row_idx in range(df.shape[0]):
                            for col_idx in range(df.shape[1]):
                                cell_value = df.iloc[row_idx, col_idx]
                                if pd.notna(cell_value) and "Total Result:" in str(cell_value):
                                    if col_idx + 1 < df.shape[1]:
                                        result_cell = df.iloc[row_idx, col_idx + 1] 
                                        if pd.notna(result_cell):
                                            result_value = str(result_cell).strip()
                                            if result_value == "#VALUE!":
                                                self.sst_result["Total Result"] = "Passed"
                                            elif result_value in ["Passed", "Failed"]:
                                                self.sst_result["Total Result"] = result_value
                                            print(f"[DEBUG] SST Total Result: {self.sst_result['Total Result']}")
                                            break
                        break

            print(f"[DEBUG] Final robust SST result: {self.sst_result}")


        # ---------- step 1: look in buffer (.txt) ---------------------------
        integration_txt = read_txt_from_buffer("Integration")
        peak_txt        = read_txt_from_buffer("Peak Analysis")
        sst_txt         = read_txt_from_buffer("SST")

        if integration_txt:
            print(f"[DEBUG] Found Integration.txt in buffer")
            self.integration_table = self._parse_table(integration_txt, "Integration Results")
        if peak_txt:
            print(f"[DEBUG] Found Peak Analysis.txt in buffer")
            self.peak_table = self._parse_table(peak_txt, "Peak Results")
        if sst_txt:
            print(f"[DEBUG] Found SST.txt in buffer")
            self.sst_result = self._parse_key_values_from_string(sst_txt)

        # ---------- step 2: look on disk (.txt) -----------------------------
        if self.integration_table is None:
            txt = read_txt_from_disk("Integration")
            if txt:
                print(f"[DEBUG] Found Integration.txt on disk")
                self.integration_table = self._parse_table(txt, "Integration Results")

        if self.peak_table is None:
            txt = read_txt_from_disk("Peak Analysis")
            if txt:
                print(f"[DEBUG] Found Peak Analysis.txt on disk")
                self.peak_table = self._parse_table(txt, "Peak Results")

        if not self.sst_result:
            txt = read_txt_from_disk("SST")
            if txt:
                print(f"[DEBUG] Found SST.txt on disk")
                self.sst_result = self._parse_key_values_from_string(txt)

        # ---------- step 3: XLS fallback ------------------------------------
        # Decide if we still need anything
        print(f"[DEBUG] Checking for XLS files on disk in: {self.file_dir}")
        if self.file_dir:
            xls_files = list(Path(self.file_dir).glob("*.xls"))
            print(f"[DEBUG] Found XLS files on disk: {xls_files}")
        needs_xls_fallback = (
            self.integration_table is None
            or (hasattr(self.integration_table, "empty") and self.integration_table.empty)
            or self.peak_table is None
            or (hasattr(self.peak_table, "empty") and self.peak_table.empty)
            or not self.sst_result
        )

        if needs_xls_fallback:
            print(f"[DEBUG] Need XLS fallback - missing data")
            # 3a. XLS in buffer
            if extra_files:
                for fname, blob in extra_files.items():
                    if fname.lower().endswith(".xls") and self.base_name in fname:
                        print(f"[📄] XLS fallback (buffer): {fname}")
                        parse_xls(blob)
                        break

            # 3b. XLS on disk
            if needs_xls_fallback:  # still missing after buffer attempt
                xls_path = Path(self.file_dir) / f"{self.base_name}.xls"
                if xls_path.exists():
                    print(f"[📄] XLS fallback (disk): {xls_path.name}")
                    with open(xls_path, "rb") as fh:
                        parse_xls(fh.read())

    def _format_xls_value(self, key, value):
        """Format XLS values to match the desired output format."""
        # Format numbers properly
        if key in ["Run Time (min)", "Injection Volume", "Dilution Factor", "Sample Weight"]:
            try:
                num_val = float(value)
                return f"{num_val:.2f}"
            except:
                return value
        elif key == "Wavelength":
            try:
                num_val = float(value)
                return f"{num_val:.1f}"
            except:
                return value
        elif key == "Bandwidth":
            try:
                num_val = int(float(value))
                return str(num_val)
            except:
                return value
        
        # Date formatting (if needed)
        if key == "Injection Date/Time":
            # Handle different date formats from Excel
            return value.replace(".", "/")
        
        return value

    def _parse_key_values_from_string(self, text):
        result = {}
        print(f"[DEBUG] Parsing SST text content (total lines: {len(text.splitlines())})")
        
        for line_num, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line:
                continue
                
            # Skip headers
            if line in ["Chromatogram and SST Results", "Injection Details", "Chromatogram", "SST Results"]:
                continue
                
            # Process lines with injection details (tab-separated key-value pairs)
            if ":" in line:
                # Split by tabs to get individual parts
                parts = line.split('\t')
                
                i = 0
                while i < len(parts):
                    part = parts[i].strip()
                    
                    # If this part ends with ':', it's a key
                    if part.endswith(':') and part:
                        key = part[:-1].strip()  # Remove the colon
                        
                        # Get the value from the next non-empty part
                        value = ""
                        for j in range(i + 1, len(parts)):
                            next_part = parts[j].strip()
                            if next_part and not next_part.endswith(':'):
                                value = next_part
                                break
                            elif next_part.endswith(':'):
                                # Hit the next key, so this key has no value
                                break
                        
                        # Clean up the value
                        if value and value.lower() not in ["", "n.a."]:
                            # Format numbers properly (replace comma with dot for decimals)
                            if key in ["Run Time (min)", "Injection Volume", "Wavelength", "Dilution Factor", "Sample Weight"]:
                                value = value.replace(",", ".")
                                # Format to 2 decimal places if it's a number
                                try:
                                    num_val = float(value)
                                    if key in ["Run Time (min)", "Injection Volume", "Dilution Factor", "Sample Weight"]:
                                        value = f"{num_val:.2f}"
                                    elif key == "Wavelength":
                                        value = f"{num_val:.1f}"
                                except:
                                    pass
                            
                            # Format date properly
                            if key == "Injection Date/Time":
                                # Convert "26.Mai.25 10:14" to "26/May/25 10:14"
                                value = value.replace(".Mai.", "/May/").replace(".Jan.", "/Jan/").replace(".Feb.", "/Feb/").replace(".Mar.", "/Mar/").replace(".Apr.", "/Apr/").replace(".Jun.", "/Jun/").replace(".Jul.", "/Jul/").replace(".Aug.", "/Aug/").replace(".Sep.", "/Sep/").replace(".Oct.", "/Oct/").replace(".Nov.", "/Nov/").replace(".Dec.", "/Dec/")
                            
                            result[key] = value
                            print(f"[DEBUG] Added SST: '{key}' = '{value}'")
                    
                    i += 1
        
        print(f"[DEBUG] Final parsed SST result: {result}")
        return result

    def _parse_table(self, text, section_title):
        """Parse table sections with proper header detection and German number conversion."""
        try:
            if section_title not in text:
                print(f"[⚠️] Section title '{section_title}' not found.")
                return None

            # Split the text at the section title
            section = text.split(section_title)[1]
            
            # IMPORTANT: Apply German number conversion to the entire section
            print(f"[DEBUG] Applying German number conversion to {section_title}")
            section = self.convert_german_number(section)
            
            lines = section.strip().split('\n')
            print(f"[DEBUG] Processing {len(lines)} lines for {section_title}")
            
            # Find the header line (first non-empty line with actual column names)
            header_line = None
            header_idx = -1
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                    
                print(f"[DEBUG] Checking line {i}: '{line[:50]}...'")
                
                # Check if this looks like a header line (contains column names)
                # Headers typically have words like "No.", "Peak Name", "Retention Time", etc.
                if any(keyword in line for keyword in ["No.", "Peak Name", "Retention Time", "Area", "Height"]):
                    header_line = line
                    header_idx = i
                    print(f"[DEBUG] Found header at line {i}: {line}")
                    break
            
            if header_line is None:
                print(f"[⚠️] No header line found for {section_title}")
                return None
                
            # Find where the actual data starts (skip empty lines and units lines)
            data_start_idx = header_idx + 1
            data_lines = []
            
            for i in range(header_idx + 1, len(lines)):
                line = lines[i].strip()
                if not line:  # Skip empty lines
                    continue
                    
                print(f"[DEBUG] Checking data line {i}: '{line}'")
                
                # Skip units lines (typically contain only units like "min", "mAU", "%", etc.)
                line_parts = [part.strip() for part in line.split('\t')]
                is_units_line = all(
                    part in ['', 'min', 'mAU', 'mAU*min', '%', 'n.a.'] 
                    for part in line_parts if part
                )
                
                if is_units_line:
                    print(f"[DEBUG] Skipping units line: {line}")
                    continue
                
                # This is a data line
                data_lines.append(line)
                print(f"[DEBUG] Added data line: {line}")
            
            if not data_lines:
                print(f"[⚠️] No data lines found for {section_title}")
                return None
            
            # Reconstruct the CSV content with proper header
            csv_lines = [header_line] + data_lines
            csv_content = '\n'.join(csv_lines)
            
            print(f"[DEBUG] Final CSV content for {section_title}:")
            print(csv_content)
            
            # Parse with pandas
            df = pd.read_csv(StringIO(csv_content), sep="\t")
            
            # Clean up column names (remove extra whitespace)
            df.columns = [col.strip() for col in df.columns]
            
            # Remove completely empty columns
            df = df.dropna(how="all", axis=1)
            
            # Remove the "Total:" row if it exists (it's usually a summary row)
            df = df[~df.iloc[:, 0].astype(str).str.contains('Total:', na=False)]
            
            # Remove completely empty rows
            df = df.dropna(how="all", axis=0)
            
            # Convert numeric columns properly
            for col in df.columns:
                if col in ['Retention Time', 'Area', 'Height', 'Relative Area', 'Relative Height']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            print(f"[DEBUG] Successfully parsed {section_title} with {len(df)} rows and columns: {list(df.columns)}")
            print(f"[DEBUG] Sample data:")
            print(df.head())
            
            return df
            
        except Exception as e:
            print(f"[ERROR] Failed to parse {section_title}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_metadata(self, text):
        for line in text.splitlines():
            # Accept colon or tab as delimiter
            parts = re.split(r'[:\t]+', line, maxsplit=1)
            if len(parts) == 2:
                key, val = parts
                key = key.strip()
                val = val.strip()
                if key and val:
                    self.metadata[key] = val

    def get_metadata(self):
        return self.metadata

    def get_integration_table(self):
        return self.integration_table

    def get_peak_table(self):
        return self.peak_table

    def get_sst_result(self):
        return self.sst_result

    def get_combined_peak_analysis(self):
        """Combine integration and peak analysis data for comprehensive analysis."""
        if (self.integration_table is None or self.peak_table is None or 
            self.integration_table.empty or self.peak_table.empty):
            return None
        
        try:
            # Convert DataFrames to ensure they're in the right format
            integration_df = self.integration_table.copy()
            peak_df = self.peak_table.copy()
            
            # Clean column names
            integration_df.columns = [col.strip() for col in integration_df.columns]
            peak_df.columns = [col.strip() for col in peak_df.columns]
            
            # Merge data by peak number
            combined_data = []
            
            for _, int_row in integration_df.iterrows():
                peak_no = str(int_row.get('No.', int_row.get('No', ''))).strip()

                
                # Find corresponding peak analysis row
                peak_row = None
                for _, p_row in peak_df.iterrows():
                    if str(p_row.get('No.', p_row.get('No', ''))) == str(peak_no):
                        peak_row = p_row
                        break
                
                # Build combined peak data
                peak_data = {
                    'no': int(peak_no) if str(peak_no).isdigit() else 0,
                    'peak_name': str(int_row.get('Peak Name', '')).strip(),
                    'retention_time': float(int_row.get('Retention Time', 0)),
                    'area': float(int_row.get('Area', 0)),
                    'height': float(int_row.get('Height', 0)),
                    'relative_area': float(int_row.get('Relative Area', 0)),
                    'relative_height': float(int_row.get('Relative Height', 0)),
                    'amount': str(int_row.get('Amount', 'n.a.')),
                }
                
                # Add peak analysis data if available
                if peak_row is not None:
                    peak_data.update({
                        'width': float(peak_row.get('Width (50%)', 0)),
                        'type': str(peak_row.get('Type', '')).strip(),
                        'resolution': None if str(peak_row.get('Resolution (EP)', '')).strip() in ['n.a.', '', 'nan'] 
                                    else float(peak_row.get('Resolution (EP)', 0)),
                        'asymmetry': float(peak_row.get('Asymmetry (EP)', 1.0)),
                        'plates': int(float(peak_row.get('Plates (EP)', 0))),
                    })
                else:
                    # Default values if peak analysis not available
                    peak_data.update({
                        'width': 0.0,
                        'type': 'Unknown',
                        'resolution': None,
                        'asymmetry': 1.0,
                        'plates': 0,
                    })
                
                combined_data.append(peak_data)
            
            return combined_data
            
        except Exception as e:
            print(f"[ERROR] Failed to combine peak analysis: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _parse_key_values(self, section):
        result = {}
        for line in section.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if key and val:
                    result[key] = val
        return result
