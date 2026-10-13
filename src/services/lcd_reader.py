"""Read Shimadzu LabSolutions ``.lcd`` data files: the PDA 3D matrix, the exported channels, and the sample record.

An ``.lcd`` is an OLE2 compound file. Everything here was derived from, and is checked against, the ASCII exports of
the same injections (see ``docs/LCD_FORMAT_NOTES.md`` and ``tests/test_lcd_reader.py``): every one of the 8401 spectra
of a 3 min run decodes to exactly the integers LabSolutions writes in the export's ``[PDA 3D]`` section.

Layout of ``PDA 3D Raw Data/3D Raw Data``: a plain concatenation of frames (one per time point), each

    int32 0x4352 'RC' | int32 1 | int32 n_wavelengths | int32 frame_length | 8 bytes
    uint16 LA | LA bytes: 256 delta tokens | uint16 LA | uint16 LB | LB bytes: n-256 delta tokens | uint16 LB

Both groups are running sums of signed deltas starting at zero (the matrix is in micro absorbance units, uAU). A delta
is a prefix code on the top three bits of its first byte: 1, 2, 3 or 4 bytes carrying 5, 13, 21 or 29 signed bits.
"""
from __future__ import annotations

import hashlib
import io
import re
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

RAW_STREAM = 'PDA 3D Raw Data/3D Raw Data'
ITEM_STREAM = 'PDA 3D Raw Data/3D Data Item'
STATUS_STREAM = 'PDA 3D Raw Data/Status'
FILE_PROPERTY = 'File Property'
SYSTEM_INFO = 'GUMM_Information/GUMMSubStg/SystemInformation'
CHANNEL_TABLE = 'LSS Data Processing/Multi Chromato Table'
CHANNEL_PREFIX = 'LSS Data Processing/SD-PDA.1.1.PDA.1.'
STATUS_ITEMS = 'LSS Raw Data/2D Data Item'
STATUS_LOG = 'LSS Raw Data/StatusLog Ch'
# Names LabSolutions' own text export gives the instrument status traces, by the stable data-source id.
STATUS_NAMES = {
    'LC.1.1.PUMP.1.ST#1': 'Pump A Pressure', 'LC.1.1.PUMP.1.ST#2': 'Pump A Degasser Pressure',
    'LC.1.1.SIL.1.ST#1': 'Sample Cooler Temp.', 'LC.1.1.OVEN.1.ST#1': 'Oven Temp.', 'LC.1.1.OVEN.1.ST#2': 'Room Temp.',
    'PDA.1.1.PDA.1.ST#1': 'PDA Cell Temp.', 'PDA.1.1.PDA.1.ST#2': 'PDA Polychromator Temp.',
    'PDA.1.1.PDA.1.ST#3': 'PDA Lamp Housing Temp.'}
FRAME_MAGIC = 0x4352
FIRST_GROUP = 256                      # values in the first group of every frame
MAX_STREAM_BYTES = 600_000_000
MAX_FRAMES = 400_000


class LcdFormatError(ValueError):
    """The file is not a readable LabSolutions data file."""


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value >= (1 << (bits - 1)) else value


def _decode_group(buf: bytes, start: int, stop: int, count: int, out: np.ndarray, offset: int) -> None:
    """``count`` delta tokens in ``buf[start:stop]`` accumulated into ``out[offset:offset+count]``."""
    i, total = start, 0
    for k in range(count):
        b = buf[i]
        cls = b >> 5
        if cls == 0:
            total += (b & 0x1F) - 32 if b & 0x10 else b & 0x1F
            i += 1
        elif cls == 1:
            v = ((b & 0x1F) << 8) | buf[i + 1]
            total += v - 8192 if v >= 4096 else v
            i += 2
        elif cls == 2:
            v = ((b & 0x1F) << 16) | (buf[i + 1] << 8) | buf[i + 2]
            total += v - 2097152 if v >= 1048576 else v
            i += 3
        elif cls == 3:
            v = ((b & 0x1F) << 24) | (buf[i + 1] << 16) | (buf[i + 2] << 8) | buf[i + 3]
            total += v - 536870912 if v >= 268435456 else v
            i += 4
        else:
            raise LcdFormatError('Unknown value code in a PDA frame.')
        out[offset + k] = total
    if i != stop:
        raise LcdFormatError('A PDA frame group does not end where it declares.')


