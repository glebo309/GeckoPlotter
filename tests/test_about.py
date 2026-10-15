"""The About window names the running version: from git in a checkout, from the launcher's record in an install."""
import json

from services import about


def test_a_launcher_install_reads_its_commit_from_installed_json(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'app.py').write_text('')
    (tmp_path / 'installed.json').write_text(json.dumps({'sha': 'a0e974d71fb7da807eb898d2e6e212a5fe923615'}))
    monkeypatch.setattr(about, 'ROOT', app)
    version = about._read_version()
    assert version['source'] == 'launcher' and version['sha'].startswith('a0e974d')
    monkeypatch.setattr(about, 'VERSION', version)
    data = about.info()
    assert data['version'] == 'a0e974d'
    assert data['commit_url'].endswith('/commit/a0e974d71fb7da807eb898d2e6e212a5fe923615')
    assert 'GeckoPlotter a0e974d' in about.as_text(data)
    assert about.update_status(version['sha']).startswith('Up to date')
    assert 'newer version (1234567)' in about.update_status('1234567' + '0' * 33)
    assert about.update_status(None).startswith('Could not reach GitHub')


def test_without_git_or_a_record_the_version_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(about, 'ROOT', tmp_path)
    assert about._read_version() == {'sha': '', 'source': 'unknown'}
