"""A double-clicked .gecko: the launcher is started with the file, opens the app at ?open=<path>, and registers the
file type (macOS applet, Windows registry)."""
import importlib.util
import platform
import shutil
import sys
import types
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / 'deploy' / 'launcher' / 'launcher.py'


def _load(monkeypatch, tmp_path, argv):
    monkeypatch.setenv('GECKO_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(sys, 'argv', ['launcher.py', *argv])
    spec = importlib.util.spec_from_file_location('gecko_launcher_open_test', LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_launcher_opens_the_app_at_the_project_it_was_given(monkeypatch, tmp_path):
    project = tmp_path / 'My project.gecko'
    project.write_bytes(b'PK')
    launcher = _load(monkeypatch, tmp_path, ['--background', '--open', str(project)])
    assert launcher.OPEN_PROJECT == str(project.resolve())
    url = launcher.with_project('http://127.0.0.1:8052/')
    assert url.startswith('http://127.0.0.1:8052/?open=') and '%20project.gecko' in url and ' ' not in url

    plain = _load(monkeypatch, tmp_path, ['--background'])
    assert plain.OPEN_PROJECT is None and plain.with_project('http://127.0.0.1:8052/') == 'http://127.0.0.1:8052/'
    missing = _load(monkeypatch, tmp_path, ['--open', str(tmp_path / 'gone.gecko')])
    assert missing.OPEN_PROJECT is None                      # a file that is not there is not passed on


def test_windows_registers_gecko_files_for_this_user_with_the_icon(monkeypatch, tmp_path):
    written = {}

    class Key:
        def __init__(self, path): self.path = path
        def __enter__(self): return self
        def __exit__(self, *exc): return False

    fake = types.SimpleNamespace(HKEY_CURRENT_USER='HKCU', REG_SZ=1, CreateKey=lambda root, path: Key(path),
                                 SetValueEx=lambda key, name, reserved, kind, value: written.__setitem__(key.path, value))
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    launcher = _load(monkeypatch, tmp_path, [])
    launcher.register_windows_file_type('"uvw.exe" run launcher.py --background --open "%1"', r'C:\G\icon.ico')
    assert written[r'Software\Classes\.gecko'] == 'GeckoPlotter.Project'
    assert written[r'Software\Classes\GeckoPlotter.Project\shell\open\command'].endswith('--open "%1"')
    assert written[r'Software\Classes\GeckoPlotter.Project\DefaultIcon'] == r'"C:\G\icon.ico",0'


def _forget(app):
    """macOS registers every app bundle it sees: a test copy must not become the app that owns .gecko files."""
    import subprocess
    lsregister = ('/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/'
                  'Support/lsregister')
    if Path(lsregister).exists():
        subprocess.run([lsregister, '-u', str(app)], capture_output=True, timeout=60)


@pytest.mark.skipif(platform.system() != 'Darwin' or not shutil.which('osacompile'), reason='macOS only')
def test_the_mac_app_declares_gecko_files_and_is_signed(monkeypatch, tmp_path):
    import plistlib
    import subprocess
    launcher = _load(monkeypatch, tmp_path, [])
    monkeypatch.setenv('GECKO_APPS_DIR', str(tmp_path / 'apps'))
    launcher.HOME.mkdir(parents=True)
    app = launcher.make_mac_app(tmp_path / 'apps', launcher.HOME / 'start-mac.command')
    _forget(app)
    info = plistlib.loads((app / 'Contents' / 'Info.plist').read_bytes())
    assert info['CFBundleIdentifier'] == 'xyz.glecko.geckoplotter'
    assert info['UTExportedTypeDeclarations'][0]['UTTypeTagSpecification']['public.filename-extension'] == ['gecko']
    assert info['CFBundleDocumentTypes'][0]['LSItemContentTypes'] == [launcher.PROJECT_TYPE]
    assert subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)]).returncode == 0
    assert '--open' in (launcher.HOME / 'GeckoPlotter.sh').read_text() or '"$@"' in (launcher.HOME / 'GeckoPlotter.sh').read_text()
