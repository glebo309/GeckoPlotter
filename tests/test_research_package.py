import hashlib
import io
import json
import zipfile
import pandas as pd
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
