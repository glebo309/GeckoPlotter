"""Synthetic LabSolutions fixtures only; no private instrument exports."""
from pathlib import Path

import numpy as np
import pytest

from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.presets.shimadzu_ascii import ShimadzuASCIIPreset
from src.ingestion.types import ColumnRole, SourceCategory

FIXTURE = Path(__file__).parent / 'fixtures' / 'shimadzu_ascii.txt'


def test_registry_recognizes_content_and_preserves_channels_and_provenance():
    result = IngestionPipeline().ingest(str(FIXTURE), 'arbitrary-name.TXT')
    assert result.identity.detected_format == 'shimadzu_ascii'
    assert result.identity.detection_stage == 2
    assert result.source_category == SourceCategory.CHROMATOGRAM
    assert result.sample_name == 'Synthetic PDA standard'
    assert result.column_roles == {'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y}
    np.testing.assert_allclose(result.data['Absorbance (mAU)'], [-1, 250, 2])
    channels = result.metadata['chromatogram_channels']
    assert len(channels) == 2
    assert channels[0]['name'] == 'PDA 250 nm (Ch1)'
    assert channels[1]['metadata']['wavelength_nm'] == 600
    np.testing.assert_allclose(channels[1]['data']['Absorbance (mAU)'], [-.5, 5, 1])
    assert result.metadata['sample_id'] == 'fixture-001'
    assert result.metadata['injection_volume_ul'] == .5
    assert result.metadata['acquired'] == '2026-07-30T13:40:04'
    assert result.metadata['instrument_peaks']['PDA-Ch1'][0]['Height'] == 250000
    assert result.metadata['instrument_peaks']['PDA-Ch2'] == []
    assert result.metadata['raw_sections']['Original Files']['Method File'].endswith('synthetic.lcm')
    pressure = result.metadata['instrument_status']['Pump A Pressure']
    assert pressure['unit'] == 'bar'
    np.testing.assert_allclose(pressure['values'], np.array([100, 101, 102]) * .980665)
    assert channels[0]['metadata']['intensity_scaling']['factor_to_mau'] == .001


def test_pda_matrix_axes_and_signed_intensities_are_preserved():
    pda = ShimadzuASCIIPreset().parse(str(FIXTURE))['metadata']['pda']
    np.testing.assert_allclose(pda['time_min'], [0, .03333, .06667])
    np.testing.assert_allclose(pda['wavelength_nm'], [249.85, 251.15, 600.36])
    np.testing.assert_allclose(pda['absorbance_mau'], [[-1, -.9, -.5], [250, 240, 5], [2, 1.9, 1]])
    assert pda['wavelength_scaling']['factor_to_nm'] == .01
    assert pda['intensity_scaling']['factor_to_mau'] == .001


@pytest.mark.parametrize('old,new', [
    ('0.06667\t2000\t1900\t1000', ''),
    ('0.03333\t250000\t240000\t5000', '0.03333\t250000\t5000'),
    ('0.06667\t2000\n', '0.06667\tbad\n'),
    ('0.06667\t2000\n', ''),
    ('0.03333\t250000\t240000\t5000', '0\t250000\t240000\t5000'),
    ('0.03333\t250000\t240000\t5000', '0.03333\tnan\t240000\t5000'),
])
def test_rejects_truncated_malformed_and_nonmonotonic_data(tmp_path, old, new):
    path = tmp_path / 'broken.txt'
    path.write_text(FIXTURE.read_text().replace(old, new))
    with pytest.raises(ValueError):
        ShimadzuASCIIPreset().parse(str(path))


def test_chromatogram_only_export_is_supported(tmp_path):
    path = tmp_path / 'channel-only.txt'
    path.write_text(FIXTURE.read_text().split('[PDA 3D]')[0])
    result = ShimadzuASCIIPreset().parse(str(path))
    assert len(result['metadata']['chromatogram_channels']) == 2
    assert 'pda' not in result['metadata']


def test_rejects_unrelated_ascii_and_unknown_intensity_unit(tmp_path):
    assert not ShimadzuASCIIPreset.sniff('file.txt', b'Raw Data:', ['Raw Data:'])
    path = tmp_path / 'unknown.txt'
    path.write_text(FIXTURE.read_text().replace('Intensity Units\tmAU', 'Intensity Units\tcounts'))
    with pytest.raises(ValueError, match='unit'):
        ShimadzuASCIIPreset().parse(str(path))


def test_recognized_corrupt_export_never_falls_back_to_heuristics(tmp_path, monkeypatch):
    path = tmp_path / 'truncated.txt'
    path.write_text(FIXTURE.read_text().replace('0.06667\t2000\t1900\t1000', ''))
    def forbidden_fallback(*args):
        pytest.fail('A recognized corrupt LabSolutions export reached heuristic parsing')
    monkeypatch.setattr('src.ingestion.pipeline.heuristic_parse', forbidden_fallback)
    assert IngestionPipeline().ingest(str(path), path.name) is None


def test_pda_only_provides_trace_at_nearest_254_nm(tmp_path):
    text = FIXTURE.read_text()
    start, end = text.index('[PDA Multi Chromatogram(Ch1)]'), text.index('[PDA 3D]')
    path = tmp_path / 'pda-only.txt'
    path.write_text(text[:start] + text[end:])
    result = ShimadzuASCIIPreset().parse(str(path))
    assert result['metadata']['wavelength_nm'] == 251.15
    assert result['metadata']['derived_from'] == 'PDA 3D'
    np.testing.assert_allclose(result['data']['Absorbance (mAU)'], [-.9, 240, 1.9])


def test_utf16_and_asc_extension_are_detected(tmp_path):
    path = tmp_path / 'sample.asc'
    path.write_text(FIXTURE.read_text(), encoding='utf-16')
    result = IngestionPipeline().ingest(str(path), path.name)
    assert result.identity.detected_format == 'shimadzu_ascii'


def test_unknown_version_does_not_silently_apply_verified_profile(tmp_path):
    path = tmp_path / 'future.txt'
    path.write_text(FIXTURE.read_text().replace('Version\t5.141', 'Version\t99.0'))
    with pytest.raises(ValueError, match='Unverified'):
        ShimadzuASCIIPreset().parse(str(path))


@pytest.mark.parametrize('old,new', [
    ('3000\t250000\tSynthetic compound', '3000\tnan\tSynthetic compound'),
    ('# of Peaks\t1', '# of Peaks\t2'),
])
def test_invalid_instrument_peak_results_are_not_silently_accepted(tmp_path, old, new):
    path = tmp_path / 'bad-peaks.txt'
    path.write_text(FIXTURE.read_text().replace(old, new))
    with pytest.raises(ValueError):
        ShimadzuASCIIPreset().parse(str(path))


def test_full_pda_uses_compact_immutable_arrays_and_verified_digest():
    import hashlib
    pda = ShimadzuASCIIPreset().parse(str(FIXTURE))['metadata']['pda']
    digest = hashlib.sha256()
    for key in ('time_min', 'wavelength_nm', 'absorbance_mau'):
        values = pda[key]
        assert isinstance(values, np.ndarray)
        assert values.dtype == np.dtype('float64')
        assert not values.flags.writeable
        digest.update(values.astype('<f8', copy=False).tobytes())
    assert pda['data_sha256'] == digest.hexdigest()
    with pytest.raises(ValueError):
        pda['absorbance_mau'][0, 0] = 999.


@pytest.mark.parametrize('bad', ['12oops', '1 # silently ignored', 'inf', '1\t2'])
def test_vectorized_matrix_reading_must_reject_invalid_cells(tmp_path, bad):
    path = tmp_path / 'bad-matrix.txt'
    path.write_text(FIXTURE.read_text().replace('0.03333\t250000\t240000\t5000', f'0.03333\t{bad}\t240000\t5000'))
    with pytest.raises(ValueError):
        ShimadzuASCIIPreset().parse(str(path))
