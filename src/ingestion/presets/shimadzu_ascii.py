"""Shimadzu LabSolutions sectioned ASCII chromatography/PDA exports.

The LabSolutions 5.141 PDA ASCII profile uses integer micro-AU despite its
``mAU / multiplier 1`` header. The 0.001 conversion was checked against paired
ANDI CDF ordinates (CDF * 1000 agrees to ASCII rounding). Do not infer this
correction from signal magnitude or extend it silently to unknown profiles.
"""
from __future__ import annotations

import re
import hashlib
import ntpath
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint, SourceCategory

_ROLES = {'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y}


def _read_sections(path):
    raw = Path(path).read_bytes()
    encodings = ('utf-16',) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp932', 'cp1252')
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError('Cannot decode LabSolutions ASCII export')
    sections, current = {}, None
    for line in text.splitlines():
        marker = re.fullmatch(r'\[([^\]]+)\]', line.strip())
        if marker:
            current = marker.group(1)
            if current in sections:
                raise ValueError(f'Duplicate LabSolutions section: {current}')
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line)
    return sections


def _headers(lines):
    result = {}
    for line in lines:
        parts = line.split('\t')
        if parts[0].strip().startswith(('R.Time', 'Peak#')):
            break
        if len(parts) == 2:
            result[parts[0].strip()] = parts[1].strip()
    return result


def _number(value, context):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid numeric value in {context}: {value!r}') from exc
    if not np.isfinite(result):
        raise ValueError(f'Non-finite numeric value in {context}')
    return result


def _count(meta, key, actual, context):
    if key in meta and _number(meta[key], context) != actual:
        raise ValueError(f'{context}: expected {meta[key]} {key}, found {actual}')


_DATE_FORMATS = ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %H:%M:%S', '%d.%m.%Y %H:%M:%S',
                 '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                 '%m/%d/%Y %I:%M %p', '%m/%d/%Y')


