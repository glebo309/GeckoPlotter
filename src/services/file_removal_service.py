"""Reversible removal from the workspace; source files are never deleted.

Large arrays stay referenced by the removal record instead of being copied.
Only state belonging to removed items is restored, preserving later edits to
other files. Peak editing keeps its own independent undo history.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class FileRemoval:
    label: str
    active_file: str | None
    bundles: list = field(default_factory=list)
    removed_ids: set = field(default_factory=set)
    component_ids: set | None = None
    maps: dict = field(default_factory=dict)
    peaks: dict = field(default_factory=dict)
    imported: set = field(default_factory=set)
    color_indexes: dict = field(default_factory=dict)
    order: list = field(default_factory=list)


class FileRemovalService:
    MAX_UNDO = 10
    STATE_MAPS = ('file_ui_state', 'visibility_state', 'collapse_state',
                  'lcms_eic_overlays', 'group_overrides')

    def __init__(self, store):
        self.store = store
        self._history = []

    @property
    def can_undo(self):
        return bool(self._history)

    @property
    def latest(self):
        return self._history[-1] if self._history else None

    def clear(self):
        self._history.clear()

    def _capture(self, bundles, label, active_file, ids, component_ids=None):
        # Bundle containers are copied; immutable loaded arrays are shared.
        snapshots = [replace(b, component_list=list(b.component_list),
                             components=dict(b.components)) for b in bundles]
        state_ids = set(ids)
        for mapping in self.STATE_MAPS:
            state_ids.update(key for key in getattr(self.store, mapping, {})
                             if key.split('|')[0] in ids)
        state_ids.update(key for key in self.store.peak_service._peaks
                         if key.split('|')[0] in ids)
        record = FileRemoval(label, active_file, snapshots, state_ids, component_ids,
                             order=list(self.store.all_bundles()))
        for mapping in self.STATE_MAPS:
            values = getattr(self.store, mapping, {})
            record.maps[mapping] = {key: copy.deepcopy(values[key]) for key in state_ids if key in values}
        service = self.store.peak_service
        record.peaks = {key: copy.deepcopy(service._peaks[key]) for key in state_ids if key in service._peaks}
        record.imported = service._imported_files.intersection(state_ids)
        record.color_indexes = {key: service._file_color_index[key] for key in state_ids if key in service._file_color_index}
        self._history.append(record)
        self._history = self._history[-self.MAX_UNDO:]
        return record

    def _remove_state(self, record):
        for mapping in self.STATE_MAPS:
            values = getattr(self.store, mapping, {})
            for key in record.removed_ids:
                values.pop(key, None)
        for key in record.removed_ids:
            self.store.peak_service.clear_peaks(key)

    def remove(self, file_id, active_file=None):
        parent, sep, well = file_id.partition('|')
        bundle = self.store.get_bundle(parent) or self.store.get_bundle_for_component(parent)
        if bundle is None:
            return None
        if sep:
            component = next((c for c in bundle.component_list if c.component_id == parent), bundle.primary)
            if component is None or component.dataframe is None or well not in component.dataframe.columns:
                return None
            y_columns = (component.standardized.y_columns if component.standardized is not None
                         else component.metadata.get('filled_wells', []))
            last_well = bool(y_columns) and not [name for name in y_columns if name != well]
            ids = {file_id, component.component_id} if last_well else {file_id}
            if last_well and len(bundle.component_list) == 1:
                ids.add(bundle.bundle_id)
            record = self._capture([bundle], well, active_file, ids, {component.component_id})
            if last_well:
                self.store.remove_component(component.component_id)
                self._remove_state(record)
                return record
            remaining = component.dataframe.drop(columns=[well])
            roles = {key: value for key, value in component.column_roles.items() if key != well}
            metadata = dict(component.metadata)
            metadata['filled_wells'] = [name for name in metadata.get('filled_wells', []) if name != well]
            standardized = component.standardized
            if standardized is not None:
                sr_meta = dict(standardized.metadata)
                sr_meta['filled_wells'] = [name for name in standardized.y_columns if name != well]
                standardized = replace(standardized, data=remaining, column_roles=roles, metadata=sr_meta)
            replacement = replace(component, dataframe=remaining, column_roles=roles,
                                  metadata=metadata, standardized=standardized)
            bundle.component_list = [replacement if c.component_id == component.component_id else c
                                     for c in bundle.component_list]
            bundle.components = {}
            for c in bundle.component_list:
                bundle.components.setdefault(c.role, c)
        elif self.store.get_bundle(file_id) is not None:
            ids = {bundle.bundle_id, *(c.component_id for c in bundle.component_list)}
            record = self._capture([bundle], bundle.name, active_file, ids)
            self.store.remove_bundle(bundle.bundle_id)
        else:
            component = next(c for c in bundle.component_list if c.component_id == file_id)
            record = self._capture([bundle], bundle.component_display_name(component), active_file,
                                   {file_id}, {file_id})
            self.store.remove_component(file_id)
        self._remove_state(record)
        return record

    def remove_all(self, active_file=None):
        bundles = list(self.store.iter_bundles())
        if not bundles:
            return None
        ids = {b.bundle_id for b in bundles}
        ids.update(c.component_id for b in bundles for c in b.component_list)
        record = self._capture(bundles, f'{len(bundles)} loaded file' + ('s' if len(bundles) != 1 else ''),
                               active_file, ids)
        for bundle in bundles:
            self.store.remove_bundle(bundle.bundle_id)
        self._remove_state(record)
        return record

    def undo(self):
        if not self._history:
            return None
        record = self._history.pop()
        for original in record.bundles:
            current = self.store.get_bundle(original.bundle_id)
            if record.component_ids is not None and current is not None:
                # Restore the removed component without replacing sibling edits.
                restored = {c.component_id: c for c in current.component_list
                            if c.component_id not in record.component_ids}
                restored.update({c.component_id: c for c in original.component_list
                                 if c.component_id in record.component_ids})
                ordered = [restored.pop(c.component_id) for c in original.component_list
                           if c.component_id in restored]
                ordered.extend(restored.values())
                original = replace(current, component_list=ordered, components={})
            self.store.add_bundle(original)
        existing = self.store.all_bundles()
        self.store._bundles = {key: existing.pop(key) for key in record.order if key in existing}
        self.store._bundles.update(existing)
        for mapping, values in record.maps.items():
            if not hasattr(self.store, mapping):
                setattr(self.store, mapping, {})
            getattr(self.store, mapping).update(values)
        service = self.store.peak_service
        service._peaks.update(record.peaks)
        service._imported_files.update(record.imported)
        service._file_color_index.update(record.color_indexes)
        return record
