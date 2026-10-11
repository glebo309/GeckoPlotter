"""Keep scientific figure content while removing transient peak editor affordances."""
from copy import deepcopy
import re


def _interaction_helper(trace):
    if str(trace.get('name', '')).startswith('__deselect__'):
        return True
    if trace.get('meta') != 'peak_overlay':
        return False
    custom = trace.get('customdata')
    if custom is None:
        return False
    if hasattr(custom, 'tolist'):
        custom = custom.tolist()
    if isinstance(custom, str):
        custom = [custom]
    for item in custom:
        if hasattr(item, 'tolist'):
            item = item.tolist()
        if isinstance(item, (list, tuple)):
            if (len(item) > 1 and item[1] in ('p-point', 'catcher')) or (item and item[0] == '__deselect__'):
                return True
        elif item == '__deselect__':
            return True
    return False


def _normal_peak_fill(color):
    if not isinstance(color, str):
        return color
    match = re.fullmatch(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)', color)
    if match:
        return 'rgba(%s, %s, %s, 0.30)' % match.groups()
    if re.fullmatch(r'#[\da-fA-F]{6}', color):
        return 'rgba(%d, %d, %d, 0.30)' % tuple(int(color[i:i+2],16) for i in (1,3,5))
    return color


def _collapse_mass_hover_traces(figure):
    """Upgrade old two-trace spectra: hover counts belong to their sticks.

    Require the known hover template and exactly matching stick endpoints,
    so an unrelated user marker signal remains untouched.
    """
    traces = []
    for trace in figure.get('data', []):
        template = trace.get('hovertemplate', '') or ''
        if (traces and trace.get('mode') == 'markers'
                and 'm/z: %{x' in template and 'Relative: %{y' in template
                and 'Intensity: %{customdata' in template):
            sticks = traces[-1]
            x, y, counts = trace.get('x'), trace.get('y'), trace.get('customdata')
            sx, sy = sticks.get('x'), sticks.get('y')
            sequences = (x, y, counts, sx, sy)
            if (sticks.get('mode') == 'lines'
                    and all(isinstance(a, (list, tuple)) or hasattr(a, 'tolist') for a in sequences)
                    and len(x) == len(y) == len(counts) and len(sx) == len(sy) == 3 * len(x)
                    and all(sx[3*i] == mass and sx[3*i+1] == mass and sx[3*i+2] is None
                            and sy[3*i] == 0 and sy[3*i+1] == y[i] and sy[3*i+2] is None
                            for i, mass in enumerate(x))):
                sticks['customdata'] = [value for count in counts for value in (count, count, None)]
                sticks['hovertemplate'] = template
                sticks.pop('hoverinfo', None)
                meta = sticks.get('meta') if isinstance(sticks.get('meta'), dict) else {}
                sticks['meta'] = {**meta, 'gecko_mass_spectrum':True}
                labels = {f'{float(mass):.2f}' for mass in x}
                for annotation in figure.get('layout', {}).get('annotations', []):
                    if (annotation.get('text') in labels and not annotation.get('showarrow', True)
                            and annotation.get('xref', 'x') == sticks.get('xaxis', 'x')
                            and annotation.get('yref', 'y') == sticks.get('yaxis', 'y')):
                        annotation['name'] = 'gecko-ms-peak'
                continue
        traces.append(trace)
    if 'data' in figure:
        figure['data'] = traces


def clean_figure_for_output(figure):
    """Return an independent figure with normal integration shading and labels.

    Peak geometry metadata stays available for later publication edits. Author
    annotations, deliberate shapes and fitted baseline traces remain untouched.
    """
    source = figure.to_plotly_json() if hasattr(figure, 'to_plotly_json') else figure
    result = deepcopy(source or {})
    _collapse_mass_hover_traces(result)
    traces = []
    for trace in result.get('data', []):
        if _interaction_helper(trace):
            continue
        if trace.get('meta') == 'peak_overlay' and trace.get('fill') == 'toself':
            trace['fillcolor'] = _normal_peak_fill(trace.get('fillcolor'))
            trace['line'] = {**trace.get('line', {}), 'width':0, 'color':'rgba(0,0,0,0)'}
            if 'opacity' in trace:
                trace['opacity'] = 1
            for key in ('selectedpoints', 'selected', 'unselected'):
                trace.pop(key, None)
        traces.append(trace)
    if 'data' in result:
        result['data'] = traces
    layout = result.get('layout', {})
    if 'shapes' in layout:
        layout['shapes'] = [shape for shape in layout['shapes']
                            if not (str(shape.get('name', '')).startswith('baseline:')
                                    and shape.get('editable') is True)]
    return result
