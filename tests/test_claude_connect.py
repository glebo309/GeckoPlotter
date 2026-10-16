"""Connect to AI apps: only GeckoPlotter's own entry is written to their settings; other servers stay.

Every app is pointed at a temporary folder or switched off here, so a test never touches the real settings of this
computer (an unstubbed CLI once connected the developer's Codex to the test Python)."""
import json

import pytest

from services import claude_connect


@pytest.fixture
def apps(tmp_path, monkeypatch):
    desktop = tmp_path / 'Claude' / 'claude_desktop_config.json'
    gemini = tmp_path / '.gemini' / 'settings.json'
    monkeypatch.setattr(claude_connect, 'desktop_config_path', lambda: desktop)
    monkeypatch.setattr(claude_connect, 'gemini_config_path', lambda: gemini)
    for cli in ('claude_code_cli', 'codex_cli', 'gemini_cli'):
        monkeypatch.setattr(claude_connect, cli, lambda: None)
    monkeypatch.setattr(claude_connect, 'agent_package_ready', lambda: True)
    return desktop, gemini


def test_desktop_gets_geckoplotter_and_keeps_the_other_servers(apps):
    config, _gemini = apps
    config.parent.mkdir()
    config.write_text(json.dumps({'mcpServers': {'obsidian': {'command': 'uvx', 'args': ['mcp-obsidian']}},
                                  'other': 1}))
    assert claude_connect.status()['desktop'] == 'available'
    done = claude_connect.connect()
    data = json.loads(config.read_text())
    assert data['other'] == 1 and data['mcpServers']['obsidian']['args'] == ['mcp-obsidian']
    assert data['mcpServers']['geckoplotter']['args'][0].endswith('gecko_mcp.py')
    assert done['results'] == [{'app': 'Claude Desktop', 'ok': True, 'restart': 'quit and reopen Claude Desktop',
                                'error': ''}]
    assert (config.parent / 'claude_desktop_config.json.bak').exists()
    assert claude_connect.status()['desktop'] == 'connected'
    assert claude_connect.connect()['results'][0]['restart'] == ''          # already connected: nothing to restart


def test_gemini_cli_gets_the_entry_in_its_settings_file(apps, monkeypatch):
    _desktop, gemini = apps
    monkeypatch.setattr(claude_connect, 'gemini_cli', lambda: '/opt/homebrew/bin/gemini')
    gemini.parent.mkdir()
    gemini.write_text(json.dumps({'theme': 'Default'}))
    assert claude_connect.status()['gemini'] == 'available'
    done = claude_connect.connect()
    assert [r['app'] for r in done['results']] == ['Gemini CLI'] and done['results'][0]['ok']
    data = json.loads(gemini.read_text())
    assert data['theme'] == 'Default' and data['mcpServers']['geckoplotter']['command']
    assert claude_connect.status()['gemini'] == 'connected'


def test_without_the_agent_package_nothing_is_changed(apps, monkeypatch):
    config, _gemini = apps
    config.parent.mkdir()
    config.write_text('{}')
    monkeypatch.setattr(claude_connect, 'agent_package_ready', lambda: False)
    assert 'start it again' in claude_connect.connect()['message'] and config.read_text() == '{}'
