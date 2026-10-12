"""Session save/restore engine: round trips, id preservation, policies and failure modes."""
import io
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services import session_service as ss
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult
from session_helpers import chromatogram_csv, edit_json, load_files, rewrite_zip

A_NAME, B_NAME = 'sampleA.csv', 'sampleB.csv'


def synthetic_store(extra_state=True):
    """Two real (re-ingestable) samples with peaks, a calibration and assorted user state."""
    store = DataStore()
    a, b = load_files(store, [(A_NAME, chromatogram_csv([3.0, 6.0])),
                              (B_NAME, chromatogram_csv([3.05, 6.1], amplitude=70.0))])
    peaks = store.peak_service
    for bundle in (a, b):
        frame = bundle.dataframe
        t, y = frame.iloc[:, 0].to_numpy(float), frame.iloc[:, 1].to_numpy(float)
        peaks.detect_peaks(bundle.bundle_id, y, t)
    # A deconvolved (EMG) peak with every deconvolution field and a manual baseline.
    deconvolved = peaks.add_baseline_peak(
        a.bundle_id, area=12.5, height=40.0, apex_x=4.5, poly_x=[4.0, 4.5, 5.0], poly_y=[0.0, 40.0, 0.0],
        p_line=[(4.0, 0.0), (5.0, 0.0)], q1=(4.0, 0.0), q2=(5.0, 0.0), source='deconvolved',
        deconv_group='deconv_4.5_c1', fit_params={'sigma': 0.1, 'gamma': 0.02, 'amplitude': 40.0})
    deconvolved.label, deconvolved.name = 'alanine', 'Comp 1'
    peaks.group_peaks_across_samples()
    peaks.set_peak_color(a.bundle_id, peaks.get_peaks(a.bundle_id)[0].peak_id, '#123456')
    model = store.calibration_service.create_model('Ala', 'grp-1', units='mM', signal_key='sig')
    for conc, area in [(1.0, 10.0), (2.0, 21.0), (4.0, 39.0)]:
        store.calibration_service.add_standard(model.model_id, 'std', conc, area)
    store.calibration_service.fit_model(model.model_id)
    store.integration_service.update_settings(a.bundle_id, smooth_window=15, baseline_method='none')
    if extra_state:
        store.visibility_state[b.bundle_id] = False
        store.collapse_state['tab-generic_time_min'] = 'collapsed'
        store.group_overrides = {b.bundle_id: ('custom_xyz', 'X')}
        store.file_ui_state[a.bundle_id] = {'file_id': a.bundle_id, 'view_mode': 'raw',
                                            'plot_settings': {'title': 'My chromatogram', 'font_size': 14},
                                            'pub_selections': {'x': {'data': {'row_ids': [1, 2]}}}}
        store._shared_plot_settings['ctx'] = {'palette': 'okabe', 'trace_overrides': {f'id:{a.bundle_id}:x': {'color': 'red'}}}
        store.analysis_plot_settings = {'smooth_window': 5}
        store.analysis_history.append({'at': '2026-01-01T00:00:00+00:00', 'trigger': ['test'], 'changes': {}})
        store.rename_dataset(a.bundle_id, 'Ala 5 mM (renamed)')
    return store, a, b


def peaks_of(store):
    return {fid: [dict(vars(p)) for p in plist] for fid, plist in store.peak_service._peaks.items()}


