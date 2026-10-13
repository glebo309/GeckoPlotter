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
    CHROMATOGRAM = "chromatogram"
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
    imported_csv: Optional[bytes] = None
    imported_at: Optional[str] = None


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

    @staticmethod
    def component_display_name(component: Component) -> str:
        """Short display name for a bundle component."""
        role = component.role
        meta = component.metadata or {}
        if meta.get('display_name'):
            return meta['display_name']
        if role in (ComponentRole.MS_POSITIVE, ComponentRole.MS_NEGATIVE):
            label = "+TIC" if role == ComponentRole.MS_POSITIVE else "-TIC"
            if meta.get('mass_spectral_data'):
                return label
            if meta.get('is_tic_only'):
                return label + ' (export)'
            return label
        if role in (ComponentRole.VWD_A, ComponentRole.VWD_B):
            wl = meta.get('wavelength')
            ch = meta.get('detector_channel', role.value[-1].upper())
            if wl:
                return f"UV {wl} nm (Ch {ch})"
            return f"UV Ch {ch}"
        if role == ComponentRole.INTEGRATION:
            return "Integration"
        if role == ComponentRole.PEAK_ANALYSIS:
            return "Peak Analysis"
        if role == ComponentRole.SST:
            return "SST"
        if role == ComponentRole.SUMMARY:
            return "Summary"
        return os.path.splitext(component.original_filename)[0]

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
        self.analysis_history = []
        self.analysis_plot_settings = {}
        self._analysis_previous = {}
        self._component_index: Dict[str, str] = {}
        self._file_index: Dict[str, str] = {}
        self.temp_files: List[str] = []
        self._persistent_state: Dict[str, Any] = {}
        self._shared_plot_settings: Dict[str, Any] = {}
        self._render_caches = []

        # UI state
        self.file_ui_state: Dict[str, Dict[str, Any]] = {}
        self.visibility_state: Dict[str, bool] = {}
        self.collapse_state: Dict[str, str] = {}
        self.instrument_methods: Dict[str, dict] = {}    # parsed LabSolutions methods by key (see shimadzu_method)
        self.instrument_method_files: Dict[str, bytes] = {}   # the original .lcm/.lcd bytes, for the FAIR package
        self.lcms_eic_overlays: Dict[str, List[Dict[str, Any]]] = {}

        # Provenance of the loaded workspace when it came from / went to a
        # .gecko session file (project_name, created_at, path, ...). See
        # services/session_service.py. Empty for a workspace never saved.
        self.session_meta: Dict[str, Any] = {}

        # Domain services
        from .peak_service import PeakService
        from .calibration_service import CalibrationService
        from .integration_service import IntegrationService
        from .plot_settings_service import PlotSettingsService
        from .export_service import ExportService
        from .lcms_service import LCMSService
        from .persistence import ProjectPersistence

        self.peak_service = PeakService(file_id_resolver=self.peak_owner_id,
                                        color_scope_resolver=self._peak_color_scope)
        self.calibration_service = CalibrationService()
        self.integration_service = IntegrationService()
        self.plot_settings_service = PlotSettingsService()
        self.export_service = ExportService()
        self.lcms_service = LCMSService()
        # Loading a page starts an empty workspace. State is saved only through
        # an explicit export, never restored from an implicit local JSON file.
        self.project = ProjectPersistence(self._STATE_FILE, enabled=False)
        from .file_removal_service import FileRemovalService
        self.file_removal_service = FileRemovalService(self)

    def scoped(self, key: str, factory):
        """A helper object that belongs to this workspace (made on first use, dropped with a reset)."""
        registry = self.__dict__.setdefault('_scoped_state', {})
        if key not in registry:
            registry[key] = factory()
        return registry[key]

    def reset_workspace(self) -> None:
        """Discard this local workspace, including undo and temporary uploads.

        Callbacks capture domain service references during registration, so
        those objects must be reset in place rather than abandoned.
        """
        services = {name: value for name, value in vars(self).items()
                    if name.endswith('_service')}
        caches = self._render_caches
        for cache in caches:
            cache.prune([])
        for path in self.temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self.__dict__.clear()
        self.__init__()
        for name, service in services.items():
            fresh = getattr(self, name)
            service.__dict__.clear()
            service.__dict__.update(fresh.__dict__)
            setattr(self, name, service)
        self._render_caches = caches

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

    def rename_dataset(self, file_id: str, name: str) -> bool:
        """Rename the displayed dataset, retaining IDs and original filenames."""
        if not isinstance(name, str) or not name.strip():
            return False
        name = name.strip()
        bundle = self.get_bundle(file_id) or self.get_bundle_for_component(file_id)
        if bundle is None:
            return False
        if file_id == bundle.bundle_id or len(bundle.component_list) == 1:
            if bundle.name == name:
                return False
            bundle.name = name
            for component in bundle.component_list:
                component.metadata['sample_name'] = name
            if len(bundle.component_list) == 1:
                bundle.primary.metadata['display_name'] = name
        else:
            component = next(c for c in bundle.component_list if c.component_id == file_id)
            if Bundle.component_display_name(component) == name:
                return False
            component.metadata['display_name'] = name
        for cache in self._render_caches:
            cache.prune([])
        for key in ('_last_processed_files', '_last_tree_items'):
            if hasattr(self, key):
                delattr(self, key)
        return True

    def get_bundle_for_file(self, original_filename: str) -> Optional[Bundle]:
        bundle_id = self._file_index.get(original_filename)
        return self.get_bundle(bundle_id) if bundle_id else None

    def peak_owner_id(self, file_id: str) -> str:
        """Match the source IDs emitted by loaded_data and PlotManager.

        Ordinary bundles expose their primary signal under the bundle ID;
        LC-MS bundles expose each detector channel independently.
        """
        bundle = self.get_bundle(file_id) or self.get_bundle_for_component(file_id)
        if bundle is None or bundle.primary is None:
            return file_id
        if bundle.bundle_type in (BundleType.CHROMATOGRAM, BundleType.LCMS):
            return bundle.primary.component_id if file_id == bundle.bundle_id else file_id
        if file_id == bundle.primary.component_id:
            return bundle.bundle_id
        return file_id

    def add_bundle(self, bundle: Bundle) -> None:
        from .research_package import csv_bytes, now
        for component in bundle.component_list:
            if component.imported_at is None:
                component.imported_at = now()
                component.imported_csv = csv_bytes(component.dataframe) if component.dataframe is not None else None
        if bundle.bundle_id in self._bundles:
            self.remove_bundle(bundle.bundle_id)

        from .bundling_service import paired_tic_exports
        for trace, spectral in paired_tic_exports(bundle):
            # Prefer the spectral source as in the former StorageManager. Keep
            # the original export available and respect an explicit eye toggle.
            self.visibility_state.setdefault(trace.component_id, False)
            bundle.components[spectral.role] = spectral

        self._bundles[bundle.bundle_id] = bundle
        for component in bundle.component_list:
            self._component_index[component.component_id] = bundle.bundle_id
            self._file_index[component.original_filename] = bundle.bundle_id

    def rekey_bundle(self, bundle_id: str, new_bundle_id: Optional[str] = None,
                     component_ids: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Give a loaded bundle (and/or some of its components) new ids.

        Every index and every id-keyed state map follows the change, so nothing
        silently detaches: ``_bundles``, ``_component_index``, ``_file_index``
        (and therefore ``loaded_data``), visibility/collapse/file-UI state,
        group overrides, LC-MS EIC overlays, peaks and the PDA / source
        pointers inside component metadata.

        ``component_ids`` maps old component id -> new component id. Returns the
        complete ``{old_id: new_id}`` mapping that was applied (empty when
        nothing changed). Raises ``KeyError`` for an unknown bundle and
        ``ValueError`` for unknown components or ids that are already in use.
        Used by session restore to give freshly ingested data the ids that the
        saved analysis refers to.
        """
        bundle = self._bundles.get(bundle_id)
        if bundle is None:
            raise KeyError(bundle_id)
        new_bundle_id = new_bundle_id or bundle_id
        mapping = {old: new for old, new in (component_ids or {}).items() if old != new}
        own = {c.component_id for c in bundle.component_list}
        unknown = set(mapping) - own
        if unknown:
            raise ValueError(f"Not components of bundle {bundle_id!r}: {sorted(unknown)}")
        if new_bundle_id != bundle_id:
            mapping[bundle_id] = new_bundle_id
        if not mapping:
            return {}
        new_ids = list(mapping.values())
        if len(set(new_ids)) != len(new_ids):
            raise ValueError("New ids must be unique.")
        in_use = (set(self._bundles) - {bundle_id}) | {
            cid for cid, bid in self._component_index.items() if bid != bundle_id}
        clash = set(new_ids) & in_use
        if clash:
            raise ValueError(f"Ids already in use: {sorted(clash)}")

        pointer_keys = ('pda_source_id', 'source_file_id')
        seen = set()
        for component in bundle.component_list:
            for meta in (component.metadata, getattr(component.standardized, 'metadata', None)):
                if not isinstance(meta, dict) or id(meta) in seen:
                    continue
                seen.add(id(meta))
                for key in pointer_keys:
                    if meta.get(key) in mapping:
                        meta[key] = mapping[meta[key]]
            component.component_id = mapping.get(component.component_id, component.component_id)
        bundle.bundle_id = new_bundle_id

        self._bundles = {(new_bundle_id if key == bundle_id else key): value
                         for key, value in self._bundles.items()}
        for old in [k for k, v in self._component_index.items() if v == bundle_id]:
            self._component_index.pop(old)
        for component in bundle.component_list:
            self._component_index[component.component_id] = new_bundle_id
        for name, value in list(self._file_index.items()):
            if value == bundle_id:
                self._file_index[name] = new_bundle_id

        for attr in ('visibility_state', 'collapse_state', 'lcms_eic_overlays',
                     'group_overrides', '_dataframe_digests'):
            current = self.__dict__.get(attr)
            if current:
                renamed = {_rekey_key(k, mapping): v for k, v in current.items()}
                current.clear()
                current.update(renamed)
        renamed = {}
        for key, value in self.file_ui_state.items():
            new_key = _rekey_key(key, mapping)
            if isinstance(value, dict) and value.get('file_id') in mapping:
                value = {**value, 'file_id': mapping[value['file_id']]}
            renamed[new_key] = value
        self.file_ui_state.clear()
        self.file_ui_state.update(renamed)
        masks = self.__dict__.get('_hidden_sample_channels')
        if masks:
            renamed = {_rekey_key(k, mapping): {_rekey_key(s, mapping): v for s, v in inner.items()}
                       for k, inner in masks.items()}
            masks.clear()
            masks.update(renamed)
        self.peak_service.rekey_files(mapping)
        for cache in self._render_caches:
            cache.prune([])
        return mapping

    def remove_bundle(self, bundle_id: str) -> Optional[Bundle]:
        bundle = self._bundles.pop(bundle_id, None)
        if bundle is None:
            return None

        for component in bundle.component_list:
            self._component_index.pop(component.component_id, None)
            if self._file_index.get(component.original_filename) == bundle_id:
                self._file_index.pop(component.original_filename, None)

        return bundle

    def remove_component(self, component_id: str) -> Optional[Component]:
        """Remove a trace from its bundle and keep role and file indexes consistent."""
        bundle = self.get_bundle_for_component(component_id)
        if bundle is None:
            return None
        component = next(c for c in bundle.component_list if c.component_id == component_id)
        bundle.component_list = [c for c in bundle.component_list if c.component_id != component_id]
        bundle.components = {}
        for remaining in bundle.component_list:
            bundle.components.setdefault(remaining.role, remaining)
        self._component_index.pop(component_id, None)
        if not any(c.original_filename == component.original_filename for c in bundle.component_list):
            self._file_index.pop(component.original_filename, None)
        if not bundle.component_list:
            self.remove_bundle(bundle.bundle_id)
        return component

    def clear(self) -> None:
        self.file_removal_service.clear()
        self._bundles.clear()
        self.analysis_history.clear()
        self.analysis_plot_settings = {}
        self._analysis_previous = {}
        self._component_index.clear()
        self._file_index.clear()
        self.file_ui_state.clear()
        self.visibility_state.clear()
        self.collapse_state.clear()
        self.__dict__.pop("_channel_combine_modes", None)
        self.__dict__.pop("_hidden_sample_channels", None)
        self.lcms_eic_overlays.clear()
        if hasattr(self, 'project'):
            self.project.clear()

    def all_bundles(self) -> Dict[str, Bundle]:
        return dict(self._bundles)

    def iter_bundles(self) -> Iterator[Bundle]:
        # Callbacks can remove/restore bundles while another callback records
        # provenance. Freeze membership, retaining the original data references.
        return iter(tuple(self._bundles.values()))

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
            'sample_name': component.metadata.get('sample_name') or (component.standardized.sample_name if component.standardized and component.standardized.sample_name else bundle.sample_name),
            'file_name': component.original_filename,
            'parent_bundle_id': bundle.bundle_id,
            'parent_bundle_name': bundle.name,
            'component_role': component.role.value,
        }

        return {
            'record': {
                'id': record_id or component.component_id,
                'name': record_name or Bundle.component_display_name(component),
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
            if bundle.bundle_type in (BundleType.CHROMATOGRAM, BundleType.LCMS):
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
            display_type = (
                bundle.source_category.value
                if bundle.source_category != SourceCategory.GENERIC
                else bundle.bundle_type.value
            )
            items.append({
                'id': bundle.bundle_id,
                'name': bundle.name,
                'type': display_type,
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
            'toolbox_tab': 'plot-tools',
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

    def remove_lcms_bundle(self, base_name):
        for bundle in list(self._bundles.values()):
            if bundle.bundle_type == BundleType.LCMS and bundle.name == base_name:
                return self.remove_bundle(bundle.bundle_id)
        return None

    def _peak_color_scope(self, file_id: str) -> str:
        """Match comparable signals across runs, independent of plot tabs/range."""
        from callbacks.viz_callbacks import _get_overlay_group
        entry = self.get_data_by_id(file_id) or {}
        group = _get_overlay_group(entry.get('metadata', {}), entry,
                                   file_id=file_id, dm=self)
        # Source and axis distinguish, for example, chromatograms from spectra.
        # Acquisition duration and the LC-MS run ID must not split compounds.
        return repr(group[:2])

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
            p = bundle.primary
            well_columns = []
            if p is not None and p.plot_hint == PlotHint.MULTI_Y:
                well_columns = list(
                    p.metadata.get('filled_wells')
                    or [c for c, r in p.column_roles.items() if r == ColumnRole.Y]
                )
            item = {
                'id': bundle.bundle_id,
                'name': bundle.name,
                'type': (
                    bundle.source_category.value
                    if bundle.source_category != SourceCategory.GENERIC
                    else bundle.bundle_type.value
                ),
                'is_bundle': is_bundle,
                'icon': '📦' if is_bundle else '📄',
                'size_display': f'{len(well_columns)} series' if well_columns else '',
            }
            if is_bundle:
                item['children'] = [
                    {'id': c.component_id, 'name': Bundle.component_display_name(c),
                     'type': c.role.value, 'is_child': True, 'original_filename': c.original_filename}
                    for c in bundle.component_list
                ]
            elif well_columns:
                item['children'] = [
                    {'id': f'{bundle.bundle_id}|{well}', 'name': str(well),
                     'type': 'uvvis_well', 'is_child': True,
                     'well_name': well}
                    for well in well_columns
                ]
            items.append(item)
        return items


def _rekey_key(key: Any, mapping: Dict[str, str]) -> Any:
    """Map an id-keyed state key; ``"<id>|<well>"`` keys follow their id."""
    if not isinstance(key, str):
        return key
    if key in mapping:
        return mapping[key]
    head, sep, tail = key.partition('|')
    return mapping[head] + sep + tail if sep and head in mapping else key


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
            {'id': c.component_id, 'name': Bundle.component_display_name(c)}
            for c in bundle.component_list
            if c.role != ComponentRole.PRIMARY
        ]
