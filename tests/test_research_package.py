import hashlib
import io
import json
import zipfile
import pandas as pd
import pytest
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from services.research_package import build_research_package, record_analysis_state


def workspace():
    store=DataStore()
    c=Component('signal',ComponentRole.PRIMARY,'original.csv',raw_bytes=b'x,y\n0,1\n1,3\n2,1\n',
                dataframe=pd.DataFrame({'x':[0.,1.,2.], 'y':[1.,3.,1.]}),
                metadata={'acquisition_time':'2025-05-07T15:56:00','wavelength':280})
    store.add_bundle(Bundle('sample','Sample',BundleType.GENERIC,component_list=[c]))
    return store,c


def test_package_preserves_import_and_links_every_file():
    store,c=workspace()
    c.dataframe.loc[1,'y']=9
    record_analysis_state(store, {'smooth_window': 9}, ['data-table.data'])
    payload=build_research_package(store, {'title':'Dataset for study'}, None, [])
    z=zipfile.ZipFile(io.BytesIO(payload))
    meta=json.loads(z.read('metadata/dataset.json'))
    sample=meta['signals'][0]
    raw=pd.read_csv(io.BytesIO(z.read(sample['raw_csv'])))
    edited=pd.read_csv(io.BytesIO(z.read(sample['processed_csv'])))
    assert raw.y.tolist()==[1,3,1]
    assert edited.y.tolist()==[1,9,1]
    assert sample['metadata']['acquisition_time']=='2025-05-07T15:56:00'
    assert meta['exported_at'] != sample['metadata']['acquisition_time']
    assert meta['processing']['smoothing']['parameters']['requested_window_points']==9
    manifest=pd.read_csv(io.BytesIO(z.read('dataset_manifest.csv')))
    for row in manifest.to_dict('records'):
        assert hashlib.sha256(z.read(row['path'])).hexdigest()==row['sha256']
    assert 'record DOI' in z.read('README.md').decode()
    assert 'report.html' in z.namelist()
    assert json.loads(z.read('analysis/history.json'))[-1]['changes']


def test_processing_history_keeps_previous_settings_and_utc_times():
    store,_=workspace()
    record_analysis_state(store, {'smooth_window': 9}, ['pt-smooth-window.value'])
    record_analysis_state(store, {'smooth_window': 51}, ['pt-smooth-window.value'])
    record_analysis_state(store, {'smooth_window': 51}, ['render-trigger.data'])
    assert store.analysis_history[-1]['changes']['plot_settings']['after']['smooth_window']==51
    assert store.analysis_history[-1]['changes']['plot_settings']['before']['smooth_window']==9
    assert all(event['at'].endswith('+00:00') for event in store.analysis_history)


def test_compact_package_reuses_unchanged_csv_and_keeps_full_provenance():
    store, _ = workspace()
    z = zipfile.ZipFile(io.BytesIO(build_research_package(store, {}, formats=[])))
    meta = json.loads(z.read('metadata/dataset.json'))
    signal = meta['signals'][0]
    assert signal['processed_csv'] == signal['raw_csv']
    assert not any(p.startswith(('processed_data/', 'metadata/signals/', 'analysis/software/')) for p in z.namelist())
    assert {'analysis/history.json', 'analysis/peaks.json', 'dataset_manifest.csv', 'report.html'} <= set(z.namelist())
    full = zipfile.ZipFile(io.BytesIO(build_research_package(store, {}, formats=[], include_code=True)))
    assert 'analysis/software/services/peak_service.py' in full.namelist()


def test_immutable_pda_digest_is_reused_without_rehashing_acquisition(monkeypatch):
    import numpy as np
    from services import research_package
    arrays = {key: np.array(value, dtype=float) for key, value in {
        'time_min': [0, 1], 'wavelength_nm': [200, 220], 'absorbance_mau': [[1, 2], [3, 4]]}.items()}
    for array in arrays.values():
        array.setflags(write=False)
    pda = {**arrays, 'data_sha256': 'verified-at-import', 'source_section': 'PDA 3D'}
    def forbidden(*args, **kwargs):
        raise AssertionError('Unchanged immutable PDA was rehashed')
    monkeypatch.setattr(research_package.hashlib, 'sha256', forbidden)
    captured = research_package._history_metadata({'pda': pda})['pda']
    assert captured['data_sha256'] == 'verified-at-import'
    assert captured['shape'] == [2, 2]
    assert 'absorbance_mau' not in captured


