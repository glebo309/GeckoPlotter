"""Match integrated responses to explicit, compatible calibration signals."""
import copy
import json
import math
import re
from collections import Counter, defaultdict

from services.calibration_service import CalibrationPoint


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None



def _measurement_label(label):
    # UV-Vis exports append a sample identifier, not a detector/channel or unit.
    # Keep every other numbered suffix and explicit wavelength unchanged.
    return re.sub(r'\s+(?:\(Solution\s*#\d+\)|Solution\s*#\d+)\s*$', '',
                  str(label or ''), flags=re.I).strip()


def _x_identity(label):
    return re.sub(r'^retention\s+time(?=\s*\(|$)', 'time', label.casefold())


def _unit(label):
    match = re.search(r'\(([^()]+)\)\s*$', str(label or ''))
    if match:
        return match.group(1).strip()
    # These native data labels are also the measurement unit.
    return str(label) if str(label).lower() in ('ion count', 'counts', 'm/z') else ''


def _canonical_signal_key(key):
    """Read prior GeckoPlotter keys compatibly without guessing external keys."""
    try:
        identity = json.loads(key)
    except (TypeError, ValueError):
        return key
    if not (isinstance(identity, dict) and isinstance(identity.get('category'), str)
            and isinstance(identity.get('x'), str) and isinstance(identity.get('y'), list)
            and all(isinstance(y, str) for y in identity['y'])):
        return key
    identity['category'] = identity['category'].casefold()
    identity['x'] = _x_identity(identity['x'].strip())
    identity['y'] = [_measurement_label(y).casefold() for y in identity['y']]
    return json.dumps(identity, sort_keys=True, separators=(',', ':'))


def _signal_identity(entry):
    standardized = entry.get('standardized')
    metadata = {**(getattr(standardized, 'metadata', {}) or {}), **(entry.get('metadata') or {})}
    xs = [metadata['auto_x']] if metadata.get('auto_x') else (getattr(standardized, 'x_columns', None) or ['Position'])
    ys = metadata.get('auto_y') or getattr(standardized, 'y_columns', None) or ['Response']
    if isinstance(ys, str):
        ys = [ys]
    x_label = str(xs[0]).strip()
    ys = [_measurement_label(y) for y in ys]
    y_label = ys[0]
    x_units, height_units = _unit(x_label), _unit(y_label)
    category = getattr(standardized, 'source_category', metadata.get('source_category', 'generic'))
    category = str(getattr(category, 'value', category)).casefold()
    role = metadata.get('component_role', '')
    polarity = str(metadata.get('ionization_mode', '')).lower()
    if role in ('ms_positive', 'ms_negative') and polarity not in ('positive', 'negative'):
        polarity = role.removeprefix('ms_')
    wavelength = metadata.get('wavelength_nm', metadata.get('wavelength'))
    if wavelength is None:
        found = re.search(r'(\d+(?:\.\d+)?)\s*nm', ' '.join(str(y) for y in ys), re.I)
        wavelength = found.group(1) if found else None
    wavelength = _number(wavelength)
    channel = metadata.get('detector_channel') or metadata.get('channel') or ''
    if role in ('vwd_a', 'vwd_b'):
        channel = channel or role[-1].upper()
        polarity = ''
    # Include channel/header identity, never the sample name or original filename.
    identity = dict(category=category, x=_x_identity(x_label), y=[str(y).casefold() for y in ys],
                    wavelength_nm=wavelength, channel=str(channel).casefold(), polarity=polarity)
    return json.dumps(identity, sort_keys=True, separators=(',', ':')), x_units, height_units


