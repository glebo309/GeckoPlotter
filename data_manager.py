# File: data_manager.py (UPDATED)
import os
import tempfile
import uuid
import pandas as pd
from readers.chromatogram_reader import ChromatogramReader
from readers.spectra_reader import SpectraReader
from readers.uvvis_csv_reader import UVVISCSVReader
print("[DEBUG] ✔️ Imported UVVISCSVReader:", UVVISCSVReader)

from readers.chromeleon_bundle_reader import ChromeleonBundleReader
from readers.lcms_cdf_reader import LCMSCDFReader
from readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader
import re
from typing import Any


class DataManager:
    """Manages different types of scientific data readers."""
    
    def __init__(self):
        self.readers = {
            'chromatogram': ChromatogramReader,
            'chromeleon_bundle': ChromeleonBundleReader,
            'spectra': SpectraReader,
            'uvvis_csv': UVVISCSVReader,
            'lcms_cdf': LCMSCDFReader,
            'lcms_vwd_cdf': LCMSVWDCDFReader
        }
        self.loaded_data = {}
        self.temp_files = []  # Track temp files for cleanup
        self.lcms_bundles = {}  # Track LC-MS bundles being built
    
    def detect_file_type(self, content, filename):
        print(f"[DEBUG] 🔍 detect_file_type called for: {filename}")
        
        # Handle binary content (CDF files)
        if isinstance(content, bytes):
            print(f"[DEBUG] 🔍 Binary content detected ({len(content)} bytes)")
            
            if filename.lower().endswith('.cdf'):
                print(f"[DEBUG] 🔍 CDF file detected by extension")
                
                # Check if it's a VWD (UV) file
                filename_lower = filename.lower()
                if 'vwd' in filename_lower:
                    print(f"[DEBUG] 💡 VWD (UV chromatogram) CDF detected")
                    print(f"[DEBUG] ✅ Detected as lcms_vwd_cdf")
                    return 'lcms_vwd_cdf'
                
                # Otherwise it's MS data
                # Try to detect ionization mode from filename
                if any(term in filename_lower for term in ['pos', 'positive', '+', 'esi+']):
                    print(f"[DEBUG] 💡 Possible POSITIVE mode CDF detected from filename")
                elif any(term in filename_lower for term in ['neg', 'negative', '-', 'esi-']):
                    print(f"[DEBUG] 💡 Possible NEGATIVE mode CDF detected from filename")
                
                print(f"[DEBUG] ✅ Detected as lcms_cdf")
                return 'lcms_cdf'
            
            # Could add other binary file types here in the future
            print(f"[DEBUG] ❌ Unknown binary file type")
            return None
        
        # Skip auxiliary Chromeleon files - they're handled by the bundle reader
        aux_patterns = ['_SST.txt', '_Chromatogram.txt', '_Integration.txt', '_Peak Analysis.txt']
        if any(pattern in filename for pattern in aux_patterns):
            print(f"[DEBUG] 🔍 Skipping auxiliary Chromeleon file: {filename}")
            return None
        
        # Handle text content (existing logic)
        if "Raw Data:" in content and "WVL:" in content:
            if "UV_VIS_1" in filename:
                print(f"[DEBUG] ✅ Detected as chromeleon_bundle")
                return 'chromeleon_bundle'
            print(f"[DEBUG] ✅ Detected as chromatogram")
            return 'chromatogram'
        elif "Spectral Data:" in content:
            print(f"[DEBUG] ✅ Detected as spectra")
            return 'spectra'
        elif filename.lower().endswith('.csv'):
            print(f"[DEBUG] 🔍 CSV file detected, checking content...")
            
            content_lower = content.lower()
            
            # Check for Synergy/BioTek specific indicators (UV-Vis)
            synergy_indicators = [
                "synergy h1", "synergy", "biotek", "reader type:", 
                "absorbance spectrum", "reader serial number:",
                "96 well plate", "plate type:"
            ]
            
            # Check for plate reader structure indicators
            structure_indicators = [
                "wavelength", "software version:", "experiment file path:",
                "protocol file path:", "plate number:", "reading type:"
            ]
            
            # Check all indicators
            all_indicators = synergy_indicators + structure_indicators
            found_indicators = [indicator for indicator in all_indicators if indicator in content_lower]
            print(f"[DEBUG] 🔍 Found indicators: {found_indicators}")
            
            # Also check if file has the characteristic CSV structure with lots of commas
            # (Synergy files have many empty columns filled with commas)
            lines = content.split('\n')[:25]  # Check first 25 lines (to get past metadata)
            has_comma_structure = False
            has_wavelength_header = False
            
            for i, line in enumerate(lines):
                # Check for typical Synergy comma-heavy structure
                if line.count(',') > 50:  # Synergy files have ~96+ commas per line
                    has_comma_structure = True
                    print(f"[DEBUG] 🔍 Found comma-heavy structure at line {i} ({line.count(',')} commas)")
                
                # Check for wavelength header (might be deep in the file)
                if 'wavelength' in line.lower():
                    has_wavelength_header = True
                    print(f"[DEBUG] 🔍 Found 'Wavelength' header at line {i}")
            
            # Classify as uvvis_csv if we have enough indicators
            is_uvvis = (
                len(found_indicators) >= 2 or  # At least 2 indicators
                has_wavelength_header or       # Has wavelength column
                (has_comma_structure and len(found_indicators) >= 1)  # Comma structure + 1 indicator
            )
            
            if is_uvvis:
                print(f"[DEBUG] ✅ Detected as uvvis_csv")
                print(f"[DEBUG]    - Indicators: {len(found_indicators)}")
                print(f"[DEBUG]    - Wavelength header: {has_wavelength_header}")
                print(f"[DEBUG]    - Comma structure: {has_comma_structure}")
                return 'uvvis_csv'
            else:
                print(f"[DEBUG] ❌ CSV file but no UV-Vis indicators found")
                print(f"[DEBUG]    - Indicators: {len(found_indicators)}")
                print(f"[DEBUG]    - Wavelength header: {has_wavelength_header}")
                print(f"[DEBUG]    - Comma structure: {has_comma_structure}")
        
        print(f"[DEBUG] ❌ No file type detected for: {filename}")
        return None



    @staticmethod
    def extract_lcms_base_name(filename, return_tag=False):
        """Extract base name from LCMS CDF filenames - everything before the detector/mode part"""
        base = os.path.splitext(os.path.basename(filename))[0]
        
        # Remove common LCMS-specific suffixes to get the true base name
        patterns_to_remove = [
            r'_MS1\s*[+-]TIC.*$',  # Remove _MS1 +TIC SCAN ESI Frag=135V Gain=1-0_spectra
            r'_VWD1[AB]$',         # Remove _VWD1A or _VWD1B
            r'_MS\d*.*$',          # Remove _MS1, _MS2, etc with anything after
            r'_[+-]$',             # Remove trailing + or -
            r'_pos(itive)?$',      # Remove _pos or _positive
            r'_neg(ative)?$',      # Remove _neg or _negative
        ]
        
        polarity_tag = None
        
        # Detect polarity before removing patterns
        if re.search(r'[+]|positive', base, re.IGNORECASE):
            polarity_tag = "ms_positive"
        elif re.search(r'[-]|negative', base, re.IGNORECASE):
            polarity_tag = "ms_negative"
        
        # Remove all the patterns
        for pattern in patterns_to_remove:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        
        # Clean up any trailing underscores or spaces
        base = base.rstrip('_- ')
        
        if return_tag:
            return base, polarity_tag
        return base


    def should_bundle_lcms(self, filename):
        """Check if this file should be part of an LC-MS bundle"""
        # Check if it's an LC-MS related file
        if filename.lower().endswith('.cdf'):
            # Check for LC-MS patterns in filename
            lcms_patterns = ['lcms', 'lc-ms', 'vwd', '_ms']
            return any(pattern in filename.lower() for pattern in lcms_patterns)
        return False

    def load_file(self, filename, content, extra_files=None):
        """Load a file using the appropriate reader."""

        print(f"[DEBUG] 🔍 Loading file: {filename}")
        content_type = "binary" if isinstance(content, bytes) else "text"
        content_length = len(content)
        print(f"[DEBUG] 🔍 Content type: {content_type}, length: {content_length}")

        if isinstance(content, str):
            print(f"[DEBUG] 🔍 First 200 chars: {repr(content[:200])}")
        else:
            print(f"[DEBUG] 🔍 Binary content: {len(content)} bytes")

        file_type = self.detect_file_type(content, filename)
        print(f"[DEBUG] 🔍 Detected file type: {file_type}")

        if file_type and file_type in self.readers:
            reader = self.readers[file_type]()
            temp_fd, temp_path = tempfile.mkstemp(suffix=f"_{filename}", prefix="temp_")
            self.temp_files.append(temp_path)

            try:
                # Write content to temp file
                if isinstance(content, bytes):
                    with os.fdopen(temp_fd, 'wb') as f:
                        f.write(content)
                else:
                    with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                        f.write(content)

                # Load the file using the reader
                success = reader.load_file(temp_path, extra_files=extra_files) if extra_files else reader.load_file(temp_path)

                if not success:
                    print(f"[DEBUG] ❌ Reader failed to process file")
                    return False, f"Failed to process {filename}"

                data = reader.get_data()
                metadata = self._extract_metadata(reader, file_type)
                print(f"[DEBUG] 📈 Data shape: {data.shape if data is not None else 'None'}")
                print(f"[DEBUG] 📋 Metadata keys: {list(metadata.keys())}")

                # Store normally (non-LCMS files)

                # === LCMS Files: Bundle by base name ===
                if file_type in ['lcms_cdf', 'lcms_vwd_cdf']:
                    base_name = self.extract_lcms_base_name(filename)
                    print(f"[DEBUG] 📦 LC-MS file detected, base name: {base_name}")
                    
                    # Initialize bundle if needed
                    if base_name not in self.lcms_bundles:
                        self.lcms_bundles[base_name] = {
                            'ms_positive': None,
                            'ms_negative': None,
                            'vwd_a': None,
                            'vwd_b': None,
                            'files': []
                        }
                    
                    bundle = self.lcms_bundles[base_name]
                    if filename not in bundle['files']:
                        bundle['files'].append(filename)
                    
                    # Store component in bundle
                    if file_type == 'lcms_cdf':
                        # MS data - use ionization mode
                        mode = metadata.get('ionization_mode', 'unknown')
                        if mode == 'positive':
                            bundle['ms_positive'] = {'filename': filename, 'reader': reader, 'data': data, 'metadata': metadata}
                            print(f"[DEBUG] 📦 Added MS+ component to {base_name}")
                        elif mode == 'negative':
                            bundle['ms_negative'] = {'filename': filename, 'reader': reader, 'data': data, 'metadata': metadata}
                            print(f"[DEBUG] 📦 Added MS- component to {base_name}")
                    
                    elif file_type == 'lcms_vwd_cdf':
                        # VWD data - use channel
                        channel = metadata.get('detector_channel', 'Unknown')
                        if channel == 'A':
                            bundle['vwd_a'] = {'filename': filename, 'reader': reader, 'data': data, 'metadata': metadata}
                            print(f"[DEBUG] 📦 Added VWD-A component to {base_name}")
                        elif channel == 'B':
                            bundle['vwd_b'] = {'filename': filename, 'reader': reader, 'data': data, 'metadata': metadata}
                            print(f"[DEBUG] 📦 Added VWD-B component to {base_name}")
                    
                    # Update bundle in loaded_data
                    bundle_key = f"{base_name}_LCMS_BUNDLE"
                    bundle_metadata = self._create_bundle_metadata(base_name, bundle)
                    self.loaded_data[bundle_key] = {
                        "type": "lcms_bundle",
                        "bundle_data": bundle,
                        "metadata": bundle_metadata
                    }
                    
                    print(f"[DEBUG] 📦 Bundle '{bundle_key}' updated. Components: {[k for k in ['ms_positive', 'ms_negative', 'vwd_a', 'vwd_b'] if bundle[k] is not None]}")
                    return True, f"Added {filename} to LC-MS bundle {base_name}"

                # Store normally (non-LCMS files)
                self.loaded_data[filename] = {
                    'reader': reader,
                    'type': file_type,
                    'data': data,
                    'metadata': metadata,
                    'manual_integration': pd.DataFrame()
                }
                return True, f"Successfully loaded {file_type} data from {filename}"

                


            except Exception as e:
                print(f"[DEBUG] ❌ Exception during file loading: {e}")
                return False, f"Error loading {filename}: {str(e)}"
            finally:
                self._cleanup_temp_file(temp_path)

        elif file_type is None:
            # Check if this is an auxiliary file that should be added to existing bundle
            aux_patterns = ['_SST.txt', '_Chromatogram.txt', '_Integration.txt', '_Peak Analysis.txt']
            if any(pattern in filename for pattern in aux_patterns):
                # Extract base name and find existing bundle
                base_name = None
                for pattern in aux_patterns:
                    if pattern in filename:
                        base_name = filename.replace(pattern, '')
                        break
                
                if base_name:
                    # Find existing chromeleon bundle
                    bundle_key = f"{base_name}_UV_VIS_1.txt"
                    if bundle_key in self.loaded_data and self.loaded_data[bundle_key]['type'] == 'chromeleon_bundle':
                        # Add to extra_files and reload bundle
                        extra_files = {filename: content}
                        reader = self.loaded_data[bundle_key]['reader']
                        reader._load_auxiliary_files(extra_files=extra_files)
                        print(f"[DEBUG] 🔄 Added {filename} to existing bundle {base_name}")
                        return True, f"Added auxiliary file {filename} to bundle"
            
            print(f"[DEBUG] 🔄 Skipping auxiliary file: {filename}")
            return True, f"Skipped auxiliary file {filename}"
        else:
            print(f"[DEBUG] ❌ Unknown file type. Available readers: {list(self.readers.keys())}")
            return False, f"Unknown file type for {filename}"

    def finalize_lcms_bundles(self):
        """Detect and merge LC-MS component files into unified bundles."""
        updated_any = False

        for file_id, file_entry in self.loaded_data.items():
            if file_entry["type"] not in ("lcms_cdf", "lcms_vwd_cdf"):
                continue

            base = file_entry.get("bundle_base")
            if not base:
                continue

            # Ensure base exists
            if base not in self.lcms_bundles:
                self.lcms_bundles[base] = {}

            # Decide component type (e.g. MS+, MS−, UV-A, UV-B)
            polarity = file_entry["metadata"].get("ionization_mode", "").lower()
            if file_entry["type"] == "lcms_cdf":
                component = "MS+" if "pos" in polarity else "MS−"
            elif file_entry["type"] == "lcms_vwd_cdf":
                channel = file_entry["metadata"].get("channel", "").upper()
                component = f"UV-{channel}" if channel else "UV-?"

            # Skip if already present
            if component in self.lcms_bundles[base]:
                continue  # don’t overwrite existing part

            # Add component to bundle
            self.lcms_bundles[base][component] = file_entry
            updated_any = True

        return updated_any

    def _cleanup_temp_file(self, temp_path):
        """Safely remove a temporary file."""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                if temp_path in self.temp_files:
                    self.temp_files.remove(temp_path)
        except Exception as e:
            print(f"Warning: Could not remove temp file {temp_path}: {e}")
    
    def _extract_metadata(self, reader, file_type):
        metadata = {
            'file_name': reader.get_file_name(),
            'data_points': len(reader.get_data()) if reader.get_data() is not None else 0,
            'file_type': file_type
        }
        
        if file_type == 'chromatogram':
            metadata['wavelength'] = reader.get_wavelength()
            if hasattr(reader, 'get_metadata'):
                reader_meta = reader.get_metadata()
                metadata.update(reader_meta)
        
        elif file_type == 'spectra':
            metadata['time_point'] = reader.get_time_point()
            if hasattr(reader, 'get_metadata'):
                reader_meta = reader.get_metadata()
                metadata.update(reader_meta)
        
        elif file_type == 'uvvis_csv':
            print(f"[DEBUG] 📊 Extracting UV-Vis metadata...")
            
            # Get basic UV-Vis info
            metadata['intensity_columns'] = reader.get_intensity_columns()
            metadata['total_wells'] = len(reader.get_intensity_columns())
            
            # Get filled wells (wells with actual data)
            filled_wells = reader.get_filled_wells()
            metadata['filled_wells'] = filled_wells
            metadata['filled_well_count'] = len(filled_wells)
            
            # Get wavelength range
            min_wl, max_wl = reader.get_wavelength_range()
            if min_wl and max_wl:
                metadata['wavelength_range'] = f"{min_wl:.0f}-{max_wl:.0f} nm"
                metadata['wavelength_min'] = min_wl
                metadata['wavelength_max'] = max_wl
            else:
                metadata['wavelength_range'] = "Unknown"
            
            # Get overflow info
            overflow_info = reader.get_overflow_info()
            if overflow_info:
                metadata['overflow_wells'] = list(overflow_info.keys())
                metadata['overflow_count'] = len(overflow_info)
            else:
                metadata['overflow_wells'] = []
                metadata['overflow_count'] = 0
            
            # Get reader-specific metadata (date, time, reader type, etc.)
            reader_meta = reader.get_metadata()
            metadata.update(reader_meta)
            
            # Add summary info for display
            metadata['summary'] = f"96-well plate, {len(filled_wells)} wells filled, {min_wl:.0f}-{max_wl:.0f} nm"
            
            print(f"[DEBUG] 📊 UV-Vis metadata: {metadata['total_wells']} total wells, {metadata['filled_well_count']} filled")
        
        elif file_type == 'chromeleon_bundle':
            metadata.update(reader.get_metadata())
            if reader.get_sst_result():
                metadata['sst_result'] = reader.get_sst_result()
            metadata['has_integration'] = reader.get_integration_table() is not None
            metadata['has_peak_table'] = reader.get_peak_table() is not None


        # ───────────────────────────────────────────────────────────────
        elif file_type == "lcms_cdf":
            # -----------------------------------------------------------
            # 1.  Make the key polarity-specific so we don’t overwrite
            # -----------------------------------------------------------
            ion_mode = reader.get_ionization_mode() or "unknown"
            base     = self.extract_lcms_base_name(reader.get_file_name())
        
            file_id  = f"{base}_{ion_mode.lower()}"                   # “…_positive/_negative”

            print(f"[DEBUG] 📊 Storing LC-MS CDF as {file_id}")

            # -----------------------------------------------------------
            # 2.  Collect rich metadata
            # -----------------------------------------------------------
            raw_metadata       = reader.get_raw_metadata()
            processed_metadata = reader.get_metadata()

            metadata: dict[str, Any] = {}
            metadata["ionization_mode"] = ion_mode
            metadata["scan_count"]      = reader.scan_count
            metadata["mass_range"]      = reader.mass_range


            # Basic LC-MS info
            metadata["ionization_mode"] = ion_mode
            metadata["scan_count"]      = reader.scan_count
            metadata["mass_range"]      = reader.mass_range

            # Retention-time / TIC info
            if getattr(reader, "tic_data", None) is not None:
                rt_col       = reader.tic_data["Time (min)"]
                intensity    = reader.tic_data["Intensity"]

                metadata["retention_time_min"]  = float(rt_col.min())
                metadata["retention_time_max"]  = float(rt_col.max())
                metadata["retention_time_range"]= f"{rt_col.min():.2f}-{rt_col.max():.2f} min"
                metadata["tic_points"]          = len(reader.tic_data)

                metadata["max_intensity"] = float(intensity.max())
                metadata["intensity_range"]= f"{intensity.min():.0f}-{intensity.max():.0f}"

            # Mass range (pretty)
            low, high = reader.mass_range
            if (low, high) != (0, 0):
                metadata["mass_range_min"] = low
                metadata["mass_range_max"] = high
                metadata["mass_range_str"] = f"{low:.0f}-{high:.0f} m/z"
            else:
                metadata["mass_range_str"] = "Unknown"

            # File-structure details
            metadata["cdf_dimensions"] = processed_metadata.get("file_structure", {})
            metadata["cdf_variables"]  = processed_metadata.get("variable_categories", {})

            # Dump the entire raw header for debug / UI drill-down
            metadata["raw_cdf_data"] = raw_metadata

            # Instrument & sample fields we care about
            for fld in (
                "instrument_name", "instrument_mfr", "instrument_model",
                "detector_name",  "sample_name",    "experiment_title",
                "separation_experiment_type"
            ):
                if fld in raw_metadata:
                    metadata[fld] = raw_metadata[fld]

            # Short human-readable summary
            det_name = metadata.get("detector_name", "MS")
            mode_str = f" {ion_mode.upper()}" if ion_mode != "unknown" else ""
            metadata["summary"] = (
                f"{det_name}{mode_str}, "
                f"{metadata['scan_count']} scans, "
                f"{metadata.get('retention_time_range', 'Unknown RT')}"
            )

            print(f"[DEBUG] 📊 Extracted {len(metadata)} LC-MS fields")
            reader.print_full_analysis()      # optional verbose dump

        elif file_type == 'lcms_vwd_cdf':
            print(f"[DEBUG] 📊 Extracting VWD CDF metadata...")
            
            # Get metadata from reader
            processed_metadata = reader.get_metadata()
            metadata.update(processed_metadata)
            
            # Add VWD specific fields
            metadata['detector_type'] = 'VWD'
            metadata['is_uv_data'] = True
            
            # Print analysis
            reader.print_full_analysis()
            
            print(f"[DEBUG] 📊 VWD metadata extracted: {len(metadata)} fields total")



        return metadata

    def get_loaded_files(self):
        return list(self.loaded_data.keys())
    
    def get_file_data(self, filename):
        entry = self.loaded_data.get(filename)
        if not entry:
            return None

        if entry['type'] == 'chromeleon_bundle':
            reader = entry['reader']
            entry['integration_table'] = reader.get_integration_table()
            entry['peak_table'] = reader.get_peak_table()
            entry['sst_result'] = reader.get_sst_result()
        return entry

    def set_manual_peaks(self, filename: str, peaks_df: pd.DataFrame):
        """Store manually integrated peaks for a file."""
        if filename in self.loaded_data:
            self.loaded_data[filename]['manual_integration'] = peaks_df

    def get_manual_peaks(self, filename: str) -> pd.DataFrame | None:
        """Retrieve manually integrated peaks for a file."""
        entry = self.loaded_data.get(filename)
        if not entry:
            return None
        return entry.get('manual_integration')

    def load_partial_bundle(self, base_name, aux_files, buffer):
        """Load auxiliary files when main chromatogram is missing."""
        try:
            # Create a minimal chromeleon bundle reader
            reader = ChromeleonBundleReader()
            reader.base_name = base_name
            reader.file_name = f"{base_name} (partial)"
            reader.data = None  # No chromatogram data
            reader.metadata = {"Status": "Chromatogram Missing"}
            
            # Set up required attributes for _load_auxiliary_files to work
            reader.file_dir = ""  # Empty string instead of None
            reader.file_path = ""  # Empty string instead of None
            
            # Initialize empty tables/results
            reader.integration_table = None
            reader.peak_table = None
            reader.sst_result = {}
            
            # Load auxiliary files directly from buffer
            reader._load_auxiliary_files(extra_files=buffer)
            
            # Store in loaded_data with special key
            filename_key = f"{base_name}_PARTIAL"
            self.loaded_data[filename_key] = {
                'reader': reader,
                'type': 'chromeleon_bundle',
                'data': None,  # No chromatogram data
                'metadata': self._extract_metadata(reader, 'chromeleon_bundle')
            }
            
            return True, f"Loaded auxiliary data for {base_name}"
            
        except Exception as e:
            return False, f"Error creating partial bundle: {str(e)}"

    def _create_bundle_metadata(self, base_name, bundle_data):
        """Create comprehensive metadata for LC-MS bundle"""
        components = []
        if bundle_data.get('ms_positive'):
            components.append('MS+')
        if bundle_data.get('ms_negative'):
            components.append('MS-')
        if bundle_data.get('vwd_a'):
            components.append('UV-A')
        if bundle_data.get('vwd_b'):
            components.append('UV-B')
        
        # Start with basic bundle info
        metadata = {
            'bundle_type': 'lcms_complete',
            'base_name': base_name,
            'components': components,
            'file_count': len([c for c in ['ms_positive', 'ms_negative', 'vwd_a', 'vwd_b'] if bundle_data.get(c)])
        }
        
        # Extract common sample info from first available component
        sample_info = {}
        for comp_key in ['ms_positive', 'ms_negative', 'vwd_a', 'vwd_b']:
            if bundle_data.get(comp_key):
                comp_meta = bundle_data[comp_key]['metadata']
                # Get sample info with proper field names
                if not sample_info.get("sample_name") and comp_meta.get("sample_name"):
                    sample_info["sample_name"] = comp_meta["sample_name"]
                if not sample_info.get("sample_id") and comp_meta.get("sample_id"):
                    sample_info["sample_id"] = comp_meta["sample_id"]
                if not sample_info.get("sample_injection_volume") and comp_meta.get("sample_injection_volume"):
                    sample_info["sample_injection_volume"] = comp_meta["sample_injection_volume"]
                if not sample_info.get("injection_date_time_stamp") and comp_meta.get("injection_date_time_stamp"):
                    sample_info["injection_date_time_stamp"] = comp_meta["injection_date_time_stamp"]
                if not sample_info.get("experiment_title") and comp_meta.get("experiment_title"):
                    sample_info["experiment_title"] = comp_meta["experiment_title"]
                if not sample_info.get("operator_name") and comp_meta.get("operator_name"):
                    sample_info["operator_name"] = comp_meta["operator_name"]

        metadata.update(sample_info)
        print(f"[DEBUG] 📋 Bundle sample info: {sample_info}")

        # Add component-specific metadata
        if bundle_data.get('ms_positive'):
            ms_pos = bundle_data['ms_positive']['metadata']
            metadata.update({
                'ms_positive_scans': ms_pos.get('scan_count', 0),
                'ms_positive_rt_range': ms_pos.get('retention_time_range', 'Unknown'),
                'ms_positive_mass_range': ms_pos.get('mass_range_str', 'Unknown'),
                'ms_positive_max_intensity': ms_pos.get('max_intensity', 0)
            })
        
        if bundle_data.get('ms_negative'):
            ms_neg = bundle_data['ms_negative']['metadata']
            metadata.update({
                'ms_negative_scans': ms_neg.get('scan_count', 0),
                'ms_negative_rt_range': ms_neg.get('retention_time_range', 'Unknown'),
                'ms_negative_mass_range': ms_neg.get('mass_range_str', 'Unknown'),
                'ms_negative_max_intensity': ms_neg.get('max_intensity', 0)
            })
        
        if bundle_data.get('vwd_a'):
            vwd_a = bundle_data['vwd_a']['metadata']
            metadata.update({
                'uv_a_wavelength': vwd_a.get('wavelength', '?'),
                'uv_a_rt_range': vwd_a.get('retention_time_range', 'Unknown'),
                'uv_a_max_intensity': vwd_a.get('max_intensity', 0),
                'uv_a_detector': vwd_a.get('detector_name', 'VWD1A'),
                'uv_a_data_points': vwd_a.get('data_points', 0),
                'uv_a_unit': vwd_a.get('detector_unit', 'mAU')
            })

        if bundle_data.get('vwd_b'):
            vwd_b = bundle_data['vwd_b']['metadata']
            metadata.update({
                'uv_b_wavelength': vwd_b.get('wavelength', '?'),
                'uv_b_rt_range': vwd_b.get('retention_time_range', 'Unknown'),
                'uv_b_max_intensity': vwd_b.get('max_intensity', 0),
                'uv_b_detector': vwd_b.get('detector_name', 'VWD1B'),
                'uv_b_data_points': vwd_b.get('data_points', 0),
                'uv_b_unit': vwd_b.get('detector_unit', 'mAU')
            })


        return metadata








    def clear_data(self):
        """Clear all loaded data and clean up any remaining temp files."""
        self.loaded_data.clear()
        self.lcms_bundles.clear()
        
        # Clean up any tracked temp files
        for temp_path in self.temp_files.copy():
            self._cleanup_temp_file(temp_path)
        
        # Also try to clean up any temp files that might have been missed
        temp_dir = tempfile.gettempdir()
        try:
            for filename in os.listdir(temp_dir):
                if filename.startswith("temp_") and ("_UV_VIS_" in filename or filename.endswith(".txt")):
                    temp_path = os.path.join(temp_dir, filename)
                    try:
                        os.remove(temp_path)
                        print(f"Cleaned up orphaned temp file: {filename}")
                    except:
                        pass  # Ignore if file is locked or already gone
        except Exception as e:
            print(f"Warning during temp file cleanup: {e}")
    
    def __del__(self):
        """Cleanup when the DataManager is destroyed."""
        try:
            self.clear_data()
        except:
            pass  # Ignore cleanup errors during destruction