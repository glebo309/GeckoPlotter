"""Read the instrument method stored inside Shimadzu LabSolutions files.

``.lcm`` (method) and ``.lcd`` (data) files are OLE2 compound files. The method lives in the same XML streams in
both: ``GUMM_Information/ShimadzuLC.1/GUC.1.METHOD`` (pump, oven, sampler, mobile phases) and
``GUMM_Information/ShimadzuPDA.1/PDA.1.METHOD`` (detector). A ``.lcd`` carries the method *as it was run*.

A method is attached to a sample in two ways, both through values stored in the files:

* a ``.lcm`` by the method file name the sample's export lists (``Method File``); the check row then compares the
  method's last-saved time with the run's acquisition time, because a method edited after a run is not what ran;
* a ``.lcd`` by the data file's created and last-saved time, which the export and the ``.lcd`` both record to the
  second (UTC in the file, local time in the export: a whole number of hours apart).

Only what is verifiably present is returned.
"""
from __future__ import annotations

import hashlib
import io
import re
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

LC_STREAM = 'GUMM_Information/ShimadzuLC.1/GUC.1.METHOD'
PDA_STREAM = 'GUMM_Information/ShimadzuPDA.1/PDA.1.METHOD'
LC_CONFIG_STREAM = 'GUMM_Information/ShimadzuLC.1/GUC.1.CONFIG'
PDA_CONFIG_STREAM = 'GUMM_Information/ShimadzuPDA.1/PDA.1.CONFIG'
KGF_CM2_TO_BAR = 0.980665
MAX_FILE_BYTES = 400_000_000
MAX_STREAM_BYTES = 8_000_000          # the real streams are about 200 kB

# Pump time program codes (TMPGcode), confirmed against the gradient encoded in the method name.
CODE_FLOW, CODE_B_PERCENT = '4', '5'

_UPD = re.compile(r'<UPD ID="([^"]+)"><Val>([^<]*)</Val><Type>(\d+)')
_UNIT = re.compile(r'<UP Name="([A-Z]+)" UI="(\d+)" LI="\d+">(.*?)</UP>', re.S)
_PROGRAM = re.compile(r'<TP Name="LC" UI="1" LI="1" UN="PUMP" PgN="PUMP\$PROG">(.*?)</TP>', re.S)
_STEP = re.compile(r'<TPLD Time="([0-9A-Fa-f]{8})"[^>]*>(.*?)</TPLD>', re.S)
_STEP_ITEM = re.compile(r'<TPD ID="([^"]+)"><Val>([^<]*)</Val>')


class MethodFormatError(ValueError):
    """The file is not a readable LabSolutions method or data file."""


def _float(hex_value: str) -> Optional[float]:
    try:
        value = struct.unpack('<f', bytes.fromhex(hex_value))[0]
    except (ValueError, struct.error):
        return None
    return round(value, 4) if value == value else None       # NaN -> None


def _values(xml: str) -> Dict[str, Any]:
    """Parameter id -> value, with the instrument's little-endian float32 fields decoded (type 4)."""
    out: Dict[str, Any] = {}
    for key, raw, kind in _UPD.findall(xml):
        out[key] = _float(raw) if kind == '4' else raw
    return out


def _units(xml: str) -> Dict[str, Dict[str, Any]]:
    """Unit name (PUMP, OVEN, DET, SIL, MOBILEPHASE, ...) -> parameters of its first (active) instance."""
    units: Dict[str, Dict[str, Any]] = {}
    for name, _index, body in _UNIT.findall(xml):
        units.setdefault(name, _values(body))
    return units


def _time_program(xml: str) -> List[Dict[str, float]]:
    match = _PROGRAM.search(xml)
    if not match:
        return []
    steps: Dict[float, Dict[str, float]] = {}
    for time_hex, body in _STEP.findall(match.group(1)):
        time = _float(time_hex)
        if time is None:
            continue
        items = dict(_STEP_ITEM.findall(body))
        code, data = items.get('TMPGcode'), _float(items.get('TMPGdata', ''))
        if data is None:
            continue
        row = steps.setdefault(time, {'time_min': time})
        if code == CODE_FLOW:
            row['flow_ml_min'] = data
        elif code == CODE_B_PERCENT:
            row['b_percent'] = data
    return [steps[t] for t in sorted(steps) if len(steps[t]) > 1]