def frames_of(store):
    return {c.component_id: c.dataframe.copy() for b in store.iter_bundles() for c in b.component_list}


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_round_trip_preserves_ids_peaks_and_user_state():
    store, a, b = synthetic_store()
    client = {'plot-tabs': [{'id': 'tab-x', 'file': a.bundle_id}], 'active-file': a.bundle_id,
              'hidden-files': [b.bundle_id], 'file-order': {'tab-x': {'order': [b.bundle_id, a.bundle_id]}}}
    data = ss.build_session(store, client, project_name='Ala test')
    fresh = DataStore()
    report = ss.restore_session(fresh, data)

    assert report.ok, (report.errors, report.missing_files)
    assert report.warnings == []
    assert report.client_state == client
    assert report.info.project_name == 'Ala test'
    assert report.restored['bundles'] == 2 and report.restored['calibrations'] == 1
    assert list(fresh.all_bundles()) == list(store.all_bundles())          # ids and order
    for bundle in store.iter_bundles():
        restored = fresh.get_bundle(bundle.bundle_id)
        assert restored.name == bundle.name
        assert [c.component_id for c in restored.component_list] == [c.component_id for c in bundle.component_list]
        assert fresh.get_bundle_for_component(bundle.primary.component_id) is restored
        pd.testing.assert_frame_equal(restored.dataframe, bundle.dataframe)
        assert restored.column_roles == bundle.column_roles
    assert fresh.get_bundle(a.bundle_id).name == 'Ala 5 mM (renamed)'
    assert fresh.get_data_by_id(a.bundle_id)['metadata']['sample_name'] == 'Ala 5 mM (renamed)'

    # Peaks: every attribute equal, deconvolution fields and tuples included.
    assert peaks_of(fresh) == peaks_of(store)
    deconv = [p for p in fresh.peak_service.get_peaks(a.bundle_id) if p.source == 'deconvolved']
    assert len(deconv) == 1
    assert deconv[0].deconv_group == 'deconv_4.5_c1' and deconv[0].label == 'alanine'
    assert deconv[0].fit_params == {'sigma': 0.1, 'gamma': 0.02, 'amplitude': 40.0}
    assert deconv[0].p_line == [(4.0, 0.0), (5.0, 0.0)] and deconv[0].q1 == (4.0, 0.0)
    assert any(p.color == '#123456' for p in fresh.peak_service.get_peaks(a.bundle_id))
    assert fresh.peak_service.serialize() == store.peak_service.serialize()
    assert fresh.calibration_service.serialize() == store.calibration_service.serialize()
    assert fresh.integration_service.serialize() == store.integration_service.serialize()

    assert fresh.visibility_state == store.visibility_state
    assert fresh.collapse_state == store.collapse_state
    assert fresh.group_overrides == {b.bundle_id: ('custom_xyz', 'X')}
    assert fresh.file_ui_state == store.file_ui_state
    assert fresh._shared_plot_settings == store._shared_plot_settings
    assert fresh.analysis_plot_settings == store.analysis_plot_settings
    assert fresh.analysis_history == store.analysis_history
    assert fresh.session_meta['project_name'] == 'Ala test'


def test_instrument_peaks_are_not_imported_again_after_restore():
    store, a, _ = synthetic_store(extra_state=False)
    store.peak_service.import_instrument_peaks(
        a.bundle_id, [{'peak_number': 1, 'peak_name': 'X', 'retention_time': 3.0, 'area': 1.0, 'height': 1.0}])
    count = len(store.peak_service.get_peaks(a.bundle_id))
    fresh = DataStore()
    ss.restore_session(fresh, ss.build_session(store))
    assert a.bundle_id in fresh.peak_service._imported_files
    again = fresh.peak_service.import_instrument_peaks(
        a.bundle_id, [{'peak_number': 1, 'peak_name': 'X', 'retention_time': 3.0, 'area': 1.0, 'height': 1.0}])
    assert len(again) == count == len(fresh.peak_service.get_peaks(a.bundle_id))


def test_restore_replaces_instead_of_merging_and_keeps_service_objects():
    store, a, b = synthetic_store()
    data = ss.build_session(store)
    target = DataStore()
    (old,) = load_files(target, [('other.csv', chromatogram_csv([5.0]))])
    target.peak_service.detect_peaks(old.bundle_id, old.dataframe.iloc[:, 1].to_numpy(float),
                                     old.dataframe.iloc[:, 0].to_numpy(float))
    target.visibility_state['stale'] = True
    services = (target.peak_service, target.calibration_service, target.integration_service,
                target.lcms_service, target.file_removal_service)
    report = ss.restore_session(target, data)
    assert report.ok
    assert set(target.all_bundles()) == {a.bundle_id, b.bundle_id}
    assert old.bundle_id not in target.peak_service._peaks
    assert 'stale' not in target.visibility_state
    assert services == (target.peak_service, target.calibration_service, target.integration_service,
                        target.lcms_service, target.file_removal_service)
    assert not target.file_removal_service.can_undo


