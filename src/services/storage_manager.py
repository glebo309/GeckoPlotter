"""Storage manager for handling file uploads and data loading in GeckoPlotter V2."""

from __future__ import annotations

import json
import os
import re
import uuid
import base64
import tempfile
import copy
from datetime import datetime
from typing import Dict, Any, List, Optional

from services.readers.chromatogram_reader import ChromatogramReader
from services.readers.uvvis_csv_reader import UVVISCSVReader
from services.readers.generic_csv_reader import GenericCSVReader
from services.readers.lcms_cdf_reader import LCMSCDFReader
from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader
from .bundle_manager import BundleManager
from .peak_service import PeakService
from .calibration_service import CalibrationService
from .integration_service import IntegrationService
from .plot_settings_service import PlotSettingsService
from .export_service import ExportService
from .lcms_service import LCMSService
from .persistence import ProjectPersistence
from src.ingestion import ingest_file

TEXT_EXTENSIONS = {"txt", "csv", "tsv", "log", "json", "xml", "cdf", "cdfx"}
BINARY_EXTENSIONS = {"cdf", "cdfx", "cdf.vwd", "raw", "dat", "bin"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "svg"}

def _decode_content(contents: str) -> bytes:
    """Decode the base64 content string returned by dcc.Upload."""
    _, encoded = contents.split(",", 1)
    return base64.b64decode(encoded)


def guess_file_type(filename: str) -> str:
    extension = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    name_lower = filename.lower()
    if extension in {"csv", "tsv"}:
        return "csv"
    if extension in {"json", "xml"}:
        return "structured"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in {"cdf", "cdfx"}:
        if any(tag in name_lower for tag in ["vwd", "uv", "channel"]):
            return "lcms_vwd_cdf"
        return "lcms_cdf"
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension in BINARY_EXTENSIONS:
        return "binary"
    return "unknown"


def _build_preview(content: bytes, file_type: str) -> str:
    if file_type in {"text", "uvvis_csv", "csv", "chromatogram", "structured", "generic_csv"}:
        try:
            text = content.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return "Binary content"
        return text[:200] + ("..." if len(text) > 200 else "")
    return f"Binary content ({file_type})"

def _pretty_size(num_bytes: int) -> str:
    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    value = float(num_bytes)
    while value >= step and idx < len(units) - 1:
        value /= step
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.1f} {units[idx]}"


def create_file_records(
    contents_list: List[str],
    filenames: List[str],
    last_modified_list: Optional[List[int]],
) -> List[Dict[str, Any]]:
    """Create normalized file records from the uploaded payload."""

    records: List[Dict[str, Any]] = []
    last_modified_list = last_modified_list or [None] * len(contents_list)

    for contents, name, last_modified in zip(contents_list, filenames, last_modified_list):
        payload = _decode_content(contents)
        file_type = guess_file_type(name)
        record = {
            "id": str(uuid.uuid4()),
            "name": name,
            "type": file_type,
            "size": len(payload),
            "size_display": _pretty_size(len(payload)),
            "last_modified": last_modified,
            "last_modified_display": (
                datetime.fromtimestamp(last_modified / 1000).strftime("%Y-%m-%d %H:%M")
                if last_modified
                else ""
            ),
            "preview": _build_preview(payload, file_type),
            "encoded": contents,
        }
        records.append(record)

    return records


def merge_records(existing: Optional[List[Dict[str, Any]]], new_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge existing file records with newly uploaded ones."""

    existing = existing or []

    # Avoid duplicate file IDs while allowing different uploads with same filename
    existing_ids = {record.get("id") for record in existing}
    merged = existing.copy()

    for record in new_records:
        if record["id"] in existing_ids:
            continue
        merged.append(record)

    # Sort by upload time (if provided) descending, fallback to name
    def sort_key(item: Dict[str, Any]):
        timestamp = item.get("last_modified")
        return (timestamp or 0, item.get("name"))

    merged.sort(key=sort_key, reverse=True)
    return merged


def summarize_records(records: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return a sanitized summary of stored records for developer diagnostics."""

    summaries: List[Dict[str, Any]] = []
    for item in records or []:
        summaries.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
                "size": item.get("size_display"),
                "last_modified": item.get("last_modified_display"),
                "preview": item.get("preview"),
            }
        )
    return summaries


