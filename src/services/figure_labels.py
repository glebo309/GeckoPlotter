"""Direct figure text edits share the active plot's persisted settings."""
from copy import deepcopy
import re
from services.axis_inspector import axis_descriptors


def edit_figure_label(settings, event, active_tab, owner):
    if (not settings or not event or not active_tab or event.get('tab') != active_tab
            or settings.get('_context_key') != owner or not owner
            or not owner.endswith(':' + active_tab)):
        return None
    field = event.get('field')
    text = event.get('text')
    if not isinstance(text, str):
        return None
    result = deepcopy(settings)
    if field == 'title':
        result['title'] = text
    elif isinstance(field, str) and re.fullmatch(r'[xy]axis\d*', field):
        descriptors = axis_descriptors({'layout':event.get('layout') or {}})
        selected = next((d for d in descriptors if field in d['axes']), None)
        if selected is None:
            return None
        result.setdefault('axis_label_overrides', {})[selected['id']] = text
        # Inspector's primary label fields represent the first measurement axis.
        first = next(d for d in descriptors if d['direction'] == field[0])
        if selected['id'] == first['id']:
            result['x_label' if field[0] == 'x' else 'y1_label'] = text
    else:
        return None
    return result if result != settings else None


def apply_figure_label_overrides(figure, overrides):
    for descriptor in axis_descriptors(figure):
        if descriptor['id'] in (overrides or {}):
            for key in descriptor['axes']:
                # Shared X titles intentionally appear only below the last row.
                if key.startswith('xaxis') and figure.layout[key].title.text == '':
                    continue
                figure.layout[key].title.text = overrides[descriptor['id']]
