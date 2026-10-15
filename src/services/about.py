"""What is running: the version (commit), where it came from, the packages and the folders, for the About window.

The version is read once, when the app starts, so it names the code that is running even after the launcher has
fetched a newer one. An install made by the launcher keeps its commit in ``installed.json`` next to the ``app``
folder; a git checkout is asked directly.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from importlib import metadata as _metadata
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]              # the folder holding app.py
REPO = os.environ.get('GECKO_REPO', 'glebo309/GeckoPlotter')
BRANCH = os.environ.get('GECKO_BRANCH', 'main')
STARTED = time.time()


def _git(*args: str) -> str:
    try:
        done = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return ''
    return done.stdout.strip() if done.returncode == 0 else ''


def _read_version() -> dict:
    if (ROOT / '.git').exists():
        sha = _git('rev-parse', 'HEAD')
        if sha:
            return {'sha': sha, 'source': 'git', 'branch': _git('rev-parse', '--abbrev-ref', 'HEAD'),
                    'date': _git('log', '-1', '--format=%cI'), 'subject': _git('log', '-1', '--format=%s'),
                    'changed': bool(_git('status', '--porcelain', '--untracked-files=no'))}
    try:
        state = json.loads((ROOT.parent / 'installed.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    sha = str(state.get('sha') or '')
    if re.fullmatch(r'[0-9a-f]{40}', sha):
        try:                                            # the launcher unpacks the download: its files carry that time
            updated = datetime.fromtimestamp((ROOT / 'app.py').stat().st_mtime).isoformat(timespec='seconds')
        except OSError:
            updated = ''
        return {'sha': sha, 'source': 'launcher', 'branch': BRANCH, 'updated': updated}
    return {'sha': '', 'source': 'unknown'}


VERSION = _read_version()


def _package(name: str) -> str:
    try:
        return _metadata.version(name)
    except _metadata.PackageNotFoundError:
        return '-'


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime('%d %b %Y, %H:%M')
    except (TypeError, ValueError):
        return ''


def _system() -> str:
    if sys.platform == 'darwin':
        return f'macOS {platform.mac_ver()[0]} ({platform.machine()})'
    if sys.platform.startswith('win'):
        return f'Windows {platform.release()} ({platform.machine()})'
    return f'{platform.system()} {platform.release()} ({platform.machine()})'


def info() -> dict:
    """Everything the About window shows, as label -> text groups."""
    from services import session_service
    sha = VERSION.get('sha', '')
    if VERSION['source'] == 'git':
        source = f"Git checkout, branch {VERSION.get('branch') or '?'}"
        if VERSION.get('changed'):
            source += ', with uncommitted changes'
        made = _when(VERSION.get('date', ''))
    elif VERSION['source'] == 'launcher':
        source = f"Installed by the launcher from {VERSION.get('branch')}"
        made = ''
    else:
        source, made = 'Unknown (no git and no launcher record)', ''
    settings = os.environ.get('GECKO_SETTINGS_DIR') or str(Path.home() / 'Documents' / 'GeckoPlotter')
    log = ROOT.parent / 'app.log'
    return {
        'version': sha[:7] or 'unknown',
        'sha': sha,
        'commit_url': f'https://github.com/{REPO}/commit/{sha}' if sha else '',
        'repo_url': f'https://github.com/{REPO}',
        'subject': VERSION.get('subject', ''),
        'details': [
            ('Source', source),
            *([('Committed', made)] if made else []),
            *([('Downloaded', _when(VERSION['updated']))] if VERSION.get('updated') else []),
            ('Running since', datetime.fromtimestamp(STARTED).strftime('%d %b %Y, %H:%M')),
            ('Computer', _system()),
            ('Python', platform.python_version()),
            ('Packages', ', '.join(f'{name} {_package(name)}' for name in
                                   ('dash', 'plotly', 'dash-mantine-components', 'numpy', 'pandas', 'scipy'))),
        ],
        'folders': [
            ('Program', str(ROOT)),
            ('Autosaves', str(session_service.autosave_dir(create=False))),
            ('Settings', settings),
            *([('Log', str(log))] if log.exists() else []),
        ],
    }


def as_text(data: dict) -> str:
    """The same, as plain text to paste into a message."""
    lines = [f"GeckoPlotter {data['version']}" + (f" ({data['sha']})" if data['sha'] else '')]
    lines += [f'{label}: {value}' for label, value in data['details'] + data['folders']]
    return '\n'.join(lines)


def latest_sha(timeout: float = 4.0) -> Optional[str]:
    """The newest commit of the branch the launcher installs, from GitHub's ref listing (no rate limit), or None."""
    try:
        request = urllib.request.Request(f'https://github.com/{REPO}.git/info/refs?service=git-upload-pack',
                                         headers={'User-Agent': 'GeckoPlotter-about'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            listing = response.read()
    except Exception:                                   # noqa: BLE001  offline, proxy, firewall
        return None
    match = re.search(rb'([0-9a-f]{40}) refs/heads/' + re.escape(BRANCH.encode()) + rb'\b', listing)
    return match.group(1).decode() if match else None


def update_status(latest: Optional[str]) -> str:
    sha = VERSION.get('sha', '')
    if latest is None:
        return f'Could not reach GitHub to compare with the newest version on {BRANCH}.'
    if latest == sha:
        return f'Up to date: this is the newest version on {BRANCH}.'
    if VERSION['source'] == 'launcher':
        idle = os.environ.get('GECKO_EXIT_WHEN_IDLE')      # started from the icon: it stops once no tab is open
        stop = (f'close every GeckoPlotter tab, wait {round(int(idle) / 60) if idle.isdigit() else 3} minutes'
                if idle else 'close the GeckoPlotter window')
        return f'A newer version ({latest[:7]}) is on GitHub. To update, {stop} and start GeckoPlotter again.'
    return f'The newest version on {BRANCH} is {latest[:7]}.'
