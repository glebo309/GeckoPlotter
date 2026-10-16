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
    monkeypatch.setattr(claude_connect, 'claude_settings_path', lambda: tmp_path / '.claude' / 'settings.json')
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


def test_claude_code_gets_turn_hooks_and_keeps_its_other_hooks(tmp_path):
    settings = tmp_path / 'settings.json'
    other = {'type': 'command', 'command': 'echo hi'}
    old = {'type': 'command', 'command': '/old/venv/python /old/app/gecko_hook.py start'}
    settings.write_text(json.dumps({'model': 'x', 'hooks': {'UserPromptSubmit': [{'hooks': [other, old]}],
                                                           'SessionStart': [{'hooks': [other]}]}}))
    assert claude_connect.write_hooks(settings) == ''
    data = json.loads(settings.read_text())
    prompt = [h['command'] for g in data['hooks']['UserPromptSubmit'] for h in g['hooks']]
    assert prompt[0] == 'echo hi' and len(prompt) == 2 and prompt[1].endswith('gecko_hook.py start')
    assert data['hooks']['Stop'][0]['hooks'][0]['command'].endswith('gecko_hook.py end')
    assert data['model'] == 'x' and data['hooks']['SessionStart'] == [{'hooks': [other]}]
    assert (tmp_path / 'settings.json.bak').exists()
    once = settings.read_text()
    assert claude_connect.write_hooks(settings) == '' and settings.read_text() == once      # nothing to change
    settings.write_text('{not json')
    assert 'could not be read' in claude_connect.write_hooks(settings)
