"""Acquisition payloads must not be walked once per UI callback or duplicated in undo."""
import json
import numpy as np
from services import research_package as rp
from services.workspace_history import WorkspaceHistory, clone
from services.data_store import DataStore


def test_snapshot_preserves_shared_objects_without_aliasing_mutable_live_state():
    shared = {'label': ['original']}
    snapshot = clone({'primary': shared, 'components': [shared]})
    assert snapshot['primary'] is snapshot['components'][0]
    assert snapshot['primary'] is not shared
    shared['label'][0] = 'edited'
    assert snapshot['primary']['label'] == ['original']


def test_instrument_traces_are_shared_readonly_arrays_through_undo():
    from services.bundling_service import assign_bundles
    from src.ingestion import ingest_file
    # Use the existing sectioned instrument fixture.
    from ingestion.test_shimadzu_ascii import FIXTURE
    result = ingest_file(str(FIXTURE), FIXTURE.name)
    bundle = assign_bundles([(FIXTURE.name, FIXTURE.read_bytes(), result)])[0]
    store = DataStore()
    store.add_bundle(bundle)
    trace = bundle.primary.metadata['instrument_status']['Pump A Pressure']
    assert isinstance(trace['values'], np.ndarray)
    assert not trace['values'].flags.writeable
    assert not trace['time_min'].flags.writeable
    history = WorkspaceHistory(store)
    original = bundle.name
    with history.edit('Rename'):
        bundle.name = 'Renamed'
    history.undo()
    restored = store.get_bundle(bundle.bundle_id)
    assert restored.name == original
    assert restored.primary.metadata['instrument_status']['Pump A Pressure']['values'] is trace['values']
    assert restored.components[restored.primary.role] is restored.primary
    history.redo()
    assert store.get_bundle(bundle.bundle_id).name == 'Renamed'


def test_status_history_is_bounded_but_detects_numeric_and_unit_changes():
    trace = {'time_min': list(range(10000)), 'values': [1.] * 10000, 'unit': 'bar'}
    old = rp._history_metadata({'instrument_status': {'Pressure': trace}})
    assert len(json.dumps(old)) < 1000
    trace['values'][5000] = 2.
    changed = rp._history_metadata({'instrument_status': {'Pressure': trace}})
    assert changed != old
    trace['unit'] = 'kPa'
    assert rp._history_metadata({'instrument_status': {'Pressure': trace}}) != changed
    assert len(trace['values']) == 10000


def test_immutable_status_digest_is_reused(monkeypatch):
    from services.bundling_service import assign_bundles
    from src.ingestion import ingest_file
    from ingestion.test_shimadzu_ascii import FIXTURE
    result = ingest_file(str(FIXTURE), FIXTURE.name)
    bundle = assign_bundles([(FIXTURE.name, FIXTURE.read_bytes(), result)])[0]
    metadata = {'instrument_status': bundle.primary.metadata['instrument_status']}
    first = rp._history_metadata(metadata)
    def forbidden(*args, **kwargs):
        raise AssertionError('Unchanged status acquisition was rehashed')
    monkeypatch.setattr(rp.hashlib, 'sha256', forbidden)
    assert rp._history_metadata(metadata) == first