def test_unchanged_tables_are_not_stored_but_edited_ones_are_and_survive():
    store, a, b = synthetic_store()
    plain = ss.build_session(store)
    assert ss.inspect_session(plain).counts['edited_tables'] == 0
    assert not [n for n in zipfile.ZipFile(io.BytesIO(plain)).namelist() if n.startswith('edited/')]

    component = a.primary
    edited = component.dataframe.copy()
    edited.loc[10, 'Signal (mAU)'] = 999.25
    component.dataframe = edited
    data = ss.build_session(store)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert f'edited/{component.component_id}.csv' in names
    assert ss.inspect_session(data).counts['edited_tables'] == 1

    fresh = DataStore()
    report = ss.restore_session(fresh, data)
    assert report.ok and report.warnings == []
    restored = fresh.get_bundle(a.bundle_id).primary
    assert restored.dataframe.loc[10, 'Signal (mAU)'] == 999.25
    pd.testing.assert_frame_equal(restored.dataframe, edited)
    assert restored.standardized.data is restored.dataframe
    # Provenance: the unmodified parsed import is still the original, so an edit is still detected.
    assert restored.imported_csv == component.imported_csv
    again = ss.build_session(fresh)
    assert ss.inspect_session(again).counts['edited_tables'] == 1


def test_bundle_without_raw_bytes_is_stored_as_table_and_round_trips():
    store = DataStore()
    frame = pd.DataFrame({'m/z': [100.0, 101.0, 102.0], 'Intensity': [1.0, 5.0, 2.0]})
    roles = {'m/z': ColumnRole.X, 'Intensity': ColumnRole.Y}
    meta = {'auto_x': 'm/z', 'auto_y': ['Intensity'], 'sample_name': 'extract',
            'big': np.arange(100000.0)}
    sr = StandardizedResult(frame, roles, FileIdentity('extract.csv', 'csv', 'ms_extract', 0),
                            plot_hint=PlotHint.LINE, source_category=SourceCategory.SPECTRUM,
                            sample_name='extract', metadata=meta)
    component = Component('comp-1', ComponentRole.PRIMARY, 'extract.csv', raw_bytes=frame.to_csv(index=False).encode(),
                          dataframe=frame, column_roles=roles, metadata=meta, source_category=SourceCategory.SPECTRUM,
                          plot_hint=PlotHint.LINE, standardized=sr)
    store.add_bundle(Bundle('bundle-1', 'extract', BundleType.GENERIC, component_list=[component]))
    store.peak_service.add_baseline_peak('bundle-1', 1.0, 5.0, 101.0, [100.0, 101.0, 102.0], [0, 5, 0],
                                         [(100.0, 0.0), (102.0, 0.0)], (100.0, 0.0), (102.0, 0.0))
    data = ss.build_session(store)
    assert ss.inspect_session(data).notes            # the array metadata was reported as not saved
    fresh = DataStore()
    report = ss.restore_session(fresh, data)
    assert report.ok
    restored = fresh.get_bundle('bundle-1').primary
    assert restored.component_id == 'comp-1'
    pd.testing.assert_frame_equal(restored.dataframe, frame)
    assert restored.column_roles == roles and restored.source_category == SourceCategory.SPECTRUM
    assert restored.standardized.identity.detected_format == 'ms_extract'
    assert 'big' not in restored.metadata and restored.metadata['sample_name'] == 'extract'
    assert fresh.peak_service.get_peaks('bundle-1')[0].area == 1.0


def test_engine_has_no_gui_dependency():
    assert not any(name.startswith('dash') for name in ss.__dict__)


# ---------------------------------------------------------------------------
# Rekey helper keeps everything attached
# ---------------------------------------------------------------------------

