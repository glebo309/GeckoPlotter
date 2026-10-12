"""Session round trips with real instrument files (skipped when the files are not on this machine)."""
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from callbacks.viz_callbacks import _collect_visible_files
from services import pda_service
from services import session_service as ss
from services.data_store import BundleType, DataStore
from services.plot_manager import PlotManager
from session_helpers import load_files

ALA_DIR = Path('/Users/glenn/Desktop/ala-calibration')
LCMS_DIR = Path('/Users/glenn/Desktop/untitled folder 2/DATA')
LCMS_RUN = 'LCMS-2025-05-06 14-07-48+02-00-03'


@pytest.fixture(autouse=True)
def ingestion_import(monkeypatch):
    # PlotManager imports `ingestion.types`; tests/ingestion would shadow it (same trick as test_overlay_axes).
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)


def ala_files():
    return sorted(ALA_DIR.glob('*.txt'))[:2] if ALA_DIR.is_dir() else []


def lcms_files():
    if not LCMS_DIR.is_dir():
        return []
    wanted = ('_MS1 +TIC SCAN ESI Frag=135V Gain=1-0.cdf', '_MS1 +TIC SCAN ESI Frag=135V Gain=1-0_spectra.cdf', '_VWD1A.cdf')
    paths = [LCMS_DIR / (LCMS_RUN + suffix) for suffix in wanted]
    return paths if all(p.is_file() for p in paths) else []


def figure_signature(store, ids):
    """Main plot traces, built through the function the app uses, as comparable arrays."""
    signature = []
    for file_id in ids:
        groups = _collect_visible_files(store, active_file_id=file_id)
        figure = PlotManager().create_multi_file_plot(groups, 'overlay')
        signature.append([(t.name, np.asarray(t.x, dtype=float), np.asarray(t.y, dtype=float)) for t in figure.data])
    return signature


def assert_same_figures(before, after):
    assert len(before) == len(after)
    for traces_a, traces_b in zip(before, after):
        assert [t[0] for t in traces_a] == [t[0] for t in traces_b]
        assert traces_a, 'the comparison must cover at least one drawn trace'
        for (_, xa, ya), (_, xb, yb) in zip(traces_a, traces_b):
            np.testing.assert_array_equal(xa, xb)
            np.testing.assert_array_equal(ya, yb)


def peaks_of(store):
    return {fid: [dict(vars(p)) for p in plist] for fid, plist in store.peak_service._peaks.items()}


def section(blob, name, key):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return json.loads(archive.read(name))[key]


@pytest.mark.skipif(len(ala_files()) < 2, reason=f'Shimadzu PDA exports not found in {ALA_DIR}')
def test_shimadzu_pda_round_trip_is_numerically_identical(tmp_path):
    paths = ala_files()
    store = DataStore()
    first, second = load_files(store, [(p.name, p.read_bytes()) for p in paths])
    assert first.bundle_type == second.bundle_type == BundleType.CHROMATOGRAM

    # The user removed the first channel of the second sample: its raw bytes and PDA
    # matrix move to the surviving channel. That state must survive the round trip.
    store.file_removal_service.remove_channels([second.bundle_id], 'uv:263')
    assert len(second.component_list) == 1 and second.component_list[0].raw_bytes
    assert second.component_list[0].metadata.get('pda')

    added = pda_service.add_pda_series(store, first.component_list[0].component_id, 220.0)
    assert set(added) == {first.bundle_id, second.bundle_id}
    ids = [first.component_list[0].component_id, added[first.bundle_id], added[second.bundle_id]]

    peaks = store.peak_service
    for file_id in ids:
        entry = store.get_data_by_id(file_id)['data']
        t, y = entry.iloc[:, 0].to_numpy(float), entry.iloc[:, 1].to_numpy(float)
        peaks.add_peak_manual(store.peak_owner_id(file_id), float(t[int(np.argmax(y))]), y, t)
    peaks.group_peaks_across_samples()
    assert sum(len(v) for v in peaks._peaks.values()) >= 3
    store.visibility_state[added[first.bundle_id]] = False
    store.rename_dataset(first.bundle_id, 'Blank (renamed)')
    client = {'active-file': ids[0], 'plot-tabs': [{'id': 'tab-x', 'file': ids[1]}]}

    before_figures = figure_signature(store, ids)
    before_pda = {c.component_id: c.metadata['pda'] for b in store.iter_bundles()
                  for c in b.component_list if c.metadata.get('pda')}
    assert len(before_pda) == 2

    path = ss.save_session(store, tmp_path / 'ala.gecko', client)
    fresh = DataStore()
    report = ss.restore_session(fresh, path)
    assert report.ok, (report.errors, report.missing_files)
    assert report.warnings == []
    assert report.client_state == client

    assert list(fresh.all_bundles()) == list(store.all_bundles())
    for bundle in store.iter_bundles():
        restored = fresh.get_bundle(bundle.bundle_id)
        assert restored.name == bundle.name
        assert [c.component_id for c in restored.component_list] == [c.component_id for c in bundle.component_list]
        for component, again in zip(bundle.component_list, restored.component_list):
            assert again.metadata.get('display_name') == component.metadata.get('display_name')
            assert again.metadata.get('pda_source_id') == component.metadata.get('pda_source_id')
            assert again.metadata.get('source_file_id') == component.metadata.get('source_file_id')
            assert again.raw_bytes == component.raw_bytes
            np.testing.assert_array_equal(again.dataframe.to_numpy(), component.dataframe.to_numpy())
    assert fresh.get_bundle(first.bundle_id).name == 'Blank (renamed)'

    # The matrices themselves: same checksum, same numbers, immutable arrays rebuilt from the original file.
    for component_id, pda in before_pda.items():
        again = next(c for b in fresh.iter_bundles() for c in b.component_list
                     if c.component_id == component_id).metadata['pda']
        assert again['data_sha256'] == pda['data_sha256']
        for key in ('time_min', 'wavelength_nm', 'absorbance_mau'):
            np.testing.assert_array_equal(again[key], pda[key])

    assert peaks_of(fresh) == peaks_of(store)               # peaks identical and attached to the same ids
    assert fresh.visibility_state == store.visibility_state
    assert_same_figures(before_figures, figure_signature(fresh, ids))

    # Saving the restored workspace again gives the same description of it.
    again = ss.build_session(fresh, client)
    original = ss.build_session(store, client)
    for key in ('bundles', 'peaks', 'visibility_state', 'calibrations', 'integration_settings'):
        assert section(again, 'state.json', key) == section(original, 'state.json', key), key


