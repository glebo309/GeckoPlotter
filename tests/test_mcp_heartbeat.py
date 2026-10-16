"""The MCP heartbeat finds the app again each time and never interrupts the stdio protocol."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import gecko_mcp


def test_heartbeat_announces_pid_then_the_handshake_label(monkeypatch):
    monkeypatch.setattr(gecko_mcp.workspace, 'agent', None)
    find = MagicMock(side_effect=[{'port': 8099, 'key': 'first'}, {'port': 8100, 'key': 'second'}])
    monkeypatch.setattr(gecko_mcp.live_client, 'find', find)
    send = MagicMock()
    monkeypatch.setattr('urllib.request.urlopen', send)
    gecko_mcp._heartbeat_once()
    ctx = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
        client_info=SimpleNamespace(name='claude-code', version='1'))))
    gecko_mcp._identify(ctx)
    gecko_mcp._heartbeat_once()
    for call, port, key, label in zip(send.call_args_list, (8099, 8100), ('first', 'second'), ('Agent', 'Claude Code')):
        request = call.args[0]
        assert request.full_url == f'http://127.0.0.1:{port}/_gecko/agent/hello'
        assert request.method == 'POST' and request.get_header('X-gecko-key') == key
        assert json.loads(request.data) == {'id': gecko_mcp.os.getpid(), 'parent': gecko_mcp.os.getppid(), 'agent': label}
        assert 0 < call.kwargs['timeout'] < 10
    assert find.call_count == 2


def test_heartbeat_without_an_app_sends_nothing(monkeypatch):
    monkeypatch.setattr(gecko_mcp.live_client, 'find', lambda: None)
    send = MagicMock()
    monkeypatch.setattr('urllib.request.urlopen', send)
    gecko_mcp._heartbeat_once()
    send.assert_not_called()


def test_heartbeat_recovers_silently_on_the_next_ten_second_tick(monkeypatch, capsys):
    beat = MagicMock(side_effect=[OSError('app closed'), None])
    monkeypatch.setattr(gecko_mcp, '_heartbeat_once', beat)
    sleep = MagicMock(side_effect=[None, KeyboardInterrupt])
    monkeypatch.setattr(gecko_mcp.time, 'sleep', sleep)
    with pytest.raises(KeyboardInterrupt):
        gecko_mcp._heartbeat()
    assert beat.call_count == 2
    assert [call.args for call in sleep.call_args_list] == [(10,), (10,)]
    assert capsys.readouterr().out == ''