def test_rekey_bundle_updates_indexes_state_and_peaks():
    store, a, b = synthetic_store()
    comp_id = a.primary.component_id
    before = [dict(vars(p), file_id='new-bundle') for p in store.peak_service.get_peaks(a.bundle_id)]
    store.file_ui_state[f'{a.bundle_id}|A1'] = {'file_id': a.bundle_id}
    old_id = a.bundle_id
    store.rekey_bundle(old_id, 'new-bundle', {comp_id: 'new-comp'})
    assert store.get_bundle('new-bundle') is a and store.get_bundle(old_id) is None
    assert a.bundle_id == 'new-bundle' and a.primary.component_id == 'new-comp'
    assert store.get_bundle_for_component('new-comp') is a
    assert store.get_bundle_for_file(A_NAME) is a
    assert 'new-comp' in store.loaded_data or 'new-bundle' in store.loaded_data
    assert [dict(vars(p)) for p in store.peak_service.get_peaks('new-bundle')] == before
    assert 'new-bundle|A1' in store.file_ui_state
    assert store.group_overrides == {b.bundle_id: ('custom_xyz', 'X')}   # unrelated state untouched
    assert list(store.all_bundles()) == ['new-bundle', b.bundle_id]       # order kept
    with pytest.raises(ValueError):
        store.rekey_bundle('new-bundle', b.bundle_id)
    with pytest.raises(KeyError):
        store.rekey_bundle('nope', 'x')


def test_remap_ids_rewrites_keys_values_substrings_and_keeps_types():
    uid = '3f2b9c1e-1111-4222-8333-444455556666'
    other = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    mapping = {uid: 'NEW-ID-0001', 'short': 'S2', 'same': 'same'}
    obj = {uid: [uid, ('x', uid), {'k': f'tab-lcms_ms_time_{uid}'}], 'id|well': f'id:{uid}:name',
           'short': 'short', 'keep': 'shorter', 'n': 3, 'u': other, 'same': 'same'}
    result = ss.remap_ids(obj, mapping)
    assert result['NEW-ID-0001'][0] == 'NEW-ID-0001'
    assert result['NEW-ID-0001'][1] == ('x', 'NEW-ID-0001')
    assert result['NEW-ID-0001'][2] == {'k': 'tab-lcms_ms_time_NEW-ID-0001'}
    assert result['id|well'] == 'id:NEW-ID-0001:name'
    assert result['S2'] == 'S2' and result['keep'] == 'shorter'      # short ids: whole strings only
    assert result['u'] == other and result['n'] == 3 and result['same'] == 'same'
    assert uid in obj                                                  # input untouched
    assert ss.remap_ids(obj, {}) == obj and ss.remap_ids(obj, {uid: uid}) == obj


def test_client_state_is_remapped_when_an_id_could_not_be_kept(monkeypatch):
    store, a, b = synthetic_store(extra_state=False)
    client = {'active-file': a.bundle_id, 'zoom': {a.bundle_id: [0, 5]}}
    data = ss.build_session(store, client)
    fresh = DataStore()
    # An id clash makes the rekey fail; the engine must keep working and remap state.
    original = DataStore.rekey_bundle

    def refuse(self, bundle_id, new_bundle_id=None, component_ids=None):
        if new_bundle_id == a.bundle_id:
            raise ValueError('clash')
        return original(self, bundle_id, new_bundle_id, component_ids)

    monkeypatch.setattr(DataStore, 'rekey_bundle', refuse)
    report = ss.restore_session(fresh, data)
    new_id = report.id_map[a.bundle_id]
    assert new_id != a.bundle_id and fresh.get_bundle(new_id) is not None
    assert report.client_state == {'active-file': new_id, 'zoom': {new_id: [0, 5]}}
    assert any('kept new internal ids' in w for w in report.warnings)
    assert new_id in fresh.peak_service._peaks and a.bundle_id not in fresh.peak_service._peaks


# ---------------------------------------------------------------------------
# Raw files: hash check, large-file policy, relocation
# ---------------------------------------------------------------------------

def test_hash_mismatch_of_embedded_file_warns_but_restores():
    store, a, b = synthetic_store(extra_state=False)
    data = ss.build_session(store)
    tampered = rewrite_zip(data, lambda n, c: c + b'\n0,0\n' if n.startswith('raw/') and n.endswith(A_NAME) else c)
    report = ss.restore_session(DataStore(), tampered)
    assert any(A_NAME in w and 'checksum' in w for w in report.warnings)
    assert report.restored['bundles'] == 2