def decode_matrix(raw: bytes, n_wavelengths: int, n_frames: Optional[int] = None) -> np.ndarray:
    """All frames of ``3D Raw Data`` as an ``(n_frames, n_wavelengths)`` int32 array in uAU (a 10 min run is 40 MB)."""
    if n_wavelengths <= FIRST_GROUP or n_wavelengths > 4096:
        raise LcdFormatError('Unexpected number of PDA wavelengths.')
    second = n_wavelengths - FIRST_GROUP
    frames: List[Tuple[int, int]] = []
    pos, size = 0, len(raw)
    while pos < size:
        if pos + 24 > size:
            raise LcdFormatError('The PDA data ends inside a frame.')
        magic, one, width, length = struct.unpack_from('<4i', raw, pos)
        if magic != FRAME_MAGIC or one != 1 or width != n_wavelengths or length < 32 or pos + length > size:
            raise LcdFormatError('The PDA data is not in the expected frame format.')
        frames.append((pos, length))
        pos += length
        if len(frames) > MAX_FRAMES:
            raise LcdFormatError('The PDA data has too many frames.')
    if n_frames is not None and len(frames) != n_frames:
        raise LcdFormatError(f'The PDA data has {len(frames)} frames, the file declares {n_frames}.')
    matrix = np.zeros((len(frames), n_wavelengths), dtype=np.int32)
    values = np.zeros(n_wavelengths, dtype=np.int64)
    limit = np.iinfo(np.int32).max
    for row, (start, length) in enumerate(frames):
        la = struct.unpack_from('<H', raw, start + 24)[0]
        first_start = start + 26
        mid = first_start + la
        if struct.unpack_from('<H', raw, mid)[0] != la:
            raise LcdFormatError('A PDA frame has an inconsistent group length.')
        lb = struct.unpack_from('<H', raw, mid + 2)[0]
        second_start = mid + 4
        end = second_start + lb
        if end + 2 != start + length or struct.unpack_from('<H', raw, end)[0] != lb:
            raise LcdFormatError('A PDA frame has an inconsistent group length.')
        _decode_group(raw, first_start, mid, FIRST_GROUP, values, 0)
        _decode_group(raw, second_start, end, second, values, FIRST_GROUP)
        if np.abs(values).max() > limit:
            raise LcdFormatError('A PDA value is outside the expected range.')
        matrix[row] = values
    return matrix


def decode_status_log(raw: bytes) -> np.ndarray:
    """One status trace (``StatusLog Ch<n>``): frames of the same shape as the PDA ones, in groups of at most 256
    values, each ``u16 L | L bytes of deltas | u16 L`` and each counting from zero."""
    if len(raw) < 28:
        raise LcdFormatError('A status trace is too short.')
    magic, interval_ms, last_index, length = struct.unpack_from('<4i', raw, 0)
    if magic != FRAME_MAGIC or length != len(raw) or interval_ms <= 0 or not 0 <= last_index < 1_000_000:
        raise LcdFormatError('A status trace is not in the expected format.')
    parts, pos = [], 24
    while pos < length:
        if pos + 4 > length:
            raise LcdFormatError('A status trace ends inside a group.')
        size = struct.unpack_from('<H', raw, pos)[0]
        start, end = pos + 2, pos + 2 + size
        if end + 2 > length or struct.unpack_from('<H', raw, end)[0] != size:
            raise LcdFormatError('A status trace has an inconsistent group length.')
        count, i = 0, start
        while i < end:
            i += _token_size(raw[i])
            count += 1
        if i != end:
            raise LcdFormatError('A status trace does not end where it declares.')
        group = np.zeros(count, dtype=np.int64)
        _decode_group(raw, start, end, count, group, 0)
        parts.append(group)
        pos = end + 2
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


def _token_size(first_byte: int) -> int:
    size = (first_byte >> 5) + 1
    if size > 4:
        raise LcdFormatError('Unknown value code in a status trace.')
    return size


def _status_traces(ole, duration_ms: float) -> Dict[str, Dict[str, Any]]:
    """Pump pressure, temperatures ... as the text export lists them (name -> time, values, unit)."""
    items = _read_stream(ole, STATUS_ITEMS)
    if not items:
        return {}
    xml = items.decode('utf-8', errors='replace')
    traces: Dict[str, Dict[str, Any]] = {}
    for number, block in enumerate(re.findall(r'<DII .*?</DII>', xml, re.S), start=1):
        raw = _read_stream(ole, f'{STATUS_LOG}{number}')
        source = re.search(r'<DSID>([^<]*)</DSID>', block)
        factor = re.search(r'<CF>([0-9A-F]{16})</CF>', block)
        unit = re.search(r'<Axis ID="0".*?<VF>([0-9A-F]{16})</VF><Unit>([^<]*)</Unit>', block, re.S)
        if not raw or not source or not factor or not unit:
            continue
        try:
            counts = decode_status_log(raw)
        except LcdFormatError:
            continue
        interval_ms = struct.unpack_from('<i', raw, 4)[0]
        expected = int(round(duration_ms / interval_ms)) + 1     # one reading per interval, both ends of the run
        if len(counts) == expected - 1:                      # the instrument's own export repeats the first reading
            counts = np.concatenate([[counts[0]], counts])
        if len(counts) != expected:
            continue
        scale = struct.unpack('<d', bytes.fromhex(factor.group(1)))[0]
        per_unit = struct.unpack('<d', bytes.fromhex(unit.group(1)))[0]      # e.g. kgf/cm2 per bar
        multiplier = 1.0 / per_unit if per_unit > 0 else 1.0
        name = STATUS_NAMES.get(source.group(1)) or (re.search(r'<DN>([^<]*)</DN>', block) or [None, source.group(1)])[1]
        traces[name] = {'time_min': (np.arange(expected) * interval_ms / 60000.0).tolist(),
                        'values': (counts * scale * multiplier).tolist(), 'unit': unit.group(2),
                        'multiplier': round(multiplier, 6),
                        'source_metadata': {'Interval(msec)': str(interval_ms), 'source': source.group(1)}}
    return traces