def peak_candidates(data_manager):
    """Return loaded integrated peaks with stable IDs and original measurement units.

    Peak.rt is the existing model's apex X coordinate, including spectral data.
    Legacy peaks without an apex use the integration midpoint, explicitly marked.
    """
    rows = []
    for file_id, peaks in data_manager.peak_service.get_all_peaks().items():
        entry = data_manager.get_data_by_id(file_id)
        if not entry:
            continue
        key, x_units, height_units = _signal_identity(entry)
        metadata = entry.get('metadata') or {}
        sample = metadata.get('parent_bundle_name') or metadata.get('sample_name') or (entry.get('record') or {}).get('name') or file_id
        for peak in peaks:
            position = _number(getattr(peak, 'apex_x', None))
            if position is None:
                position = _number(getattr(peak, 'rt', None))
            position_source = 'apex'
            if position is None:
                start, end = _number(getattr(peak, 'rt_start', None)), _number(getattr(peak, 'rt_end', None))
                position = (start + end) / 2 if start is not None and end is not None else None
                position_source = 'midpoint' if position is not None else 'unavailable'
            rows.append(dict(id=f'{file_id}:{peak.peak_id}', file_id=file_id, peak_id=peak.peak_id,
                             sample=sample, sample_id=metadata.get('parent_bundle_id') or file_id,
                             peak_name=getattr(peak, 'label', '') or peak.name,
                             position=position, position_source=position_source,
                             response=_number(peak.area), height=_number(peak.height), signal_key=key,
                             x_units=x_units, height_units=height_units,
                             response_units='·'.join(unit for unit in (height_units, x_units) if unit)))
    return rows


def _matches(model, row):
    position, tolerance = _number(getattr(model, 'match_position', None)), _number(getattr(model, 'match_tolerance', None))
    response_type = getattr(model, 'response_type', 'area')
    unit = row['height_units'] if response_type == 'height' else row['response_units']
    return (getattr(model, 'auto_apply', False) and model.coefficients is not None
            and response_type in ('area', 'height')
            and position is not None and tolerance is not None and tolerance >= 0
            and row['position'] is not None and abs(row['position'] - position) <= tolerance
            and bool(getattr(model, 'signal_key', None))
            and _canonical_signal_key(model.signal_key) == _canonical_signal_key(row['signal_key'])
            and getattr(model, 'x_units', None) == row['x_units']
            and getattr(model, 'response_units', None) == unit)


def apply_calibrations(data_manager):
    """Refresh predictions; never leave obsolete concentration on an unmatched peak.

    Returns display values keyed by candidate ID. A peak with the calibrated peak's name is taken first; otherwise
    every peak in the window is a match, and two in one signal are ambiguous (no concentration rather than the
    wrong peak's). A standard sample's other peaks are never candidate unknowns for that model.
    """
    rows = peak_candidates(data_manager)
    service = data_manager.calibration_service
    models = list(service.get_all_models().values())
    by_id = {row['id']: row for row in rows}
    signals = defaultdict(list)
    for row in rows:
        signals[row['file_id']].append(row)
    matches = {row['id']: [] for row in rows}
    for model in models:
        source_ids = {point.source_id for point in model.standards if point.source_id}
        standards = [by_id[key] for key in source_ids if key in by_id]
        # Removing the selected peak must not turn its sample's other peaks into unknowns.
        standard_files = {key.rsplit(':', 1)[0] for key in source_ids}
        standard_samples = {row['sample_id'] for row in rows if row['file_id'] in standard_files}
        names = {row['peak_name'] for row in standards}
        # Portable calibrations retain the selected peak name even without its source file loaded.
        if not names:
            names = {point.sample_name.rsplit(' / ', 1)[1] for point in model.standards
                     if point.source_id and ' / ' in point.sample_name}
        names = names or {model.analyte_name}
        for candidates in signals.values():
            if candidates[0]['sample_id'] in standard_samples:
                selected = [row for row in candidates if row['id'] in source_ids and _matches(model, row)]
            else:
                named = [row for row in candidates if row['peak_name'] in names]
                selected = [row for row in (named or candidates) if _matches(model, row)]   # named, if there is one
            for row in selected:
                matches[row['id']].append(model)
    counts = Counter((row['file_id'], model.model_id) for row in rows for model in matches[row['id']])
    peaks = {f'{fid}:{peak.peak_id}': peak for fid, items in data_manager.peak_service.get_all_peaks().items() for peak in items}
    results = {}
    for row in rows:
        peak = peaks[row['id']]
        peak.concentration = None
        peak.calibration_id = None
        result = dict(concentration=None, units='', model='', model_id=None, status='No matching calibration')
        compatible = matches[row['id']]
        if len(compatible) > 1:
            result['status'] = 'Ambiguous calibration'
        elif compatible:
            model = compatible[0]
            result.update(model=model.analyte_name, model_id=model.model_id, units=model.units)
            response = row['height'] if getattr(model, 'response_type', 'area') == 'height' else row['response']
            if counts[(row['file_id'], model.model_id)] > 1:
                result['status'] = 'Ambiguous peak match'
            elif response is None:
                result['status'] = 'Invalid response'
            else:
                try:
                    concentration = _number(service.predict_concentration(model.model_id, response))
                except (ValueError, TypeError, ArithmeticError):
                    concentration = None
                if concentration is None:
                    result['status'] = 'Prediction unavailable'
                else:
                    peak.concentration, peak.calibration_id = concentration, model.model_id
                    result['concentration'] = concentration
                    standards = [s.concentration for s in model.standards if s.included]
                    result['status'] = ('Outside calibration range' if standards and not
                                        min(standards) <= concentration <= max(standards) else 'Calibrated')
        results[row['id']] = result
    return results


