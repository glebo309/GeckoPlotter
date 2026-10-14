"""The one-click launcher: unpacking an update safely, and the start-up flow without a network or a real install."""
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / 'deploy' / 'launcher' / 'launcher.py'


def _make_zip(path, files):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return path


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    """The launcher module loaded fresh with its own home folder and a local zip standing in for GitHub."""
    source = _make_zip(tmp_path / 'github.zip', {'GeckoPlotter-main/app.py': 'print(1)\n',
                                                 'GeckoPlotter-main/requirements.txt': 'dash==3.0.4\n',
                                                 'GeckoPlotter-main/src/a.py': 'x = 1\n'})
    monkeypatch.setenv('GECKO_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('GECKO_SOURCE_ZIP', str(source))
    monkeypatch.setenv('GECKO_SKIP_INSTALL', '1')
    monkeypatch.delenv('GECKO_NO_SHORTCUTS', raising=False)
    monkeypatch.setenv('GECKO_APP_CMD', f'{sys.executable} -m http.server {{port}} --bind 127.0.0.1')
    spec = importlib.util.spec_from_file_location('gecko_launcher_under_test', LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_update_replaces_the_code_and_ignores_paths_that_climb_out(launcher, tmp_path):
    launcher.HOME.mkdir(parents=True)
    launcher.APP.mkdir()
    (launcher.APP / 'old.txt').write_text('old')
    archive = _make_zip(tmp_path / 'u.zip', {'GeckoPlotter-main/app.py': 'new', 'GeckoPlotter-main/../evil.txt': 'x',
                                             'GeckoPlotter-main/sub/b.py': 'b',
                                             'GeckoPlotter-main/Icon\r': '', 'GeckoPlotter-main/a:b.txt': ''})
    launcher.replace_app(archive)
    assert (launcher.APP / 'app.py').read_text() == 'new' and (launcher.APP / 'sub' / 'b.py').exists()
    assert not (launcher.APP / 'old.txt').exists() and not (launcher.HOME / 'evil.txt').exists()
    assert not (launcher.HOME / 'app.old').exists() and not (launcher.HOME / 'app.new').exists()
    assert sorted(p.name for p in launcher.APP.iterdir()) == ['app.py', 'sub']     # names Windows rejects are skipped


def test_packages_are_reinstalled_only_when_the_requirements_change(launcher):
    launcher.APP.mkdir(parents=True)
    (launcher.APP / 'requirements.txt').write_text('dash==3.0.4\n')
    first = launcher.requirements_hash()
    assert launcher.requirements_hash() == first
    (launcher.APP / 'requirements.txt').write_text('dash==3.0.4\nolefile\n')
    assert launcher.requirements_hash() != first


def test_without_internet_the_latest_version_is_unknown_not_an_error(launcher, monkeypatch):
    monkeypatch.setattr(launcher, 'SOURCE_ZIP', None)
    monkeypatch.setattr(launcher.urllib.request, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
    assert launcher.latest_sha() is None


def test_first_start_downloads_unpacks_starts_the_app_and_a_second_start_reuses_it(launcher):
    process = launcher.prepare()
    try:
        assert launcher.STATUS.url.startswith('http://127.0.0.1:')
        assert (launcher.APP / 'app.py').exists() and launcher.read_state()['sha']
        steps = launcher.STATUS.snapshot()['steps']
        assert [s['state'] for s in steps] == ['done', 'done', 'skip', 'done']
        assert launcher.STATUS.snapshot()['progress'] == 1.0
    finally:
        process.terminate()
        process.wait(timeout=10)
    launcher.STATUS = launcher.Status()
    process = launcher.prepare()
    try:
        assert launcher.STATUS.snapshot()['steps'][1]['state'] == 'skip'      # same version: nothing downloaded
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_the_mac_shortcut_is_an_app_with_the_gecko_icon_that_runs_the_start_script(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(launcher.Path, 'home', lambda: tmp_path / 'user')
    launcher.HOME.mkdir(parents=True)
    (launcher.HOME / 'Start GeckoPlotter.command').write_text('#!/bin/bash\n')
    launcher.create_shortcuts()
    app = tmp_path / 'user' / 'Applications' / 'GeckoPlotter.app' / 'Contents'
    runner = app / 'MacOS' / 'GeckoPlotter'
    assert 'Start GeckoPlotter.command' in runner.read_text() and runner.stat().st_mode & 0o111
    assert '<string>icon</string>' in (app / 'Info.plist').read_text() and (app / 'Resources' / 'icon.icns').exists()
    assert launcher.read_state()['shortcuts'] == 1
    (runner).unlink()
    launcher.create_shortcuts()                                # only once: a removed shortcut is not forced back
    assert not runner.exists()


def test_the_linux_shortcut_is_a_menu_entry(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.platform, 'system', lambda: 'Linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'share'))
    launcher.HOME.mkdir(parents=True)
    (launcher.HOME / 'start-geckoplotter.sh').write_text('#!/bin/sh\n')
    launcher.create_shortcuts()
    entry = (tmp_path / 'share' / 'applications' / 'geckoplotter.desktop').read_text()
    assert 'Name=GeckoPlotter' in entry and 'start-geckoplotter.sh' in entry and 'icon.png' in entry
