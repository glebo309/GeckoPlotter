"""Editable publication views built from an immutable source figure."""
from copy import deepcopy
import math
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services.figure_actions import publication_plot_settings
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS, PlotSettingsService
from services.plot_smoothing import smooth_plotly_traces
from services.axis_linking import apply_axis_linking


def editable_publication_figure(source, settings, source_settings=None):
    s = {**DEFAULT_PLOT_SETTINGS, **(settings or {})}
    original = publication_plot_settings(source, source_settings)
    fig = go.Figure(source)
    if 'plot_type' in original and s['plot_type'] != original['plot_type']:
        converted = []
        for trace in fig.data:
            item = trace.to_plotly_json()
            auxiliary = (item.get('fill') or str(item.get('name', '')).startswith(('peak:', '__deselect__'))
                         or 'baseline' in str(item.get('name', '')).lower())
            if not auxiliary and trace.type in ('bar', 'scatter', 'scattergl'):
                if s['plot_type'] == 'bar':
                    item['type'] = 'bar'
                    trace = go.Bar(item, skip_invalid=True)
                else:
                    item.update(type='scatter', mode='lines+markers' if s['plot_type'] == 'line' else 'markers')
                    trace = go.Scatter(item, skip_invalid=True)
            converted.append(trace)
        fig = go.Figure(data=converted, layout=fig.layout)
    rows = max(1, int(s.get('subplot_rows', 1) or 1))
    cols = max(1, int(s.get('subplot_cols', 1) or 1))
    mode = s['layout_mode']
    changed = mode != original['layout_mode'] or any(
        s.get(key, default) != original.get(key, default)
        for key, default in [('subplot_rows', 1), ('subplot_cols', 1), ('subplot_spacing', .08)])
    if changed:
        old = fig.layout.to_plotly_json()
        traces = list(fig.data)
        data_indices = [i for i, t in enumerate(traces)
                        if not (getattr(t, 'fill', None) or str(t.name or '').startswith(('peak:', '__deselect__'))
                                or 'baseline' in str(t.name or '').lower())]
        if not data_indices:
            data_indices = list(range(len(traces)))
        targets = {}
        unit_axes = {}
        old_axis_targets = {}
        units = {}
        identities = {}
        source_identities = (old.get('meta') or {}).get('gecko_axis_identities', {})
        if mode == 'stacked':
            if rows * cols == 1:
                rows = max(1, len(data_indices))
            rows = max(rows, math.ceil(len(data_indices) / cols))
            spacing = min(float(s['subplot_spacing']), .9 / max(1, rows - 1))
            result = make_subplots(rows=rows, cols=cols, vertical_spacing=spacing)
        else:
            result = go.Figure()
        for panel, index in enumerate(data_indices):
            trace = traces[index]
            old_y = trace.yaxis or 'y'
            old_key = old_y.replace('y', 'yaxis', 1)
            label = (source_identities.get(old_key, {}).get('label')
                     or old.get(old_key, {}).get('title', {}).get('text', '')
                     or (old.get('meta') or {}).get('gecko_axis_units', {}).get(old_key, ''))
            if mode == 'stacked':
                n = panel + 1
                xref, yref = ('x' if n == 1 else f'x{n}'), ('y' if n == 1 else f'y{n}')
            else:
                n = unit_axes.setdefault(label, len(unit_axes) + 1)
                xref, yref = 'x', ('y' if n == 1 else f'y{n}')
                if n > 1:
                    result.update_layout(**{f'yaxis{n}':dict(overlaying='y', anchor='free', side='right', autoshift=True, tickmode='sync')})
            previous_x = (trace.xaxis or 'x').replace('x', 'xaxis', 1)
            if previous_x in source_identities:
                identities[xref.replace('x', 'xaxis', 1)] = source_identities[previous_x]
            targets[index] = (xref, yref)
            old_axis_targets.setdefault(old_y, (xref, yref))
            unit_key = yref.replace('y', 'yaxis', 1)
            units[unit_key] = label
            result.update_layout(**{unit_key:dict(title=label, color='#444')})
        for i, trace in enumerate(traces):
            target = targets.get(i)
            if target is None:
                # Peak fills/baselines follow their source trace, not their list position.
                target = old_axis_targets.get(trace.yaxis or 'y', ('x', 'y'))
            trace.xaxis, trace.yaxis = target
            trace.legend = ('legend' if mode == 'overlay' or target[1] == 'y' else 'legend' + target[1][1:])
            result.update_layout(**{trace.legend: dict(x=1, y=1)})
            result.add_trace(trace)
        retained = {k:v for k,v in old.items() if not re.fullmatch(r'[xy]axis\d*|legend\d*', k)
                    and k not in ('annotations', 'shapes', 'template')}
        result.update_layout(**retained)
        result.update_layout(meta={**(old.get('meta') or {}), 'gecko_axis_units':units,
                                   'gecko_axis_identities':identities})
        for key in result.layout:
            if re.fullmatch(r'xaxis\d*', key):
                result.layout[key].title.text = old.get('xaxis', {}).get('title', {}).get('text', '')
                if old.get('xaxis', {}).get('range'):
                    result.layout[key].range = old['xaxis']['range']
        # Keep annotations and integration shapes attached to their axes.
        for collection in ('shapes', 'annotations'):
            items = deepcopy(old.get(collection, []))
            for item in items:
                yref = item.get('yref', 'y')
                if yref in old_axis_targets:
                    item['xref'], item['yref'] = old_axis_targets[yref]
            result.update_layout(**{collection:items})
        fig = result
    if s.get('smooth_window', 0) != original.get('smooth_window', 0):
        smooth_plotly_traces(fig.data, s.get('smooth_window', 0))
    if (s.get('axis_label_modes', {}).get('x') != 'custom'
            and s['x_label'] == DEFAULT_PLOT_SETTINGS['x_label'] and fig.layout.xaxis.title.text):
        s['x_label'] = fig.layout.xaxis.title.text
    # Explicit user labels must override source unit labels; default labels don't.
    if (s.get('axis_label_modes', {}).get('y') != 'auto'
            and (s['y1_label'] != DEFAULT_PLOT_SETTINGS['y1_label'] or s.get('axis_label_modes', {}).get('y') == 'custom')):
        fig.update_yaxes(title_text=s['y1_label'])
    # Captured Separate figures also need a legend anchored in every pane.
    if mode == 'stacked':
        for trace in fig.data:
            ref = trace.yaxis or 'y'
            trace.legend = 'legend' + ref[1:]
            fig.update_layout(**{trace.legend: dict(x=1, y=1)})
    PlotSettingsService.apply_to_figure(fig, PlotSettingsService.from_dict(dict(s, y_label=s['y1_label'])))
    if s['auto_range'] and (original.get('auto_range') is False or s.get('_axis_range_revision', 0) != original.get('_axis_range_revision', 0)):
        fig.update_xaxes(autorange=True)
        fig.update_yaxes(autorange=True)
    apply_axis_linking(fig, s.get('link_x', True), s.get('y_scope') == 'global')
    from services.axis_inspector import apply_axis_overrides
    apply_axis_overrides(fig, s.get('axis_overrides', {}))
    if mode == 'stacked' and s.get('link_x', True):
        for key in fig.layout:
            if re.fullmatch(r'xaxis\d*', key):
                domain = fig.layout['yaxis' + key[5:]].domain or [0, 1]
                fig.layout[key].showticklabels = domain[0] == 0
    shared_y = False
    if mode == 'stacked' and s.get('shared_axis_labels'):
        fig.layout.annotations = tuple(a for a in fig.layout.annotations if a.name != 'gecko-shared-y')
        columns = {}
        for key in fig.layout:
            if re.fullmatch(r'yaxis\d*', key):
                axis = fig.layout[key]
                xkey = 'xaxis' + key[5:]
                xaxis = fig.layout[xkey] if xkey in fig.layout else fig.layout.xaxis
                columns.setdefault(tuple(xaxis.domain or [0,1]), []).append(axis)
        for xdomain, axes in columns.items():
            groups = []
            for axis in sorted(axes, key=lambda a:(a.domain or [0,1])[0], reverse=True):
                label = axis.title.text
                if not label:
                    continue
                domain = axis.domain or [0,1]
                if groups and groups[-1][0] == label:
                    groups[-1][1] = domain[0]
                else:
                    groups.append([label, domain[0], domain[1]])
                axis.title.text = ''
            if len(axes) == 1:
                axes[0].title.text = groups[0][0] if groups else ''
                continue
            for label, lo, hi in groups:
                fig.add_annotation(name='gecko-shared-y', text=label, xref='paper', yref='paper',
                    x=xdomain[0], y=(lo+hi)/2, xshift=-(s['tick_font_size']*3+10),
                    xanchor='center', yanchor='middle', textangle=-90, showarrow=False,
                    font=dict(size=s['tick_font_size'],color=fig.layout.font.color or '#444'))
                shared_y = True
    # Compact margins and legend samples suit a printed column, with room for ticks.
    for key in fig.layout:
        if re.fullmatch(r'legend\d*', key):
            fig.layout[key].update(itemwidth=30, tracegroupgap=0)
    # Publication labels sit close to their axes; desktop-size title gaps waste
    # a large fraction of an 84 mm column, especially with two Y axes.
    fig.update_xaxes(title_standoff=3)
    fig.update_yaxes(title_standoff=3)
    fig.update_layout(autosize=True, margin=dict(l=(s['tick_font_size']*4+8) if shared_y else 4,
                                                r=4, t=20 if s.get('title') else 6, b=4, pad=0))
    return fig