# ---------------------------------------------------------------------------
# Metadata streams
# ---------------------------------------------------------------------------

def _read_stream(ole, name: str, required: bool = False) -> Optional[bytes]:
    if not ole.exists(name):
        if required:
            raise LcdFormatError(f'This file has no "{name}" stream.')
        return None
    if ole.get_size(name) > MAX_STREAM_BYTES:
        raise LcdFormatError(f'Stream "{name}" is unexpectedly large; the file was not read.')
    return ole.openstream(name).read()


def _hex_text(value: str) -> str:
    """LabSolutions stores text as ``@StoX@`` plus the hex of its bytes."""
    value = value.replace('@StoX@', '')
    try:
        return bytes.fromhex(value).decode('cp1252').strip()
    except ValueError:
        return value.strip()


def _tags(xml: str, block: str) -> Dict[str, str]:
    match = re.search(rf'<{block}>(.*?)</{block}>', xml, re.S)
    return dict(re.findall(r'<(\w+)>([^<]*)</\1>', match.group(1))) if match else {}


def _number(value: str) -> Optional[float]:
    try:
        return float(value.replace('@FtoX@', '').strip())
    except ValueError:
        return None


def _filetime(low: str, high: str) -> Optional[datetime]:
    try:
        ticks = ((int(high) & 0xFFFFFFFF) << 32) | (int(low) & 0xFFFFFFFF)
        return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
    except (ValueError, OverflowError):
        return None


def _local_naive(moment: Optional[datetime]) -> Optional[str]:
    """ISO text in this computer's local time, as LabSolutions writes times into its text exports."""
    return moment.astimezone().replace(tzinfo=None, microsecond=0).isoformat() if moment else None


def _file_name(path: str) -> Optional[str]:
    return re.split(r'[\\/]', path.strip())[-1] or None if path.strip() else None


def _sample_record(file_property: str) -> Dict[str, Any]:
    info, files = _tags(file_property, 'SampleInfo'), _tags(file_property, 'SampleInfoFile')
    props = _tags(file_property, 'FileProperty')
    details = _tags(file_property, 'DataFileProperty')
    operator = _hex_text(info.get('operator_name', ''))
    record: Dict[str, Any] = {
        'sample_name': _hex_text(info.get('smpl_name', '')) or None,
        'sample_id': _hex_text(info.get('smpl_id', '')) or None,
        'sample_type': _hex_text(info.get('smpl_type', '')) or None,
        'level': int(info['level']) if info.get('level', '').lstrip('-').isdigit() else None,
        'vial': _hex_text(info.get('vial_num', '')) or None,
        'tray': _hex_text(info.get('tray_name', '')) or None,
        'injection_volume_ul': _number(info.get('inj_vol', '')),
        'sample_amount': _number(info.get('smpl_amount', '')),
        'dilution_factor': _number(info.get('dil_factor', '')),
        'operator': operator or None,
        'acquired': _local_naive(_filetime(info.get('dwLowDateTime', ''), info.get('dwHighDateTime', ''))),
        'file_generated': _local_naive(_filetime(props.get('dwLowGeneratedDateTime', ''),
                                                  props.get('dwHighGeneratedDateTime', ''))),
        'file_modified': _local_naive(_filetime(props.get('dwLowModifiedDateTime', ''),
                                                 props.get('dwHighModifiedDateTime', ''))),
        'software_version': _hex_text(details.get('szVersion', '')) or None,
        'data_file': _file_name(_hex_text(files.get('datafile', ''))),
        'method_file': _file_name(_hex_text(files.get('methodfile', ''))),
        'batch_file': _file_name(_hex_text(files.get('batchfile', ''))),
    }
    return {k: v for k, v in record.items() if v is not None}


