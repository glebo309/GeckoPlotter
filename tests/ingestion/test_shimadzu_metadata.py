"""Curated metadata of the synthetic LabSolutions export (no private instrument data)."""
from pathlib import Path

import numpy as np

from src.ingestion.presets.shimadzu_ascii import ShimadzuASCIIPreset

FIXTURE = Path(__file__).parent / 'fixtures' / 'shimadzu_ascii.txt'

RICH = (FIXTURE.read_text()
        .replace('[Header]\nApplication Name\tLabSolutions\nVersion\t5.141\n',
                 '[Header]\nApplication Name\tLabSolutions\nVersion\t5.141\n'
                 'Data File Name\tC:\\LabSolutions\\Data\\run_001.lcd\n')
        .replace('Sample ID\tfixture-001\n',
                 'Operator Name\tSystem Administrator\nSample Type\t1:Standard\nLevel\t3\n'
                 'Sample ID\tfixture-001\nISTD Amount1\t1\nSample Amount\t1\nDilution Factor\t2\n')
        .replace('Instrument Name\tSynthetic LC-PDA\n',
                 'Instrument Name\tSynthetic LC-PDA\nDetector Name\tPDA\n')
        .replace('Method File\tC:\\LabSolutions\\synthetic.lcm\n',
                 'Method File\tC:\\LabSolutions\\Methods\\synthetic.lcm\nBatch File\t\n'))


def _meta(tmp_path, text=RICH):
    path = tmp_path / 'sample.txt'
    path.write_text(text)
    return ShimadzuASCIIPreset().parse(str(path))['metadata']


def test_curated_fields_are_typed_named_and_free_of_windows_paths(tmp_path):
    meta = _meta(tmp_path)
    assert meta['sample_name'] == 'Synthetic PDA standard'
    assert meta['sample_id'] == 'fixture-001'
    assert meta['sample_type'] == 'Standard'
    assert meta['level'] == 3 and isinstance(meta['level'], int)
    assert meta['vial'] == 11 and isinstance(meta['vial'], int)
    assert meta['injection_volume_ul'] == .5
    assert meta['dilution_factor'] == 2.0 and meta['sample_amount'] == 1.0
    assert meta['operator'] == 'System Administrator'
    assert meta['instrument'] == 'Synthetic LC-PDA' and meta['detector'] == 'PDA'
    assert meta['software'] == 'LabSolutions' and meta['software_version'] == '5.141'
    assert meta['acquired'] == '2026-07-30T13:40:04'
    assert meta['exported'] == '2026-07-30T14:25:10'
    assert meta['data_file'] == 'synthetic.lcd'  # [Original Files] wins over the header copy
    assert meta['method_file'] == 'synthetic.lcm'
    assert 'ISTD Amount1' not in meta and not any('\\' in str(v) for v in meta.values() if isinstance(v, str))


def test_acquisition_detector_and_channel_summary(tmp_path):
    meta = _meta(tmp_path)
    assert (meta['time_start_min'], meta['time_end_min'], meta['data_points']) == (0, .06667, 3)
    assert meta['sampling_interval_ms'] == 2000
    assert (meta['wavelength_min_nm'], meta['wavelength_max_nm']) == (250, 600)
    assert meta['wavelength_points'] == 3
    np.testing.assert_allclose(meta['wavelength_resolution_nm'], np.median([1.3, 349.21]), atol=.01)
    assert meta['channels'] == [{'channel': 'Ch1', 'wavelength_nm': 250.0, 'bandwidth_nm': 4.0},
                                {'channel': 'Ch2', 'wavelength_nm': 600.0, 'bandwidth_nm': 4.0}]
    assert (meta['detector_channel'], meta['wavelength_nm'], meta['bandwidth_nm']) == ('Ch1', 250, 4)


def test_no_empty_values_and_raw_sections_hold_every_header(tmp_path):
    meta = _meta(tmp_path)
    assert 'source_sections' not in meta
    assert not [k for k, v in meta.items() if v is None or v == '']
    assert 'batch_file' not in meta  # empty in the source
    raw = meta['raw_sections']
    assert raw['Sample Information']['ISTD Amount1'] == '1'
    assert raw['Original Files']['Method File'].endswith('synthetic.lcm')
    assert raw['Header']['Data File Name'].endswith('run_001.lcd')


def test_downstream_keys_are_unchanged(tmp_path):
    meta = _meta(tmp_path)
    assert meta['pda']['data_sha256'] and len(meta['chromatogram_channels']) == 2
    assert 'Pump A Pressure' in meta['instrument_status'] and 'PDA-Ch1' in meta['instrument_peaks']


def test_acquired_date_formats_and_unparsable_text(tmp_path):
    from src.ingestion.presets.shimadzu_ascii import _iso_datetime
    assert _iso_datetime('10/12/2026 4:06:41 PM') == '2026-10-12T16:06:41'
    assert _iso_datetime('12.10.2026 16:06:41') == '2026-10-12T16:06:41'
    assert _iso_datetime('10/12/2026', '4:35:07 PM') == '2026-10-12T16:35:07'
    assert _iso_datetime('not a date') == 'not a date' and _iso_datetime('') is None


def test_minimal_export_omits_missing_fields(tmp_path):
    meta = _meta(tmp_path, FIXTURE.read_text())
    for key in ('operator', 'sample_type', 'level', 'detector', 'batch_file', 'dilution_factor'):
        assert key not in meta
