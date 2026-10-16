"""Live mode: an agent's call runs in the workspace of the browser tab used last, only from this computer with the
key, and the page learns that it must redraw (services/live_agent, services/live_client, gecko_mcp)."""
import json

import pytest
from flask import Flask

from services import live_agent, live_client
from services.data_store import DataStore
from services.workspaces import COOKIE, WorkspaceRegistry

SID = 'a' * 32


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path))
    server = Flask(__name__)
    registry = WorkspaceRegistry(DataStore)
    live = live_agent.install(server, registry, 8099)
    client = server.test_client()
    client.set_cookie(COOKIE, SID)
    return server, registry, live, client


def _call(client, live, method, *args, key=None, **kwargs):
    return client.post(live_agent.CALL, json={'method': method, 'args': list(args), 'kwargs': kwargs,
                                              'agent': {'client': 'claude-code', 'client_label': 'Claude Code'}},
                       headers={'X-Gecko-Key': key or live.key}, environ_base={'REMOTE_ADDR': '127.0.0.1'})


def test_the_live_file_is_private_and_names_the_port(app, tmp_path):
    _server, _registry, live, _client = app
    info = json.loads(live.path.read_text())
    assert info['port'] == 8099 and info['key'] == live.key
    assert (live.path.stat().st_mode & 0o077) == 0
    assert live_client.find()['port'] == 8099


def test_a_call_runs_in_the_tab_used_last_and_the_page_redraws(app):
    _server, registry, live, client = app
    assert _call(client, live, 'samples').status_code == 409          # no tab yet
    client.post(live_agent.HERE)
    before = client.get(live_agent.STATE).get_json()
    assert before['here'] and before['version'] == 0
    answer = _call(client, live, 'samples')
    assert answer.status_code == 200 and answer.get_json() == {'result': []}
    assert client.get(live_agent.STATE).get_json()['version'] == 0      # reading does not redraw
    assert _call(client, live, 'open', '/no/such/folder').get_json()['result']['error'].startswith('Not found')
    state = client.get(live_agent.STATE).get_json()
    assert state['version'] == 1 and state['agent'] == 'Claude Code' and state['doing'] == 'opening folder'
    assert live.workspace(SID).store is registry.for_session(SID)
    assert live.workspace(SID).agent == {'client': 'claude-code'}       # the label is for the status bar only


def test_without_the_key_from_elsewhere_or_after_stop_nothing_runs(app):
    _server, _registry, live, client = app
    client.post(live_agent.HERE)
    assert _call(client, live, 'samples', key='wrong').status_code == 403
    away = client.post(live_agent.CALL, json={'method': 'samples'}, headers={'X-Gecko-Key': live.key},
                       environ_base={'REMOTE_ADDR': '192.168.1.20'})
    assert away.status_code == 403
    assert _call(client, live, '__init__').status_code == 409           # only the agent tools
    assert client.post(live_agent.STOP).get_json()['stopped']
    assert 'Stopped' in _call(client, live, 'samples').get_json()['refused']
    client.post(live_agent.STOP)
    assert _call(client, live, 'samples').status_code == 200


def test_the_agent_works_on_its_own_when_no_geckoplotter_runs(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path))
    (tmp_path / 'live').mkdir()
    (tmp_path / 'live' / '8098.json').write_text(json.dumps({'port': 8098, 'pid': 2 ** 22 + 12345, 'key': 'k'}))
    assert live_client.find() is None                                   # that app is gone
    with pytest.raises(live_client.NotRunning):
        live_client.call('samples')


def test_status_bar_text():
    assert live_agent.describe('integrate', [10.4, 11.2]) == 'integrating 10.4-11.2 min'
    assert live_agent.describe('open', ['/Users/x/Desktop/run 7']) == 'opening run 7'
    assert live_agent.describe('rename_peak', []) == 'renaming'
    assert live_agent.describe('remove_peak', [None, 'alanine']) == 'removing alanine'


def test_hello_tracks_processes_and_updates_the_handshake_label(app):
    _server, _registry, live, client = app
    assert client.get(live_agent.STATE).get_json()['connected'] == []
    for pid, label in [(101, 'Agent'), (102, 'Codex'), (101, 'Claude Code'), (103, 'Claude Code')]:
        response = client.post('/_gecko/agent/hello', json={'id': pid, 'agent': label},
                               headers={'X-Gecko-Key': live.key})
        assert response.status_code == 204
    state = client.get(live_agent.STATE).get_json()
    assert state['connected'] == ['Claude Code', 'Codex']
    assert not state['busy'] and state['version'] == 0
    assert live.target is None                            # no tool call or browser tab needed


