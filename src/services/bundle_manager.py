# =============================================================================
# File: services/bundle_manager.py
# =============================================================================
"""
Bundle Manager for GeckoPlotter V2 - Groups related files into bundles.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FileBundle:
    """Represents a bundle of related files."""
    base_name: str
    bundle_type: str  # 'chromeleon', 'lcms', 'uvvis_multi'
    main_file: Dict[str, Any]
    auxiliary_files: List[Dict[str, Any]]
    bundle_id: str
    wells: List[str] = None  # For UV-Vis files with multiple wells


class BundleManager:
    """Manages file bundling logic."""

    def __init__(self):
        self.bundles: Dict[str, FileBundle] = {}
        
        # Patterns for different bundle types
        self.chromeleon_patterns = {
            'main': r'^(.+)_UV_VIS_\d+\.txt$',
            'auxiliary': [
                r'^(.+)_SST\.txt$',
                r'^(.+)_Chromatogram\.txt$', 
                r'^(.+)_Integration\.txt$',
                r'^(.+)_Peak Analysis\.txt$'
            ]
        }
        
        self.lcms_patterns = {
            'positive': r'^(.+)_pos\.cdf$',
            'negative': r'^(.+)_neg\.cdf$',
            'vwd_a': r'^(.+)_VWD_A\.cdf$',
            'vwd_b': r'^(.+)_VWD_B\.cdf$'
        }

    def extract_base_name(self, filename: str, file_type: str) -> Optional[str]:
        """Extract base name from filename based on file type."""
        
        # Remove 'temp_' prefix if present
        clean_name = filename.replace('temp_', '')
        
        if file_type in ['chromatogram', 'text']:
            # Check for Chromeleon main file pattern
            match = re.match(self.chromeleon_patterns['main'], clean_name)
            if match:
                return match.group(1).strip()
            
            # Check for auxiliary file patterns
            for pattern in self.chromeleon_patterns['auxiliary']:
                match = re.match(pattern, clean_name)
                if match:
                    return match.group(1).strip()
        
        elif file_type == 'lcms_cdf':
            # Check LC-MS patterns
            for pattern_type, pattern in self.lcms_patterns.items():
                match = re.match(pattern, clean_name)
                if match:
                    return match.group(1).strip()
        
        return None

    def should_bundle(self, filename: str, file_type: str) -> bool:
        """Check if a file should be bundled."""
        return self.extract_base_name(filename, file_type) is not None

    def add_file_to_bundle(self, file_record: Dict[str, Any]) -> Optional[str]:
        """Add a file to appropriate bundle. Returns bundle_id if bundled."""
        
        filename = file_record.get('name', '')
        file_type = file_record.get('type', '')
        
        base_name = self.extract_base_name(filename, file_type)
        if not base_name:
            return None
        
        # Determine bundle type
        bundle_type = self._determine_bundle_type(filename, file_type)
        if not bundle_type:
            return None
        
        bundle_id = f"{base_name}_{bundle_type}"
        
        # Create bundle if it doesn't exist
        if bundle_id not in self.bundles:
            self.bundles[bundle_id] = FileBundle(
                base_name=base_name,
                bundle_type=bundle_type,
                main_file=file_record,
                auxiliary_files=[],
                bundle_id=bundle_id
            )
        else:
            # Add to existing bundle
            bundle = self.bundles[bundle_id]
            
            # Determine if this is main or auxiliary
            if self._is_main_file(filename, file_type):
                bundle.main_file = file_record
            else:
                bundle.auxiliary_files.append(file_record)
        
        return bundle_id

    def _determine_bundle_type(self, filename: str, file_type: str) -> Optional[str]:
        """Determine the type of bundle this file belongs to."""
        
        if file_type in ['chromatogram', 'text']:
            if re.match(self.chromeleon_patterns['main'], filename):
                return 'chromeleon'
            for pattern in self.chromeleon_patterns['auxiliary']:
                if re.match(pattern, filename):
                    return 'chromeleon'
        
        elif file_type == 'lcms_cdf':
            for pattern_type in self.lcms_patterns:
                if re.match(self.lcms_patterns[pattern_type], filename):
                    return 'lcms'
        
        return None

    def _is_main_file(self, filename: str, file_type: str) -> bool:
        """Check if this is a main file (not auxiliary)."""
        
        if file_type in ['chromatogram', 'text']:
            return bool(re.match(self.chromeleon_patterns['main'], filename))
        
        elif file_type == 'lcms_cdf':
            # For LC-MS, positive mode is considered "main"
            return bool(re.match(self.lcms_patterns['positive'], filename))
        
        return True

    def get_bundle_tree_items(self) -> List[Dict[str, Any]]:
        """Generate tree items for bundles (expandable groups)."""
        
        tree_items = []
        
        for bundle_id, bundle in self.bundles.items():
            if bundle.bundle_type == 'uvvis_multi':
                # Use special UV-Vis tree item creation
                tree_items.append(self._create_uvvis_tree_item(bundle))
            else:
                # Use standard bundle tree item creation (Chromeleon, etc.)
                bundle_icon = self._get_bundle_icon(bundle.bundle_type)
                file_count = 1 + len(bundle.auxiliary_files)
                
                bundle_item = {
                    'id': bundle_id,
                    'name': f"{bundle.base_name} ({bundle.bundle_type.title()} Bundle)",
                    'type': f'{bundle.bundle_type}_bundle',
                    'size_display': f"{file_count} files",
                    'is_bundle': True,
                    'expanded': True,
                    'icon': bundle_icon,
                    'children': []
                }
                
                # Add main file as child
                main_child = bundle.main_file.copy()
                main_child['parent_bundle'] = bundle_id
                main_child['is_bundle_child'] = True
                bundle_item['children'].append(main_child)
                
                # Add auxiliary files as children
                for aux_file in bundle.auxiliary_files:
                    aux_child = aux_file.copy()
                    aux_child['parent_bundle'] = bundle_id
                    aux_child['is_bundle_child'] = True
                    bundle_item['children'].append(aux_child)
                
                tree_items.append(bundle_item)
        
        return tree_items

    def _create_uvvis_tree_item(self, bundle: FileBundle) -> Dict[str, Any]:
        """Create tree item for UV-Vis bundle with wells as children."""
        main_file = bundle.main_file
        filled_wells = bundle.wells or []
        
        bundle_item = {
            'id': bundle.bundle_id,
            'name': f"{bundle.base_name} (UV-Vis)",
            'type': 'uvvis_bundle',
            'size_display': f"{len(filled_wells)} wells",
            'is_bundle': True,
            'expanded': True,
            'icon': '📊',
            'children': []
        }
        
        # Add individual wells as children
        for well in filled_wells[:10]:  # Limit to first 10 wells
            well_child = {
                'id': f"{bundle.bundle_id}|{well}",
                'name': f"Well {well}",
                'type': 'uvvis_well',
                'size_display': 'spectrum',
                'parent_bundle': bundle.bundle_id,
                'is_bundle_child': True,
                'well_name': well,
                'parent_file_id': main_file['id']
            }
            bundle_item['children'].append(well_child)
        
        return bundle_item

    def _get_bundle_icon(self, bundle_type: str) -> str:
        """Get icon for bundle type."""
        icons = {
            'chromeleon': '📦',
            'lcms': '🧪',
            'uvvis_multi': '📊'
        }
        return icons.get(bundle_type, '📁')

    def try_create_chromeleon_bundle(self, file_record: Dict[str, Any]) -> Optional[str]:
        """Try to create a Chromeleon bundle from a file record."""
        filename = file_record.get('name', '')
        file_type = file_record.get('type', '')
        
        # Check if this is a Chromeleon main file (UV_VIS pattern)
        main_match = re.match(self.chromeleon_patterns['main'], filename)
        if not main_match:
            return None
        
        base_name = main_match.group(1)
        bundle_id = f"{base_name}_chromeleon"
        
        # Create the bundle with empty auxiliary files initially
        bundle = FileBundle(
            base_name=base_name,
            bundle_type='chromeleon',
            main_file=file_record,
            auxiliary_files=[],
            bundle_id=bundle_id
        )
        
        self.bundles[bundle_id] = bundle
        print(f"📦 Created Chromeleon bundle: {bundle_id}")
        
        return bundle_id

    def add_auxiliary_file_to_bundle(self, bundle_id: str, aux_file: Dict[str, Any]) -> bool:
        """Add an auxiliary file to an existing bundle."""
        if bundle_id not in self.bundles:
            return False
        
        bundle = self.bundles[bundle_id]
        bundle.auxiliary_files.append(aux_file)
        print(f"📎 Added auxiliary file {aux_file.get('name')} to bundle {bundle_id}")
        return True

    def find_chromeleon_bundle_for_file(self, file_record: Dict[str, Any]) -> Optional[str]:
        """Find if this file belongs to an existing Chromeleon bundle."""
        filename = file_record.get('name', '')
        
        # Check if this matches any auxiliary pattern
        for pattern in self.chromeleon_patterns['auxiliary']:
            match = re.match(pattern, filename)
            if match:
                base_name = match.group(1)
                bundle_id = f"{base_name}_chromeleon"
                if bundle_id in self.bundles:
                    return bundle_id
        
        return None

    def create_uvvis_bundle(self, file_record: Dict[str, Any]) -> Optional[str]:
        """Create a UV-Vis bundle for a file with multiple wells."""
        if file_record.get('type') != 'uvvis_csv':
            return None
        
        metadata = file_record.get('metadata', {})
        filled_wells = metadata.get('filled_wells', [])
        
        # Only create bundle if there are multiple wells
        if len(filled_wells) <= 1:
            return None
        
        base_name = self.extract_base_name(file_record['name'], 'uvvis_csv')
        if not base_name:
            base_name = file_record['name'].replace('.csv', '')
        
        bundle_id = f"{base_name}_uvvis"
        
        # Create the bundle
        bundle = FileBundle(
            base_name=base_name,
            bundle_type='uvvis_multi',
            main_file=file_record,
            auxiliary_files=[],
            bundle_id=bundle_id,
            wells=filled_wells
        )
        
        self.bundles[bundle_id] = bundle
        print(f"📊 Created UV-Vis bundle: {bundle_id} with {len(filled_wells)} wells")
        
        return bundle_id

    def get_bundle(self, file_id: str) -> Optional[FileBundle]:
        """Get bundle that contains the given file ID."""
        # Direct bundle lookup
        if file_id in self.bundles:
            return self.bundles[file_id]
        
        # Search in bundle main files
        for bundle in self.bundles.values():
            if bundle.main_file.get('id') == file_id:
                return bundle
            for aux_file in bundle.auxiliary_files:
                if aux_file.get('id') == file_id:
                    return bundle
        
        return None

    def get_bundle_by_id(self, bundle_id: str) -> Optional[FileBundle]:
        """Get bundle by ID."""
        return self.bundles.get(bundle_id)

    def get_file_bundle_id(self, file_id: str) -> Optional[str]:
        """Get bundle ID that contains this file."""
        for bundle_id, bundle in self.bundles.items():
            if bundle.main_file.get('id') == file_id:
                return bundle_id
            for aux_file in bundle.auxiliary_files:
                if aux_file.get('id') == file_id:
                    return bundle_id
        return None

    def remove_bundle(self, bundle_id: str) -> bool:
        """Remove a specific bundle by ID. Returns True if removed."""
        if bundle_id in self.bundles:
            del self.bundles[bundle_id]
            print(f"Removed bundle from manager: {bundle_id}")
            return True
        return False

    def clear_bundles(self):
        """Clear all bundles."""
        self.bundles.clear()
        print("Cleared all bundles")

    def remove_file_from_bundles(self, file_id: str) -> None:
        """Remove a file from all bundles."""
        bundles_to_remove = []
        
        for bundle_id, bundle in self.bundles.items():
            # Remove from main file
            if bundle.main_file.get('id') == file_id:
                bundles_to_remove.append(bundle_id)
                continue
            
            # Remove from auxiliary files
            bundle.auxiliary_files = [
                f for f in bundle.auxiliary_files 
                if f.get('id') != file_id
            ]
        
        # Remove empty bundles
        for bundle_id in bundles_to_remove:
            del self.bundles[bundle_id]
