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
    source_transfers: list = field(default_factory=list)
    batch: int = 0  # Records sharing a non-zero batch id are undone together
    batch_label: str = ''


class FileRemovalService:
    MAX_UNDO = 10
    STATE_MAPS = ('file_ui_state', 'visibility_state', 'collapse_state',
                  'lcms_eic_overlays', 'group_overrides')

    def __init__(self, store):
        self.store = store
        self._history = []
        self._batching = False
        self._batch_seq = 0

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
        if not self._batching:
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
            ids = {file_id}
            if len(bundle.component_list) == 1:
                # Removing the final signal also removes its bundle. Imported
                # peaks and plot settings may be keyed by that bundle ID.
                ids.add(bundle.bundle_id)
            record = self._capture([bundle], bundle.component_display_name(component), active_file,
                                   ids, {file_id})
            self.store.remove_component(file_id)
        self._remove_state(record)
        return record

    def remove_many(self, file_ids, active_file=None):
        """Remove several rows as one undo step; ids already gone with an earlier row are skipped."""
        records = []
        self._batching = True
        try:
            for file_id in dict.fromkeys(file_ids):
                record = self.remove(file_id, active_file=active_file)
                if record is not None:
                    records.append(record)
        finally:
            self._batching = False
        if len(records) < 2:
            self._history = self._history[-self.MAX_UNDO:]
            return records[0] if records else None
        self._batch_seq += 1
        label = f'{len(records)} items'
        for record in records:
            record.batch, record.batch_label = self._batch_seq, label
        self._history = self._history[-max(self.MAX_UNDO, len(records)):]
        return replace(records[-1], label=label,
                       removed_ids=set().union(*(r.removed_ids for r in records)))

    @staticmethod
    def _with_metadata(component, metadata, **changes):
        standardized = component.standardized
        if standardized is not None:
            standardized = replace(standardized, metadata=metadata)
        return replace(component, metadata=metadata, standardized=standardized, **changes)

    def _retain_sample_sources(self, bundle, removed, record):
        """Move shared source payloads by reference before removing their signal."""
        survivors = [c for c in bundle.component_list if c.component_id not in removed]
        if not survivors:
            return
        for owner in list(bundle.component_list):
            if owner.component_id not in removed:
                continue
            related = [c for c in survivors if c.original_filename == owner.original_filename
                       or c.metadata.get('pda_source_id') == owner.component_id
                       or c.metadata.get('source_file_id') == owner.component_id]
            if not related:
                continue
            successor = related[0]
            payloads = {key: value for key, value in owner.metadata.items()
                        if key in ('pda', 'instrument_status', 'instrument_peaks') and key not in successor.metadata}
            raw = owner.raw_bytes if owner.raw_bytes and not successor.raw_bytes else None
            if not payloads and raw is None:
                continue
            record.source_transfers.append({'owner': owner.component_id, 'successor': successor.component_id,
                                            'payloads': payloads, 'raw': raw})
            changed = []
            for component in bundle.component_list:
                if component.component_id in removed:
                    changed.append(component)
                    continue
                metadata = dict(component.metadata)
                for key in ('pda_source_id', 'source_file_id'):
                    if metadata.get(key) == owner.component_id:
                        metadata[key] = successor.component_id
                changes = {}
                if component.component_id == successor.component_id:
                    metadata.update(payloads)
                    if raw is not None:
                        changes['raw_bytes'] = raw
                changed.append(self._with_metadata(component, metadata, **changes))
            bundle.component_list = changed
            survivors = [c for c in changed if c.component_id not in removed]

    def remove_channels(self, bundle_ids, channel_key, active_file=None):
        """Remove one detector channel across samples as a single undo action."""
        from .channel_visibility import channel_identity
        bundles, removed, label = [], set(), None
        state_ids = set()
        for bundle_id in dict.fromkeys(bundle_ids):
            bundle = self.store.get_bundle(bundle_id)
            if bundle is None:
                continue
            matching = []
            for component in bundle.component_list:
                identity = channel_identity(component)
                if identity and identity[0] == channel_key:
                    matching.append(component.component_id)
                    label = identity[1]
                    state_ids.add(self.store.peak_owner_id(component.component_id))
            # Ion chromatograms extracted from a removed MS channel go with it (they could not be rebuilt).
            for component in bundle.component_list:
                if (component.metadata or {}).get('eic_extracted') and \
                        component.metadata.get('source_file_id') in matching and component.component_id not in matching:
                    matching.append(component.component_id)
                    state_ids.add(self.store.peak_owner_id(component.component_id))
            if matching:
                bundles.append(bundle)
                removed.update(matching)
                if len(matching) == len(bundle.component_list):
                    state_ids.add(bundle.bundle_id)
        if not bundles:
            return None
        state_ids.update(removed)
        count = len(bundles)
        record = self._capture(bundles, f'{label} channel from {count} sample' + ('s' if count != 1 else ''),
                               active_file, state_ids, removed)
        for bundle in bundles:
            self._retain_sample_sources(bundle, removed, record)
            for component in list(bundle.component_list):
                if component.component_id in removed:
                    self.store.remove_component(component.component_id)
            remaining = self.store.get_bundle(bundle.bundle_id)
            if remaining:
                self.store.visibility_state[bundle.bundle_id] = any(
                    self.store.visibility_state.get(self.store.peak_owner_id(c.component_id), True)
                    for c in remaining.component_list)
        self._remove_state(record)
        return record

    def _restore_sample_sources(self, record):
        for transfer in reversed(record.source_transfers):
            owner, successor = transfer['owner'], transfer['successor']
            bundle = self.store.get_bundle_for_component(owner)
            if bundle is None:
                continue
            changed = []
            for component in bundle.component_list:
                metadata = dict(component.metadata)
                for key in ('pda_source_id', 'source_file_id'):
                    if metadata.get(key) == successor:
                        metadata[key] = owner
                changes = {}
                if component.component_id == successor:
                    for key, value in transfer['payloads'].items():
                        if metadata.get(key) is value:
                            metadata.pop(key)
                    if transfer['raw'] is not None and component.raw_bytes is transfer['raw']:
                        changes['raw_bytes'] = b''
                changed.append(self._with_metadata(component, metadata, **changes))
            self.store.add_bundle(replace(bundle, component_list=changed, components={}))

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
        record = self._undo_one()
        if record.batch:
            batch = record.batch
            while self._history and self._history[-1].batch == batch:
                self._undo_one()
            record = replace(record, label=record.batch_label or record.label)
        return record

    def _undo_one(self):
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
        self._restore_sample_sources(record)
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
