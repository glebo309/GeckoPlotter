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
