"""Metadata panel grouping: curated groups, readable labels, raw keys hidden."""
from pathlib import Path

from callbacks.viz_callbacks import build_metadata_panel, create_data_table
from components.workspace_layout import walk
from services.metadata_display import group_metadata
from src.ingestion.presets.shimadzu_ascii import ShimadzuASCIIPreset

FIXTURE = Path(__file__).parent / 'ingestion' / 'fixtures' / 'shimadzu_ascii.txt'
RICH = (FIXTURE.read_text()
        .replace('Sample ID\tfixture-001\n', 'Operator Name\tSystem Administrator\nSample Type\t1:Standard\nLevel\t3\n'
                 'Sample ID\tfixture-001\nISTD Amount1\t1\n')
        .replace('Instrument Name\tSynthetic LC-PDA\n', 'Instrument Name\tSynthetic LC-PDA\nDetector Name\tPDA\n')
        .replace('Method File\tC:\\LabSolutions\\synthetic.lcm\n', 'Method File\tC:\\LabSolutions\\Methods\\synthetic.lcm\n'))


def _parsed(tmp_path):
    path = tmp_path / 'sample.txt'
    path.write_text(RICH)
    return ShimadzuASCIIPreset().parse(str(path))['metadata']


def _as_dict(groups):
    return {name: dict(rows) for name, rows in groups}


def test_shimadzu_metadata_is_grouped_with_readable_labels(tmp_path):
    groups = group_metadata(_parsed(tmp_path))
    assert [g for g, _ in groups] == ['Sample', 'Acquisition', 'Instrument', 'Method', 'Detector', 'Channels', 'Instrument data']
    d = _as_dict(groups)
    assert d['Sample']['Name'] == 'Synthetic PDA standard'
    assert d['Sample']['Sample type'] == 'Standard' and d['Sample']['Injection volume'] == '0.5 \u00b5L'
    assert d['Acquisition']['Acquired'] == '2026-07-30 13:40:04'
    assert d['Acquisition']['Sampling interval'] == '2,000 ms'
    assert d['Instrument']['Software'] == 'LabSolutions 5.141'
    assert d['Method']['Method file'] == 'synthetic.lcm'
    assert d['Detector']['Wavelength range'] == '250 \u2013 600 nm'
    assert d['Channels']['Ch1'] == '250 nm, bandwidth 4 nm' and d['Channels']['Ch2'] == '600 nm, bandwidth 4 nm'
    assert 'Wavelength' not in d['Channels']  # per-channel rows replace the single-channel ones
    assert d['Instrument data']['3D PDA matrix'].startswith('3 time points')


def test_raw_and_internal_keys_never_reach_the_panel(tmp_path):
    meta = {**_parsed(tmp_path), 'display_name': 'x', 'parent_bundle_id': 'b', 'auto_x': 'Time', '_private': 1}
    rows = [(g, l, v) for g, rs in group_metadata(meta) for l, v in rs]
    text = ' '.join(f'{l} {v}' for _, l, v in rows)
    assert not any(g == 'Other' for g, _, _ in rows)
    for noise in ('ISTD', 'raw_sections', 'Raw sections', 'intensity', 'Intensity scaling', 'C:\\', 'Display name', 'Auto x'):
        assert noise not in text
    labels = [(g, l) for g, l, _ in rows]
    assert len(labels) == len(set(labels))


def test_unknown_scalar_keys_fall_into_other_and_bulk_is_skipped():
    groups = _as_dict(group_metadata({'custom_field': 'abc', 'blob': 'x' * 400, 'matrix': [[1, 2], [3, 4]],
                                      'empty': '', 'none': None, 'flag': True, '\ufefffile_path': 'chrom://a/b'}))
    assert groups['Other'] == {'Custom field': 'abc', 'Flag': 'yes'}
    assert groups['Method']['Source path'] == 'chrom://a/b'


def test_chromeleon_style_metadata_is_grouped():
    d = _as_dict(group_metadata({'injection': '1 - 15', 'position': 'BA2', 'injection_volume_\u00b5l': '2,000',
                                 'injection_date': '26.05.2025', 'injection_time': '10:14:53',
                                 'instrument_method': '5-95 4 min TFA', 'detector': 'UV', 'wavelength_nm': '210',
                                 'channel': 'UV_VIS_1', 'exporting_data_system': 'Chromeleon 7.1'}))
    assert d['Sample']['Injection volume'] == '2 \u00b5L'  # decimal comma read as 2.000
    assert d['Acquisition']['Injected'] == '26.05.2025 10:14:53'
    assert d['Method']['Instrument method'] == '5-95 4 min TFA'
    assert d['Channels']['Wavelength'] == '210 nm' and d['Channels']['Channel'] == 'UV_VIS_1'


def test_panel_renders_group_headings_and_no_raw_dump(tmp_path):
    panel = build_metadata_panel(_parsed(tmp_path))
    text = ' '.join(str(n.children) for n in walk(panel) if isinstance(getattr(n, 'children', None), str))
    for heading in ('Sample', 'Acquisition', 'Instrument', 'Method', 'Detector', 'Channels'):
        assert heading in text
    assert 'ISTD' not in text and 'raw_sections' not in text and 'Peak Table' not in text
    assert build_metadata_panel({}).children is None


def test_data_table_uses_curated_panel(tmp_path):
    meta = _parsed(tmp_path)
    panel = create_data_table({'record': {'name': 'run', 'type': 'primary'}, 'metadata': meta})
    text = ' '.join(str(n.children) for n in walk(panel) if isinstance(getattr(n, 'children', None), str))
    assert 'Synthetic LC-PDA' in text and 'Raw Sections' not in text and 'Source Sections' not in text
