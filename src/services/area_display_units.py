"""Presentation units for absorbance peak areas; PeakService retains the original measurements."""
from copy import deepcopy

AREA_UNITS = {'mAU·min': 1., 'mAU·s': 60., 'µAU·s': 60000.}


def display_peak_areas(frame, data_manager, owners, requested='mAU·min'):
    from services.calibration_workflow import _signal_identity
    result = frame.copy()
    source_units = []
    for peak_id in result['peak_id']:
        entry = data_manager.get_data_by_id(owners[peak_id])
        _, x_unit, y_unit = _signal_identity(entry or {})
        source_units.append((y_unit, x_unit))
    # A mixed detector table must never label ion counts or unknown responses as absorbance.
    if not source_units or any(unit != ('mAU', 'min') for unit in source_units):
        return result
    unit = requested if isinstance(requested, str) and requested in AREA_UNITS else 'mAU·min'
    result['Area'] = result['Area'] * AREA_UNITS[unit]
    result['_area_display_unit'] = unit
    return result


def area_label(frame):
    units = set(frame.get('_area_display_unit', []).tolist()) if '_area_display_unit' in frame else set()
    return f'Area ({next(iter(units))})' if len(units) == 1 else 'Area'


def publication_area_units(frame, selections):
    """Give plotted/exported displayed areas their unit while preserving table selection IDs."""
    label = area_label(frame)
    if label == 'Area' or 'Area' not in frame:
        return frame, selections
    selected = deepcopy(selections)

    def replace(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'column_id' and item == 'Area':
                    value[key] = label
                else:
                    replace(item)
        elif isinstance(value, list):
            for item in value:
                replace(item)

    replace(selected)
    return frame.rename(columns={'Area': label}), selected
