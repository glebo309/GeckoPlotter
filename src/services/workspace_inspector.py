"""Resolve visible workspace targets without leaking state between figures."""
from collections import Counter
from copy import deepcopy


def active_figure(tab_id, tabs, raw, publication):
    kind = next((t.get('type') for t in tabs or [] if t.get('id') == tab_id), 'raw')
    figure = publication if kind == 'publication' else raw
    if not figure:
        return None
    meta = figure.get('layout', {}).get('meta') or {}
    if isinstance(meta, dict) and meta.get('gecko_tab_id') not in (None, tab_id):
        return None
    return figure


def signal_choices(figure):
    traces = [t for t in (figure or {}).get('data', []) if not (
        t.get('fill') or str(t.get('name', '')).startswith(('peak:', '__deselect__'))
        or 'baseline' in str(t.get('name', '')).lower())]
    names = Counter(t.get('name', 'Signal') for t in traces)
    options = []
    for i, trace in enumerate(traces):
        name = trace.get('name') or f'Signal {i+1}'
        meta = trace.get('meta') or {}
        fid = meta.get('file_id') if isinstance(meta, dict) else None
        key = f'id:{fid}:{name}' if fid else f'trace:{i}'
        label = name if names[name] == 1 else f'{name} ({i+1})'
        options.append({'value':key, 'label':label, 'trace':trace})
    return options


def edit_signal(settings, owner, key, changes):
    if not owner or owner != (settings or {}).get('_context_key') or not key:
        return None
    result = deepcopy(settings)
    overrides = result.setdefault('trace_overrides', {})
    overrides[key] = {**overrides.get(key, {}), **changes}
    return result if result != settings else None


def result_options(has_spectra):
    options = [{'value':'data-overview','label':'Data'},
               {'value':'peak-analysis','label':'Peaks'},
               {'value':'metadata','label':'Metadata'},
               {'value':'across-samples','label':'Compare samples'},
               {'value':'calibration','label':'Calibration'}]
    if has_spectra:
        options += [{'value':'ms-scan','label':'MS scan'}, {'value':'ms-eic','label':'Extracted ion chromatogram'},
                    {'value':'ms-peak-mass','label':'Peak mass spectrum'}]
    return options
