"""Automatic source labels and explicit per-figure label ownership."""
from copy import deepcopy
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
from services.axis_inspector import axis_descriptors


def label_modes(settings):
    stored=(settings or {}).get('axis_label_modes') or {}
    return {direction:stored.get(direction) or ('custom' if (settings or {}).get(key) not in
            (None, DEFAULT_PLOT_SETTINGS[key]) else 'auto')
            for direction,key in (('x','x_label'),('y','y1_label'))}


def source_axis_labels(figure):
    source=figure.to_plotly_json() if hasattr(figure,'to_plotly_json') else (figure or {})
    layout=source.get('layout',{})
    meta=layout.get('meta') or {}
    identities=meta.get('gecko_axis_identities',{}) if isinstance(meta,dict) else {}
    result={}
    for descriptor in axis_descriptors(source):
        direction=descriptor['direction']
        if direction in result:
            continue
        # Identity labels were captured before styling, so Use data labels can
        # restore the source even when a displayed title is custom or hidden.
        original=next((identities[key].get('label') for key in descriptor['axes']
                       if identities.get(key,{}).get('label')),None)
        result[direction]=original or descriptor['label']
    return result


def sync_automatic_labels(settings, figure, reset=False):
    if not settings:
        return None
    result=deepcopy(settings)
    modes={'x':'auto','y':'auto'} if reset else label_modes(settings)
    result['axis_label_modes']=modes
    for direction,label in source_axis_labels(figure).items():
        if modes[direction]=='auto':
            result['x_label' if direction=='x' else 'y1_label']=label
    return result if result!=settings else None
