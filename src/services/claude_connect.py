"""Connect GeckoPlotter's agent interface (gecko_mcp.py) to the Claude apps on this computer, on request (About window).

Claude Desktop lists its MCP servers in claude_desktop_config.json; Claude Code is told with ``claude mcp add``. Both get
the same entry, ``geckoplotter``: the Python running this app and gecko_mcp.py next to app.py, so it keeps working after
every update (the launcher replaces the code in the same folder). Only that entry is added or replaced; a copy of the
Desktop file is kept as ``claude_desktop_config.json.bak``. Nothing is changed without the user's click.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

NAME = 'geckoplotter'


def server_command() -> List[str]:
    from services.about import ROOT
    return [sys.executable, str(ROOT / 'gecko_mcp.py')]


def agent_package_ready() -> bool:
    """The Python running the app can run the MCP server (the ``mcp`` package is installed)."""
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def desktop_config_path() -> Path:
    if platform.system() == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json'
    if platform.system() == 'Windows':
        return Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'Claude' / \
            'claude_desktop_config.json'
    return Path.home() / '.config' / 'Claude' / 'claude_desktop_config.json'


def claude_code_cli() -> Optional[str]:
    found = shutil.which('claude')
    if found:
        return found
    for candidate in (Path.home() / '.local' / 'bin' / 'claude', Path.home() / '.claude' / 'local' / 'claude',
                      Path('/opt/homebrew/bin/claude'), Path('/usr/local/bin/claude'),
                      Path(os.environ.get('APPDATA') or '') / 'npm' / 'claude.cmd'):
        if str(candidate) not in ('', '.') and candidate.is_file():
            return str(candidate)
    return None


def status() -> dict:
    """Which Claude apps are here and whether GeckoPlotter is connected to them already."""
    command = server_command()
    config = desktop_config_path()
    desktop = None
    if config.parent.exists():
        try:
            entry = (json.loads(config.read_text(encoding='utf-8')).get('mcpServers') or {}).get(NAME)
        except (OSError, ValueError):
            entry = None
        desktop = 'connected' if entry and [entry.get('command'), *entry.get('args', [])] == command else 'available'
    return {'desktop': desktop, 'code': 'available' if claude_code_cli() else None,
            'ready': agent_package_ready(), 'command': command}


def connect_desktop() -> str:
    config = desktop_config_path()
    if not config.parent.exists():
        return 'Claude Desktop is not installed.'
    data = {}
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding='utf-8'))
        except ValueError:
            return f'Claude Desktop: its settings file could not be read ({config}); nothing was changed.'
        shutil.copyfile(config, config.with_name(config.name + '.bak'))
    command = server_command()
    data.setdefault('mcpServers', {})[NAME] = {'command': command[0], 'args': command[1:]}
    tmp = config.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(config)
    return 'Claude Desktop: connected. Quit and reopen Claude Desktop to use it.'


def connect_code() -> str:
    cli = claude_code_cli()
    if not cli:
        return 'Claude Code is not installed.'
    command = server_command()
    subprocess.run([cli, 'mcp', 'remove', '--scope', 'user', NAME], capture_output=True, timeout=60)
    done = subprocess.run([cli, 'mcp', 'add', '--scope', 'user', NAME, '--', *command],
                          capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        return 'Claude Code: could not add GeckoPlotter (' + (done.stderr or done.stdout).strip()[:200] + ').'
    return 'Claude Code: connected. Start a new Claude Code session to use it.'


def connect() -> List[str]:
    """Connect every Claude app found; one message per app."""
    if not agent_package_ready():
        return ['The agent interface is not installed in this GeckoPlotter yet: close GeckoPlotter and start it '
                'again so it updates, then try again.']
    found = status()
    messages = []
    if found['desktop']:
        messages.append(connect_desktop())
    if found['code']:
        messages.append(connect_code())
    if not messages:
        messages.append('No Claude app found on this computer. Install Claude Desktop (claude.ai/download) or Claude '
                        'Code, then connect again.')
    return messages
