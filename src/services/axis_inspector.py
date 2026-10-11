"""Named measurement axes and per-figure range edits, independent of pane order."""
from copy import deepcopy
import math
import re


def _identity(direction, label):
    unit = re.search(r'\(([^)]+)\)\s*$', label)
    text = unit.group(1) if unit else label
    return direction + ':' + re.sub(r'[^a-z0-9%]+', '', text.lower())


def axis_descriptors(figure):
    """Group matching units across panes; retain identities when labels change."""
    source = figure.to_plotly_json() if hasattr(figure, 'to_plotly_json') else (figure or {})
    layout = source.get('layout', {})
    meta = layout.get('meta') or {}
    units = meta.get('gecko_axis_units', {}) if isinstance(meta, dict) else {}
    identities = meta.get('gecko_axis_identities', {}) if isinstance(meta, dict) else {}
    groups = {}
    keys = sorted((key for key in layout if re.fullmatch(r'[xy]axis\d*', key)),
                  key=lambda key:(key[0], int(key[5:] or 1)))
    for key in keys:
        axis = layout[key]
        if axis.get('visible') is False:
            continue
        title = axis.get('title') or {}
        label = units.get(key) or (title.get('text') if isinstance(title, dict) else title)
        remembered = identities.get(key, {})
        label = label or remembered.get('label') or ('X axis' if key[0] == 'x' else 'Y axis')
        identity = _identity(key[0], units[key]) if key in units else remembered.get('id') or _identity(key[0], label)
        item = groups.setdefault(identity, {'id':identity, 'label':label, 'direction':key[0], 'axes':[]})
        item['axes'].append(key)
    return list(groups.values())


def remember_axis_identities(figure):
    meta = figure.layout.meta or {}
    previous = meta.get('gecko_axis_identities', {}) if isinstance(meta, dict) else {}
    identities = {key:{'id':item['id'], 'label':
                      previous[key].get('label', item['label'])
                      if previous.get(key, {}).get('id') == item['id'] else item['label']}
                  for item in axis_descriptors(figure) for key in item['axes']}
    figure.update_layout(meta={**(meta if isinstance(meta, dict) else {}), 'gecko_axis_identities':identities})


def apply_axis_overrides(figure, overrides):
    """Apply data-unit bounds after global styling/linking and restored zoom."""
    if not overrides:
        return figure
    for descriptor in axis_descriptors(figure):
        option = overrides.get(descriptor['id'])
        if not option:
            continue
        scale = option.get('scale', 'linear')
        auto = option.get('mode', 'auto') == 'auto'
        limits = [option.get('min'), option.get('max')]
        if scale == 'log':
            limits = [math.log10(v) if v is not None and v > 0 else None for v in limits]
        autorange = (True if limits == [None, None] else 'min' if limits[0] is None
                     else 'max' if limits[1] is None else False)
        for key in descriptor['axes']:
            figure.layout[key].update(type=scale, range=None if auto else limits,
                                      autorange=True if auto else autorange)
    return figure


def update_axis_override(settings, owner, identity, mode, minimum, maximum, scale):
    """Validate an inspector edit; stale contexts and hydration are no-ops."""
    if not settings or settings.get('_context_key') != owner:
        return None
    def number(value):
        if value in (None, ''):
            return None
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Enter a finite axis limit.')
        return value
    minimum, maximum = number(minimum), number(maximum)
    if mode == 'manual':
        if minimum is not None and maximum is not None and minimum >= maximum:
            raise ValueError('Minimum must be smaller than maximum.')
        if scale == 'log' and any(v is not None and v <= 0 for v in (minimum, maximum)):
            raise ValueError('Logarithmic limits must be positive.')
    option = {'mode':mode or 'auto', 'min':minimum, 'max':maximum, 'scale':scale or 'linear'}
    if option == (settings.get('axis_overrides') or {}).get(identity, default_axis_option(settings, identity[0])):
        return None
    result = deepcopy(settings)
    result.setdefault('axis_overrides', {})[identity] = option
    result['_axis_range_revision'] = settings.get('_axis_range_revision', 0) + 1
    return result


def default_axis_option(settings, direction):
    return {'mode':'auto' if settings.get('auto_range', True) else 'manual',
            'min':settings.get(direction+'_min'), 'max':settings.get(direction+'_max'),
            'scale':settings.get(direction+'_scale', 'linear')}


def reset_axis_settings(settings, figure, axis_key, view):
    """Persist a one-axis reset, preserving the other axes' displayed zoom."""
    descriptors = axis_descriptors(figure)
    selected = next((d for d in descriptors if axis_key in d['axes']), None)
    if selected is None:
        return None
    result = deepcopy(settings)
    overrides = result.setdefault('axis_overrides', {})
    for descriptor in descriptors:
        current = next((view[key] for key in descriptor['axes'] if key in view), None)
        if not current:
            continue
        scale = current.get('type', 'linear')
        scale = scale if scale in ('linear','log') else 'linear'
        if descriptor['id'] == selected['id']:
            overrides[descriptor['id']] = {'mode':'auto', 'min':None, 'max':None, 'scale':scale}
        elif current.get('userZoom') and current.get('range') and len(current['range']) == 2:
            low, high = current['range']
            if not all(isinstance(v, (int,float)) for v in (low, high)):
                continue
            if scale == 'log':
                low, high = 10 ** low, 10 ** high
            overrides[descriptor['id']] = {'mode':'manual','min':low,'max':high,'scale':scale}
    if overrides == settings.get('axis_overrides', {}):
        return None
    result['_axis_range_revision'] = settings.get('_axis_range_revision', 0) + 1
    return result


def preserve_other_axes(settings, view, selected_identity):
    """Save live zoom for untouched measurement axes before applying one edit."""
    for descriptor in axis_descriptors({'layout':view.get('layout', {})}):
        if descriptor['id'] == selected_identity:
            continue
        current = next((view.get('axes', {}).get(key) for key in descriptor['axes']
                        if view.get('axes', {}).get(key)), None)
        if not current or not current.get('userZoom') or current.get('autorange', False) is not False:
            continue
        limits = current.get('range')
        if not limits or len(limits) != 2 or not all(isinstance(v, (int,float)) for v in limits):
            continue
        scale = current.get('type', 'linear')
        if scale not in ('linear','log'):
            continue
        low, high = [10 ** v for v in limits] if scale == 'log' else limits
        settings.setdefault('axis_overrides', {})[descriptor['id']] = {
            'mode':'manual','min':low,'max':high,'scale':scale}
    return settings
