"""Keep automatic line-plot X bounds independent of editing handles."""
import numpy as np
from services.plot_arrays import numeric_plot_array


def apply_signal_x_bounds(figure):
    groups = {}
    for trace in figure.data:
        if (not isinstance(trace.meta, dict) or not trace.meta.get('file_id')
                or trace.visible in (False, 'legendonly') or trace.type != 'scatter'
                or trace.mode not in (None, 'lines')):
            continue
        ref = trace.xaxis or 'x'
        key = ref.replace('x', 'xaxis', 1)
        axis = figure.layout[key]
        root = axis.matches or ref
        try:
            values = numeric_plot_array(trace.x)
            values = values[np.isfinite(values)]
            if axis.type == 'log':
                values = values[values > 0]
        except (TypeError, ValueError):
            continue
        if values.size:
            item = groups.setdefault(root, {'keys': set(), 'low': float('inf'), 'high': -float('inf')})
            item['keys'].update((key, root.replace('x', 'xaxis', 1)))
            item['low'] = min(item['low'], float(values.min()))
            item['high'] = max(item['high'], float(values.max()))
    for item in groups.values():
        if item['low'] < item['high']:
            for key in item['keys']:
                figure.layout[key].autorangeoptions = dict(minallowed=item['low'], maxallowed=item['high'])
    return figure
