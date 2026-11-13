"""Opening the same project twice must never interleave reset and installation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from services import session_service as ss
from services.data_store import DataStore
from services.workspaces import WorkspaceRegistry
from test_session_service import synthetic_store


def test_overlapping_gui_and_agent_opens_share_one_restore_lock(monkeypatch):
    source, a, b = synthetic_store()
    data = ss.build_session(source, {'active-file': a.bundle_id})
    registry = WorkspaceRegistry(DataStore)
    target = registry.default()
    first_installed, release_first, second_started, second_reset = Event(), Event(), Event(), Event()
    install = ss._install_ingested_bundle
    reset = DataStore.reset_workspace

    def pause_first(*args, **kwargs):
        result = install(*args, **kwargs)
        if current_thread().name.startswith('first') and not first_installed.is_set():
            first_installed.set()
            assert release_first.wait(5)
        return result

    def observe_reset(self):
        if current_thread().name.startswith('second'):
            second_reset.set()
        reset(self)

    monkeypatch.setattr(ss, '_install_ingested_bundle', pause_first)
    monkeypatch.setattr(DataStore, 'reset_workspace', observe_reset)
    def second_open():
        second_started.set()
        return ss.restore_session(target, data)
    with ThreadPoolExecutor(1, thread_name_prefix='first') as one, ThreadPoolExecutor(1, thread_name_prefix='second') as two:
        first = one.submit(ss.restore_session, registry.proxy, data)
        assert first_installed.wait(5)
        second = two.submit(second_open)
        assert second_started.wait(5)
        interleaved = second_reset.wait(.3)
        release_first.set()
        reports = [first.result(timeout=10), second.result(timeout=10)]
    assert not interleaved, 'The second open reset a workspace still being restored by the first'
    assert all(r.ok and not r.warnings for r in reports)
    assert set(target.all_bundles()) == set(source.all_bundles())
    assert len(list(target.iter_bundles())) == 2
    assert target.peak_service.serialize() == source.peak_service.serialize()
