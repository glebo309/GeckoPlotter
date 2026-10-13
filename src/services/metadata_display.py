"""Group imported file metadata into readable (group, label, value) rows for the Metadata panel.

Pure functions (no Dash): the panel renders whatever ``group_metadata`` returns. Known keys get a
fixed group, label and unit; raw/internal keys are hidden; anything unrecognised and simple enough
to print falls into an "Other" group so no curated information from other formats is lost.
"""
from __future__ import annotations

import ntpath
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

GROUP_ORDER = ('Sample', 'Acquisition', 'Instrument', 'Method', 'Gradient', 'Detector', 'Channels', 'Instrument data', 'Other')

# Raw dumps, provenance helpers and ids that only other code needs.
HIDDEN_KEYS = frozenset({
    'raw_sections', 'source_sections', 'intensity_scaling', 'source_section', 'derived_from',
    'display_name', 'auto_x', 'auto_y', 'file_name', 'file_type', 'file_type_detail',
    'parent_bundle_id', 'parent_bundle_name', 'component_role', 'source_file_id', 'pda_source_id',
    'chromatogram_channels', 'mass_spectral_data', 'bundle_type',
})

Rows = List[Tuple[str, str]]


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def fmt_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if number != number or number in (float('inf'), float('-inf')):
        return str(value)
    return f'{int(number):,}' if number.is_integer() and abs(number) < 1e15 else f'{number:.6g}'


def _with_unit(unit: str) -> Callable[[Any], str]:
    def build(value):
        if isinstance(value, str) and re.fullmatch(r'-?\d+,\d+', value.strip()):
            value = value.strip().replace(',', '.')  # European decimal comma (Chromeleon exports)
        return f'{fmt_number(value)} {unit}'
    return build


def fmt_datetime(value: Any) -> str:
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return text


def _file_name(value: Any) -> str:
    text = str(value).strip()
    return text if '://' in text else (ntpath.basename(text) or text)


def _range(low: str, high: str, unit: str) -> Callable[[Dict[str, Any]], Optional[str]]:
    def build(meta):
        if _present(meta.get(low)) and _present(meta.get(high)):
            return f'{fmt_number(meta[low])} – {fmt_number(meta[high])} {unit}'
        return None
    return build


def _injected(meta):
    parts = [str(meta[k]).strip() for k in ('injection_date', 'injection_time') if _present(meta.get(k))]
    return ' '.join(parts) or None


def _summarise(key: str) -> Callable[[Dict[str, Any]], Optional[str]]:
    def build(meta):
        return measurement_summary(key, meta.get(key))
    return build


def _single(key: str, fmt: Callable[[Any], str] = lambda v: str(v).strip()):
    return lambda meta: fmt(meta[key]) if _present(meta.get(key)) else None


def _channel_text(channel: Dict[str, Any]) -> str:
    parts = []
    if _present(channel.get('wavelength_nm')):
        parts.append(f"{fmt_number(channel['wavelength_nm'])} nm")
    if _present(channel.get('bandwidth_nm')):
        parts.append(f"bandwidth {fmt_number(channel['bandwidth_nm'])} nm")
    return ', '.join(parts)


def measurement_summary(key: str, value: Any) -> Optional[str]:
    """One-line description of bulky measurement containers (never the numbers themselves)."""
    if not isinstance(value, dict):
        return None
    if key == 'pda':
        return f"{len(value.get('time_min', []))} time points × {len(value.get('wavelength_nm', []))} wavelengths; absorbance in mAU"
    if key == 'instrument_status':
        return '; '.join(value.keys())
    if key == 'instrument_peaks':
        return '; '.join(f'{channel}: {len(rows)} reported peaks' for channel, rows in value.items())
    return None


