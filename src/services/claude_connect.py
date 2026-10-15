"""Connect GeckoPlotter's agent interface (gecko_mcp.py) to the AI apps on this computer, on request (About window).

Claude Desktop lists its MCP servers in claude_desktop_config.json; Claude Code and Codex are told with ``claude mcp add``
and ``codex mcp add``. All get the same entry, ``geckoplotter``: the Python running this app and gecko_mcp.py next to app.py, so it keeps working after
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


def codex_cli() -> Optional[str]:
    found = shutil.which('codex')
    if found:
        return found
    for candidate in (Path('/opt/homebrew/bin/codex'), Path('/usr/local/bin/codex'), Path.home() / '.local' / 'bin' / 'codex',
                      Path(os.environ.get('APPDATA') or '') / 'npm' / 'codex.cmd'):
        if str(candidate) not in ('', '.') and candidate.is_file():
            return str(candidate)
    return None


def _run(cli: str, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run an AI app's command line. Started from the Dock or Finder, the app's PATH lacks the folder of the CLI, so
    a CLI that is a Node script (codex: ``#!/usr/bin/env node``) would not find node; its own folder comes first."""
    folders = [str(Path(cli).parent), '/opt/homebrew/bin', '/usr/local/bin']
    env = dict(os.environ, PATH=os.pathsep.join(folders + [os.environ.get('PATH', '')]))
    return subprocess.run([cli, *args], capture_output=True, text=True, timeout=timeout, cwd=str(Path.home()),
                          env=env)


def _cli_has_entry(cli: Optional[str]) -> bool:
    """The CLI has a ``geckoplotter`` entry that starts this GeckoPlotter (not an old or hand-made one elsewhere)."""
    if not cli:
        return False
    try:
        done = _run(cli, 'mcp', 'get', NAME, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and server_command()[1] in (done.stdout or '')


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
    code, codex = claude_code_cli(), codex_cli()
    return {'desktop': desktop,
            'code': ('connected' if _cli_has_entry(code) else 'available') if code else None,
            'codex': ('connected' if _cli_has_entry(codex) else 'available') if codex else None,
            'ready': agent_package_ready(), 'command': command}


def _replace_entry(cli: str, app: str, remove_scopes, add_args) -> str:
    """Remove the old entry and add this GeckoPlotter's; tried twice, because a running session of the app can write
    its settings file back between the two steps."""
    if _cli_has_entry(cli):
        return f'{app}: connected.'
    done = None
    for _attempt in range(2):
        for scope in remove_scopes:
            _run(cli, 'mcp', 'remove', *scope, NAME)
        done = _run(cli, 'mcp', 'add', *add_args, NAME, '--', *server_command())
        if done.returncode == 0 or _cli_has_entry(cli):
            return f'{app}: connected. Start a new {app} session to use it.'
    return f'{app}: could not add GeckoPlotter (' + (done.stderr or done.stdout).strip()[:200] + ').'


def connect_codex() -> str:
    cli = codex_cli()
    if not cli:
        return 'Codex is not installed.'
    return _replace_entry(cli, 'Codex', [()], ())


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
    # An older entry added by hand may sit in the local scope (the default) as well as the user scope.
    return _replace_entry(cli, 'Claude Code', [('--scope', 'local'), ('--scope', 'user')], ('--scope', 'user'))


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
    if found['codex']:
        messages.append(connect_codex())
    if not messages:
        messages.append('No AI app found on this computer (Claude Desktop, Claude Code or Codex). Install one, then '
                        'connect again.')
    return messages