def test_external_files_missing_then_found_by_relocate_or_search_dir(tmp_path):
    store, a, b = synthetic_store()
    folder = tmp_path / 'raw'
    folder.mkdir()
    for name, size in [(A_NAME, 1.0), (B_NAME, 0.7)]:
        (folder / name).write_bytes(chromatogram_csv([3.0, 6.0]) if name == A_NAME else chromatogram_csv([3.05, 6.1], amplitude=70.0))
    path = ss.save_session(store, tmp_path / 'proj', {'active-file': b.bundle_id}, embed_raw=False,
                           source_paths={A_NAME: folder / A_NAME, B_NAME: folder / B_NAME})
    assert path.suffix == '.gecko'
    info = ss.inspect_session(path)
    assert info.raw_embedded is False and all(f['original_path'] for f in info.files)
    assert not [n for n in zipfile.ZipFile(path).namelist() if n.startswith('raw/')]

    # Everything is where it was stored: nothing missing.
    ok = ss.restore_session(DataStore(), path)
    assert ok.ok and ok.restored['bundles'] == 2

    # The folder moves: without help the samples are reported, not crashed on, and their state is dropped.
    moved = tmp_path / 'moved'
    folder.rename(moved)
    fresh = DataStore()
    # (the session lives in tmp_path; 'moved' is one level below, but we do not pass it)
    report = ss.restore_session(fresh, path.read_bytes())
    assert not report.ok and len(report.missing_files) == 2
    assert {m['name'] for m in report.missing_files} == {A_NAME, B_NAME}
    assert all(m['sha256'] and m['size'] for m in report.missing_files)
    assert report.missing_files[0]['bundles'] and report.restored['bundles'] == 0
    assert set(report.missing_ids) >= {a.bundle_id, b.bundle_id}
    assert fresh.all_bundles() == {} and fresh.peak_service._peaks == {}
    assert fresh.calibration_service.get_all_models()            # global state still restored
    assert report.client_state == {'active-file': b.bundle_id}

    calls = []

    def relocate(entry):
        calls.append(entry['name'])
        return moved / entry['name']

    relocated = DataStore()
    report = ss.restore_session(relocated, path.read_bytes(), relocate=relocate)
    assert report.ok and sorted(calls) == [A_NAME, B_NAME]
    assert peaks_of(relocated) == peaks_of(store)

    # search_dirs: one level of sub-folders is looked at; the session file's own folder too.
    searched = DataStore()
    report = ss.restore_session(searched, path.read_bytes(), search_dirs=[tmp_path])
    assert report.ok and set(searched.all_bundles()) == {a.bundle_id, b.bundle_id}

    # Only one file can be found: the other sample is reported, the rest restored.
    (moved / B_NAME).unlink()
    partial = DataStore()
    report = ss.restore_session(partial, path.read_bytes(), search_dirs=[moved])
    assert not report.ok and [m['name'] for m in report.missing_files] == [B_NAME]
    assert set(partial.all_bundles()) == {a.bundle_id}
    assert set(partial.peak_service._peaks) == {a.bundle_id}
    assert b.bundle_id not in partial.visibility_state


def test_changed_external_file_is_used_with_a_warning(tmp_path):
    store, a, b = synthetic_store(extra_state=False)
    folder = tmp_path / 'raw'
    folder.mkdir()
    (folder / A_NAME).write_bytes(chromatogram_csv([3.0, 6.0]) + b'0,0\n')
    (folder / B_NAME).write_bytes(chromatogram_csv([3.05, 6.1], amplitude=70.0))
    data = ss.build_session(store, embed_raw=False, source_paths={A_NAME: folder / A_NAME, B_NAME: folder / B_NAME})
    report = ss.restore_session(DataStore(), data)
    assert report.restored['bundles'] == 2
    assert any(A_NAME in w and 'checksum' in w for w in report.warnings)


def test_raw_limit_switches_to_references_only():
    store, *_ = synthetic_store(extra_state=False)
    big = ss.build_session(store, raw_limit_bytes=10)
    info = ss.inspect_session(big)
    assert info.raw_embedded is False and info.notes
    assert all(not f['embedded'] and f['sha256'] and f['size'] for f in info.files)
    assert len(big) < len(ss.build_session(store))