# (group, label, keys consumed, builder(meta) -> text | None). Order inside a group is display order.
_SPEC = [
    ('Sample', 'Name', ('sample_name',), _single('sample_name')),
    ('Sample', 'Sample ID', ('sample_id',), _single('sample_id')),
    ('Sample', 'Sample type', ('sample_type',), _single('sample_type')),
    ('Sample', 'Level', ('level',), _single('level', fmt_number)),
    ('Sample', 'Vial', ('vial',), _single('vial', fmt_number)),
    ('Sample', 'Injection', ('injection',), _single('injection')),
    ('Sample', 'Injection number', ('injection_number',), _single('injection_number')),
    ('Sample', 'Position', ('position',), _single('position')),
    ('Sample', 'Injection volume', ('injection_volume_ul',), _single('injection_volume_ul', _with_unit('µL'))),
    ('Sample', 'Injection volume', ('injection_volume_µl',), _single('injection_volume_µl', _with_unit('µL'))),
    ('Sample', 'Injection volume', ('injection_volume_μl',), _single('injection_volume_μl', _with_unit('µL'))),
    ('Sample', 'Sample amount', ('sample_amount',), _single('sample_amount', fmt_number)),
    ('Sample', 'Weight', ('weight',), _single('weight')),
    ('Sample', 'Dilution factor', ('dilution_factor',), _single('dilution_factor', fmt_number)),
    ('Sample', 'Operator', ('operator',), _single('operator')),
    ('Sample', 'Type', ('type',), _single('type')),

    ('Acquisition', 'Acquired', ('acquired', 'acquisition_time'),
     lambda m: next((fmt_datetime(m[k]) for k in ('acquired', 'acquisition_time') if _present(m.get(k))), None)),
    ('Acquisition', 'Injected', ('injection_date', 'injection_time'), _injected),
    ('Acquisition', 'Exported', ('exported',), _single('exported', fmt_datetime)),
    ('Acquisition', 'Status', ('status',), _single('status')),
    ('Acquisition', 'Time range', ('time_range',), _single('time_range')),
    ('Acquisition', 'Time range', ('time_start_min', 'time_end_min'), _range('time_start_min', 'time_end_min', 'min')),
    ('Acquisition', 'Time range', ('time_min_min', 'time_max_min'), _range('time_min_min', 'time_max_min', 'min')),
    ('Acquisition', 'Sampling interval', ('sampling_interval_ms',), _single('sampling_interval_ms', _with_unit('ms'))),
    ('Acquisition', 'Points', ('data_points',), _single('data_points', fmt_number)),

    ('Instrument', 'Instrument', ('instrument', 'instrument_name'),
     lambda m: next((str(m[k]).strip() for k in ('instrument', 'instrument_name')
                     if _present(m.get(k)) and not isinstance(m[k], (dict, list))), None)),
    ('Instrument', 'Manufacturer', ('manufacturer',), _single('manufacturer')),
    ('Instrument', 'Software', ('software', 'software_version'),
     lambda m: ' '.join(str(m[k]).strip() for k in ('software', 'software_version') if _present(m.get(k))) or None),
    ('Instrument', 'Data system', ('exporting_data_system',), _single('exporting_data_system')),
    ('Instrument', 'Driver', ('driver_name',), _single('driver_name')),

    ('Method', 'Data file', ('data_file',), _single('data_file', _file_name)),
    ('Method', 'Method file', ('method_file',), _single('method_file', _file_name)),
    ('Method', 'Batch file', ('batch_file',), _single('batch_file', _file_name)),
    ('Method', 'Processing method', ('processing_method',), _single('processing_method')),
    ('Method', 'Instrument method', ('instrument_method',), _single('instrument_method')),
    ('Method', 'Data vault', ('data_vault',), _single('data_vault')),
    ('Method', 'Source path', ('file_path',), _single('file_path')),

    ('Detector', 'Detector', ('detector',), _single('detector')),
    ('Detector', 'Wavelength range', ('wavelength_min_nm', 'wavelength_max_nm'),
     _range('wavelength_min_nm', 'wavelength_max_nm', 'nm')),
    ('Detector', 'Wavelength resolution', ('wavelength_resolution_nm',), _single('wavelength_resolution_nm', _with_unit('nm'))),
    ('Detector', 'Wavelength points', ('wavelength_points',), _single('wavelength_points', fmt_number)),

    ('Channels', 'Channel', ('detector_channel', 'channel'),
     lambda m: next((str(m[k]).strip() for k in ('detector_channel', 'channel') if _present(m.get(k))), None)),
    ('Channels', 'Channel type', ('channel_type',), _single('channel_type')),
    ('Channels', 'Wavelength', ('wavelength_nm',), _single('wavelength_nm', _with_unit('nm'))),
    ('Channels', 'Bandwidth', ('bandwidth_nm',), _single('bandwidth_nm', _with_unit('nm'))),
    ('Channels', 'Signal', ('signal_quantity',), _single('signal_quantity')),
    ('Channels', 'Signal unit', ('signal_unit',), _single('signal_unit')),
    ('Channels', 'Signal info', ('signal_info',), _single('signal_info')),
    ('Channels', 'Value range', ('value_range',), _single('value_range')),

    ('Instrument data', '3D PDA matrix', ('pda',), _summarise('pda')),
    ('Instrument data', 'Status traces', ('instrument_status',), _summarise('instrument_status')),
    ('Instrument data', 'Instrument peak tables', ('instrument_peaks',), _summarise('instrument_peaks')),
]

