"""Chronological undo for workspace edits. Immutable measurement arrays are shared, not copied."""
from contextlib import contextmanager
from copy import copy
from dataclasses import fields, is_dataclass
from enum import Enum
from threading import RLock

import numpy as np
import pandas as pd


FIELDS = ('_bundles', '_component_index', '_file_index', '_persistent_state', '_shared_plot_settings',
          'file_ui_state', 'visibility_state', 'collapse_state', 'group_overrides', 'group_labels',
          '_hidden_sample_channels', '_channel_combine_modes', 'lcms_eic_overlays')
SERVICES = ('peak_service', 'calibration_service', 'integration_service')


def clone(value):
    if isinstance(value, dict):
        return {k: clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clone(v) for v in value]
    if isinstance(value, tuple):
        return tuple(clone(v) for v in value)
    if isinstance(value, set):
        return set(value)
    if is_dataclass(value) and not isinstance(value, type):
        result = copy(value)
        for field in fields(value):
            object.__setattr__(result, field.name, clone(getattr(value, field.name)))
        return result
    # Frames and instrument arrays are replaced on edits; originals and parsed source arrays are immutable.
    return value


def signature(value):
    if isinstance(value, (pd.DataFrame, pd.Series, np.ndarray, bytes)):
        return (type(value).__name__, id(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return tuple(sorted(((str(k), signature(v)) for k, v in value.items()), key=lambda pair: pair[0]))
    if isinstance(value, (list, tuple)):
        return tuple(signature(v) for v in value)
    if isinstance(value, set):
        return tuple(sorted(map(repr, value)))
    if is_dataclass(value) and not isinstance(value, type):
        return tuple((f.name, signature(getattr(value, f.name))) for f in fields(value))
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return 'NaN'
    return value


class WorkspaceHistory:
    def __init__(self, store, limit=50):
        self.store = store
        self.limit = limit
        self.client = {}
        self.navigation = {}
        self.tables = {}
        self.past = []
        self.future = []
        self.lock = RLock()

    def capture(self):
        return clone({'fields': {name: getattr(self.store, name, {}) for name in FIELDS},
                      'services': {name: getattr(self.store, name).serialize() for name in SERVICES},
                      'client': self.client, 'navigation': self.navigation, 'tables': self.tables})

    def commit(self, before, label):
        after = self.capture()
        if signature({k: v for k, v in before.items() if k != 'navigation'}) == signature({k: v for k, v in after.items() if k != 'navigation'}):
            return False
        self.past.append((label, before, after))
        del self.past[:-self.limit]
        self.future.clear()
        return True

    @contextmanager
    def edit(self, label):
        with self.lock:
            before = self.capture()
            try:
                yield
            finally:
                self.commit(before, label)

    def restore(self, snapshot):
        value = clone(snapshot)
        for name, item in value['fields'].items():
            setattr(self.store, name, item)
        for name, item in value['services'].items():
            getattr(self.store, name).deserialize(item)
        self.client = value['client']
        self.navigation = value.get('navigation', {})
        self.tables = value.get('tables', {})
        self.store.file_removal_service.clear()
        for cache in self.store._render_caches:
            cache.prune([])

    def undo(self):
        with self.lock:
            if not self.past:
                return None
            action = self.past.pop()
            self.restore(action[1])
            self.future.append(action)
            return action[0]

    def redo(self):
        with self.lock:
            if not self.future:
                return None
            action = self.future.pop()
            self.restore(action[2])
            self.past.append(action)
            return action[0]

    def clear(self):
        self.past.clear()
        self.future.clear()
        self.client.clear()
        self.navigation.clear()
        self.tables.clear()


def history_for(store):
    return store.scoped('workspace-history', lambda: WorkspaceHistory(store))