def test_hello_expires_each_process_after_30_seconds(app, monkeypatch):
    _server, _registry, live, client = app
    now = [100.0]
    monkeypatch.setattr(live_agent.time, 'monotonic', lambda: now[0])
    for pid in (101, 102):
        client.post('/_gecko/agent/hello', json={'id': pid, 'agent': 'Claude Code'},
                    headers={'X-Gecko-Key': live.key})
    now[0] += 20
    client.post('/_gecko/agent/hello', json={'id': 102, 'agent': 'Claude Code'},
                headers={'X-Gecko-Key': live.key})
    now[0] += 11
    assert live.state(None)['connected'] == ['Claude Code']
    now[0] += 20
    assert live.state(None)['connected'] == []


@pytest.mark.parametrize('key, address', [(None, '127.0.0.1'), ('wrong', '127.0.0.1'),
                                        ('valid', '192.168.1.20')])
def test_hello_requires_the_key_and_loopback(app, key, address):
    _server, _registry, live, client = app
    headers = {'X-Gecko-Key': live.key if key == 'valid' else key} if key else {}
    response = client.post('/_gecko/agent/hello', json={'id': 101, 'agent': 'Codex'}, headers=headers,
                           environ_base={'REMOTE_ADDR': address})
    assert response.status_code == 403
    assert live.state(None)['connected'] == []


@pytest.mark.parametrize('body', [{}, {'id': []}, {'id': True}, {'id': 0}, {'id': 101, 'agent': []}])
def test_hello_refuses_invalid_process_details(app, body):
    _server, _registry, live, client = app
    response = client.post('/_gecko/agent/hello', json=body, headers={'X-Gecko-Key': live.key})
    assert response.status_code == 400


def test_hello_continues_while_stopped_or_a_call_holds_the_work_lock(app):
    _server, _registry, live, client = app
    client.post(live_agent.STOP)
    with live._lock:
        response = client.post('/_gecko/agent/hello', json={'id': 101, 'agent': 'Codex'},
                               headers={'X-Gecko-Key': live.key})
        assert response.status_code == 204
        assert live.state(None)['connected'] == ['Codex']
    assert live.stopped


def test_remove_peak_is_a_live_mutation_that_redraws_the_page(app, monkeypatch):
    _server, _registry, live, client = app
    client.post(live_agent.HERE)
    calls = []
    monkeypatch.setattr(live.workspace(SID), 'remove_peak', lambda *args: calls.append(args) or [])
    result = _call(client, live, 'remove_peak', None, 'alanine')
    assert result.status_code == 200 and result.get_json() == {'result': []}
    assert calls == [(None, 'alanine')]
    state = client.get(live_agent.STATE).get_json()
    assert state['version'] == 1 and state['doing'] == 'removing alanine'


def test_the_agent_counts_as_working_for_its_whole_turn(app, monkeypatch):
    _server, _registry, live, client = app
    clock = [1000.0]
    monkeypatch.setattr(live_agent.time, 'monotonic', lambda: clock[0])
    live.hello(501, 'Claude Code', parent=400)          # its MCP server, started by the agent (pid 400)
    live.hello(601, 'Codex', parent=900)
    assert not live.state(None)['working']
    live.turn([7000, 400, 300], started=True)            # the hook runs in a shell under the agent
    assert live.state(None)['working']
    clock[0] += 120                                      # still thinking two minutes later (heartbeats go on)
    live.hello(501, 'Claude Code', parent=400)
    live.hello(601, 'Codex', parent=900)
    assert live.state(None)['working']
    live.turn([7001, 400, 300], started=False)
    assert not live.state(None)['working']
    live.turn([8000, 555, 300], started=True)            # a session without GeckoPlotter changes nothing
    assert not live.state(None)['working']
    live._last_call[601] = clock[0]                      # an agent without hooks: working shortly after a call
    assert live.state(None)['working']
    clock[0] += live_agent.LINGER + 1
    assert not live.state(None)['working']
