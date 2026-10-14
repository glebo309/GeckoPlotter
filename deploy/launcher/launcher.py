#!/usr/bin/env python3
"""GeckoPlotter launcher: update from GitHub, install what is missing, start the app on this computer.

Standard library only. The Start scripts run it with a private Python managed by ``uv``, so nothing is installed
system-wide. It shows an animated progress page in the browser while it works, then sends that tab to the app.

Folder (per user): Windows %LOCALAPPDATA%/GeckoPlotter, macOS ~/Library/Application Support/GeckoPlotter,
Linux ~/.local/share/GeckoPlotter. It holds ``app`` (the code), ``venv`` (the packages), ``installed.json``
and ``launcher.log``. Autosaves and projects stay where the app already puts them (~/Documents/GeckoPlotter).

Settings for testing and forks: GECKO_REPO, GECKO_BRANCH, GECKO_HOME, GECKO_SOURCE_ZIP (a local zip instead of
GitHub), GECKO_SKIP_INSTALL=1, GECKO_APP_CMD (run this command instead of app.py).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
import zipfile
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = os.environ.get('GECKO_REPO', 'glebo309/GeckoPlotter')
BRANCH = os.environ.get('GECKO_BRANCH', 'main')
SOURCE_ZIP = os.environ.get('GECKO_SOURCE_ZIP')
PYTHON_VERSION = '3.12'
FIRST_PORT = 8052
USER_AGENT = {'User-Agent': 'GeckoPlotter-launcher'}
IS_WINDOWS = platform.system() == 'Windows'


def data_dir() -> Path:
    if os.environ.get('GECKO_HOME'):
        return Path(os.environ['GECKO_HOME'])
    if IS_WINDOWS:
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'GeckoPlotter'
    if platform.system() == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'GeckoPlotter'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'GeckoPlotter'


HOME = data_dir()
APP = HOME / 'app'
VENV = HOME / 'venv'
STATE_FILE = HOME / 'installed.json'
LOG_FILE = HOME / 'launcher.log'
VENV_PYTHON = VENV / ('Scripts/python.exe' if IS_WINDOWS else 'bin/python')


def log(message: str) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as handle:
        handle.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")}  {message}\n')


# ---------------------------------------------------------------------------
# What the progress page shows
# ---------------------------------------------------------------------------

class Status:
    STEPS = [('check', 'Looking for the latest version'), ('download', 'Fetching GeckoPlotter'),
             ('install', 'Installing what it needs'), ('start', 'Waking the app up')]

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = {key: 'todo' for key, _ in self.STEPS}
        self.detail = ''
        self.url = ''
        self.error = ''
        self.version = ''
        self.started = {}
        self.lines = deque(maxlen=6)

    def set(self, key: str, value: str, detail: str = '') -> None:
        with self.lock:
            self.state[key] = value
            if value == 'active':
                self.started[key] = time.time()
            if detail or value == 'active':
                self.detail = detail
                if detail:
                    self.lines.append(detail)

    def note(self, detail: str) -> None:
        with self.lock:
            self.detail = detail[:160]
            self.lines.append(detail[:160])

    def progress(self) -> float:
        weights = {'check': .05, 'download': .15, 'install': .55, 'start': .25}
        total = 0.0
        for key, weight in weights.items():
            if self.state[key] in ('done', 'skip'):
                total += weight
            elif self.state[key] == 'active':
                elapsed = time.time() - self.started.get(key, time.time())
                total += weight * (1 - math.exp(-elapsed / (60 if key == 'install' else 12))) * .95
        return 1.0 if self.url else min(total, .99)

    def snapshot(self) -> dict:
        with self.lock:
            return {'steps': [{'key': key, 'label': label, 'state': self.state[key]} for key, label in self.STEPS],
                    'detail': self.detail, 'url': self.url, 'error': self.error, 'version': self.version,
                    'progress': self.progress(), 'log': str(LOG_FILE), 'lines': list(self.lines)}


STATUS = Status()


def asset(name: str) -> Path | None:
    """A launcher file (splash.html, icon.png ...): the copy in the home folder, else the one next to this script."""
    here = Path(__file__).resolve().parent
    for candidate in (HOME / name, here / name, here / 'icon' / name):
        if candidate.exists():
            return candidate
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.startswith('/status'):
            body, kind = json.dumps(STATUS.snapshot()).encode(), 'application/json'
        elif self.path in ('/icon.png', '/favicon.ico') and asset('icon.png'):
            body, kind = asset('icon.png').read_bytes(), 'image/png'
        else:
            page = asset('splash.html')
            body = page.read_bytes() if page else b'<h1>GeckoPlotter is starting...</h1>'
            kind = 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def start_splash() -> str:
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{server.server_address[1]}/'


# ---------------------------------------------------------------------------
# Update, install, start
# ---------------------------------------------------------------------------

def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding='utf-8')


def latest_sha() -> str | None:
    """The newest commit on the branch, or None when GitHub cannot be reached (offline, rate limit)."""
    if SOURCE_ZIP:
        return hashlib.sha256(Path(SOURCE_ZIP).read_bytes()).hexdigest()[:40]
    request = urllib.request.Request(f'https://api.github.com/repos/{REPO}/commits/{BRANCH}',
                                     headers={**USER_AGENT, 'Accept': 'application/vnd.github.sha'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read().decode().strip() or None
    except Exception as error:                                # noqa: BLE001 - any failure means "use what is installed"
        log(f'could not ask GitHub for the latest version: {error}')
        return None


def download_zip(target: Path) -> None:
    if SOURCE_ZIP:
        shutil.copyfile(SOURCE_ZIP, target)
        return
    request = urllib.request.Request(f'https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}', headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=60) as response, open(target, 'wb') as out:
        shutil.copyfileobj(response, out)


def _portable(relative: str) -> bool:
    """False for names Windows cannot create (a stray macOS "Icon\\r" file, "a:b", ...): those are skipped."""
    return not any(ch in '<>:"|?*' or ord(ch) < 32 for ch in relative.replace('/', ''))


def replace_app(zip_path: Path) -> None:
    """Unpack the zip next to the current code, then swap folders, so a failed download never breaks what works."""
    staging, old = HOME / 'app.new', HOME / 'app.old'
    shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        root = archive.namelist()[0].split('/')[0] + '/'
        for info in archive.infolist():
            relative = info.filename[len(root):] if info.filename.startswith(root) else ''
            if not relative or '..' in Path(relative).parts or not _portable(relative):
                continue
            target = staging / relative
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, open(target, 'wb') as out:
                    shutil.copyfileobj(source, out)
    shutil.rmtree(old, ignore_errors=True)
    if APP.exists():
        APP.rename(old)
    staging.rename(APP)
    shutil.rmtree(old, ignore_errors=True)


def find_uv() -> str:
    found = shutil.which('uv') or os.environ.get('UV')
    if not found:
        raise RuntimeError('The Python helper "uv" was not found. Run the Start script again.')
    return found


def run_logged(command: list[str], **kwargs) -> None:
    """Run a command, keep its output in the log and show its latest line on the page."""
    log('run: ' + ' '.join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding='utf-8', errors='replace', **kwargs)
    for line in process.stdout:                               # type: ignore[union-attr]
        line = line.rstrip()
        if line:
            log('  ' + line)
            STATUS.note(line)
    if process.wait() != 0:
        raise RuntimeError(f'A setup step failed ({Path(command[0]).name}). Details are in {LOG_FILE}')


def requirements_hash() -> str:
    text = (APP / 'requirements.txt').read_bytes() if (APP / 'requirements.txt').exists() else b''
    return hashlib.sha256(text + PYTHON_VERSION.encode()).hexdigest()[:16]


def free_port(first: int) -> int:
    for port in range(first, first + 40):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError('No free port found for the app.')


def prepare() -> subprocess.Popen:
    state = read_state()

    STATUS.set('check', 'active', 'Asking GitHub for the newest version')
    remote = latest_sha()
    need_download = not (APP / 'app.py').exists() or (remote is not None and remote != state.get('sha'))
    if not (APP / 'app.py').exists() and remote is None and not SOURCE_ZIP:
        raise RuntimeError('GeckoPlotter could not be downloaded. Check the internet connection and start it again.')
    STATUS.set('check', 'done')

    if need_download:
        STATUS.set('download', 'active', 'Downloading the newest code')
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'gecko.zip'
            download_zip(archive)
            STATUS.note('Unpacking')
            replace_app(archive)
        state['sha'] = remote or state.get('sha', 'unknown')
        write_state(state)
        STATUS.set('download', 'done')
    else:
        STATUS.set('download', 'skip', 'Already up to date')

    STATUS.version = (state.get('sha') or '')[:7]
    wanted = requirements_hash()
    if os.environ.get('GECKO_SKIP_INSTALL') or (VENV_PYTHON.exists() and state.get('requirements') == wanted):
        STATUS.set('install', 'skip', 'Everything is already installed')
    else:
        STATUS.set('install', 'active', 'First start: installing packages. This takes a few minutes, once.')
        uv = find_uv()
        if not VENV_PYTHON.exists():
            run_logged([uv, 'venv', '--python', PYTHON_VERSION, str(VENV)])
        run_logged([uv, 'pip', 'install', '--python', str(VENV_PYTHON), '-r', str(APP / 'requirements.txt')])
        state['requirements'] = wanted
        write_state(state)
        STATUS.set('install', 'done')

    STATUS.set('start', 'active', 'Starting GeckoPlotter')
    port = free_port(FIRST_PORT)
    environment = {**os.environ, 'GECKO_HOST': '127.0.0.1', 'GECKO_PORT': str(port), 'GECKO_DEBUG': '0',
                   'PYTHONUNBUFFERED': '1', 'PYTHONUTF8': '1'}
    command = shlex.split(os.environ['GECKO_APP_CMD'].replace('{port}', str(port)), posix=not IS_WINDOWS) \
        if os.environ.get('GECKO_APP_CMD') else [str(VENV_PYTHON), 'app.py']
    out = open(HOME / 'app.log', 'a', encoding='utf-8')
    process = subprocess.Popen(command, cwd=APP, env=environment, stdout=out, stderr=subprocess.STDOUT)
    deadline = time.time() + 240
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'GeckoPlotter stopped while starting. Details are in {HOME / "app.log"}')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2):
                break
        except Exception:                                      # noqa: BLE001 - not up yet
            time.sleep(.4)
    else:
        process.terminate()
        raise RuntimeError('GeckoPlotter did not start in time.')
    STATUS.set('start', 'done')
    STATUS.url = f'http://127.0.0.1:{port}/'
    log(f'running at {STATUS.url} (version {STATUS.version})')
    return process


SHORTCUTS_VERSION = 2                                  # raise to rebuild everyone's shortcut once
ICONS = ('icon.png', 'icon.ico', 'icon.icns')


def fetch_icons() -> None:
    """The shortcut icon comes from GitHub too, so the download stays a handful of scripts."""
    for name in ICONS:
        target = HOME / name
        if target.exists() or os.environ.get('GECKO_SOURCE_ZIP'):
            continue
        try:
            request = urllib.request.Request(
                f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/deploy/launcher/icon/{name}', headers=USER_AGENT)
            with urllib.request.urlopen(request, timeout=20) as response:
                target.write_bytes(response.read())
        except Exception as error:                             # noqa: BLE001 - a shortcut without icon still works
            log(f'could not fetch {name}: {error}')


def create_shortcuts() -> None:
    """Once per computer: a GeckoPlotter entry with the gecko icon (Start menu and Desktop on Windows, an app in
    ~/Applications on macOS, the applications menu on Linux) that runs the Start script kept in the home folder."""
    if os.environ.get('GECKO_NO_SHORTCUTS'):
        return
    state = read_state()
    if state.get('shortcuts') == SHORTCUTS_VERSION:
        return
    system = platform.system()
    try:
        if system == 'Windows':
            script, icon = HOME / 'start-windows.bat', asset('icon.ico')
            if not script.exists():
                return
            ps = ("$w = New-Object -ComObject WScript.Shell; "
                  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
                  "$s = $w.CreateShortcut((Join-Path $d 'GeckoPlotter.lnk')); "
                  f"$s.TargetPath = '{script}'; $s.WorkingDirectory = '{HOME}'; "
                  f"$s.IconLocation = '{icon or ''}'; $s.Description = 'GeckoPlotter'; $s.Save() }}")
            subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                           check=True, capture_output=True, timeout=60)
        elif system == 'Darwin':
            script = HOME / 'start-mac.command'
            if not script.exists():
                return
            app = Path.home() / 'Applications' / 'GeckoPlotter.app'
            (app / 'Contents' / 'MacOS').mkdir(parents=True, exist_ok=True)
            (app / 'Contents' / 'Resources').mkdir(parents=True, exist_ok=True)
            if asset('icon.icns'):
                shutil.copyfile(asset('icon.icns'), app / 'Contents' / 'Resources' / 'icon.icns')
            (app / 'Contents' / 'Info.plist').write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                '<key>CFBundleName</key><string>GeckoPlotter</string>'
                '<key>CFBundleDisplayName</key><string>GeckoPlotter</string>'
                '<key>CFBundleIdentifier</key><string>xyz.glecko.geckoplotter</string>'
                '<key>CFBundleExecutable</key><string>GeckoPlotter</string>'
                '<key>CFBundleIconFile</key><string>icon</string>'
                '<key>CFBundlePackageType</key><string>APPL</string>'
                '<key>CFBundleShortVersionString</key><string>1.0</string>'
                '</dict></plist>\n', encoding='utf-8')
            runner = app / 'Contents' / 'MacOS' / 'GeckoPlotter'
            runner.write_text(f'#!/bin/sh\nexec open -a Terminal "{script}"\n', encoding='utf-8')
            runner.chmod(0o755)
        else:
            script = HOME / 'start-linux.sh'
            if not script.exists():
                return
            entries = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'applications'
            entries.mkdir(parents=True, exist_ok=True)
            (entries / 'geckoplotter.desktop').write_text(
                '[Desktop Entry]\nType=Application\nName=GeckoPlotter\nComment=HPLC and LC-MS data, plotted\n'
                f'Exec=bash "{script}"\nIcon={asset("icon.png") or ""}\nTerminal=true\nCategories=Science;Education;\n',
                encoding='utf-8')
        state['shortcuts'] = SHORTCUTS_VERSION
        write_state(state)
        log('created the GeckoPlotter shortcut')
    except Exception as error:                                 # noqa: BLE001 - a missing shortcut never blocks the app
        log(f'could not create the shortcut: {error}')


def ensure_chrome() -> None:
    """Figure export (PNG/PDF) needs a Chrome that kaleido can drive. Fetch one in the background, once, if missing."""
    if os.environ.get('GECKO_SKIP_INSTALL') or os.environ.get('GECKO_APP_CMD'):
        return
    state = read_state()
    wanted = requirements_hash()
    if state.get('chrome') == wanted:
        return
    try:
        run_logged([str(VENV_PYTHON), '-c', 'import kaleido; kaleido.get_chrome_sync()'])
        state['chrome'] = wanted
        write_state(state)
    except Exception as error:                                 # noqa: BLE001 - export only; the app itself runs
        log(f'could not set up the figure-export browser: {error}')


def main() -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    splash = start_splash()
    print('GeckoPlotter is starting. Your browser opens in a moment.', flush=True)
    print(f'(If it does not, open {splash} yourself.)', flush=True)
    print('Keep this window open while you work. Close it to stop GeckoPlotter.\n', flush=True)
    if not os.environ.get('GECKO_NO_BROWSER'):
        webbrowser.open(splash)
    try:
        process = prepare()
    except Exception as error:                                 # noqa: BLE001 - show every failure on the page
        log(traceback.format_exc())
        STATUS.error = str(error)
        print(f'\nSomething went wrong: {error}\n', flush=True)
        if sys.stdin and sys.stdin.isatty():
            input('Press Enter to close this window. ')
        else:
            time.sleep(600)
        return 1
    print(f'GeckoPlotter is running at {STATUS.url}', flush=True)
    threading.Thread(target=ensure_chrome, daemon=True).start()
    if not os.environ.get('GECKO_NO_SHORTCUTS'):
        fetch_icons()
    create_shortcuts()
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 0


if __name__ == '__main__':
    sys.exit(main())