def _filetime(low: str, high: str) -> Optional[str]:
    try:
        ticks = (int(high) << 32) | (int(low) & 0xFFFFFFFF)
        return (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)).isoformat(timespec='seconds')
    except (ValueError, OverflowError):
        return None


def _hex_text(value: str) -> str:
    value = value.replace('@StoX@', '')
    try:
        return bytes.fromhex(value).decode('latin-1').strip()
    except ValueError:
        return value


def _file_property(raw: bytes) -> Dict[str, Any]:
    text = raw.decode('utf-8', errors='replace')
    tags = dict(re.findall(r'<(\w+)>([^<]*)</\1>', text))
    out: Dict[str, Any] = {}
    if tags.get('szGeneratedBy'):
        out['generated_by'] = _hex_text(tags['szGeneratedBy'])
    if tags.get('szModifiedBy'):
        out['modified_by'] = _hex_text(tags['szModifiedBy'])
    if 'dwLowGeneratedDateTime' in tags:
        out['generated_utc'] = _filetime(tags['dwLowGeneratedDateTime'], tags.get('dwHighGeneratedDateTime', '0'))
    if 'dwLowModifiedDateTime' in tags:
        out['modified_utc'] = _filetime(tags['dwLowModifiedDateTime'], tags.get('dwHighModifiedDateTime', '0'))
    if tags.get('nModifiedCount', '').isdigit():
        out['times_modified'] = int(tags['nModifiedCount'])
    if tags.get('szVersion'):
        out['software_version'] = _hex_text(tags['szVersion'])
    return {k: v for k, v in out.items() if v not in (None, '')}


def _read_stream(ole, name: str) -> Optional[bytes]:
    if not ole.exists(name):
        return None
    if ole.get_size(name) > MAX_STREAM_BYTES:
        raise MethodFormatError(f'Stream {name!r} is unexpectedly large; the file was not read.')
    return ole.openstream(name).read()


def _utf16(raw: bytes) -> str:
    return raw.decode('utf-16le', errors='replace')


_DEVICE_ROLES = (('LC-', 'pump'), ('SIL-', 'autosampler'), ('CTO-', 'column_oven'), ('SPD-', 'detector'), ('CBM-', 'controller'))
_OEM = re.compile(r'<UPD ID="(?:OEMName|DeviceProductName)"><Val>([^<]+)')


def _devices(*configs: Optional[bytes]) -> Dict[str, str]:
    """Model names of the modules the method was written for, by role (pump, autosampler, ...)."""
    found: Dict[str, str] = {}
    for raw in configs:
        if not raw:
            continue
        for model in _OEM.findall(_utf16(raw)):
            model = model.strip()
            for prefix, role in _DEVICE_ROLES:
                if model.startswith(prefix):
                    found.setdefault(role, model)
    return found