# The calibration editor's steps (callbacks/calibration_callbacks.py), also used by the agent (gecko_api.calibrate),
# so a calibration made either way is the same model.

def _form_number(value, label):
    import math
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a number.') from None
    if not math.isfinite(number):
        raise ValueError(f'{label} must be finite.')
    return number


def add_peak_rows(rows, selected_ids, candidates, response_type):
    """Append selected measured peaks without losing entered concentrations."""
    result = copy.deepcopy(rows or [])
    existing = {r.get('id') for r in result}
    signals = {(r['signal_key'], r.get('x_units', '')) for r in result if r.get('signal_key')}
    by_id = {r['id']: r for r in candidates}
    for key in selected_ids or []:
        if key in existing:
            continue
        if key not in by_id:
            raise ValueError('A selected peak is no longer available. Refresh the peak selection.')
        peak = by_id[key]
        signals.add((peak['signal_key'], peak['x_units']))
        if len(signals) > 1:
            raise ValueError('Use peaks from the same signal and X units for one calibration.')
        result.append(dict(id=key, sample_name=f"{peak['sample']} / {peak['peak_name']}",
            concentration=None, area=peak['height'] if response_type == 'height' else peak['response'],
            position=peak['position'], signal_key=peak['signal_key'], x_units=peak['x_units'],
            response_units=peak.get('height_units', '') if response_type == 'height' else peak['response_units'],
            measured_area=peak['response'], measured_height=peak['height'],
            area_units=peak['response_units'], height_units=peak.get('height_units', '')))
        existing.add(key)
    return result


def fit_calibration_form(service, model_id, rows, included_rows, *, name, units,
                         fit_type, force_zero, response_type, position, tolerance, auto_apply):
    """Validate and fit a copy; failed edits never partially replace a model."""
    if not str(name or '').strip():
        raise ValueError('Give the calibration an analyte name.')
    tolerance = _form_number(tolerance, 'Matching tolerance')
    if tolerance <= 0:
        raise ValueError('Matching tolerance must be greater than zero.')
    position = None if position in (None, '') else _form_number(position, 'Peak position')
    signals = {(r['signal_key'], r.get('x_units', ''), r.get('response_units', ''))
               for r in rows if r.get('signal_key')}
    if len(signals) > 1:
        raise ValueError('Use standards from the same signal and units.')
    trial = copy.deepcopy(service)
    model = trial.get_model(model_id) if model_id else None
    if model is None:
        model = trial.create_model(str(name).strip(), '')
    if signals:
        model.signal_key, model.x_units, model.response_units = next(iter(signals))
    model.analyte_name, model.units = str(name).strip(), str(units or '').strip()
    model.fit_type, model.force_zero = fit_type or 'linear', bool(force_zero)
    model.response_type = response_type or 'area'
    model.match_position, model.match_tolerance = position, tolerance
    model.auto_apply = bool(auto_apply and model.signal_key and position is not None)
    selected = set(included_rows or [])
    points = []
    for index, row in enumerate(rows):
        included = index in selected
        if not included and row.get('concentration') in (None, ''):
            continue
        concentration = _form_number(row.get('concentration'), f"Concentration in row {index + 1}")
        response = _form_number(row.get('area'), f"Response in row {index + 1}")
        if concentration < 0:
            raise ValueError('Standard concentrations cannot be negative.')
        measured_position = row.get('position')
        if included and position is not None and measured_position is not None:
            if abs(float(measured_position) - position) > tolerance:
                raise ValueError(f'Peak in row {index + 1} is outside the matching tolerance.')
        points.append(CalibrationPoint(str(row.get('sample_name') or f'Standard {index+1}'),
            concentration, response, included, source_id=str(row.get('id') or ''), position=measured_position))
    trial.update_standards(model.model_id, points)
    trial.fit_model(model.model_id)
    return service.replace_model(model)
