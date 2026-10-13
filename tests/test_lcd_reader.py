"""Shimadzu .lcd reader: the frame codec, and the real files against their ASCII exports."""
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services import lcd_reader as lr  # noqa: E402

SHARE = Path('/Volumes/Paradisi/Group_Members/Glenn-Synology/SHIMZU/Minling/Data_Minling/12-10-l-alanine calibration curve 1')
EXPORTS = Path('/Users/glenn/Desktop/ala-calibration')


# -- an encoder for the documented format, to test the decoder without a real file -----------------------------

def _token(delta: int) -> bytes:
    if -16 <= delta < 16:
        return bytes([delta & 0x1F])
    if -4096 <= delta < 4096:
        v = delta & 0x1FFF
        return bytes([0x20 | (v >> 8), v & 0xFF])
    if -1048576 <= delta < 1048576:
        v = delta & 0x1FFFFF
        return bytes([0x40 | (v >> 16), (v >> 8) & 0xFF, v & 0xFF])
    v = delta & 0x1FFFFFFF
    return bytes([0x60 | (v >> 24), (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])


def _frame(values, width) -> bytes:
    deltas = np.diff(np.concatenate([[0], values[:256]])).tolist() + np.diff(np.concatenate([[0], values[256:]])).tolist()
    first = b''.join(_token(d) for d in deltas[:256])
    second = b''.join(_token(d) for d in deltas[256:])
    body = struct.pack('<H', len(first)) + first + struct.pack('<H', len(first)) \
        + struct.pack('<H', len(second)) + second + struct.pack('<H', len(second))
    length = 24 + len(body)
    return struct.pack('<4i', lr.FRAME_MAGIC, 1, width, length) + bytes(8) + body


def test_decoder_round_trips_every_token_size():
    rng = np.random.default_rng(1)
    width = 300

    def row(limit):
        # Each group starts from zero, as in the real files, and every step fits its token class.
        steps = rng.integers(-limit, limit, width)
        steps[[0, 256]] = rng.integers(-limit, limit, 2)
        return np.concatenate([np.cumsum(steps[:256]), np.cumsum(steps[256:])])

    rows = [np.zeros(width, dtype=np.int64), row(12), row(3000), row(900_000), row(4_000_000)]
    raw = b''.join(_frame(row, width) for row in rows)
    matrix = lr.decode_matrix(raw, width, len(rows))
    assert np.array_equal(matrix, np.array(rows))


def test_all_frames_at_once_decode_exactly_like_one_frame_at_a_time():
    rng = np.random.default_rng(3)
    width = 400

    def row():
        steps = rng.integers(-1, 2, width) * rng.choice([9, 2500, 700_000, 3_000_000], width)
        return np.concatenate([np.cumsum(steps[:256]), np.cumsum(steps[256:])])

    rows = [row() for _ in range(40)]
    raw = b''.join(_frame(r, width) for r in rows)
    expected = np.zeros((len(rows), width), dtype=np.int64)
    pos = 0
    for index in range(len(rows)):
        length = struct.unpack_from('<i', raw, pos + 12)[0]
        la = struct.unpack_from('<H', raw, pos + 24)[0]
        mid = pos + 26 + la
        lb = struct.unpack_from('<H', raw, mid + 2)[0]
        lr._decode_group(raw, pos + 26, mid, 256, expected[index], 0)
        lr._decode_group(raw, mid + 4, mid + 4 + lb, width - 256, expected[index], 256)
        pos += length
    assert np.array_equal(lr.decode_matrix(raw, width, len(rows)), expected)


def test_decoder_rejects_damaged_data_instead_of_returning_garbage():
    width = 300
    raw = _frame(np.arange(width), width)
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(raw[:-5], width)                                  # truncated
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(b'XX' + raw[2:], width)                           # not a frame
    corrupt = bytearray(raw)
    corrupt[24] ^= 0x07                                                    # group length disagrees with its copy
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(bytes(corrupt), width)
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(raw, width, n_frames=2)                           # wrong declared frame count
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(raw, 100)                                         # implausible wavelength count
    huge = _frame(np.concatenate([np.cumsum(np.full(256, 200_000_000)), np.zeros(44, dtype=np.int64)]), 300)
    with pytest.raises(lr.LcdFormatError):
        lr.decode_matrix(huge, 300)                                        # beyond what the instrument can record


def test_sample_record_decodes_hex_text_numbers_and_times():
    xml = ('<FileProperty><dwLowGeneratedDateTime>-1184221357</dwLowGeneratedDateTime>'
           '<dwHighGeneratedDateTime>31283791</dwHighGeneratedDateTime></FileProperty>'
           '<DataFileProperty><szVersion>@StoX@352E313431</szVersion></DataFileProperty>'
           '<SampleInfo><vial_num>@StoX@3436</vial_num><level>1</level><smpl_type>@StoX@5374616E64617264</smpl_type>'
           '<smpl_name>@StoX@6C2D616C616E696E652031306D4D</smpl_name><smpl_id>@StoX@</smpl_id>'
           '<operator_name>@StoX@4D2E</operator_name><inj_vol>@FtoX@2.5</inj_vol><smpl_amount>@FtoX@1</smpl_amount>'
           '<dil_factor>@FtoX@1</dil_factor></SampleInfo>')
    record = lr._sample_record(xml)
    assert record['sample_name'] == 'l-alanine 10mM' and record['sample_type'] == 'Standard'
    assert record['vial'] == '46' and record['level'] == 1 and record['injection_volume_ul'] == 2.5
    assert record['software_version'] == '5.141' and record['operator'] == 'M.'
    assert 'sample_id' not in record and record['file_generated'].startswith('2026-10-12T')


def test_a_non_ole_file_is_rejected():
    with pytest.raises(lr.LcdFormatError):
        lr.read_lcd(b'this is not a compound file')


# -- real files against the text exports of the same injections ------------------------------------------------

def _pairs():
    if not SHARE.is_dir() or not EXPORTS.is_dir():
        return []
    return [(p, EXPORTS / (p.stem + '.txt')) for p in sorted(SHARE.glob('*.lcd')) if (EXPORTS / (p.stem + '.txt')).exists()]


def _export_matrix(path: Path):
    lines = path.read_text(encoding='latin-1').split('\n')
    start = lines.index('[PDA 3D]')
    header = next(i for i in range(start, start + 14) if lines[i].startswith('R.Time')) + 1
    rows = [[float(v) for v in line.split('\t')[1:413]] for line in lines[header + 1:header + 1 + 8401]]
    return np.array(rows), lines


@pytest.mark.skipif(not _pairs(), reason='needs the alanine .lcd files and their text exports')
@pytest.mark.parametrize('lcd,export', _pairs()[:3], ids=lambda p: p.name[9:30])
def test_real_lcd_matches_its_ascii_export_exactly(lcd, export):
    data = lr.read_lcd(lcd)
    matrix, lines = _export_matrix(export)
    assert np.array_equal(data['matrix_uau'], matrix)                      # every one of 8401 spectra, all 412 points
    assert data['interval_ms'] == 25 and len(data['time_min']) == 8401
    for channel in data['channels']:
        section = lines.index(f"[PDA Multi Chromatogram({channel['channel']})]")
        header = next(i for i in range(section, section + 15) if lines[i].startswith('R.Time'))
        expected = np.array([float(l.split('\t')[1]) for l in lines[header + 1:header + 1 + 8401]])
        fields = dict(l.split('\t')[:2] for l in lines[section + 1:header] if '\t' in l)
        assert float(fields['Wavelength(nm)']) == channel['wavelength_nm']
        assert float(fields['Bandwidth(nm)']) == channel['bandwidth_nm']
        assert np.array_equal(lr.channel_trace(data['matrix_uau'], data['wavelength_nm'], channel['wavelength_nm'],
                                               channel['bandwidth_nm']), expected)
    info = {k.strip(): v.strip() for k, v in (l.split('\t', 1) for l in lines[:60] if '\t' in l)}
    sample = data['sample']
    assert sample['sample_name'] == info['Sample Name'] and sample['vial'] == info['Vial#']
    assert str(sample['level']) == info['Level'] and sample['operator'] == info['Operator Name']
    assert data['instrument'] == 'Shimadzu LC-PDA-1'


@pytest.mark.skipif(not _pairs(), reason='needs the alanine .lcd files and their text exports')
def test_lcd_and_ascii_ingest_to_the_same_sample(monkeypatch):
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    from src.ingestion import ingest_file
    lcd, export = _pairs()[0]
    a, b = ingest_file(str(lcd), lcd.name), ingest_file(str(export), export.name)
    assert a.identity.detected_format == 'shimadzu_lcd' and b.identity.detected_format == 'shimadzu_ascii'
    assert a.sample_name == b.sample_name and a.source_category == b.source_category
    for key in ('sample_type', 'level', 'vial', 'injection_volume_ul', 'operator', 'acquired', 'instrument', 'detector',
                'method_file', 'data_file', 'file_generated', 'file_modified', 'channels', 'wavelength_points'):
        assert a.metadata[key] == b.metadata[key], key
    for ca, cb in zip(a.metadata['chromatogram_channels'], b.metadata['chromatogram_channels']):
        assert ca['name'] == cb['name'] and np.allclose(ca['data'].iloc[:, 1], cb['data'].iloc[:, 1], atol=1e-9, rtol=0)


@pytest.mark.skipif(not _pairs(), reason='needs the alanine .lcd files and their text exports')
def test_status_traces_match_the_export_names_units_and_values():
    lcd, export = _pairs()[0]
    data = lr.read_lcd(lcd)
    lines = export.read_text(encoding='latin-1').split('\n')
    exported = [l[len('[LC Status Trace('):-2] for l in lines if l.startswith('[LC Status Trace(')]
    assert sorted(data['status_traces']) == sorted(exported)
    for name in exported:
        start = lines.index(f'[LC Status Trace({name})]')
        header = next(i for i in range(start, start + 12) if lines[i].startswith('R.Time'))
        fields = dict(l.split('\t')[:2] for l in lines[start + 1:header] if '\t' in l)
        values = np.array([float(l.split('\t')[1]) for l in lines[header + 1:header + 1 + 211]]) * float(fields['Intensity Multiplier'])
        trace = data['status_traces'][name]
        assert trace['unit'] == fields['Intensity Units']
        assert len(trace['values']) == 211
        assert np.allclose(trace['values'], values, atol=0.06)          # the export rounds temperatures to 0.1


@pytest.mark.skipif(not _pairs(), reason='needs the alanine .lcd files and their text exports')
def test_an_lcd_survives_saving_and_reopening_a_project(monkeypatch):
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    from services import session_service
    from services.data_store import DataStore
    from session_helpers import load_files
    lcd, _export = _pairs()[0]
    store = DataStore()
    (bundle,) = load_files(store, [(lcd.name, lcd.read_bytes())])
    before = {c.component_id: c.dataframe.copy() for c in bundle.component_list}
    restored = DataStore()
    session_service.restore_session(restored, session_service.build_session(store))
    after = {c.component_id: c.dataframe for b in restored.iter_bundles() for c in b.component_list}
    assert before.keys() == after.keys() and all(before[k].equals(after[k]) for k in before)
