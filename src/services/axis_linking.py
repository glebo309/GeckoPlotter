"""Apply shared axis scales without mixing incompatible measurements."""
import re


def apply_axis_linking(figure, link_x=True, global_y=False):
    keys = figure.layout.to_plotly_json()
    x_axes = sorted((k for k in keys if re.fullmatch(r'xaxis\d*', k)),
                    key=lambda k: int(k[5:] or 1))
    y_axes = sorted((k for k in keys if re.fullmatch(r'yaxis\d*', k)),
                    key=lambda k: int(k[5:] or 1))
    for index, key in enumerate(x_axes):
        figure.layout[key].matches = 'x' if link_x and index else None
        if not link_x:
            figure.layout[key].showticklabels = True
    groups = {}
    meta = figure.layout.meta or {}
    units = meta.get('gecko_axis_units', {}) if isinstance(meta, dict) else {}
    for key in y_axes:
        axis = figure.layout[key]
        # The first right-hand scale is the frame edge, not a free shifted axis.
        if axis.overlaying == 'y' and axis.side == 'right' and key == 'yaxis2':
            axis.update(anchor='x', autoshift=False, shift=0, mirror=False)
        unit = units.get(key, axis.title.text or '')
        reference = groups.setdefault(unit, key.replace('axis', ''))
        axis.matches = reference if global_y and reference != key.replace('axis', '') else None
        if key in units:
            traces = [trace for trace in figure.data
                          if (trace.yaxis or 'y') == key.replace('axis', '')
                          and isinstance(trace.meta, dict)]
            if traces:
                color = figure.layout.font.color or '#444'
                axis.color = color
                axis.tickfont.color = color
                axis.title.font.color = color
            if key != 'yaxis' and axis.overlaying:
                axis.showgrid = False
                axis.mirror = False
    return figure