def test_mutable_pda_payload_still_records_value_changes():
    from services.research_package import _history_metadata
    pda = {'time_min': [0, 1], 'wavelength_nm': [200, 220],
           'absorbance_mau': [[1., 2.], [3., 4.]], 'data_sha256': 'stale'}
    old = _history_metadata({'pda': pda})['pda']['data_sha256']
    pda['absorbance_mau'][0][0] = 9.
    new = _history_metadata({'pda': pda})['pda']['data_sha256']
    assert old != new and 'stale' not in (old, new)


# ---------------------------------------------------------------------------
# A FAIR package is also a reopenable project (session/project.gecko)
# ---------------------------------------------------------------------------

def _package_of_synthetic_workspace(**kwargs):
    from test_session_service import synthetic_store
    store, a, b = synthetic_store()
    record_analysis_state(store, {'smooth_window': 9}, ['pt-smooth-window.value'])
    return store, build_research_package(store, {'title': 'Ala study'}, None, [], **kwargs)


def _peaks(store):
    return {fid: [dict(vars(p)) for p in plist] for fid, plist in store.peak_service._peaks.items()}


def test_package_contains_a_reopenable_project_listed_everywhere():
    store, payload = _package_of_synthetic_workspace()
    z = zipfile.ZipFile(io.BytesIO(payload))
    assert 'session/project.gecko' in z.namelist()
    manifest = pd.read_csv(io.BytesIO(z.read('dataset_manifest.csv')))
    row = manifest[manifest.path == 'session/project.gecko'].iloc[0]
    assert hashlib.sha256(z.read('session/project.gecko')).hexdigest() == row.sha256
    assert 'reopenable' in row.source or 'reopenable' in row['kind']
    assert 'session/project.gecko' in z.read('README.md').decode()
    assert 'session/project.gecko' in z.read('report.html').decode()
    meta = json.loads(z.read('metadata/dataset.json'))
    assert meta['project_file'] == 'session/project.gecko' and meta['project_file_note'] is None
    # State only: the instrument files are not stored a second time inside the project.
    inner = zipfile.ZipFile(io.BytesIO(z.read('session/project.gecko')))
    assert not any(n.startswith('raw/') for n in inner.namelist())


def test_opening_a_package_restores_peaks_and_files():
    from services import session_service as ss
    store, payload = _package_of_synthetic_workspace()
    info = ss.inspect_session(payload)
    assert info.from_package and info.project_name == 'Ala study' and len(info.samples) == 2
    fresh = DataStore()
    report = ss.restore_session(fresh, payload)
    assert report.ok, (report.errors, report.missing_files)
    assert report.missing_files == [] and report.restored['bundles'] == 2
    assert _peaks(fresh) == _peaks(store) and _peaks(fresh)
    assert list(fresh.all_bundles()) == list(store.all_bundles())
    for bundle in store.iter_bundles():
        again = fresh.get_bundle(bundle.bundle_id)
        pd.testing.assert_frame_equal(again.dataframe, bundle.dataframe)
        assert [c.raw_bytes for c in again.component_list] == [c.raw_bytes for c in bundle.component_list]
    assert 'path' not in fresh.session_meta       # a deposit is not "the project file" that Save would overwrite
    assert fresh.calibration_service.serialize() == store.calibration_service.serialize()


def test_package_opens_from_a_path_and_from_an_unzipped_folder(tmp_path):
    from services import session_service as ss
    store, payload = _package_of_synthetic_workspace()
    zip_path = tmp_path / 'deposit.zip'
    zip_path.write_bytes(payload)
    first = DataStore()
    assert ss.restore_session(first, zip_path).missing_files == []
    assert _peaks(first) == _peaks(store)
    folder = tmp_path / 'unzipped'
    zipfile.ZipFile(zip_path).extractall(folder)
    second = DataStore()
    report = ss.restore_session(second, folder / 'session' / 'project.gecko')   # originals found at ../raw_data/originals
    assert report.missing_files == [], report.missing_files
    assert _peaks(second) == _peaks(store)