def _iso_datetime(*parts):
    """ISO-8601 text for a LabSolutions timestamp; the original text when no known layout fits."""
    text = ' '.join(str(p).strip() for p in parts if p and str(p).strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return text or None


def _file_name(path):
    """File name without the acquisition PC's Windows directory (empty -> None)."""
    return ntpath.basename(str(path or '').strip()) or None


def _optional_number(value):
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _numeric_or_text(value):
    """Integers stay ints, other numbers floats, anything else stripped text (empty -> None)."""
    text = str(value if value is not None else '').strip()
    number = _optional_number(text)
    if number is None:
        return text or None
    return int(number) if number.is_integer() and re.fullmatch(r'[+-]?\d+', text) else number


def _sample_type(value):
    """'1:Standard' -> 'Standard' (LabSolutions prefixes the type with its numeric code)."""
    text = str(value or '').strip()
    return text.split(':', 1)[1].strip() if re.match(r'^\d+:', text) else text or None


def _curated_metadata(source, version):
    """Small, consistently named and typed summary of the raw sections (no empty values)."""
    header, sample = source.get('Header', {}), source.get('Sample Information', {})
    files, config = source.get('Original Files', {}), source.get('Configuration', {})
    detector = config.get('Detector Name') or config.get('Detector ID')
    curated = {
        'file_type_detail': 'shimadzu_labsolutions_ascii', 'manufacturer': 'Shimadzu',
        'software': 'LabSolutions', 'software_version': version or None,
        'sample_name': sample.get('Sample Name') or None,
        'sample_id': sample.get('Sample ID') or None,
        'sample_type': _sample_type(sample.get('Sample Type')),
        'level': _numeric_or_text(sample.get('Level')),
        'vial': _numeric_or_text(sample.get('Vial#')),
        'injection_volume_ul': _optional_number(sample.get('Injection Volume')),
        'sample_amount': _optional_number(sample.get('Sample Amount')),
        'dilution_factor': _optional_number(sample.get('Dilution Factor')),
        'operator': sample.get('Operator Name') or None,
        'acquired': _iso_datetime(sample.get('Acquired')),
        'exported': _iso_datetime(header.get('Output Date'), header.get('Output Time')),
        'instrument': config.get('Instrument Name') or None,
        'detector': detector or None,
        'data_file': _file_name(files.get('Data File') or header.get('Data File Name')),
        'method_file': _file_name(files.get('Method File')),
        'batch_file': _file_name(files.get('Batch File')),
    }
    if sample.get('Injection Volume'):
        # An unparsable volume is a corrupt export, not something to hide.
        curated['injection_volume_ul'] = _number(sample['Injection Volume'], 'Injection Volume')
    return {k: v for k, v in curated.items() if v is not None}


def _acquisition_extent(fields, time):
    extent = {'time_start_min': round(float(time[0]), 6), 'time_end_min': round(float(time[-1]), 6),
              'data_points': len(time)}
    interval = _optional_number(fields.get('Interval(msec)'))
    if interval is not None:
        extent['sampling_interval_ms'] = interval
    return extent


def _increasing(values, context):
    if not len(values) or (len(values) > 1 and np.any(np.diff(values) <= 0)):
        raise ValueError(f'{context}: axis must be nonempty and strictly increasing')


def _numeric_rows(lines, columns, context):
    """Parse the rectangular table in NumPy, retaining strict cell validation."""
    if not lines:
        raise ValueError(f'{context}: empty data')
    try:
        array = np.loadtxt(lines, delimiter='\t', comments=None, dtype=np.float64, ndmin=2)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{context}: invalid numeric table: {exc}') from exc
    if array.shape[1] != columns:
        raise ValueError(f'{context}: expected {columns} columns, found {array.shape[1]}')
    if not np.isfinite(array).all():
        raise ValueError(f'{context}: non-finite numeric value')
    return array


def _xy(lines, name):
    meta = _headers(lines)
    start = next((i for i, line in enumerate(lines) if line.split('\t')[0].strip().startswith('R.Time')), None)
    if start is None:
        raise ValueError(f'{name}: missing time/intensity header')
    array = _numeric_rows(lines[start + 1:], 2, name)
    _count(meta, '# of Points', len(array), name)
    _increasing(array[:, 0], name)
    return meta, array[:, 0], array[:, 1]


def _intensity_scaling(meta, version, *, pda=False):
    declared = meta.get('Intensity Units', '').strip()
    unit = declared.lower().replace('μ', 'u').replace('µ', 'u')
    multiplier = _number(meta.get('Intensity Multiplier', '1'), 'Intensity Multiplier')
    if multiplier <= 0:
        raise ValueError('Intensity Multiplier must be positive')
    if unit == 'au':
        factor, basis = 1000 * multiplier, 'declared AU converted to mAU'
    elif unit == 'uau':
        factor, basis = .001 * multiplier, 'declared micro-AU converted to mAU'
    elif (unit == 'mau' or (pda and not unit)) and version == '5.141':
        factor, basis = .001 * multiplier, 'LabSolutions 5.141 PDA ASCII micro-AU profile; verified against paired ANDI CDF'
    else:
        raise ValueError(f'Unverified LabSolutions {version} intensity unit/profile: {declared or "missing"}')
    return {'factor_to_mau': factor, 'declared_unit': declared or None,
            'declared_multiplier': multiplier, 'output_unit': 'mAU', 'basis': basis}


def _peak_table(lines, name):
    meta = _headers(lines)
    start = next((i for i, line in enumerate(lines) if line.startswith('Peak#\t')), None)
    records = []
    if start is not None:
        columns = [x.strip() for x in lines[start].split('\t')]
        for line in lines[start + 1:]:
            parts = line.split('\t')
            if len(parts) != len(columns):
                raise ValueError(f'{name}: peak table column count mismatch')
            record = {}
            for key, value in zip(columns, parts):
                value = value.strip()
                # Labels and identifiers remain strings; numeric results retain source units.
                if value and key not in ('Name', 'Mark', 'ID#'):
                    value = _number(value, name)
                record[key] = value
            records.append(record)
    _count(meta, '# of Peaks', len(records), name)
    return records


def _pda(lines, version):
    name = 'PDA 3D'
    meta = _headers(lines)
    start = next((i for i, line in enumerate(lines) if line.split('\t')[0].strip().startswith('R.Time')), None)
    if start is None or len(lines) <= start + 2:
        raise ValueError('PDA 3D: missing wavelength axis or matrix')
    wavelength_fields = lines[start + 1].split('\t')
    if wavelength_fields[0].strip():
        raise ValueError('PDA 3D: missing wavelength axis label cell')
    raw_wavelength = np.asarray([_number(v, name) for v in wavelength_fields[1:]])
    # LabSolutions writes hundredths of nm, independently of the integer range labels.
    wavelength = raw_wavelength * .01
    _count(meta, '# of Wavelength Axis Points', len(wavelength), name)
    _increasing(wavelength, 'PDA wavelength')
    if np.any((wavelength < 100) | (wavelength > 2000)):
        raise ValueError('PDA 3D: unrecognized wavelength encoding')
    matrix = _numeric_rows(lines[start + 2:], len(wavelength) + 1, name)
    _count(meta, '# of Time Axis Points', len(matrix), name)
    _increasing(matrix[:, 0], 'PDA time')
    scale = _intensity_scaling(meta, version, pda=True)
    # Immutable contiguous arrays retain every measured value without millions
    # of boxed Python floats. The checksum can be reused by provenance capture.
    arrays = {'time_min': matrix[:, 0].copy(), 'wavelength_nm': wavelength,
              'absorbance_mau': matrix[:, 1:] * scale['factor_to_mau']}
    digest = hashlib.sha256()
    for values in arrays.values():
        digest.update(values.astype('<f8', copy=False).tobytes())
        values.setflags(write=False)
    return {**arrays, 'data_sha256': digest.hexdigest(),
            'intensity_scaling': scale,
            'wavelength_scaling': {'factor_to_nm': .01, 'basis': 'LabSolutions PDA ASCII hundredths of nm'},
            'source_metadata': meta, 'source_section': name}


def _pda_summary(pda):
    """Detector scan range (as configured) and measured wavelength resolution of the 3D matrix."""
    source, axis = pda['source_metadata'], np.asarray(pda['wavelength_nm'])
    summary = {'wavelength_min_nm': _optional_number(source.get('Start Wavelength(nm)')),
               'wavelength_max_nm': _optional_number(source.get('End Wavelength(nm)'))}
    if summary['wavelength_min_nm'] is None or summary['wavelength_max_nm'] is None:
        summary.update(wavelength_min_nm=round(float(axis[0]), 2), wavelength_max_nm=round(float(axis[-1]), 2))
    if len(axis) > 1:
        summary['wavelength_resolution_nm'] = round(float(np.median(np.diff(axis))), 2)
    summary['wavelength_points'] = len(axis)
    return summary


class ShimadzuASCIIPreset(FormatPreset):
    name = 'shimadzu_ascii'
    extensions = {'txt', 'asc'}
    priority = 95
    strict = True  # Recognized malformed scientific exports must not become heuristic tables.

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        if head_bytes.startswith((b'\xff\xfe', b'\xfe\xff')):
            text = head_bytes.decode('utf-16', errors='ignore')
        else:
            text = '\n'.join(head_lines).lstrip('\ufeff')
        return '[Header]' in text and bool(re.search(r'^Application Name\s+LabSolutions\s*$', text, re.MULTILINE))

    def parse(self, path: str) -> dict:
        sections = _read_sections(path)
        source_meta = {name: _headers(lines) for name, lines in sections.items()}
        header = source_meta.get('Header', {})
        if header.get('Application Name') != 'LabSolutions':
            raise ValueError('Not a LabSolutions ASCII export')
        version = header.get('Version', '')
        sample = source_meta.get('Sample Information', {})
        metadata = _curated_metadata(source_meta, version)
        metadata.update(instrument_peaks={}, instrument_status={})
        channels = []
        for name, lines in sections.items():
            match = re.fullmatch(r'PDA Multi Chromatogram\((.+)\)', name)
            if match:
                channel = match.group(1)
                fields, time, values = _xy(lines, name)
                wavelength = _number(fields.get('Wavelength(nm)'), name)
                scaling = _intensity_scaling(fields, version)
                channel_meta = {'detector_channel': channel, 'wavelength_nm': wavelength}
                if fields.get('Bandwidth(nm)'):
                    channel_meta['bandwidth_nm'] = _number(fields['Bandwidth(nm)'], name)
                channel_meta.update(_acquisition_extent(fields, time))
                channel_meta.update(intensity_scaling=scaling, source_section=name)
                channels.append({'name': f'PDA {wavelength:g} nm ({channel})',
                                 'data': pd.DataFrame({'Time (min)': time, 'Absorbance (mAU)': values * scaling['factor_to_mau']}),
                                 'column_roles': dict(_ROLES), 'metadata': channel_meta})
            elif name.startswith('Peak Table(') and name.endswith(')'):
                metadata['instrument_peaks'][name[11:-1]] = _peak_table(lines, name)
            elif name.startswith('LC Status Trace(') and name.endswith(')'):
                fields, time, values = _xy(lines, name)
                factor = _number(fields.get('Intensity Multiplier', '1'), name)
                metadata['instrument_status'][name[16:-1]] = {
                    'time_min': time.tolist(), 'values': (values * factor).tolist(),
                    'unit': fields.get('Intensity Units', ''), 'multiplier': factor,
                    'source_metadata': fields}
        if 'PDA 3D' in sections:
            metadata['pda'] = _pda(sections['PDA 3D'], version)
        if not channels and 'pda' in metadata:
            pda = metadata['pda']
            index = int(np.argmin(abs(np.asarray(pda['wavelength_nm']) - 254)))
            wavelength = pda['wavelength_nm'][index]
            channels.append({'name': f'PDA {wavelength:g} nm',
                             'data': pd.DataFrame({'Time (min)': pda['time_min'], 'Absorbance (mAU)': np.asarray(pda['absorbance_mau'])[:, index]}),
                             'column_roles': dict(_ROLES),
                             'metadata': {'detector_channel': 'PDA', 'wavelength_nm': wavelength,
                                          **_acquisition_extent(pda['source_metadata'], pda['time_min']),
                                          'derived_from': 'PDA 3D', 'intensity_scaling': pda['intensity_scaling']}})
        if not channels:
            raise ValueError('LabSolutions export contains no supported chromatogram or PDA data')
        metadata.update(channels[0]['metadata'])
        if 'pda' in metadata:
            metadata.update(_pda_summary(metadata['pda']))
        metadata['channels'] = [
            {k: v for k, v in (('channel', c['metadata']['detector_channel']),
                               ('wavelength_nm', float(c['metadata']['wavelength_nm'])),
                               ('bandwidth_nm', c['metadata'].get('bandwidth_nm'))) if v is not None}
            for c in channels]
        metadata['chromatogram_channels'] = channels
        metadata['raw_sections'] = source_meta  # full headers of every section; not for display
        return {'data': channels[0]['data'], 'column_roles': dict(_ROLES), 'plot_hint': PlotHint.LINE,
                'source_category': SourceCategory.CHROMATOGRAM,
                'sample_name': sample.get('Sample Name') or Path(path).stem, 'metadata': metadata}
