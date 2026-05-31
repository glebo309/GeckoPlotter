from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pandas as pd

log = logging.getLogger(__name__)

try:
    from ..ingestion.types import ColumnRole, PlotHint, SourceCategory, StandardizedResult
except ImportError:
    try:
        from src.ingestion.types import ColumnRole, PlotHint, SourceCategory, StandardizedResult
    except ImportError:
        from ingestion.types import ColumnRole, PlotHint, SourceCategory, StandardizedResult


class ComponentRole(str, Enum):
    PRIMARY = "primary"
    INTEGRATION = "integration"
    SST = "sst"
    PEAK_ANALYSIS = "peak_analysis"
    SUMMARY = "summary"
    MS_POSITIVE = "ms_positive"
    MS_NEGATIVE = "ms_negative"
    VWD_A = "vwd_a"
    VWD_B = "vwd_b"
    GENERIC = "generic"


class BundleType(str, Enum):
    CHROMELEON = "chromeleon"
    LCMS = "lcms"
    PLATE_READER = "plate_reader"
    EXCEL = "excel"
    KINETICS = "kinetics"
    GENERIC = "generic"


@dataclass
class Component:
    component_id: str
    role: ComponentRole
    original_filename: str
    raw_bytes: bytes = b""
    dataframe: Optional[pd.DataFrame] = None
    column_roles: Dict[str, ColumnRole] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_category: SourceCategory = SourceCategory.GENERIC
    plot_hint: PlotHint = PlotHint.LINE
    standardized: Optional[StandardizedResult] = None


