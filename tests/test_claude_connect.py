"""Connect to Claude: only GeckoPlotter's own entry is written to Claude Desktop's settings; other servers stay."""
import json

from services import claude_connect


def test_desktop_gets_geckoplotter_and_keeps_the_other_servers(tmp_path, monkeypatch):
    config = tmp_path / 'Claude' / 'claude_desktop_config.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'mcpServers': {'obsidian': {'command': 'uvx', 'args': ['mcp-obsidian']}},
                                  'other': 1}))
    monkeypatch.setattr(claude_connect, 'desktop_config_path', lambda: config)
    monkeypatch.setattr(claude_connect, 'claude_code_cli', lambda: None)
    monkeypatch.setattr(claude_connect, 'agent_package_ready', lambda: True)
    assert claude_connect.status()['desktop'] == 'available'
    messages = claude_connect.connect()
    data = json.loads(config.read_text())
    assert data['other'] == 1 and data['mcpServers']['obsidian']['args'] == ['mcp-obsidian']
    entry = data['mcpServers']['geckoplotter']
    assert entry['args'][0].endswith('gecko_mcp.py') and 'reopen Claude Desktop' in messages[0]
    assert (config.parent / 'claude_desktop_config.json.bak').exists()
    assert claude_connect.status()['desktop'] == 'connected'


def test_without_the_agent_package_nothing_is_changed(tmp_path, monkeypatch):
    config = tmp_path / 'Claude' / 'claude_desktop_config.json'
    config.parent.mkdir()
    config.write_text('{}')
    monkeypatch.setattr(claude_connect, 'desktop_config_path', lambda: config)
    monkeypatch.setattr(claude_connect, 'agent_package_ready', lambda: False)
    assert 'start it again' in claude_connect.connect()[0] and config.read_text() == '{}'