def test_identical_originals_are_stored_once():
    store = DataStore()
    data = chromatogram_csv([3.0])
    load_files(store, [('one.csv', data)])
    load_files(store, [('one.csv', data)])         # same name and bytes loaded twice
    blob = ss.build_session(store)
    raw = [n for n in zipfile.ZipFile(io.BytesIO(blob)).namelist() if n.startswith('raw/')]
    assert len(raw) == 1


# ---------------------------------------------------------------------------
# Schema versions and migrations
# ---------------------------------------------------------------------------

def test_newer_schema_gives_a_clear_error_and_leaves_the_workspace_alone():
    store, a, _ = synthetic_store(extra_state=False)
    newer = edit_json(ss.build_session(store), 'manifest.json', lambda m: m.update(schema_version=ss.SCHEMA_VERSION + 4))
    target = DataStore()
    (kept,) = load_files(target, [('keep.csv', chromatogram_csv([2.0]))])
    with pytest.raises(ss.SessionVersionError) as error:
        ss.restore_session(target, newer)
    text = str(error.value)
    assert 'newer version' in text and str(ss.SCHEMA_VERSION + 4) in text and 'update' in text.lower()
    assert isinstance(error.value, ValueError)
    assert list(target.all_bundles()) == [kept.bundle_id]
    info = ss.inspect_session(newer)
    assert info.compatible is False and 'newer version' in info.problem


def test_not_a_session_file(tmp_path):
    with pytest.raises(ss.SessionFormatError, match='not a GeckoPlotter session'):
        ss.restore_session(DataStore(), b'definitely not a zip')
    plain = io.BytesIO()
    with zipfile.ZipFile(plain, 'w') as archive:
        archive.writestr('hello.txt', 'hi')
    with pytest.raises(ss.SessionFormatError):
        ss.inspect_session(plain.getvalue())
    with pytest.raises(ss.SessionFormatError, match='not found'):
        ss.inspect_session(tmp_path / 'missing.gecko')


def test_migration_chain_runs_in_order_and_stamps_versions():
    order = []

    def step(n):
        def run(session):
            order.append(n)
            session['state'][f'step{n}'] = True
            return session
        return run

    session = {'manifest': {'schema_version': 0}, 'state': {}, 'client_state': {}}
    done = ss.migrate_session(session, target=3, migrations={0: step(0), 1: step(1), 2: step(2)})
    assert order == [0, 1, 2]
    assert done['manifest']['schema_version'] == 3 and done['state']['schema_version'] == 3
    assert all(done['state'][f'step{n}'] for n in range(3))
    with pytest.raises(ss.SessionFormatError, match='old format'):
        ss.migrate_session({'manifest': {'schema_version': 0}, 'state': {}, 'client_state': {}},
                           target=2, migrations={0: step(0)})
    with pytest.raises(ss.SessionVersionError):
        ss.migrate_session({'manifest': {'schema_version': 5}, 'state': {}, 'client_state': {}}, target=2)


def test_synthetic_v0_session_is_migrated_to_v1_on_restore(monkeypatch):
    store, a, b = synthetic_store(extra_state=False)
    current = ss.build_session(store, {'active-file': a.bundle_id})

    # A pretend "v0" layout: 'samples' instead of 'bundles', and no analysis history key.
    def to_v0(state):
        state['samples'] = state.pop('bundles')
        state.pop('analysis_history')
        state['schema_version'] = 0

    old = edit_json(edit_json(current, 'state.json', to_v0), 'manifest.json', lambda m: m.update(schema_version=0))

    def v0_to_v1(session):
        state = session['state']
        state['bundles'] = state.pop('samples')
        state['analysis_history'] = []
        return session

    with pytest.raises(ss.SessionFormatError):                      # no migration registered yet
        ss.restore_session(DataStore(), old)
    monkeypatch.setitem(ss.MIGRATIONS, 0, v0_to_v1)
    fresh = DataStore()
    report = ss.restore_session(fresh, old)
    assert report.ok and report.info.schema_version == 1
    assert set(fresh.all_bundles()) == {a.bundle_id, b.bundle_id}
    assert peaks_of(fresh) == peaks_of(store)
    assert ss.inspect_session(old).schema_version == 1