# Chromeleon step statistics, kept compact: min/avg/max step in one row.
_SPEC.append(('Acquisition', 'Step (min / avg / max)', ('min_step_s', 'average_step_s', 'max_step_s'),
              lambda m: ' / '.join(str(m[k]).strip() for k in ('min_step_s', 'average_step_s', 'max_step_s'))
              + ' s' if all(_present(m.get(k)) for k in ('min_step_s', 'average_step_s', 'max_step_s')) else None))
# Signal range columns only make sense next to each other.
_SPEC.append(('Channels', 'Signal min / max', ('signal_min', 'signal_max'),
              lambda m: f"{m['signal_min']} / {m['signal_max']}"
              if _present(m.get('signal_min')) and _present(m.get('signal_max')) else None))

_KNOWN_KEYS = frozenset(k for _, _, keys, _ in _SPEC for k in keys) | {'channels', 'method_details'}


def _label_for(key: str) -> str:
    return key.replace('_', ' ').strip().capitalize()


def _printable(value: Any) -> Optional[str]:
    """Text for a leftover value, or None when it is bulky/structured and should stay out of the panel."""
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, (int, float)):
        return fmt_number(value)
    if isinstance(value, str):
        text = value.strip()
        return None if not text or len(text) > 300 else text
    if isinstance(value, dict):
        if len(value) > 12 or not all(isinstance(v, (str, int, float, bool)) and _present(v) for v in value.values()):
            return None
        return '; '.join(f'{k}: {v}' for k, v in value.items())
    if isinstance(value, (list, tuple)) and len(value) <= 8 and all(isinstance(v, (str, int, float)) for v in value):
        return ', '.join(str(v) for v in value) or None
    return None


def group_metadata(metadata: Optional[Dict[str, Any]]) -> List[Tuple[str, Rows]]:
    """Return ``[(group, [(label, text), ...]), ...]`` for the non-empty groups, in display order."""
    meta = {str(k).lstrip('﻿'): v for k, v in (metadata or {}).items()}
    groups: Dict[str, Rows] = {name: [] for name in GROUP_ORDER}
    seen = set()

    def add(group, label, text):
        if text and (group, label) not in seen:
            seen.add((group, label))
            groups[group].append((label, text))

    # A multi-channel export lists every channel; the single-channel rows would then be redundant.
    channels = meta.get('channels')
    listed = [c for c in channels if isinstance(c, dict)] if isinstance(channels, (list, tuple)) else []
    for group, label, keys, build in _SPEC:
        if group == 'Channels' and listed and keys[0] in ('detector_channel', 'wavelength_nm', 'bandwidth_nm'):
            continue
        try:
            add(group, label, build(meta))
        except (TypeError, ValueError, KeyError):
            continue
    if listed:
        rows = [(str(c.get('channel') or f'Channel {i}'), _channel_text(c)) for i, c in enumerate(listed, 1)]
        groups['Channels'] = [(label, text) for label, text in rows if text] + groups['Channels']

    details = meta.get('method_details')
    if isinstance(details, (list, tuple)):
        for row in details:
            if isinstance(row, dict) and row.get('group') in groups:
                add(row['group'], str(row.get('name', '')), str(row.get('value', '')))

    for key, value in meta.items():
        if key in HIDDEN_KEYS or key in _KNOWN_KEYS or key.startswith('_'):
            continue
        add('Other', _label_for(key), _printable(value))
    return [(name, rows) for name, rows in ((n, groups[n]) for n in GROUP_ORDER) if rows]