@dataclass
class Bundle:
    bundle_id: str
    name: str
    bundle_type: BundleType
    components: Dict[ComponentRole, Component] = field(default_factory=dict)
    component_list: List[Component] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.components and not self.component_list:
            self.component_list = list(self.components.values())
        elif self.component_list and not self.components:
            for component in self.component_list:
                self.components.setdefault(component.role, component)
        elif self.component_list:
            for component in self.component_list:
                self.components.setdefault(component.role, component)

    @property
    def primary(self) -> Optional[Component]:
        for role in (
            ComponentRole.PRIMARY,
            ComponentRole.MS_POSITIVE,
            ComponentRole.VWD_A,
            ComponentRole.MS_NEGATIVE,
            ComponentRole.VWD_B,
            ComponentRole.GENERIC,
        ):
            component = self.components.get(role)
            if component is not None and component.dataframe is not None:
                return component

        for component in self.component_list:
            if component.dataframe is not None:
                return component

        return self.component_list[0] if self.component_list else None

    @property
    def dataframe(self) -> Optional[pd.DataFrame]:
        return self.primary.dataframe if self.primary else None

    @property
    def column_roles(self) -> Dict[str, ColumnRole]:
        return dict(self.primary.column_roles) if self.primary else {}

    @property
    def source_category(self) -> SourceCategory:
        return self.primary.source_category if self.primary else SourceCategory.GENERIC

    @property
    def plot_hint(self) -> PlotHint:
        return self.primary.plot_hint if self.primary else PlotHint.LINE

    @property
    def metadata(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for component in self.component_list:
            merged.update(component.metadata or {})
        return merged

    @property
    def sample_name(self) -> str:
        if self.metadata.get("sample_name"):
            return str(self.metadata["sample_name"])
        if self.primary and self.primary.standardized and self.primary.standardized.sample_name:
            return self.primary.standardized.sample_name
        return self.name

    @property
    def x_columns(self) -> List[str]:
        return [column for column, role in self.column_roles.items() if role == ColumnRole.X]

    @property
    def y_columns(self) -> List[str]:
        return [column for column, role in self.column_roles.items() if role == ColumnRole.Y]

    def get_component(self, role: ComponentRole) -> Optional[Component]:
        return self.components.get(role)

    def has_integration_data(self) -> bool:
        return self.get_component(ComponentRole.INTEGRATION) is not None

    def get_integration_text(self) -> Optional[str]:
        component = self.get_component(ComponentRole.INTEGRATION)
        if component is None or not component.raw_bytes:
            return None

        for encoding in ("utf-8", "utf-16", "latin-1"):
            try:
                return component.raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return component.raw_bytes.decode("utf-8", errors="replace")


class DataStore:
    """Single source of truth for all loaded data. Every item is a Bundle.

    Also hosts domain services (peaks, calibration, integration, etc.)
    and provides backward-compatible methods so existing callbacks can
    be migrated incrementally.
    """

    _STATE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'file_state.json',
    )

    def __init__(self) -> None:
        self._bundles: Dict[str, Bundle] = {}
        self._component_index: Dict[str, str] = {}
        self._file_index: Dict[str, str] = {}
        self.temp_files: List[str] = []

        # UI state
        self.file_ui_state: Dict[str, Dict[str, Any]] = {}
        self.visibility_state: Dict[str, bool] = {}
        self.collapse_state: Dict[str, str] = {}
        self.lcms_eic_overlays: Dict[str, List[Dict[str, Any]]] = {}

        # Domain services
        from .peak_service import PeakService
        from .calibration_service import CalibrationService
        from .integration_service import IntegrationService
        from .plot_settings_service import PlotSettingsService
        from .export_service import ExportService
        from .lcms_service import LCMSService
        from .persistence import ProjectPersistence

        self.peak_service = PeakService()
        self.calibration_service = CalibrationService()
        self.integration_service = IntegrationService()
        self.plot_settings_service = PlotSettingsService()
        self.export_service = ExportService()
        self.lcms_service = LCMSService()
        self.project = ProjectPersistence(self._STATE_FILE)
        self._restore_services()

    def _restore_services(self) -> None:
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
            log.warning("Could not restore services: %s", e)

    def persist_services(self) -> None:
        self.project.set_section('peaks', self.peak_service.serialize(), auto_save=False)
        self.project.set_section('calibrations', self.calibration_service.serialize(), auto_save=False)
        self.project.set_section('integration_settings', self.integration_service.serialize(), auto_save=False)
        self.project.save()

    def get_bundle(self, bundle_id: str) -> Optional[Bundle]:
        return self._bundles.get(bundle_id)

    def get_bundle_for_component(self, component_id: str) -> Optional[Bundle]:
        bundle_id = self._component_index.get(component_id)
        return self.get_bundle(bundle_id) if bundle_id else None

    def get_bundle_for_file(self, original_filename: str) -> Optional[Bundle]:
        bundle_id = self._file_index.get(original_filename)
        return self.get_bundle(bundle_id) if bundle_id else None

    def add_bundle(self, bundle: Bundle) -> None:
        if bundle.bundle_id in self._bundles:
            self.remove_bundle(bundle.bundle_id)

        self._bundles[bundle.bundle_id] = bundle
        for component in bundle.component_list:
            self._component_index[component.component_id] = bundle.bundle_id
            self._file_index[component.original_filename] = bundle.bundle_id

    def remove_bundle(self, bundle_id: str) -> Optional[Bundle]:
        bundle = self._bundles.pop(bundle_id, None)
        if bundle is None:
            return None

        for component in bundle.component_list:
            self._component_index.pop(component.component_id, None)
            if self._file_index.get(component.original_filename) == bundle_id:
                self._file_index.pop(component.original_filename, None)

        return bundle

    def clear(self) -> None:
        self._bundles.clear()
        self._component_index.clear()
        self._file_index.clear()
        self.lcms_eic_overlays.clear()

    def all_bundles(self) -> Dict[str, Bundle]:
        return dict(self._bundles)

    def iter_bundles(self) -> Iterator[Bundle]:
        return iter(self._bundles.values())

    def get_dataframe(self, bundle_id: str) -> Optional[pd.DataFrame]:
        bundle = self.get_bundle(bundle_id)
        return bundle.dataframe if bundle else None

    def get_xy_arrays(self, bundle_id: str) -> Tuple[Optional[Any], Optional[Any]]:
        bundle = self.get_bundle(bundle_id)
        if bundle is None:
            return None, None

        df = bundle.dataframe
        if df is None:
            return None, None

        primary = bundle.primary
        metadata = primary.metadata if primary else {}
        x_col = metadata.get("auto_x") or bundle.metadata.get("auto_x")
        y_cols = metadata.get("auto_y") or bundle.metadata.get("auto_y")

        if not x_col and bundle.x_columns:
            x_col = bundle.x_columns[0]
        if not y_cols and bundle.y_columns:
            y_cols = bundle.y_columns

        if not x_col or not y_cols:
            numeric = df.select_dtypes(include="number").columns.tolist()
            if len(numeric) >= 2:
                x_col = numeric[0]
                y_cols = [numeric[1]]

        y_col = y_cols[0] if isinstance(y_cols, list) else y_cols
        if not x_col or not y_col or x_col not in df.columns or y_col not in df.columns:
            return None, None

        return (
            df[x_col].to_numpy(dtype=float),
            df[y_col].to_numpy(dtype=float),
        )

    # ------------------------------------------------------------------
    # Backward-compatible API (allows incremental callback migration)
    # ------------------------------------------------------------------

    def get_data_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Compat: returns old-style dict {record, data, metadata, standardized}."""
        bundle = self.get_bundle(file_id)
        if not bundle:
            bundle = self.get_bundle_for_component(file_id)
            if not bundle:
                return None
            component = next(
                (c for c in bundle.component_list if c.component_id == file_id),
                None,
            )
            return self._component_data_entry(bundle, component) if component else None

        p = bundle.primary
        return self._component_data_entry(bundle, p, record_id=bundle.bundle_id, record_name=bundle.name) if p else None

    def _component_data_entry(
        self,
        bundle: Bundle,
        component: Optional[Component],
        *,
        record_id: Optional[str] = None,
        record_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Build the old callback-facing data dict for one bundle component."""
        if component is None:
            return None

        x_columns = [
            column
            for column, role in component.column_roles.items()
            if role == ColumnRole.X
        ]
        y_columns = [
            column
            for column, role in component.column_roles.items()
            if role == ColumnRole.Y
        ]

        metadata = {
            **component.metadata,
            'auto_x': component.metadata.get('auto_x', x_columns[0] if x_columns else None),
            'auto_y': component.metadata.get('auto_y', y_columns if y_columns else None),
            'sample_name': component.standardized.sample_name if component.standardized and component.standardized.sample_name else bundle.sample_name,
            'file_name': component.original_filename,
            'parent_bundle_id': bundle.bundle_id,
            'parent_bundle_name': bundle.name,
            'component_role': component.role.value,
        }

        return {
            'record': {
                'id': record_id or component.component_id,
                'name': record_name or component.original_filename,
                'type': component.role.value,
                'parent_bundle_id': bundle.bundle_id,
            },
            'data': component.dataframe,
            'metadata': metadata,
            'standardized': component.standardized,
            'eic_overlays': self.get_lcms_eic_overlays(component.component_id),
        }

    def add_lcms_eic_overlay(self, file_id: str, overlay: Dict[str, Any]) -> None:
        """Store an LC-MS EIC overlay against a stable component id."""
        if not file_id:
            return
        self.lcms_eic_overlays.setdefault(file_id, []).append(overlay)

    def get_lcms_eic_overlays(self, file_id: str) -> List[Dict[str, Any]]:
        """Return EIC overlays for a component id without exposing internals."""
        if not file_id:
            return []
        return list(self.lcms_eic_overlays.get(file_id, []))

    def clear_lcms_eic_overlays(self, file_id: str) -> None:
        """Clear EIC overlays for one LC-MS component."""
        if file_id:
            self.lcms_eic_overlays.pop(file_id, None)

    def get_bundle_by_id(self, bundle_id: str):
        """Compat: returns a compat object with .main_file, .bundle_id, .base_name."""
        bundle = self.get_bundle(bundle_id)
        if not bundle:
            return None
        return _BundleCompat(bundle)

    def get_loaded_data(self) -> Dict[str, Dict[str, Any]]:
        """Compat: returns old-style loaded_data dict."""
        result = {}
        for bid, bundle in self._bundles.items():
            entry = self.get_data_by_id(bid)
            if entry:
                result[bid] = entry
        return result

    @property
    def loaded_data(self) -> Dict[str, Dict[str, Any]]:
        """Compat property: direct access pattern used by some callbacks."""
        result = {}
        for bid, bundle in self._bundles.items():
            if bundle.bundle_type == BundleType.LCMS and len(bundle.component_list) > 1:
                for component in bundle.component_list:
                    entry = self._component_data_entry(bundle, component)
                    if entry:
                        result[component.component_id] = entry
            else:
                entry = self.get_data_by_id(bid)
                if entry:
                    result[bid] = entry
        return result

    def get_loaded_files_list(self) -> List[Dict[str, Any]]:
        """Return the format that loaded-files dcc.Store expects."""
        items = []
        for bundle in self._bundles.values():
            items.append({
                'id': bundle.bundle_id,
                'name': bundle.name,
                'type': bundle.bundle_type.value,
                'size_display': '',
            })
        return items

    def clear_data(self) -> None:
        """Compat: clears all data and services."""
        self.clear()
        self.peak_service.clear_all_peaks()
        for f in self.temp_files:
            try:
                os.unlink(f)
            except OSError:
                pass
        self.temp_files.clear()

    def register_file_id(self, file_id: str, filename: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Per-file UI state
    # ------------------------------------------------------------------

    def build_default_file_state(self, file_id=None, file_data=None):
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

    def get_file_state(self, file_id=None, file_data=None):
        import copy
        if not file_id:
            return self.build_default_file_state(file_id, file_data)
        if file_id not in self.file_ui_state:
            self.file_ui_state[file_id] = self.build_default_file_state(file_id, file_data)
        state = copy.deepcopy(self.file_ui_state[file_id])
        state['file_id'] = file_id
        return state

    def save_file_state(self, file_id=None, state=None):
        import copy
        if not file_id:
            return self.build_default_file_state(file_id)
        existing = self.get_file_state(file_id)
        merged = copy.deepcopy(existing)
        if state:
            merged.update(copy.deepcopy(state))
        merged['file_id'] = file_id
        self.file_ui_state[file_id] = merged
        return copy.deepcopy(merged)

    def clear_file_state(self, file_id=None):
        if file_id:
            self.file_ui_state.pop(file_id, None)

    @property
    def publication_memory(self):
        import copy
        memory = {}
        for fid, state in self.file_ui_state.items():
            sel = state.get('pub_selections')
            if sel is not None:
                memory[fid] = copy.deepcopy(sel)
        return memory

    def initialise_publication_memory(self, file_id, selections=None):
        import copy
        if not file_id:
            return {}
        state = self.get_file_state(file_id)
        if not state.get('pub_selections'):
            state['pub_selections'] = copy.deepcopy(selections or {})
            self.save_file_state(file_id, state)
        return copy.deepcopy(self.get_file_state(file_id).get('pub_selections', {}))

    def get_publication_memory(self, file_id=None):
        import copy
        if not file_id:
            return None
        return copy.deepcopy(self.get_file_state(file_id).get('pub_selections'))

    def save_publication_memory(self, file_id, selections):
        import copy
        if not file_id:
            return
        state = self.get_file_state(file_id)
        state['pub_selections'] = copy.deepcopy(selections or {})
        self.save_file_state(file_id, state)

    def delete_publication_memory(self, file_id):
        if not file_id:
            return
        state = self.get_file_state(file_id)
        state['pub_selections'] = self.build_default_file_state(file_id).get('pub_selections', {})
        self.save_file_state(file_id, state)

    def clear_publication_memory(self):
        for file_id in list(self.file_ui_state.keys()):
            self.delete_publication_memory(file_id)

    # Stubs for remaining compat methods
    _persistent_state: Dict[str, Any] = {}
    _shared_plot_settings: Dict[str, Any] = {}

    def remove_lcms_bundle(self, base_name):
        for bundle in list(self._bundles.values()):
            if bundle.bundle_type == BundleType.LCMS and bundle.name == base_name:
                return self.remove_bundle(bundle.bundle_id)
        return None

    def build_file_overlay_map(self) -> Dict[str, str]:
        """Build {file_id: overlay_group_key_string} for peak color scoping."""
        from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
        result = {}
        for bid, bundle in self._bundles.items():
            entry = self.get_data_by_id(bid)
            if not entry:
                continue
            metadata = entry.get('metadata', {})
            group = _get_overlay_group(metadata, entry, file_id=bid, dm=self)
            result[bid] = _tab_id_from_group(group)
        return result

    def persist_file_state(self, file_id):
        pass

    def get_lcms_bundle_by_id(self, bundle_id: str):
        """Compat: LC-MS bundles are just regular bundles now."""
        bundle = self.get_bundle(bundle_id)
        if bundle and bundle.bundle_type == BundleType.LCMS:
            return self.get_data_by_id(bundle_id)
        return None

    def find_lcms_bundle_for_component(self, component_id):
        """Compat: returns (base_name, bundle_data) or (None, None)."""
        bundle = self.get_bundle_for_component(component_id)
        if bundle and bundle.bundle_type == BundleType.LCMS:
            return bundle.name, self.get_data_by_id(bundle.bundle_id)
        return None, None

    @property
    def bundle_manager(self):
        """Compat shim for callbacks that access data_manager.bundle_manager."""
        return _BundleManagerCompat(self)

    @property
    def lcms_bundles(self) -> Dict[str, Any]:
        """Compat: returns LC-MS bundles in old format."""
        result = {}
        for bundle in self._bundles.values():
            if bundle.bundle_type == BundleType.LCMS:
                result[bundle.name] = self.get_data_by_id(bundle.bundle_id)
        return result

    def get_bundled_tree_items(self, loaded_files=None):
        """Compat: returns tree items for file tree rendering."""
        items = []
        for bundle in self._bundles.values():
            is_bundle = len(bundle.component_list) > 1
            item = {
                'id': bundle.bundle_id,
                'name': bundle.name,
                'type': bundle.bundle_type.value,
                'is_bundle': is_bundle,
                'icon': '📦' if is_bundle else '📄',
                'size_display': '',
            }
            if is_bundle:
                item['children'] = [
                    {'id': c.component_id, 'name': c.original_filename,
                     'type': c.role.value, 'is_child': True}
                    for c in bundle.component_list
                ]
            items.append(item)
        return items


class _BundleManagerCompat:
    """Shim for data_manager.bundle_manager.* access patterns."""

    def __init__(self, store: 'DataStore'):
        self._store = store

    @property
    def bundles(self) -> Dict[str, _BundleCompat]:
        return {bid: _BundleCompat(b) for bid, b in self._store._bundles.items()}

    def get_bundle_by_id(self, bundle_id: str):
        return self._store.get_bundle_by_id(bundle_id)

    def clear_bundles(self):
        self._store.clear()

    def remove_bundle(self, bundle_id: str):
        self._store.remove_bundle(bundle_id)

    def get_bundle_tree_items(self):
        return self._store.get_bundled_tree_items()


class _BundleCompat:
    """Shim so old callbacks that access bundle.main_file, bundle.bundle_id etc. still work."""

    def __init__(self, bundle: Bundle):
        self._bundle = bundle
        self.bundle_id = bundle.bundle_id
        self.base_name = bundle.name
        self.bundle_type = bundle.bundle_type.value
        p = bundle.primary
        self.main_file = {
            'id': bundle.bundle_id,
            'name': p.original_filename if p else bundle.name,
        } if p else None
        self.auxiliary_files = [
            {'id': c.component_id, 'name': c.original_filename}
            for c in bundle.component_list
            if c.role != ComponentRole.PRIMARY
        ]
