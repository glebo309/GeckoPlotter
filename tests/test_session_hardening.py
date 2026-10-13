"""Hostile / damaged .gecko files: path traversal, half-applied restores, oversize members."""
import io
import json
import zipfile

import pytest

from services import session_service as ss
from services.data_store import DataStore
from services.peak_service import PeakService
from services.plot_settings_service import COLOR_PALETTES
from session_helpers import chromatogram_csv, edit_json, load_files, rewrite_zip

A_NAME = 'sampleA.csv'


def small_store():
    store = DataStore()
    (a,) = load_files(store, [(A_NAME, chromatogram_csv([3.0, 6.0]))])
    frame = a.dataframe
    store.peak_service.detect_peaks(a.bundle_id, frame.iloc[:, 1].to_numpy(float), frame.iloc[:, 0].to_numpy(float))
    return store, a


def snapshot(store):
    return ([b.bundle_id for b in store.iter_bundles()],
            {fid: [p.peak_id for p in plist] for fid, plist in store.peak_service._peaks.items()})


# ---------------------------------------------------------------- 1. sha256 as a path
@pytest.mark.parametrize('bad', ['../secret', '/etc/hosts', 'A' * 64, '0' * 63, ''])
def test_manifest_sha256_is_never_used_as_a_path(tmp_path, bad):
    store, _ = small_store()
    data = ss.build_session(store, embed_raw=False)
    good = json.loads(zipfile.ZipFile(io.BytesIO(data)).read('manifest.json'))['files'][0]['sha256']

    def swap(node):
        if isinstance(node, dict):
            return {k: (bad if k == 'sha256' and v == good else swap(v)) for k, v in node.items()}
        if isinstance(node, list):
            return [swap(v) for v in node]
        return node

    def change(name, content):
        if name in ('manifest.json', 'state.json'):
            value = swap(json.loads(content))
            if name == 'manifest.json':
                value['raw_cache'] = True
            return json.dumps(value).encode()
        return content

    folder = tmp_path / 'proj'
    (folder / 'raw').mkdir(parents=True)
    (folder / 'secret').write_bytes(chromatogram_csv([3.0, 6.0]))     # what '../secret' would reach
    path = folder / 'p.gecko'
    path.write_bytes(rewrite_zip(data, change))
    report = ss.restore_session(DataStore(), path)
    assert report.restored['bundles'] == 0
    assert report.missing_files and report.ok is False
    assert any('invalid checksum' in w for w in report.warnings)


def test_valid_sha256_helper():
    assert ss._valid_sha256('a' * 64)
    assert not ss._valid_sha256('../../x') and not ss._valid_sha256(None) and not ss._valid_sha256('A' * 64)


# ---------------------------------------------------------------- 2. restore must not destroy the workspace
def corrupted_peak_session():
    store, _ = small_store()
    data = ss.build_session(store)

    def edit(state):
        peak = next(iter(state['peaks']['peaks'].values()))[0]
        del peak['rt']                       # a required measurement
    return edit_json(data, 'state.json', edit)


def test_corrupt_peak_is_rejected_before_the_workspace_is_touched():
    live, _ = small_store()
    before = snapshot(live)
    with pytest.raises(ss.SessionFormatError, match='peaks'):
        ss.restore_session(live, corrupted_peak_session())
    assert snapshot(live) == before


def test_peak_without_identity_fields_gets_defaults():
    peak = PeakService._peak_from_dict({'rt': 1.0, 'rt_start': 0.9, 'rt_end': 1.1, 'area': 2.0,
                                        'height': 3.0, 'width': 0.2}, 'file-1')
    assert peak.file_id == 'file-1' and peak.peak_id and peak.name == ''


def test_failure_after_reset_rolls_back_to_the_previous_workspace(monkeypatch):
    live, _ = small_store()
    before = snapshot(live)
    donor, _ = small_store()
    data = ss.build_session(donor)

    def boom(*args, **kwargs):
        raise RuntimeError('boom')
    real = ss._apply_state
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('boom')
        return real(*args, **kwargs)
    monkeypatch.setattr(ss, '_apply_state', flaky)
    report = ss.restore_session(live, data)
    assert report.ok is False and report.rolled_back and report.workspace_replaced
    assert any('boom' in e for e in report.errors)
    assert snapshot(live)[0] == before[0]
    assert sum(len(v) for v in live.peak_service._peaks.values()) == sum(len(v) for v in before[1].values())


def test_failure_after_reset_without_snapshot_reports_and_keeps_partial(monkeypatch):
    live, _ = small_store()
    data = ss.build_session(small_store()[0])
    monkeypatch.setattr(ss, 'ROLLBACK_MAX_BYTES', 0)

    def boom(*args, **kwargs):
        raise RuntimeError('boom')
    monkeypatch.setattr(ss, '_apply_state', boom)
    report = ss.restore_session(live, data)
    assert report.ok is False and not report.rolled_back and report.workspace_replaced
    assert any('boom' in e for e in report.errors)
    assert report.restored['bundles'] == 1                 # the bundles that installed cleanly stay


# ---------------------------------------------------------------- 3. size caps
def test_oversize_state_json_is_refused_before_inflating(monkeypatch):
    data = ss.build_session(small_store()[0])
    monkeypatch.setattr(ss, 'MAX_JSON_BYTES', 100)
    with pytest.raises(ss.SessionFormatError, match='not safe'):
        ss.restore_session(DataStore(), data)


def test_raw_member_larger_than_declared_size_is_refused(monkeypatch):
    live = DataStore()
    data = ss.build_session(small_store()[0])
    data = edit_json(data, 'manifest.json', lambda m: m['files'][0].update(size=10))
    monkeypatch.setattr(ss, 'RAW_SLACK_BYTES', 0)
    report = ss.restore_session(live, data)
    assert report.ok is False
    assert any('not safe' in e for e in report.errors)
    assert report.restored['bundles'] == 0


def test_raw_member_within_declared_size_passes():
    report = ss.restore_session(DataStore(), ss.build_session(small_store()[0]))
    assert report.ok and report.restored['bundles'] == 1


def test_total_cap(monkeypatch):
    data = ss.build_session(small_store()[0])
    monkeypatch.setattr(ss, 'MAX_TOTAL_BYTES', 50)
    with pytest.raises(ss.SessionFormatError):
        ss.restore_session(DataStore(), data)


# ---------------------------------------------------------------- 5. palette default
def test_peak_service_default_palette_matches_its_name():
    ps = PeakService()
    assert ps._palette[:3] == COLOR_PALETTES[ps._palette_name][:3]
