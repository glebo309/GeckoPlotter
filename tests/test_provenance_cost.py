"""Provenance capture runs after every callback; it must not re-serialise unchanged tables."""
import hashlib
import pandas as pd
from types import SimpleNamespace
from services import research_package as rp


def _component(frame):
    return SimpleNamespace(component_id='c1', dataframe=frame)


def test_unchanged_table_is_hashed_once_and_matches_the_csv_digest(monkeypatch):
    store = SimpleNamespace()
    frame = pd.DataFrame({'Time (min)': [0., .5, 1.], 'Signal': [1., 4., 2.]})
    calls = []
    real = rp.csv_bytes
    monkeypatch.setattr(rp, 'csv_bytes', lambda f: calls.append(1) or real(f))
    first = rp._dataframe_sha256(store, _component(frame))
    again = rp._dataframe_sha256(store, _component(frame))
    assert first == again == hashlib.sha256(real(frame)).hexdigest()
    assert len(calls) == 1


def test_in_place_edits_are_detected():
    store = SimpleNamespace()
    frame = pd.DataFrame({'x': [0., 1.], 'y': [1., 2.]})
    before = rp._dataframe_sha256(store, _component(frame))
    frame.loc[1, 'y'] = 9.
    after = rp._dataframe_sha256(store, _component(frame))
    assert before != after
    assert after == hashlib.sha256(rp.csv_bytes(frame)).hexdigest()


def test_replaced_table_is_detected_even_with_equal_shape():
    store = SimpleNamespace()
    one = rp._dataframe_sha256(store, _component(pd.DataFrame({'x': [0., 1.]})))
    two = rp._dataframe_sha256(store, _component(pd.DataFrame({'x': [5., 6.]})))
    assert one != two


def test_direct_and_browser_access_share_one_workspace_digest_cache(monkeypatch):
    from services.data_store import DataStore
    from services.workspaces import WorkspaceRegistry
    registry = WorkspaceRegistry(DataStore, session_id=lambda: 'one')
    store = registry.for_session('one')
    component = _component(pd.DataFrame({'x': [0., 1.], 'y': [1., 2.]}))
    calls = []
    real = rp.csv_bytes
    monkeypatch.setattr(rp, 'csv_bytes', lambda frame: calls.append(1) or real(frame))
    assert rp._dataframe_sha256(store, component) == rp._dataframe_sha256(registry.proxy, component)
    assert len(calls) == 1
    # Reset must release the old cache; a proxy must never keep workspace data on itself.
    store.reset_workspace()
    rp._dataframe_sha256(registry.proxy, component)
    assert len(calls) == 2
    assert '_dataframe_digests' not in vars(registry.proxy)
