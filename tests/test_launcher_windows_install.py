"""Windows installs use prebuilt x64 packages, including recovery from an ARM environment."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
REQUEST = 'cpython-3.12-windows-x86_64'


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_HOME', str(tmp_path / 'GeckoPlotter'))
    monkeypatch.delenv('GECKO_SKIP_INSTALL', raising=False)
    monkeypatch.setattr('platform.system', lambda: 'Windows')
    spec = importlib.util.spec_from_file_location('windows_launcher', ROOT / 'deploy/launcher/launcher.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.APP.mkdir(parents=True)
    (module.APP / 'app.py').write_text('')
    (module.APP / 'requirements.txt').write_text('cryptography\n')
    monkeypatch.setattr(module, 'latest_sha', lambda: None)
    monkeypatch.setattr(module, 'find_uv', lambda: 'uv')
    return module


@pytest.mark.parametrize('architecture,installed,create', [
    (None, False, True),             # first install
    ('ARM64', False, True),          # Evely's failed install
    ('ARM64', True, True),           # old environment, even with a current requirements marker
    ('AMD64', True, False),          # healthy install is reused
    ('AMD64', False, False),         # package install retry keeps compatible Python
    ('broken', True, True),          # an interpreter which cannot start is repaired
])
def test_prepare_selects_and_repairs_windows_python(launcher, monkeypatch, architecture, installed, create):
    if architecture:
        launcher.VENV_PYTHON.parent.mkdir(parents=True)
        launcher.VENV_PYTHON.touch()
    if installed:
        launcher.write_state({'requirements': launcher.requirements_hash()})
    project = launcher.HOME / 'saved.gecko'
    project.write_bytes(b'project data')
    commands = []
    monkeypatch.setattr(launcher, 'run_logged', lambda command: commands.append(command))

    def probe(command, **kwargs):
        assert command[0] == str(launcher.VENV_PYTHON)
        if architecture == 'broken':
            raise OSError('invalid executable')
        build_platform = {'ARM64': 'win-arm64', 'AMD64': 'win-amd64'}[architecture]
        return SimpleNamespace(returncode=0, stdout=build_platform + '\n')

    monkeypatch.setattr(launcher.subprocess, 'run', probe)

    class Installed(Exception):
        pass

    def stop_before_starting_app(port):
        raise Installed()

    monkeypatch.setattr(launcher, 'free_port', stop_before_starting_app)
    with pytest.raises(Installed):
        launcher.prepare()
    venv_commands = [c for c in commands if c[1] == 'venv']
    assert bool(venv_commands) == create
    if create:
        assert venv_commands[0][venv_commands[0].index('--python') + 1] == REQUEST
        assert ('--clear' in venv_commands[0]) == bool(architecture)
        assert venv_commands[0][-1] == str(launcher.VENV)
    assert any(c[1:3] == ['pip', 'install'] for c in commands) == (create or not installed)
    assert project.read_bytes() == b'project data'


def test_windows_bootstrap_and_shortcuts_request_x64(launcher, monkeypatch):
    script = ROOT / 'deploy/launcher/start-windows.bat'
    assert f'uv run --python {REQUEST} --no-project' in script.read_text()
    (launcher.HOME / 'start-windows.bat').write_bytes(script.read_bytes())
    launcher.write_state({'shortcuts': 5})
    monkeypatch.setattr(launcher.shutil, 'which', lambda name: 'uvw.exe')
    commands = []
    monkeypatch.setattr(launcher.subprocess, 'run', lambda command, **kwargs: commands.append(command))
    registered = []
    monkeypatch.setattr(launcher, 'register_windows_file_type', lambda command, icon: registered.append(command))
    launcher.create_shortcuts()
    assert commands and REQUEST in commands[0][-1]
    assert registered and REQUEST in registered[0]


def test_emulated_x64_python_is_compatible_on_an_arm_computer(launcher, monkeypatch):
    launcher.VENV_PYTHON.parent.mkdir(parents=True)
    launcher.VENV_PYTHON.touch()

    def probe(command, **kwargs):
        # platform.machine() describes the physical CPU; sysconfig describes Python's build.
        output = 'ARM64' if 'platform.machine()' in command[2] else 'win-amd64'
        return SimpleNamespace(returncode=0, stdout=output + '\n')

    monkeypatch.setattr(launcher.subprocess, 'run', probe)
    assert launcher.compatible_venv()