@pytest.mark.skipif(len(lcms_files()) < 3, reason=f'LC-MS CDF files not found in {LCMS_DIR}')
def test_lcms_bundle_round_trip_is_numerically_identical():
    store = DataStore()
    (bundle,) = load_files(store, [(p.name, p.read_bytes()) for p in lcms_files()])
    assert bundle.bundle_type == BundleType.LCMS and len(bundle.component_list) == 3
    uv = next(c for c in bundle.component_list if c.role.value == 'vwd_a')
    ms = next(c for c in bundle.component_list if c.metadata.get('mass_spectral_data'))
    ids = [c.component_id for c in bundle.component_list]

    table = uv.dataframe
    t, y = table.iloc[:, 0].to_numpy(float), table.iloc[:, 1].to_numpy(float)
    store.peak_service.add_peak_manual(uv.component_id, float(t[int(np.argmax(y))]), y, t)
    store.peak_service.detect_peaks(uv.component_id, y, t)
    masses = np.asarray(ms.metadata['mass_spectral_data']['mass_values'])
    mz = float(np.round(masses[len(masses) // 2], 1))
    entry = store.get_data_by_id(ms.component_id)
    eic_time, eic = store.lcms_service.extract_eic(entry, mz, 0.5)
    store.add_lcms_eic_overlay(ms.component_id, {'mz': mz, 'tolerance': 0.5, 'time': eic_time, 'intensity': eic})
    store.visibility_state[uv.component_id] = False
    store.visibility_state[ms.component_id] = True
    before_figures = figure_signature(store, ids)
    mass_before = {c.component_id: {k: np.asarray(v) for k, v in c.metadata['mass_spectral_data'].items()
                                    if isinstance(v, (list, np.ndarray))}
                   for c in bundle.component_list if c.metadata.get('mass_spectral_data')}

    blob = ss.build_session(store, {'active-file': uv.component_id})
    assert ss.inspect_session(blob).counts['files'] == 3
    fresh = DataStore()
    report = ss.restore_session(fresh, blob)
    assert report.ok, (report.errors, report.missing_files)

    restored = fresh.get_bundle(bundle.bundle_id)
    assert restored.bundle_type == BundleType.LCMS
    assert [c.component_id for c in restored.component_list] == ids
    assert {r.role for r in restored.component_list} == {r.role for r in bundle.component_list}
    assert peaks_of(fresh) == peaks_of(store) and peaks_of(fresh)
    for component in restored.component_list:
        original = next(c for c in bundle.component_list if c.component_id == component.component_id)
        np.testing.assert_array_equal(component.dataframe.to_numpy(), original.dataframe.to_numpy())
        for key, values in mass_before.get(component.component_id, {}).items():
            np.testing.assert_array_equal(np.asarray(component.metadata['mass_spectral_data'][key]), values)
    overlays = fresh.get_lcms_eic_overlays(ms.component_id)
    assert len(overlays) == 1 and overlays[0]['mz'] == mz
    np.testing.assert_array_equal(overlays[0]['intensity'], eic)
    np.testing.assert_array_equal(overlays[0]['time'], eic_time)
    assert fresh.visibility_state == store.visibility_state
    assert_same_figures(before_figures, figure_signature(fresh, ids))
    # The paired spectral export still hides its plain TIC twin, as before saving.
    assert {c.role for c in restored.components.values()} == {c.role for c in bundle.components.values()}


def chromeleon_files():
    if not LCMS_DIR.is_dir():
        return []
    paths = sorted(LCMS_DIR.glob('1 - 120_*.txt'))
    return paths if len(paths) >= 4 else []


@pytest.mark.skipif(not chromeleon_files(), reason=f'Chromeleon exports not found in {LCMS_DIR}')
def test_chromeleon_bundle_keeps_imported_peaks_without_importing_them_twice():
    from callbacks.upload_callbacks import _auto_import_peaks
    store = DataStore()
    (bundle,) = load_files(store, [(p.name, p.read_bytes()) for p in chromeleon_files()], skip_unparsable=True)
    assert bundle.bundle_type == BundleType.CHROMELEON and bundle.has_integration_data()
    _auto_import_peaks(store, bundle)
    before = peaks_of(store)
    assert before and sum(len(v) for v in before.values()) == 2

    fresh = DataStore()
    report = ss.restore_session(fresh, ss.build_session(store))
    assert report.ok and report.warnings == []
    restored = fresh.get_bundle(bundle.bundle_id)
    assert [c.role for c in restored.component_list] == [c.role for c in bundle.component_list]
    assert peaks_of(fresh) == before                                   # not doubled by a second auto-import
    assert fresh.peak_service.serialize() == store.peak_service.serialize()
    assert restored.get_integration_text() == bundle.get_integration_text()