# ---------------------------------------------------------------------------
# Files, inspect, autosave
# ---------------------------------------------------------------------------

def test_save_session_is_atomic_and_adds_the_extension(tmp_path, monkeypatch):
    store, *_ = synthetic_store(extra_state=False)
    target = tmp_path / 'deep' / 'folder' / 'My project'
    path = ss.save_session(store, target)
    assert path == target.with_suffix('.gecko') or path.name == 'My project.gecko'
    assert path.exists() and [p.name for p in path.parent.iterdir()] == [path.name]
    first = path.read_bytes()
    assert ss.inspect_session(path).project_name == 'My project'
    assert store.session_meta['path'] == str(path)

    def boom(fileobj, parts):
        fileobj.write(b'partial')
        raise RuntimeError('disk full')

    monkeypatch.setattr(ss, '_write_archive', boom)
    with pytest.raises(RuntimeError):
        ss.save_session(store, path)
    assert path.read_bytes() == first                                  # old file intact
    assert [p.name for p in path.parent.iterdir()] == [path.name]      # no temp debris
    with pytest.raises(TypeError):
        ss.save_session(store, path, bogus=1)


def test_inspect_reads_only_the_manifest(tmp_path):
    store, a, b = synthetic_store()
    path = ss.save_session(store, tmp_path / 'p.gecko', {'k': 1}, project_name='Preview me')
    garbled = rewrite_zip(path.read_bytes(), lambda n, c: b'{ not json' if n == 'state.json' else c)
    info = ss.inspect_session(garbled)       # state.json is unreadable but never touched
    assert info.project_name == 'Preview me' and info.compatible and info.raw_embedded
    assert info.samples == ['Ala 5 mM (renamed)', 'sampleB']
    assert info.counts['bundles'] == 2 and info.counts['peaks'] == sum(len(p) for p in store.peak_service._peaks.values())
    assert info.counts['calibrations'] == 1 and info.has_client_state
    assert {f['name'] for f in info.files} == {A_NAME, B_NAME}
    assert info.saved_at and info.created_at and info.schema_version == ss.SCHEMA_VERSION
    assert ss.inspect_session(path).size_bytes == path.stat().st_size


def test_saving_again_keeps_created_at_and_project_name(tmp_path):
    store, *_ = synthetic_store(extra_state=False)
    first = ss.save_session(store, tmp_path / 'one.gecko', project_name='Keep me')
    created = ss.inspect_session(first).created_at
    fresh = DataStore()
    ss.restore_session(fresh, first)
    second = ss.save_session(fresh, tmp_path / 'two.gecko')
    info = ss.inspect_session(second)
    assert info.project_name == 'Keep me' and info.created_at == created


def test_autosave_dir_latest_and_rotation(tmp_path, monkeypatch):
    target = tmp_path / 'auto'
    monkeypatch.setenv('GECKO_AUTOSAVE_DIR', str(target))
    assert ss.autosave_dir(create=False) == target and not target.exists()
    assert ss.latest_autosave() is None and not target.exists()       # looking never creates
    assert ss.autosave_dir() == target and target.is_dir()
    store, *_ = synthetic_store(extra_state=False)
    written = []
    for i in range(4):
        path = ss.save_autosave(store, {'n': i}, keep=2)
        os.utime(path, (1_000_000 + i, 1_000_000 + i))
        written.append(path)
    left = sorted(target.glob('*.gecko'))
    assert len(left) == 2 and ss.latest_autosave() == written[-1]
    assert 'path' not in store.session_meta                            # autosave is not the project file
    monkeypatch.delenv('GECKO_AUTOSAVE_DIR')
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    assert ss.autosave_dir(create=False) == Path(os.path.expanduser('~')) / 'Documents' / 'GeckoPlotter' / 'Autosave'


def test_no_temp_files_are_left_behind_by_restore(tmp_path, monkeypatch):
    store, *_ = synthetic_store(extra_state=False)
    data = ss.build_session(store)
    monkeypatch.setattr('tempfile.tempdir', str(tmp_path))
    ss.restore_session(DataStore(), data)
    assert list(tmp_path.iterdir()) == []
