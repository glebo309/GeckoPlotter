"""The agent interface (src/gecko_api.py, gecko_mcp.py) on a small LC-MS sequence written here: two run folders, each
with full-scan spectra (ANDI netCDF) and a UV trace, as Agilent exports them."""
import os
import sys

import numpy as np
import pytest

netCDF4 = pytest.importorskip('netCDF4')

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))

from gecko_api import GeckoError, Workspace  # noqa: E402

TIMES = np.linspace(0.01, 14.0, 490)
ION = 633.8                       # the compound, at 8.4 min
BACKGROUND = 60.1


def _spectra(path, amount):
    """Full-scan positive spectra: the compound (with its 13C isotope) eluting at 8.4 min over a constant ion."""
    profile = amount * 6e5 * np.exp(-((TIMES - 8.4) / 0.06) ** 2)
    mz, intensity, index, counts = [], [], [], []
    for height in profile:
        index.append(len(mz))
        ions = [(BACKGROUND, 5e4), (ION, height), (ION + 1, 0.45 * height)]
        mz += [m for m, _ in ions]
        intensity += [v for _, v in ions]
        counts.append(len(ions))
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('scan_number', len(TIMES))
        ds.createDimension('point_number', len(mz))
        for name, values, kind, dim in (
                ('scan_acquisition_time', TIMES * 60, 'f8', 'scan_number'),
                ('total_intensity', [sum(intensity[i:i + n]) for i, n in zip(index, counts)], 'f8', 'scan_number'),
                ('scan_index', index, 'i4', 'scan_number'), ('point_count', counts, 'i4', 'scan_number'),
                ('mass_values', mz, 'f4', 'point_number'), ('intensity_values', intensity, 'f4', 'point_number')):
            ds.createVariable(name, kind, (dim,))[:] = np.asarray(values)
        ds.experiment_title = os.path.basename(path).split('_MS1')[0] + '.dx'


def _run(folder, stamp, amount):
    folder.mkdir()
    base = f'2026-09-10 {stamp}+02-00-07'
    _spectra(str(folder / f'{base}_MS1 +TIC SCAN ESI Frag=135V Gain=1-0_spectra.cdf'), amount)
    uv = amount * 800 * np.exp(-((TIMES - 7.3) / 0.05) ** 2)
    (folder / f'{base}.dx_VWD1A.CSV').write_text('\n'.join(f'{t:.4f},{v:.4f}' for t, v in zip(TIMES, uv)) + '\n')


@pytest.fixture(autouse=True)
def real_ingestion(monkeypatch):
    """In a full run ``tests/ingestion`` is imported as ``ingestion`` first; these tests read files with the app's."""
    def ours():
        return {k: v for k, v in sys.modules.items() if k == 'ingestion' or k.startswith('ingestion.')}
    before = ours()
    for name in before:
        del sys.modules[name]
    monkeypatch.syspath_prepend(os.path.join(ROOT, 'src'))
    yield
    for name in ours():
        del sys.modules[name]
    sys.modules.update(before)


@pytest.fixture
def sequence(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path / 'settings'))
    root = tmp_path / 'HalB'
    root.mkdir()
    _run(root / '2026-10-15 11-05-28+02-00-4', '15-53-54', 2.0)
    _run(root / '2026-10-15 11-05-28+02-00-CONTROL 4', '15-39-09', 1.0)
    return root


def test_a_folder_of_run_folders_opens_as_one_named_sample_per_run(sequence):
    ws = Workspace()
    ws.open(str(sequence))
    names = sorted(s['name'] for s in ws.samples() if s['type'] == 'lcms')
    assert names == ['4', 'CONTROL 4']
    channels = {c['name']: c for c in next(s for s in ws.samples() if s['name'] == '4')['channels']}
    assert channels['+TIC']['mass_spectra'] and channels['+TIC']['kind'] == 'ms+'
    with pytest.raises(GeckoError, match='Loaded: '):
        ws._sample('nope')


def test_eic_areas_follow_the_amount_and_the_spectrum_names_the_ion(sequence):
    ws = Workspace()
    ws.open(str(sequence))
    rows = {r['sample']: r for r in ws.eic(ION, 0.5)}
    assert rows['4']['apex_rt'] == pytest.approx(8.4, abs=0.03)
    assert rows['4']['area'] / rows['CONTROL 4']['area'] == pytest.approx(2.0, rel=0.02)
    spectrum = ws.mass_spectrum('4', rt_start=8.3, rt_end=8.5, top=3)
    assert [p['mz'] for p in spectrum['peaks']][:2] == [ION, round(ION + 1, 2)]


