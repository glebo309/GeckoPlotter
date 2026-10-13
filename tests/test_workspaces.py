"""Every browser gets its own workspace."""
import pytest
from flask import Flask, jsonify

from services import session_service as ss
from services import workspaces as ws
from services.data_store import DataStore


class Store:
    def __init__(self):
        self.files = []
        self._scoped = {}

    def scoped(self, key, factory):
        return self._scoped.setdefault(key, factory())


def make_app():
    registry = ws.WorkspaceRegistry(Store)
    server = Flask(__name__)
    ws.install(server)

    @server.route('/add/<name>')
    def add(name):
        registry.proxy.files.append(name)
        return jsonify(registry.proxy.files)

    @server.route('/files')
    def files():
        return jsonify(registry.proxy.files)

    return registry, server


def test_two_browsers_never_see_each_others_files():
    registry, server = make_app()
    ann, ben = server.test_client(), server.test_client()
    ann.get('/add/ann.lcd')
    ben.get('/add/ben.txt')
    assert ann.get('/files').get_json() == ['ann.lcd']
    assert ben.get('/files').get_json() == ['ben.txt']
    assert registry.count() == 2


def test_a_browser_keeps_its_workspace_across_requests_and_gets_a_safe_cookie():
    registry, server = make_app()
    client = server.test_client()
    first = client.get('/add/a')
    cookie = first.headers['Set-Cookie']
    assert ws.COOKIE in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert client.get('/add/b').get_json() == ['a', 'b']
    assert 'Set-Cookie' not in client.get('/files').headers          # the id is only issued once
    assert registry.count() == 1


def test_a_forged_cookie_cannot_pick_a_path_or_someone_elses_id():
    registry, server = make_app()
    client = server.test_client()
    client.set_cookie(ws.COOKIE, '../../etc', domain='localhost')
    response = client.get('/add/x')
    assert ws.COOKIE in response.headers['Set-Cookie']                # replaced by a fresh random id
    assert not ws.valid_session_id('../../etc') and ws.valid_session_id('a' * 32)


def test_outside_a_request_the_default_workspace_is_used():
    registry = ws.WorkspaceRegistry(Store)
    registry.proxy.files.append('startup')
    assert registry.default().files == ['startup'] and registry.count() == 0


def test_idle_and_surplus_workspaces_are_dropped():
    clock = {'now': 1000.0}
    sid = {'value': None}
    registry = ws.WorkspaceRegistry(Store, max_idle_seconds=100, max_workspaces=2, session_id=lambda: sid['value'])
    import time as real_time
    original = real_time.time
    real_time.time = lambda: clock['now']
    try:
        for name in ('a' * 32, 'b' * 32):
            sid['value'] = name
            registry.proxy.files.append(name[0])
            clock['now'] += 1
        sid['value'] = 'c' * 32
        registry.proxy.files.append('c')                             # a third one evicts the oldest
        assert registry.count() == 2
        sid['value'] = 'a' * 32
        assert registry.proxy.files == []                            # 'a' was dropped and starts empty
        clock['now'] += 500
        sid['value'] = 'd' * 32
        registry.proxy.files.append('d')                             # everything else is idle by now
        assert registry.count() == 1
    finally:
        real_time.time = original


def test_scoped_helpers_exist_once_per_workspace_and_fall_back_for_test_doubles():
    registry = ws.WorkspaceRegistry(DataStore, session_id=lambda: 'a' * 32)
    drafts = ws.scoped(registry.proxy, 'drafts', dict)
    drafts['x'] = 1
    assert drafts['x'] == 1 and 'x' in drafts and len(drafts) == 1
    registry._session_id = lambda: 'b' * 32
    assert 'x' not in drafts and len(drafts) == 0                    # another browser, another dict

    class Double:                                                    # a test double without ``scoped``
        pass
    shared = ws.scoped(Double(), 'cache', list)
    shared.append(1)
    assert list(shared) == [1]


def test_service_of_follows_the_current_workspace():
    registry = ws.WorkspaceRegistry(DataStore, session_id=lambda: 'a' * 32)
    peaks = ws.service_of(registry.proxy, 'peak_service')
    first = peaks.get_peaks('missing')
    assert first == []
    registry._session_id = lambda: 'b' * 32
    assert registry.proxy.peak_service is not registry.for_session('a' * 32).peak_service
    assert peaks.get_peaks('missing') == []


def test_every_browser_autosaves_into_a_folder_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_AUTOSAVE_DIR', str(tmp_path))
    monkeypatch.setattr(ss, 'autosave_scope', lambda: 'a' * 16)
    assert ss.autosave_dir() == tmp_path / ('a' * 16)
    monkeypatch.setattr(ss, 'autosave_scope', lambda: '../x')        # never a path taken from outside
    assert ss.autosave_dir(create=False) == tmp_path
    monkeypatch.setattr(ss, 'autosave_scope', None)
    assert ss.autosave_dir(create=False) == tmp_path
