"""Connect GeckoPlotter's agent interface (gecko_mcp.py) to the AI apps on this computer, on request (About window).

Claude Desktop and Gemini CLI list their MCP servers in a settings file (claude_desktop_config.json,
~/.gemini/settings.json); Claude Code and Codex are told with ``claude mcp add`` and ``codex mcp add``. All get the same
entry, ``geckoplotter``: the Python running this app and gecko_mcp.py next to app.py, so it keeps working after every
update (the launcher replaces the code in the same folder). Only that entry is added or replaced; a copy of a settings
file is kept as ``<name>.bak``. Nothing is changed without the user's click.

Claude Code also gets two turn hooks in ~/.claude/settings.json (gecko_hook.py, on a prompt and on the answer), so
GeckoPlotter's status bar shows it at work for the whole turn (services/live_agent). Any other hook stays.
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


def claude_settings_path() -> Path:
    return Path.home() / '.claude' / 'settings.json'


HOOKS = {'UserPromptSubmit': 'start', 'Stop': 'end'}
HOOK_SCRIPT = 'gecko_hook.py'


def hook_command(state: str) -> str:
    from services.about import ROOT
    parts = [sys.executable, str(ROOT / HOOK_SCRIPT), state]
    if platform.system() == 'Windows':
        return subprocess.list2cmdline(parts)
    import shlex
    return shlex.join(parts)


def write_hooks(config: Optional[Path] = None) -> str:
    """Put GeckoPlotter's turn hooks in Claude Code's settings, replacing earlier ones (another GeckoPlotter
    folder) and keeping every other hook and setting. Returns '' or why nothing was changed."""
    config = config or claude_settings_path()
    data = {}
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding='utf-8'))
        except ValueError:
            return f'its settings file could not be read ({config}); the status bar shows it only during its calls'
    if not isinstance(data, dict):
        return f'its settings file is not a settings object ({config})'
    before = json.dumps(data, sort_keys=True)
    hooks = data.setdefault('hooks', {})
    for event, state in HOOKS.items():
        groups = []
        for group in hooks.get(event) or []:
            kept = [h for h in (group.get('hooks') or []) if HOOK_SCRIPT not in str(h.get('command', ''))]
            if kept:
                groups.append(dict(group, hooks=kept))
        groups.append({'hooks': [{'type': 'command', 'command': hook_command(state), 'timeout': 5}]})
        hooks[event] = groups
    if json.dumps(data, sort_keys=True) == before:
        return ''
    if config.exists():
        shutil.copyfile(config, config.with_name(config.name + '.bak'))
    config.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(config)
    return ''


def codex_cli() -> Optional[str]:
    found = shutil.which('codex')
    if found:
        return found
    for candidate in (Path('/opt/homebrew/bin/codex'), Path('/usr/local/bin/codex'), Path.home() / '.local' / 'bin' / 'codex',
                      Path(os.environ.get('APPDATA') or '') / 'npm' / 'codex.cmd'):
        if str(candidate) not in ('', '.') and candidate.is_file():
            return str(candidate)
    return None


def gemini_cli() -> Optional[str]:
    found = shutil.which('gemini')
    if found:
        return found
    for candidate in (Path('/opt/homebrew/bin/gemini'), Path('/usr/local/bin/gemini'), Path.home() / '.local' / 'bin' / 'gemini',
                      Path(os.environ.get('APPDATA') or '') / 'npm' / 'gemini.cmd'):
        if str(candidate) not in ('', '.') and candidate.is_file():
            return str(candidate)
    return None


def gemini_config_path() -> Path:
    return Path.home() / '.gemini' / 'settings.json'


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


# (key, name shown, what to do so the app sees the new entry)
APPS = [('desktop', 'Claude Desktop', 'quit and reopen Claude Desktop'),
        ('code', 'Claude Code', 'start a new Claude Code session'),
        ('codex', 'Codex', 'start a new Codex session'),
        ('gemini', 'Gemini CLI', 'start a new Gemini CLI session')]


def _file_has_entry(config: Path) -> bool:
    try:
        entry = (json.loads(config.read_text(encoding='utf-8')).get('mcpServers') or {}).get(NAME)
    except (OSError, ValueError, AttributeError):
        return False
    return bool(entry) and [entry.get('command'), *entry.get('args', [])] == server_command()


def status() -> dict:
    """Which AI apps are here: None (not installed), 'available' or 'connected' (to this GeckoPlotter)."""
    desktop, code, codex, gemini = desktop_config_path(), claude_code_cli(), codex_cli(), gemini_cli()
    return {'desktop': ('connected' if _file_has_entry(desktop) else 'available') if desktop.parent.exists() else None,
            'code': ('connected' if _cli_has_entry(code) else 'available') if code else None,
            'codex': ('connected' if _cli_has_entry(codex) else 'available') if codex else None,
            'gemini': ('connected' if _file_has_entry(gemini_config_path()) else 'available') if gemini else None,
            'ready': agent_package_ready(), 'command': server_command()}


def _result(key: str, ok: bool, already: bool = False, error: str = '') -> dict:
    name, restart = next((n, r) for k, n, r in APPS if k == key)
    return {'app': name, 'ok': ok, 'restart': '' if already or not ok else restart, 'error': error}


def _replace_entry(cli: str, key: str, remove_scopes, add_args) -> dict:
    """Remove the old entry and add this GeckoPlotter's; tried twice, because a running session of the app can write
    its settings file back between the two steps."""
    if _cli_has_entry(cli):
        return _result(key, True, already=True)
    done = None
    for _attempt in range(2):
        for scope in remove_scopes:
            _run(cli, 'mcp', 'remove', *scope, NAME)
        done = _run(cli, 'mcp', 'add', *add_args, NAME, '--', *server_command())
        if done.returncode == 0 or _cli_has_entry(cli):
            return _result(key, True)
    return _result(key, False, error=(done.stderr or done.stdout).strip()[:200])


def _write_entry(config: Path, key: str) -> dict:
    """Add or replace the entry in a JSON settings file, keeping everything else (and a .bak copy)."""
    if _file_has_entry(config):
        return _result(key, True, already=True)
    data = {}
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding='utf-8'))
        except ValueError:
            return _result(key, False, error=f'its settings file could not be read ({config}); nothing was changed')
        shutil.copyfile(config, config.with_name(config.name + '.bak'))
    config.parent.mkdir(parents=True, exist_ok=True)
    command = server_command()
    data.setdefault('mcpServers', {})[NAME] = {'command': command[0], 'args': command[1:]}
    tmp = config.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(config)
    return _result(key, True)


def connect_desktop() -> dict:
    return _write_entry(desktop_config_path(), 'desktop')


def connect_gemini() -> dict:
    return _write_entry(gemini_config_path(), 'gemini')


def connect_code() -> dict:
    # An older entry added by hand may sit in the local scope (the default) as well as the user scope.
    done = _replace_entry(claude_code_cli(), 'code', [('--scope', 'local'), ('--scope', 'user')], ('--scope', 'user'))
    if done['ok']:
        try:
            problem = write_hooks()
        except OSError as exc:
            problem = str(exc)
        if problem:
            done['error'] = 'turn hooks not added: ' + problem
    return done


def connect_codex() -> dict:
    return _replace_entry(codex_cli(), 'codex', [()], ())


def connect() -> dict:
    """Connect every AI app found: {'results': [{app, ok, restart, error}], 'message': text when nothing was done}."""
    if not agent_package_ready():
        return {'results': [], 'message': 'The agent interface is not installed in this GeckoPlotter yet: close '
                                          'GeckoPlotter and start it again so it updates, then try again.'}
    found = status()
    steps = {'desktop': connect_desktop, 'code': connect_code, 'codex': connect_codex, 'gemini': connect_gemini}
    results = [steps[key]() for key, _name, _restart in APPS if found[key]]
    return {'results': results, 'message': '' if results else
            'No AI app found on this computer (Claude Desktop, Claude Code, Codex or Gemini CLI). Install one, then '
            'connect again.'}