def test_an_integration_is_saved_in_a_project_that_reopens_with_the_peak(sequence, tmp_path):
    ws = Workspace()
    ws.open(str(sequence))
    peak = ws.integrate(8.2, 8.6, samples='4', channel='+TIC', name='m634 compound')[0]
    assert peak['name'] == 'm634 compound' and peak['area'] > 0
    assert ws.mass_spectrum('4', peak='m634 compound', top=1)['peaks'][0]['mz'] == ION
    project = ws.save(str(tmp_path / 'halb'))
    again = Workspace()
    again.open(project)
    reopened = [r for r in again.peaks() if r['name'] == 'm634 compound']
    assert len(reopened) == 1 and reopened[0]['area'] == pytest.approx(peak['area'])


def test_detected_peaks_are_the_detect_buttons_peaks(sequence):
    from services.detection import detect
    ws = Workspace()
    ws.open(str(sequence))
    rows = ws.detect_peaks(samples='4', channel='UV', sensitivity=50)
    assert [round(r['rt'], 1) for r in rows] == [7.3]
    component = ws._channel(ws._sample('4'), 'UV')
    x, y = ws._xy(component.component_id)
    again = detect(ws.store, component.component_id, x, y, 50)
    assert [p.area for p in again] == [pytest.approx(rows[0]['area'], rel=1e-5)]


def test_the_mcp_server_offers_the_tools():
    pytest.importorskip('mcp')
    sys.path.insert(0, ROOT)
    import gecko_mcp
    import asyncio
    names = {tool.name for tool in asyncio.run(gecko_mcp.server.list_tools())}
    assert {'open_data', 'list_samples', 'detect_peaks', 'integrate', 'peak_table', 'extract_ion_chromatogram',
            'mass_spectrum', 'figure', 'save_project'} <= names


def test_an_integration_window_on_the_flanks_takes_the_whole_peak(sequence):
    ws = Workspace()
    ws.open(str(sequence))
    whole = ws.integrate(7.9, 8.9, samples='CONTROL 4', channel='+TIC', snap_to_valleys=False)[0]
    flanks = ws.integrate(8.35, 8.45, samples='4', channel='+TIC')[0]
    assert flanks['rt_start'] < 8.3 and flanks['rt_end'] > 8.5
    assert flanks['area'] == pytest.approx(2 * whole['area'], rel=0.03)      # sample 4 holds twice the amount


def test_duplicate_agilent_exports_are_left_out_when_the_spectra_are_there():
    from services.workspace_loader import split_duplicate_exports
    files = [(n, b'') for n in ('run_MS1 +TIC SCAN ESI_spectra.cdf', 'run.dx_VWD1A.CSV', '4.cdf', '4_004.cdf',
                                'run.dx_MS1 +EIC(633.7-634.7) ESI.CSV', 'method.lcm')]
    kept, duplicates = split_duplicate_exports(files)
    assert [n for n, _ in kept] == ['run_MS1 +TIC SCAN ESI_spectra.cdf', 'run.dx_VWD1A.CSV', 'method.lcm']
    assert [n for n, _ in duplicates] == ['4.cdf', '4_004.cdf', 'run.dx_MS1 +EIC(633.7-634.7) ESI.CSV']
    assert split_duplicate_exports(files[1:]) == (files[1:], [])          # no spectra: everything is the data


def test_a_folder_of_runs_is_one_group_and_tab_named_after_it_with_one_run_shown(sequence):
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group, _tab_label_from_group
    ws = Workspace()
    ws.open(str(sequence))
    runs = [b for b in ws._bundles() if b.bundle_type.value == 'lcms']
    keys = set()
    for bundle in runs:
        entry = ws.store.get_data_by_id(bundle.bundle_id)
        keys.add(_get_overlay_group(entry['metadata'], entry, file_id=bundle.bundle_id, dm=ws.store))
    assert len(keys) == 1 and _tab_label_from_group(keys.pop(), ws.store) == 'HalB'
    assert sorted(ws.store.visibility_state.get(b.bundle_id, True) for b in runs) == [False, True]