def read_method(source: Union[str, Path, bytes], file_name: str = '') -> Dict[str, Any]:
    """Method settings from a ``.lcm`` or ``.lcd``. Raises ``MethodFormatError`` when there are none."""
    try:
        import olefile
    except ImportError as exc:                                # pragma: no cover - dependency is in requirements.txt
        raise MethodFormatError('Reading LabSolutions files needs the "olefile" package (pip install olefile).') from exc
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        path = Path(source)
        file_name = file_name or path.name
        if path.stat().st_size > MAX_FILE_BYTES:
            raise MethodFormatError('This file is too large to be a LabSolutions method or data file.')
        data = path.read_bytes()
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except OSError as exc:        # olefile.NotOleFileError is an OSError
        raise MethodFormatError('This is not a LabSolutions compound file.') from exc
    with ole:
        lc_raw, pda_raw = _read_stream(ole, LC_STREAM), _read_stream(ole, PDA_STREAM)
        devices = _devices(_read_stream(ole, LC_CONFIG_STREAM), _read_stream(ole, PDA_CONFIG_STREAM))
        if lc_raw is None and pda_raw is None:
            raise MethodFormatError('No instrument method found in this file (is it a batch .lcb?).')
        run_props = {}
        raw_run = _read_stream(ole, 'File Property') if file_name.lower().endswith('.lcd') else None
        if raw_run:
            run_props = _file_property(raw_run)
        file_props = {}
        for stream in ('Method File Property', 'File Property'):          # .lcd keeps the method's own record first
            raw = _read_stream(ole, stream)
            if raw:
                file_props = _file_property(raw)
                if file_props:
                    break

    result: Dict[str, Any] = {'file_name': file_name, 'sha256': hashlib.sha256(data).hexdigest(),
                              'kind': Path(file_name).suffix.lower().lstrip('.') or 'unknown',
                              'file_properties': file_props}
    if devices:
        result['devices'] = devices
    if run_props.get('generated_utc') and run_props.get('modified_utc'):
        result['run_identity'] = {'generated_utc': run_props['generated_utc'], 'modified_utc': run_props['modified_utc']}
    if lc_raw:
        xml = _utf16(lc_raw)
        units = _units(xml)
        pump, oven, sampler, phases = (units.get(k, {}) for k in ('PUMP', 'OVEN', 'SIL', 'MOBILEPHASE'))
        result['pump_program'] = _time_program(xml)
        result['mobile_phase'] = {side: phases.get(key) or pump.get(key2)
                                  for side, key, key2 in (('A', 'PumpA_MobilePhaseName#1A', 'PumpA_MobilePhaseName#1A'),
                                                          ('B', 'PumpA_MobilePhaseName#2A', 'PumpA_MobilePhaseName#2A'))
                                  if (phases.get(key) or pump.get(key2)) not in (None, '', '?')}
        if isinstance(pump.get('PumpA_PMax'), float):
            result['pressure_limit_bar'] = round(pump['PumpA_PMax'] * KGF_CM2_TO_BAR)
        if isinstance(oven.get('OVEN$ovent'), float):
            result['column_oven'] = {'temperature_c': oven['OVEN$ovent'], 'enabled': oven.get('OVEN$use') == 1.0}
        sampler_info = {'cooler_temperature_c': sampler.get('SIL$cltemp'), 'rinse_volume_ul': sampler.get('SIL$rnsvol'),
                        'rinse_speed': sampler.get('SIL$rnsspd'), 'sampling_speed': sampler.get('SIL$smpspd')}
        result['autosampler'] = {k: v for k, v in sampler_info.items() if isinstance(v, float)}
    if pda_raw:
        # Per-channel wavelengths are not reported: the method's channel table can differ from what a run
        # recorded (the data file's own header is authoritative for those).
        values = _values(_utf16(pda_raw))
        result['pda'] = {key: values.get(src) for key, src in (('cell_temperature_c', 'CompositeCellTemp'),
                                                                 ('slit', 'Slit'), ('lamp_mode', 'LampMd'))
                         if values.get(src) not in (None, '')}
    return result


def describe_method(method: Dict[str, Any], acquired: Any = None) -> List[Dict[str, str]]:
    """Display rows ``{group, name, value}`` for the Metadata tab."""
    rows: List[Dict[str, str]] = []

    def add(group: str, name: str, value: Any) -> None:
        if value not in (None, '', [], {}):
            rows.append({'group': group, 'name': name, 'value': str(value)})

    add('Method', 'Method read from', method.get('file_name'))
    for step in method.get('pump_program', []):
        parts = []
        if 'b_percent' in step:
            parts.append(f"{step['b_percent']:g} % B")
        if 'flow_ml_min' in step:
            parts.append(f"{step['flow_ml_min']:g} mL/min")
        add('Gradient', f"{step['time_min']:g} min", ', '.join(parts))
    phases = method.get('mobile_phase', {})
    add('Method', 'Mobile phase A', phases.get('A'))
    add('Method', 'Mobile phase B', phases.get('B'))
    add('Method', 'Pressure limit', f"{method['pressure_limit_bar']} bar" if 'pressure_limit_bar' in method else None)
    oven = method.get('column_oven')
    if oven:
        add('Method', 'Column oven', f"{oven['temperature_c']:g} °C" + ('' if oven['enabled'] else ' (off)'))
    sampler = method.get('autosampler', {})
    add('Method', 'Autosampler cooler', f"{sampler['cooler_temperature_c']:g} °C" if 'cooler_temperature_c' in sampler else None)
    pda = method.get('pda', {})
    add('Detector', 'PDA cell temperature', f"{pda['cell_temperature_c']:g} °C" if pda.get('cell_temperature_c') else None)
    props = method.get('file_properties', {})
    if props.get('modified_utc'):
        stamp = props['modified_utc'][:16].replace('T', ' ')
        add('Method', 'Last modified', f"{stamp} by {props['modified_by']}" if props.get('modified_by') else stamp)
    add('Method', 'Times modified', props.get('times_modified'))
    add('Method', 'Check against this run', _check_text(method, acquired))
    return rows