class DataManager:
    """Manages file uploads, data loading, and bundling."""

    # Path for persistent per-file state (lives next to app.py)
    _STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'file_state.json')

    def __init__(self):
        self.loaded_data: Dict[str, Dict[str, Any]] = {}
        self.temp_files: List[str] = []
        self.bundle_manager = BundleManager()
        self.lcms_bundles: Dict[str, Dict[str, Any]] = {}
        self.file_ui_state: Dict[str, Dict[str, Any]] = {}

        # Persistent state keyed by filename (survives across sessions)
        self._persistent_state: Dict[str, Dict[str, Any]] = {}
        self._load_persistent_state()

        # Maps runtime file_id → filename for persistence lookups
        self._id_to_filename: Dict[str, str] = {}

        # Initialize readers
        self.readers = {
            'chromatogram': ChromatogramReader,
            'uvvis_csv': UVVISCSVReader,
            'generic_csv': GenericCSVReader,
            'lcms_cdf': LCMSCDFReader,
            'lcms_vwd_cdf': LCMSVWDCDFReader,
        }

        # ── Domain services ──────────────────────────────────────────
        # These are the canonical owners of scientific state.
        # Callbacks should call these services, not implement logic inline.
        self.peak_service = PeakService()
        self.calibration_service = CalibrationService()
        self.integration_service = IntegrationService()
        self.plot_settings_service = PlotSettingsService()
        self.export_service = ExportService()
        self.lcms_service = LCMSService()

        # Project-level persistence (wraps file_state.json)
        self.project = ProjectPersistence(self._STATE_FILE)
        self._restore_services_from_project()

    # ------------------------------------------------------------------
    # Service ↔ persistence bridge
    # ------------------------------------------------------------------
    def _restore_services_from_project(self) -> None:
        """Restore domain service state from ProjectPersistence on startup."""
        try:
            peaks = self.project.peaks
            if peaks:
                self.peak_service.deserialize(peaks)
            cals = self.project.calibrations
            if cals:
                self.calibration_service.deserialize(cals)
            integ = self.project.integration_settings
            if integ:
                self.integration_service.deserialize(integ)
        except Exception as e:
            import logging
            logging.getLogger('geckoplotter').warning(f"Could not restore services: {e}")

    def persist_services(self) -> None:
        """Save current domain service state to ProjectPersistence."""
        self.project.set_section('peaks', self.peak_service.serialize(), auto_save=False)
        self.project.set_section('calibrations', self.calibration_service.serialize(), auto_save=False)
        self.project.set_section('integration_settings', self.integration_service.serialize(), auto_save=False)
        self.project.save()

    # ------------------------------------------------------------------
    # Persistent JSON state (keyed by filename, survives app restarts)
    # ------------------------------------------------------------------
    def _load_persistent_state(self) -> None:
        """Load per-file state from disk."""
        try:
            if os.path.exists(self._STATE_FILE):
                with open(self._STATE_FILE, 'r') as f:
                    self._persistent_state = json.load(f)
                print(f"Loaded persistent state for {len(self._persistent_state)} files from {self._STATE_FILE}")
        except Exception as e:
            print(f"Could not load persistent state: {e}")
            self._persistent_state = {}

    def _save_persistent_state(self) -> None:
        """Write per-file state to disk."""
        try:
            with open(self._STATE_FILE, 'w') as f:
                json.dump(self._persistent_state, f, indent=2, default=str)
        except Exception as e:
            print(f"Could not save persistent state: {e}")

    def register_file_id(self, file_id: str, filename: str) -> None:
        """Map a runtime file_id to its filename for persistent lookup.
        If persistent state exists for this filename, restore it."""
        self._id_to_filename[file_id] = filename

        if filename in self._persistent_state:
            # Restore saved state into the in-memory store
            restored = copy.deepcopy(self._persistent_state[filename])
            restored['file_id'] = file_id  # update to current session's ID
            existing = self.file_ui_state.get(file_id, {})
            existing.update(restored)
            self.file_ui_state[file_id] = existing

    def persist_file_state(self, file_id: str) -> None:
        """Write current in-memory state for file_id to the persistent store."""
        filename = self._id_to_filename.get(file_id)
        if not filename:
            return

        state = self.file_ui_state.get(file_id)
        if not state:
            return

        # Only persist UI-relevant fields (not transient runtime data)
        to_save = {}
        for key in ('pub_selections', 'plot_settings', 'view_mode',
                     'active_tab', 'toolbox_tab'):
            if key in state:
                to_save[key] = copy.deepcopy(state[key])

        # Strip transient fields from pub_selections before saving
        sel = to_save.get('pub_selections')
        if isinstance(sel, dict):
            sel.pop('file_id', None)
            sel.pop('last_updated', None)

        self._persistent_state[filename] = to_save
        self._save_persistent_state()

    # ------------------------------------------------------------------
    # Unified per-file UI state helpers
    # ------------------------------------------------------------------
    def build_default_file_state(
        self,
        file_id: Optional[str],
        file_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the default UI state capsule for a file."""
        from components.axis_mapper import get_empty_selections

        return {
            'file_id': file_id,
            'view_mode': 'raw',
            'active_tab': 'data-overview',
            'toolbox_tab': 'pub-plotter',
            'plot_settings': {},
            'dev_settings': {'show': False},
            'pub_selections': get_empty_selections(),
        }

    def get_file_state(
        self,
        file_id: Optional[str],
        file_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a deep-copied per-file UI state, creating defaults if needed."""
        if not file_id:
            return self.build_default_file_state(file_id, file_data)

        if file_id not in self.file_ui_state:
            self.file_ui_state[file_id] = self.build_default_file_state(file_id, file_data)

        state = copy.deepcopy(self.file_ui_state[file_id])
        state['file_id'] = file_id
        return state

    def save_file_state(self, file_id: Optional[str], state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Persist a full per-file UI state capsule (in-memory + disk)."""
        if not file_id:
            return self.build_default_file_state(file_id)

        existing = self.get_file_state(file_id)
        merged = copy.deepcopy(existing)
        if state:
            merged.update(copy.deepcopy(state))
        merged['file_id'] = file_id
        self.file_ui_state[file_id] = merged

        # Also write to persistent JSON (keyed by filename)
        self.persist_file_state(file_id)

        return copy.deepcopy(merged)

    def clear_file_state(self, file_id: Optional[str]) -> None:
        """Remove persisted UI state for a file."""
        if not file_id:
            return
        self.file_ui_state.pop(file_id, None)

    # ------------------------------------------------------------------
    # Publication plotter memory helpers
    # ------------------------------------------------------------------
    @property
    def publication_memory(self) -> Dict[str, Dict[str, Any]]:
        """Compatibility view over the unified per-file state."""
        memory: Dict[str, Dict[str, Any]] = {}
        for file_id, state in self.file_ui_state.items():
            selections = state.get('pub_selections')
            if selections is not None:
                memory[file_id] = copy.deepcopy(selections)
        return memory

    def initialise_publication_memory(self, file_id: str, selections: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ensure a publication memory entry exists for the given file."""
        if not file_id:
            return {}

        state = self.get_file_state(file_id)
        if not state.get('pub_selections'):
            state['pub_selections'] = copy.deepcopy(selections or {})
            self.save_file_state(file_id, state)

        return copy.deepcopy(self.get_file_state(file_id).get('pub_selections', {}))

    def get_publication_memory(self, file_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return saved publication selections for the given file."""
        if not file_id:
            return None
        return copy.deepcopy(self.get_file_state(file_id).get('pub_selections'))

    def save_publication_memory(self, file_id: str, selections: Dict[str, Any]) -> None:
        """Persist publication selections for a file."""
        if not file_id:
            return
        state = self.get_file_state(file_id)
        state['pub_selections'] = copy.deepcopy(selections or {})
        self.save_file_state(file_id, state)

    def delete_publication_memory(self, file_id: str) -> None:
        """Remove publication selections for a file if present."""
        if not file_id:
            return
        state = self.get_file_state(file_id)
        state['pub_selections'] = self.build_default_file_state(file_id).get('pub_selections', {})
        self.save_file_state(file_id, state)

    def clear_publication_memory(self) -> None:
        """Remove all stored publication selections."""
        for file_id in list(self.file_ui_state.keys()):
            self.delete_publication_memory(file_id)

    def load_file_data(self, file_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load actual data from a file record using appropriate reader."""
        try:
            # Create temporary file
            content_bytes = _decode_content(file_record['encoded'])
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_record['name']}")
            temp_file.write(content_bytes)
            temp_file.close()

            # Track temp file for cleanup
            self.temp_files.append(temp_file.name)

            standardized = ingest_file(temp_file.name, file_record['name'])

            # Detect file type (pass temp file path for content-based detection)
            file_type = self.detect_file_type(file_record['name'], temp_file.name)

            # Update the record type to match content-based detection
            if file_type:
                file_record['type'] = file_type

            # Register the file_id ↔ filename mapping so persistent state
            # can be looked up by filename across sessions.
            self.register_file_id(file_record['id'], file_record['name'])

            if file_type and file_type in self.readers:
                # Create reader instance
                reader = self.readers[file_type]()

                # Load the file
                if reader.load_file(temp_file.name):
                    # Get data and metadata
                    data = reader.get_data()
                    metadata = reader.get_metadata()

                    file_id = file_record['id']

                    if file_type in {'lcms_cdf', 'lcms_vwd_cdf'}:
                        base_name = self.extract_lcms_base_name(file_record['name'])
                        self._init_lcms_bundle(base_name)
                        bundle = self.lcms_bundles[base_name]
                        if file_id not in bundle['files']:
                            bundle['files'].append(file_id)

                        component_entry = {
                            'id': file_id,
                            'record': file_record,
                            'data': data,
                            'metadata': metadata,
                            'reader': reader,
                            'type': file_type,
                        }

                        if standardized is not None:
                            component_entry['standardized'] = standardized

                        if file_type == 'lcms_cdf':
                            mode = metadata.get('ionization_mode', 'unknown')
                            key = 'ms_positive' if mode == 'positive' else 'ms_negative' if mode == 'negative' else None
                        else:
                            channel = metadata.get('detector_channel', 'Unknown')
                            key = 'vwd_a' if channel == 'A' else 'vwd_b' if channel == 'B' else None

                        if key:
                            bundle[key] = component_entry

                        self.loaded_data[file_id] = component_entry
                        self._update_lcms_bundle_metadata(base_name)

                        print(f"✅ Loaded {file_record['name']} as {file_type} (LCMS bundle {base_name})")
                        return component_entry

                    # Non-LCMS storage
                    entry = {
                        'record': file_record,
                        'data': data,
                        'metadata': metadata,
                        'reader': reader,
                        'type': file_type
                    }
                    if standardized is not None:
                        entry['standardized'] = standardized

                    self.loaded_data[file_id] = entry

                    print(f"✅ Loaded {file_record['name']} as {file_type}")
                    return self.loaded_data[file_id]

            print(f"❌ Could not load {file_record['name']} - unknown type or no reader")
            return None

        except Exception as e:
            print(f"❌ Error loading {file_record['name']}: {str(e)}")
            return None

    # ------------------------------------------------------------------
    # LC-MS bundle helpers
    # ------------------------------------------------------------------
    def get_lcms_bundle_by_id(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        if not bundle_id or not bundle_id.endswith('_LCMS_BUNDLE'):
            return None
        base_name = bundle_id[: -len('_LCMS_BUNDLE')]
        return self.lcms_bundles.get(base_name)

    def find_lcms_bundle_for_component(self, component_id: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        for base_name, bundle in self.lcms_bundles.items():
            if component_id in bundle.get('files', []):
                return base_name, bundle
        return None, None

    def remove_lcms_bundle(self, base_name: str) -> Optional[Dict[str, Any]]:
        return self.lcms_bundles.pop(base_name, None)

    def detect_file_type(self, filename: str, file_path: Optional[str] = None) -> Optional[str]:
        """Determine which reader to use based on filename and content."""
        filename_lower = filename.lower()

        if filename_lower.endswith('.txt'):
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        head = f.read(2048)
                    if 'Raw Data:' in head and ('Time (min)' in head or 'Value (mAU)' in head):
                        return 'chromatogram'
                except Exception:
                    pass
            return 'chromatogram'

        if filename_lower.endswith('.csv'):
            # Check file content to distinguish UV-Vis from generic CSV
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        # Read first 50 lines to check for "Wavelength" header (plate readers have lots of metadata)
                        for i, line in enumerate(f):
                            if i > 50:  # Check first 50 lines for plate reader files
                                break
                            if 'Wavelength' in line:
                                print(f"✅ Found 'Wavelength' in line {i} - detected as UV-Vis CSV")
                                return 'uvvis_csv'
                        print(f"⚠️ No 'Wavelength' found in first 50 lines - treating as generic CSV")
                except Exception as e:
                    print(f"❌ Error checking CSV content: {e}")
            # Default to generic CSV for simple tabular data
            return 'generic_csv'
        
        if filename_lower.endswith('.cdf'):
            if any(tag in filename_lower for tag in ['vwd', 'uvw', 'uv-']):
                return 'lcms_vwd_cdf'
            return 'lcms_cdf'

        return None

    @staticmethod
    def extract_lcms_base_name(filename: str) -> str:
        base = os.path.splitext(os.path.basename(filename))[0]
        patterns = [
            r'_MS1\s*[+-]TIC.*$',
            r'_VWD1[AB]$',
            r'_MS\d*.*$',
            r'_[+-]$',
            r'_pos(itive)?$',
            r'_neg(ative)?$',
        ]
        for pattern in patterns:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        return base.rstrip('_- ')

    def _init_lcms_bundle(self, base_name: str) -> None:
        if base_name not in self.lcms_bundles:
            self.lcms_bundles[base_name] = {
                'ms_positive': None,
                'ms_negative': None,
                'vwd_a': None,
                'vwd_b': None,
                'files': [],
                'metadata': {},
                'base_name': base_name,
            }

    def _update_lcms_bundle_metadata(self, base_name: str) -> None:
        bundle = self.lcms_bundles.get(base_name)
        if not bundle:
            return

        components = []
        if bundle['ms_positive']:
            components.append('MS+')
        if bundle['ms_negative']:
            components.append('MS-')
        if bundle['vwd_a']:
            components.append('UV-A')
        if bundle['vwd_b']:
            components.append('UV-B')

        metadata: Dict[str, Any] = {
            'bundle_type': 'lcms_bundle',
            'base_name': base_name,
            'components': components,
            'file_count': len([c for c in ['ms_positive', 'ms_negative', 'vwd_a', 'vwd_b'] if bundle.get(c)]),
        }

        sample_info_fields = [
            'sample_name',
            'sample_id',
            'experiment_title',
            'injection_date_time_stamp',
        ]

        for component_key in ['ms_positive', 'ms_negative', 'vwd_a', 'vwd_b']:
            component = bundle.get(component_key)
            if not component:
                continue
            comp_meta = component['metadata']
            for field in sample_info_fields:
                if field in comp_meta and field not in metadata:
                    metadata[field] = comp_meta[field]

            if component_key == 'ms_positive':
                metadata['ms_positive_rt_range'] = comp_meta.get('retention_time_range')
                metadata['ms_positive_mass_range'] = comp_meta.get('mass_range_str')
                metadata['ms_positive_scans'] = comp_meta.get('scan_count')
            elif component_key == 'ms_negative':
                metadata['ms_negative_rt_range'] = comp_meta.get('retention_time_range')
                metadata['ms_negative_mass_range'] = comp_meta.get('mass_range_str')
                metadata['ms_negative_scans'] = comp_meta.get('scan_count')
            elif component_key == 'vwd_a':
                metadata['uv_a_wavelength'] = comp_meta.get('wavelength')
                metadata['uv_a_rt_range'] = comp_meta.get('retention_time_range')
                metadata['uv_a_max_intensity'] = comp_meta.get('max_intensity')
            elif component_key == 'vwd_b':
                metadata['uv_b_wavelength'] = comp_meta.get('wavelength')
                metadata['uv_b_rt_range'] = comp_meta.get('retention_time_range')
                metadata['uv_b_max_intensity'] = comp_meta.get('max_intensity')

        bundle['metadata'] = metadata
        bundle_key = f"{base_name}_LCMS_BUNDLE"
        self.loaded_data[bundle_key] = {
            'type': 'lcms_bundle',
            'bundle_data': bundle,
            'metadata': metadata,
        }

    def get_loaded_data(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded data."""
        return self.loaded_data.copy()

    def get_data_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get loaded data by file ID."""
        return self.loaded_data.get(file_id)

    def clear_data(self) -> None:
        """Clear all loaded data and cleanup temp files."""
        self.loaded_data.clear()
        self.bundle_manager.clear_bundles()
        self.lcms_bundles.clear()
        self.file_ui_state.clear()

        # Cleanup temp files
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass

        self.temp_files.clear()

    def process_file_for_bundling(self, file_record: Dict[str, Any]) -> Optional[str]:
        """Process a file for potential bundling. Returns bundle_id if bundled."""
        return self.bundle_manager.add_file_to_bundle(file_record)

    def get_bundled_tree_items(self, individual_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get tree items with bundles and individual files."""
        # Check if we've already processed these files to avoid double processing
        if hasattr(self, '_last_processed_files') and self._last_processed_files == individual_files:
            print("Skipping duplicate bundling call")
            return self._last_tree_items
        
        tree_items = []
        bundled_file_ids = set()
        
        # FIRST PASS: Create main bundles (UV_VIS files, CSV files with multiple wells)
        print(f"Processing {len(individual_files)} files for bundling...")
        for file_record in individual_files:
            file_id = file_record.get('id')
            file_type = file_record.get('type')
            file_name = file_record.get('name')
            
            bundle_id = None
            
            # Check actual detected type from loaded data (more reliable than record type)
            actual_type = file_type
            if file_id in self.loaded_data:
                actual_type = (self.loaded_data[file_id].get('metadata', {}).get('file_type')
                              or self.loaded_data[file_id].get('type')
                              or file_type)

            # Try Chromeleon bundle first (for HPLC main files)
            if actual_type == 'chromatogram' or file_name.endswith('_UV_VIS_1.txt'):
                print(f"🧬 Trying to create Chromeleon bundle for: {file_name}")
                bundle_id = self.bundle_manager.try_create_chromeleon_bundle(file_record)
                if bundle_id:
                    print(f"📦 Created Chromeleon bundle: {bundle_id}")
                    bundled_file_ids.add(file_id)  # Mark main file as bundled
                else:
                    print(f"❌ Failed to create Chromeleon bundle for: {file_name}")
            
            # UV-Vis files get wells as children (like old system)
            elif file_type == 'uvvis_csv' and file_id in self.loaded_data:
                file_data = self.loaded_data[file_id]
                filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
                
                print(f"🧪 UV-Vis file {file_name}: {len(filled_wells)} wells found: {filled_wells[:5]}")
                
                # Don't create a separate bundle - just mark this file to have wells as children
                # The tree rendering will handle adding wells as children
                if len(filled_wells) > 0:
                    print(f"📊 UV-Vis file {file_name} will have {len(filled_wells)} well children")
                else:
                    print(f"⚠️ UV-Vis file {file_name} has no wells")
        
        # SECOND PASS: Add auxiliary files to existing bundles
        for file_record in individual_files:
            file_id = file_record.get('id')
            file_type = file_record.get('type')
            file_name = file_record.get('name')
            
            # Skip if already bundled as main file
            if file_id in bundled_file_ids:
                continue
            
            # Check if this is an auxiliary file for an existing Chromeleon bundle
            if file_type == 'text':
                print(f"🔍 Checking if {file_name} is auxiliary file for existing bundle...")
                existing_bundle_id = self.bundle_manager.find_chromeleon_bundle_for_file(file_record)
                if existing_bundle_id:
                    # Add this file as auxiliary to the existing bundle
                    self.bundle_manager.add_auxiliary_file_to_bundle(existing_bundle_id, file_record)
                    bundled_file_ids.add(file_id)  # Mark as bundled so it doesn't appear individually
                    print(f"📎 Added {file_name} to bundle {existing_bundle_id}")
                    continue
                else:
                    print(f"❌ No existing bundle found for auxiliary file: {file_name}")
        
        # STEP 2: Get all bundle tree items and mark ALL their children as bundled
        bundle_items = self.bundle_manager.get_bundle_tree_items()
        for bundle_item in bundle_items:
            # Store bundle data for clicking
            bundle = self.bundle_manager.get_bundle_by_id(bundle_item['id'])
            if bundle and bundle.main_file:
                main_file_id = bundle.main_file.get('id')
                if main_file_id in self.loaded_data:
                    self.loaded_data[bundle_item['id']] = self.loaded_data[main_file_id]
                    print(f"📦 Stored bundle data for: {bundle_item['id']}")
                
                # Mark ALL files in this bundle as bundled
                bundled_file_ids.add(main_file_id)
                print(f"🔒 Marked main file {main_file_id} as bundled")
                
                for aux_file in bundle.auxiliary_files:
                    aux_id = aux_file.get('id')
                    bundled_file_ids.add(aux_id)
                    print(f"🔒 Marked auxiliary file {aux_id} as bundled")
            
            tree_items.append(bundle_item)
        
        # Collect LCMS component IDs ahead of individual-item processing to avoid duplicates
        lcms_component_ids = set()
        for bundle in self.lcms_bundles.values():
            lcms_component_ids.update(bundle.get('files', []))

        # STEP 3: Add individual files that are NOT bundled, with UV-Vis wells as children
        print(f"🔍 Checking individual files against bundled set: {bundled_file_ids}")
        for file_record in individual_files:
            file_id = file_record.get('id')
            file_name = file_record.get('name')
            file_type = file_record.get('type')

            if file_id in lcms_component_ids:
                print(f"🧪 Skipping standalone LCMS component already in bundle: {file_name}")
                continue

            if file_id not in bundled_file_ids:
                if file_type in {'lcms_cdf', 'lcms_vwd_cdf'}:
                    print(f"🧪 LCMS component {file_name} not in bundle yet, showing individually")
                    # fall through to add individually (helps debugging)
                print(f"✅ Adding individual file: {file_name} (ID: {file_id})")
                # For UV-Vis files, add wells as children (like old system)
                if file_type == 'uvvis_csv' and file_id in self.loaded_data:
                    file_data = self.loaded_data[file_id]
                    filled_wells = file_data.get('metadata', {}).get('filled_wells', [])
                    
                    if len(filled_wells) > 0:
                        # Add wells as children to the file record
                        file_record_copy = file_record.copy()
                        file_record_copy['children'] = []
                        
                        for well in filled_wells[:10]:  # Limit to first 10 wells
                            well_child = {
                                'id': f"{file_id}|{well}",
                                'name': f"Well {well}",
                                'type': 'uvvis_well',
                                'size_display': 'spectrum',
                                'parent_file_id': file_id,
                                'well_name': well
                            }
                            file_record_copy['children'].append(well_child)
                        
                        tree_items.append(file_record_copy)
                        print(f"📊 Added UV-Vis file {file_name} with {len(filled_wells)} well children")
                    else:
                        tree_items.append(file_record)
                else:
                    tree_items.append(file_record)
            else:
                print(f"⚠️ SKIPPING bundled file: {file_name} (ID: {file_id}) - already in bundle")
        
        # STEP 4: Append LC-MS bundles collected via DataManager
        if self.lcms_bundles:
            print(f"🧪 Integrating {len(self.lcms_bundles)} LC-MS bundles into tree")

        for base_name, bundle in self.lcms_bundles.items():
            bundle_key = f"{base_name}_LCMS_BUNDLE"
            components = []

            for component_id in bundle.get('files', []):
                entry = self.loaded_data.get(component_id)
                if not entry:
                    continue

                record_meta = entry.get('metadata', {})
                record_info = entry.get('record', {})
                comp_type = entry.get('type')
                component_label = record_info.get('name', 'LC-MS Component')
                icon = '🧪'
                bundle_component_type = 'component'
                rendered_type = comp_type

                if comp_type == 'lcms_cdf':
                    mode = record_meta.get('ionization_mode', 'unknown')
                    if mode == 'positive':
                        component_label = 'TIC (MS+)'
                        rendered_type = 'lcms_ms_positive'
                        bundle_component_type = 'ms_positive'
                    elif mode == 'negative':
                        component_label = 'TIC (MS-)'
                        rendered_type = 'lcms_ms_negative'
                        bundle_component_type = 'ms_negative'
                    else:
                        component_label = 'TIC (MS)'
                        rendered_type = 'lcms_cdf'
                        bundle_component_type = 'ms_unknown'
                    icon = '🧪'
                elif comp_type == 'lcms_vwd_cdf':
                    channel = record_meta.get('detector_channel', 'Unknown')
                    wavelength = record_meta.get('wavelength')
                    if channel and channel != 'Unknown':
                        component_label = f"UV Channel {channel}"
                    else:
                        component_label = 'UV Chromatogram'
                    if wavelength:
                        component_label += f" ({wavelength} nm)"
                    if channel == 'A':
                        rendered_type = 'lcms_uv_a'
                        bundle_component_type = 'vwd_a'
                    elif channel == 'B':
                        rendered_type = 'lcms_uv_b'
                        bundle_component_type = 'vwd_b'
                    else:
                        rendered_type = 'lcms_vwd_cdf'
                        bundle_component_type = 'vwd'
                    icon = '🌈'

                record = {
                    'id': component_id,
                    'name': component_label,
                    'raw_name': record_info.get('name'),
                    'type': rendered_type,
                    'component_type': bundle_component_type,
                    'parent_bundle': bundle_key,
                    'is_bundle_child': True,
                    'icon': icon,
                    'size_display': record_info.get('size_display', ''),
                }

                components.append(record)
                bundled_file_ids.add(component_id)

            if not components:
                print(f"⚠️ LC-MS bundle {base_name} has no component records yet")
                continue

            metadata = bundle.get('metadata', {})
            bundle_item = {
                'id': bundle_key,
                'name': f"{base_name} (LC-MS)",
                'type': 'lcms_bundle',
                'size_display': f"{metadata.get('file_count', len(components))} files",
                'is_bundle': True,
                'expanded': True,
                'icon': '🧪',
                'metadata': metadata,
                'children': components,
            }

            tree_items.append(bundle_item)

        print(f"✅ Final tree: {len(tree_items)} items, {len(bundled_file_ids)} files bundled")
        
        # Cache the result to avoid double processing
        self._last_processed_files = individual_files
        self._last_tree_items = tree_items
        
        return tree_items

    def get_bundle_by_id(self, bundle_id: str):
        """Get bundle by ID."""
        return self.bundle_manager.get_bundle_by_id(bundle_id)