def _channels(ole, wavelengths_nm: np.ndarray) -> List[Dict[str, Any]]:
    """The 2D channels LabSolutions exports (one ``SD-...PDA.1.n`` stream each) with wavelength and bandwidth."""
    table = _read_stream(ole, CHANNEL_TABLE)
    active = sorted(int(m.group(1)) for e in ole.listdir(streams=True, storages=False)
                    if (m := re.fullmatch(re.escape(CHANNEL_PREFIX) + r'(\d+)', '/'.join(e))))
    if not table or not active:
        return []
    ints = struct.unpack(f'<{len(table) // 4}i', table[:len(table) // 4 * 4])
    channels = []
    for number in active:
        base = 4 + 8 * number
        if base + 3 >= len(ints):
            continue
        wavelength, bandwidth = ints[base] / 100.0, float(ints[base + 3] & 0xFF)
        if not (wavelengths_nm[0] - 1 <= wavelength <= wavelengths_nm[-1] + 1) or bandwidth <= 0:
            continue
        channels.append({'channel': f'Ch{number}', 'number': number, 'wavelength_nm': wavelength,
                         'bandwidth_nm': bandwidth})
    return channels


def channel_trace(matrix_uau: np.ndarray, wavelengths_nm: np.ndarray, wavelength: float, bandwidth: float) -> np.ndarray:
    """A channel chromatogram in uAU: the mean of the spectrum columns within ``wavelength`` +/- ``bandwidth``.

    This reproduces the instrument's own channel export to within its rounding (+/- 0.5 uAU).
    """
    selected = (wavelengths_nm >= wavelength - bandwidth) & (wavelengths_nm <= wavelength + bandwidth)
    if not selected.any():
        raise LcdFormatError('No spectrum column lies within the channel bandwidth.')
    return np.floor(matrix_uau[:, selected].mean(axis=1) + 0.5)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_lcd(source: Union[str, Path, bytes]) -> Dict[str, Any]:
    """Read an ``.lcd``. Returns a dict with ``time_min``, ``wavelength_nm``, ``matrix_uau`` (int32), ``interval_ms``,
    ``channels`` (wavelength, bandwidth), ``sample`` (record fields) and ``instrument``.
    """
    try:
        import olefile
    except ImportError as exc:                                # pragma: no cover - dependency is in requirements.txt
        raise LcdFormatError('Reading .lcd files needs the "olefile" package (pip install olefile).') from exc
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        if Path(source).stat().st_size > MAX_STREAM_BYTES:
            raise LcdFormatError('This file is too large to be a LabSolutions data file.')
        data = Path(source).read_bytes()
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except OSError as exc:
        raise LcdFormatError('This is not a LabSolutions compound file.') from exc
    with ole:
        raw = _read_stream(ole, RAW_STREAM, required=True)
        item = _read_stream(ole, ITEM_STREAM, required=True).decode('utf-8', errors='replace')
        status = _read_stream(ole, STATUS_STREAM, required=True)
        property_xml = (_read_stream(ole, FILE_PROPERTY) or b'').decode('utf-8', errors='replace')
        system = _read_stream(ole, SYSTEM_INFO)
        wavelengths = np.asarray([struct.unpack('<d', bytes.fromhex(x))[0] / 100.0
                                  for x in re.findall(r'<DT>([0-9A-F]{16})</DT>', item)])
        count = re.search(r'<CN>(\d+)</CN>', item)
        if len(wavelengths) < FIRST_GROUP + 1 or not count:
            raise LcdFormatError('The PDA wavelength table is missing.')
        if len(status) < 28:
            raise LcdFormatError('The PDA status record is missing.')
        n_frames, interval_ms = struct.unpack_from('<i', status, 4)[0], struct.unpack_from('<i', status, 24)[0]
        if n_frames != int(count.group(1)) or interval_ms <= 0:
            raise LcdFormatError('The PDA time axis is inconsistent.')
        matrix = decode_matrix(raw, len(wavelengths), n_frames)
        channels = _channels(ole, wavelengths)
        traces = _status_traces(ole, (n_frames - 1) * interval_ms)
        scan = [struct.unpack('<d', bytes.fromhex(m.group(1)))[0] / 100.0
                for tag in ('WVB', 'WVE') if (m := re.search(rf'<{tag}>([0-9A-F]{{16}})</{tag}>', item))]
    instrument = None
    if system:
        found = re.search(r'<IN>([^<]+)</IN>', system.decode('utf-16le', errors='replace'))
        instrument = found.group(1).strip() if found else None
    return {
        'time_min': np.arange(n_frames, dtype=float) * interval_ms / 60000.0,
        'wavelength_nm': wavelengths, 'matrix_uau': matrix, 'interval_ms': interval_ms,
        'channels': channels, 'sample': _sample_record(property_xml), 'instrument': instrument,
        'scan_range_nm': tuple(scan) if len(scan) == 2 else (float(wavelengths[0]), float(wavelengths[-1])),
        'status_traces': traces, 'sha256': hashlib.sha256(data).hexdigest(),
    }