METHOD_EXTENSIONS = ('.lcm',)           # an .lcd is a data file: it is read as data and brings its own method
MAX_UTC_OFFSET_HOURS = 3        # local time (CET/CEST and neighbours) minus the stored UTC


def is_method_upload(file_name: str) -> bool:
    return str(file_name or '').lower().endswith(METHOD_EXTENSIONS)


def _stamp(text: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text)).replace(tzinfo=None)
    except ValueError:
        return None


def _base_name(value: Any) -> str:
    return re.split(r'[\\/]', str(value or ''))[-1].strip().lower()


def belongs_to_run(method: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    """A ``.lcd`` method belongs to a sample when both record the same created and last-saved moments.

    The sample's export lists the data file's created and last-saved time; the ``.lcd`` stores the same two moments as
    UTC. They must agree to the second with one shared whole-hour offset.
    """
    identity = method.get('run_identity')
    if not identity:
        return False
    pairs = [(_stamp(metadata.get(key)), _stamp(identity.get(utc_key)))
             for key, utc_key in (('file_generated', 'generated_utc'), ('file_modified', 'modified_utc'))]
    if any(local is None or utc is None for local, utc in pairs):
        return False
    offsets = {(local - utc).total_seconds() for local, utc in pairs}
    if len(offsets) != 1:
        return False
    seconds = offsets.pop()
    return seconds % 3600 == 0 and 0 <= seconds / 3600 <= MAX_UTC_OFFSET_HOURS


def belongs_by_name(method: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    """A ``.lcm`` method belongs to a sample whose export names it as its ``Method File``."""
    return (not method.get('run_identity') and bool(method.get('file_name'))
            and _base_name(metadata.get('method_file')) == _base_name(method['file_name']))


def _check_text(method: Dict[str, Any], acquired: Any) -> Optional[str]:
    """Was the method already saved when this run was acquired? Only a definite answer is given."""
    saved = _stamp((method.get('file_properties') or {}).get('modified_utc'))
    ran = _stamp(acquired)
    if method.get('run_identity') or saved is None or ran is None:
        return 'Read from this run\'s own data file' if method.get('run_identity') else None
    hours = (ran - saved).total_seconds() / 3600       # the run is local time, the save UTC: allow up to 3 h
    when = saved.strftime('%Y-%m-%d %H:%M')
    if hours > MAX_UTC_OFFSET_HOURS:
        return f'Method last saved {when} UTC, before this run: unchanged since'
    if hours < 0:
        return f'Method was saved {when} UTC, after this run: it may not be what was run'
    return f'Method saved {when} UTC, close to this run: check it is the one used'


def method_key(method: Dict[str, Any]) -> str:
    identity = method.get('run_identity')
    if identity:
        return f"lcd:{identity.get('generated_utc')}|{identity.get('modified_utc')}"
    return f"lcm:{_base_name(method.get('file_name'))}"


def register_method(store, method: Dict[str, Any], raw: Optional[bytes] = None) -> int:
    """Remember a parsed method (and the original file bytes) and attach it to the samples it belongs to."""
    key = method_key(method)
    store.instrument_methods[key] = method
    if raw is not None:
        store.instrument_method_files[key] = raw
    return apply_methods(store)


def apply_methods(store) -> int:
    """Copy the display rows of each registered method into the components it belongs to."""
    if not store.instrument_methods:
        return 0
    matched = set()
    # ``loaded_data`` is rebuilt from the components on every access, so the method goes on the components.
    for bundle in list(store._bundles.values()):
        for component in bundle.component_list:
            metadata = component.metadata
            if not isinstance(metadata, dict):
                continue
            for key, method in store.instrument_methods.items():
                if belongs_to_run(method, metadata) or belongs_by_name(method, metadata):
                    metadata['method_key'] = key
                    metadata['method_details'] = describe_method(method, metadata.get('acquired'))
                    matched.add(component.component_id)
                    break
    return len(matched)


GRADIENT_AXIS = 'yaxis9'


def gradient_points(method: Dict[str, Any]) -> List[tuple]:
    """``(time_min, percent_B)`` of the pump time program, in order."""
    return [(step['time_min'], step['b_percent']) for step in method.get('pump_program', []) if 'b_percent' in step]


def add_gradient_overlay(figure, store, entries, dwell_volume_ul: Optional[float] = None) -> int:
    """Draw each distinct method's %B gradient on its own right-hand axis. Returns how many were drawn.

    ``entries`` are the ``(name, file_data)`` pairs shown in the plot; a gradient is drawn once per method and
    labelled with the samples that used it. Only the time program's own points are drawn (no invented start).
    """
    import plotly.graph_objects as go
    users: Dict[str, List[str]] = {}
    signatures: Dict[tuple, str] = {}     # runs of the same gradient (each .lcd brings its own copy) draw one line
    for name, data in entries:
        key = (data.get('metadata') or {}).get('method_key')
        if key in store.instrument_methods and len(gradient_points(store.instrument_methods[key])) > 1:
            method = store.instrument_methods[key]
            signature = (tuple(gradient_points(method)),
                         tuple(sorted({s['flow_ml_min'] for s in method.get('pump_program', []) if 'flow_ml_min' in s})))
            users.setdefault(signatures.setdefault(signature, key), []).append(name)
    if not users:
        return 0
    run_end = max((float((d.get('metadata') or {}).get('time_end_min') or 0) for _, d in entries), default=0.0)
    for index, (key, names) in enumerate(users.items()):
        times, percent = zip(*gradient_points(store.instrument_methods[key]))
        delay = 0.0
        flows = [s['flow_ml_min'] for s in store.instrument_methods[key].get('pump_program', []) if s.get('flow_ml_min')]
        if dwell_volume_ul and flows:       # the programmed composition reaches the column dwell/flow minutes later
            delay = round(dwell_volume_ul / 1000.0 / flows[0], 3)
            times = tuple(x + delay for x in times)
        if run_end > times[-1]:             # a time program holds its last value until the run ends
            times, percent = times + (run_end,), percent + (percent[-1],)
        label = ('LC gradient at the column inlet (% B)' if delay else 'LC gradient (% B)') if len(users) == 1 else f'LC gradient (% B): {names[0]}' + (' …' if len(names) > 1 else '')
        figure.add_trace(go.Scatter(
            x=list(times), y=list(percent), mode='lines', name=label, yaxis=GRADIENT_AXIS.replace('axis', ''),
            line=dict(color='#8a8a8a', width=1.5, dash='dot'), opacity=0.9, showlegend=True,
            hovertemplate='%{x:.2f} min: %{y:g} % B<extra></extra>',
            meta={'gecko_gradient': True, 'method_key': key}))
    figure.update_layout(**{GRADIENT_AXIS: dict(
        overlaying='y', side='right', range=[0, 105], showgrid=False, zeroline=False, rangemode='tozero',
        tickmode='array', tickvals=[0, 25, 50, 75, 100], automargin=True,
        title=dict(text='% B', standoff=6), tickfont=dict(color='#8a8a8a'), ticks='outside', anchor='x')})
    return len(users)


STATUS_OVERLAYS = ('Pump A Pressure', 'Pump A Degasser Pressure', 'Sample Cooler Temp.', 'Oven Temp.', 'Room Temp.',
                   'PDA Cell Temp.', 'PDA Polychromator Temp.', 'PDA Lamp Housing Temp.')


def add_status_overlay(figure, entries, trace_name: str) -> int:
    """Draw an instrument status trace (pressure, temperature ...) of each sample on the right-hand axis.

    The values come from the sample's own export (``LC Status Trace`` sections); each sample is drawn once, dotted,
    in the colour of its chromatogram. Returns how many traces were drawn.
    """
    import plotly.graph_objects as go
    colours = {}
    for trace in figure.data:
        meta = trace.meta if isinstance(trace.meta, dict) else {}
        if meta.get('file_id') and meta['file_id'] not in colours:
            colours[meta['file_id']] = getattr(trace.line, 'color', None)
    drawn, unit, seen = 0, '', set()
    for name, data in entries:
        metadata = data.get('metadata') or {}
        series = (metadata.get('instrument_status') or {}).get(trace_name)
        owner = metadata.get('parent_bundle_id') or name
        if not series or owner in seen:
            continue
        seen.add(owner)
        unit = series.get('unit') or unit
        figure.add_trace(go.Scatter(
            x=series['time_min'], y=series['values'], mode='lines', name=f'{name}: {trace_name}',
            yaxis=GRADIENT_AXIS.replace('axis', ''), showlegend=True, opacity=0.85,
            line=dict(color=colours.get((data.get('record') or {}).get('id')) or '#8a8a8a', width=1.5, dash='dot'),
            hovertemplate=f'%{{x:.2f}} min: %{{y:g}} {unit}<extra>{trace_name}</extra>',
            meta={'gecko_gradient': True, 'status_trace': trace_name}))
        drawn += 1
    if drawn:
        figure.update_layout(**{GRADIENT_AXIS: dict(
            overlaying='y', side='right', showgrid=False, zeroline=False, automargin=True, ticks='outside', anchor='x',
            title=dict(text=trace_name.rstrip('.') + (f' ({unit})' if unit else ''), standoff=6))})
    return drawn


# ---------------------------------------------------------------------------
# Journal-style methods paragraph
# ---------------------------------------------------------------------------

COLUMN_PLACEHOLDER = ('[column: not recorded in the method file; add manufacturer, stationary phase, '
                      'particle size and dimensions]')


STEP_MAX_MIN = 0.05      # a change faster than this is described as a step, not a gradient


def _g(value: float) -> str:
    return f'{value:g}'


def _gradient_sentence(method: Dict[str, Any]) -> str:
    steps = [s for s in method.get('pump_program', []) if 'b_percent' in s]
    if len(steps) < 2:
        return ''
    parts, index = [], 0
    while index < len(steps) - 1:
        first, second = steps[index], steps[index + 1]
        span = round(second['time_min'] - first['time_min'], 3)
        if second['b_percent'] == first['b_percent']:
            parts.append(f"a hold at {_g(first['b_percent'])}% B for {_g(span)} min")
        elif span < STEP_MAX_MIN:
            # An (almost) instantaneous change followed by a hold reads as one step.
            nxt = steps[index + 2] if index + 2 < len(steps) else None
            hold = round(nxt['time_min'] - second['time_min'], 3) if nxt and nxt['b_percent'] == second['b_percent'] else 0
            parts.append(f"a step to {_g(second['b_percent'])}% B held for {_g(round(span + hold, 3))} min")
            index += 2 if hold else 1
            continue
        else:
            verb = 'a linear gradient from' if second['b_percent'] > first['b_percent'] else 'a linear return from'
            parts.append(f"{verb} {_g(first['b_percent'])}% to {_g(second['b_percent'])}% B over {_g(span)} min")
        index += 1
    text = parts[0] + (', followed by ' + _join(parts[1:]) if len(parts) > 1 else '')
    flows = sorted({s['flow_ml_min'] for s in method['pump_program'] if 'flow_ml_min' in s})
    flow = (f" at a flow rate of {_g(flows[0])} mL min\u22121" if len(flows) == 1
            else f" at flow rates of {' to '.join(_g(f) for f in flows)} mL min\u22121 (see the method table)" if flows else '')
    return text[0].upper() + text[1:] + (',' if len(parts) > 1 else '') + ' was applied' + flow


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1] if items else ''


def method_paragraph(method: Dict[str, Any], samples: List[Dict[str, Any]], column: str = '',
                     dwell_volume_ul: Optional[float] = None) -> Dict[str, str]:
    """Heading and one methods paragraph for a method, using the metadata of the samples it was attached to."""
    devices = method.get('devices', {})
    instrument = next((s.get('instrument') for s in samples if s.get('instrument')), None)
    system = f"a {instrument} system" if instrument else 'a Shimadzu HPLC system'
    modules = [f"{devices[role]} {label}" for role, label in (('pump', 'pump'), ('autosampler', 'autosampler'),
                                                              ('column_oven', 'column oven')) if role in devices]
    sentences = [f"Samples were analyzed using {system}" + (f" ({_join(modules)})" if modules else '')
                 + f" on a {column.strip() or COLUMN_PLACEHOLDER}."]
    phases = method.get('mobile_phase', {})
    if phases.get('A') or phases.get('B'):
        names = [f"mobile phase {side} ({str(phases[side]).lower()})" for side in 'AB' if phases.get(side)]
        sentences.append(f"The solvents were {_join(names)}.")
    gradient = _gradient_sentence(method)
    if gradient:
        sentences.append(gradient + '.')
    oven = method.get('column_oven')
    if oven and oven.get('enabled'):
        sentences.append(f"The column was maintained at {_g(oven['temperature_c'])} \u00b0C.")
    if dwell_volume_ul and gradient:
        sentences.append(f"The pre-column dwell volume of the system was approximately {_g(dwell_volume_ul)} \u00b5L.")
    volumes = sorted({v for v in (s.get('injection_volume_ul') for s in samples) if isinstance(v, (int, float))})
    cooler = method.get('autosampler', {}).get('cooler_temperature_c')
    if volumes:
        sentences.append(f"A volume of {' to '.join(_g(v) for v in volumes)} \u00b5L was injected"
                         + (f" from an autosampler kept at {_g(cooler)} \u00b0C" if cooler else '') + '.')
    channels = sorted({(s['wavelength_nm'], s.get('bandwidth_nm')) for s in samples
                       if isinstance(s.get('wavelength_nm'), (int, float))})
    detector = devices.get('detector')
    if channels or detector:
        wavelengths = _join([_g(w) for w, _ in channels]) + (' nm' if channels else '')
        bandwidths = sorted({b for _, b in channels if b})
        extent = next(((s['wavelength_min_nm'], s['wavelength_max_nm']) for s in samples
                       if s.get('wavelength_min_nm') and s.get('wavelength_max_nm')), None)
        interval = next((s['sampling_interval_ms'] for s in samples if s.get('sampling_interval_ms')), None)
        text = 'Absorbance was recorded' + (f" with an {detector} photodiode array detector" if detector else '')
        if wavelengths:
            text += f" at {wavelengths}" + (f" (bandwidth {_g(bandwidths[0])} nm)" if len(bandwidths) == 1 else '')
        if extent:
            text += f", acquiring spectra from {_g(extent[0])} to {_g(extent[1])} nm"
        if interval:
            text += f" every {_g(interval)} ms"
        sentences.append(text + '.')
    version = next((s.get('software_version') for s in samples if s.get('software_version')), None)
    sentences.append(f"Instruments were controlled and data acquired with LabSolutions"
                     + (f" (version {version})" if version else '') + '.')
    return {'heading': 'General procedure for HPLC\u2013PDA analysis' if devices.get('detector') or channels
            else 'General procedure for HPLC analysis', 'text': ' '.join(sentences)}


def methods_text(store, column: str = '', dwell_volume_ul: Optional[float] = None) -> List[Dict[str, str]]:
    """One journal-style methods paragraph for each method that is attached to at least one sample."""
    users: Dict[str, List[Dict[str, Any]]] = {}
    for bundle in store.iter_bundles():
        for component in bundle.component_list:
            key = component.metadata.get('method_key')
            if key in getattr(store, 'instrument_methods', {}):
                users.setdefault(key, []).append(component.metadata)
    return [method_paragraph(store.instrument_methods[key], samples, column, dwell_volume_ul)
            for key, samples in users.items()]