def test_export_never_fails_when_the_project_cannot_be_built(monkeypatch):
    from services import session_service as ss
    def boom(*a, **k):
        raise RuntimeError('disk on fire')
    monkeypatch.setattr(ss, 'build_session', boom)
    store, c = workspace()
    payload = build_research_package(store, {'title': 'T'}, None, [])
    z = zipfile.ZipFile(io.BytesIO(payload))
    assert 'session/project.gecko' not in z.namelist()
    meta = json.loads(z.read('metadata/dataset.json'))
    assert meta['project_file'] is None and 'disk on fire' in meta['project_file_note']
    assert 'disk on fire' in z.read('report.html').decode()
    assert 'no reopenable project' in z.read('README.md').decode()
    with pytest.raises(ss.SessionFormatError, match='does not contain a GeckoPlotter project'):
        ss.restore_session(DataStore(), payload)


def test_oversized_project_is_left_out_with_a_note(monkeypatch):
    from services import research_package
    monkeypatch.setattr(research_package, 'SESSION_MAX_BYTES', 10)
    store, c = workspace()
    z = zipfile.ZipFile(io.BytesIO(build_research_package(store, {}, None, [])))
    assert 'session/project.gecko' not in z.namelist()
    assert 'left out' in json.loads(z.read('metadata/dataset.json'))['project_file_note']


def test_zip_with_unsafe_member_names_is_refused():
    from services import session_service as ss
    store, payload = _package_of_synthetic_workspace()
    for bad in ('/etc/evil', '../evil', 'a/../../evil'):
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(payload)) as src, zipfile.ZipFile(out, 'w') as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info.filename))
            dst.writestr(bad, b'x')
        with pytest.raises(ss.SessionFormatError, match='outside the package'):
            ss.restore_session(DataStore(), out.getvalue())


def test_ordinary_zip_is_not_a_project():
    import base64
    from services import session_files as sf
    from services import session_service as ss
    plain_zip = io.BytesIO()
    with zipfile.ZipFile(plain_zip, 'w') as z:
        z.writestr('notes.txt', 'hello')
    url = lambda data: 'data:application/zip;base64,' + base64.b64encode(data).decode()
    _, payload = _package_of_synthetic_workspace()
    assert sf.is_project_upload(url(payload), 'Ala study.zip')
    assert not sf.is_project_upload(url(plain_zip.getvalue()), 'notes.zip')
    assert sf.is_project_upload('data:,', 'x.gecko') and not sf.is_project_upload(url(payload), 'x.csv')
    with pytest.raises(ss.SessionFormatError):
        ss.restore_session(DataStore(), plain_zip.getvalue())


def test_instrument_method_and_its_original_file_are_in_the_package_and_survive_reopening():
    from services import session_service, shimadzu_method
    store, c = workspace()
    c.metadata['method_file'] = 'run.lcm'
    method = {'file_name': 'run.lcm', 'sha256': hashlib.sha256(b'LCM-BYTES').hexdigest(),
              'pump_program': [{'time_min': 1.0, 'b_percent': 5.0, 'flow_ml_min': 0.9}]}
    assert shimadzu_method.register_method(store, method, b'LCM-BYTES') == 1

    z = zipfile.ZipFile(io.BytesIO(build_research_package(store, {'title': 'Dataset for study'}, None, [])))
    methods = json.loads(z.read('analysis/instrument_methods.json'))
    assert methods[0]['pump_program'] == method['pump_program']
    assert methods[0]['attached_to_samples'] == ['Sample (signal)'] or methods[0]['attached_to_samples']
    assert z.read(methods[0]['original_file']) == b'LCM-BYTES'
    assert 'General procedure for HPLC' in z.read('README.md').decode()
    assert 'was applied at a flow rate' not in z.read('README.md').decode()   # one-point program: no gradient sentence
    assert json.loads(z.read('metadata/dataset.json'))['methods_text'][0]['text']
    manifest = pd.read_csv(io.BytesIO(z.read('dataset_manifest.csv')))
    assert methods[0]['original_file'] in set(manifest.path)
    assert 'method_details' not in json.dumps(json.loads(z.read('metadata/dataset.json'))['signals'])

    # The project saved on its own brings the original method file back too.
    restored = DataStore()
    session_service.restore_session(restored, session_service.build_session(store))
    assert list(restored.instrument_method_files.values()) == [b'LCM-BYTES']
