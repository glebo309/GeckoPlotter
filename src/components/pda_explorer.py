"""Linked wavelength/time explorer, mounted in the relevant analysis tab."""
from dash import html, dcc
import dash_mantine_components as dmc

import json

from services.themes import HEATMAP_COLORMAPS


def create_pda_explorer():
    graph_config = {'displayModeBar': False, 'scrollZoom': True, 'doubleClick': 'reset', 'responsive': True}
    # Plain drag moves the cross (pda-heatmap-cursor.js); Shift + drag box-zooms. No scroll zoom.
    # No double-click reset: the heatmap zoom only resets with Shift + click (pda-heatmap-cursor.js).
    heatmap_config = {**graph_config, 'scrollZoom': False, 'doubleClick': False}
    return html.Div([
        html.Div([
            html.Label(['Wavelength (nm)', dmc.NumberInput(id='pda-wavelength', value=254, decimalScale=0,
                debounce=True, step=1, size='xs', hideControls=True)], className='pda-field'),
            html.Label(['Time (min)', dmc.NumberInput(id='pda-time', value=0, decimalScale=3,
                debounce=True, step=.001, size='xs', hideControls=True)], className='pda-field'),
            dmc.Switch(id='pda-live', label='Live preview', checked=True, size='sm'),
            dmc.Button('Add wavelength channel', id='pda-add-chromatogram', variant='default', size='xs', disabled=True),
            html.Div(id='pda-channel-controls'),
        ], className='pda-controls'),
        html.Div(id='pda-selection-info', className='pda-selection-info', role='status'),
        html.Div([
            html.Div([
                dcc.Graph(id='pda-heatmap', config=heatmap_config, responsive=True,
                          className='pda-heatmap'),
                html.Div(id='pda-hover-info', className='pda-hover-info'),
            ], className='pda-heatmap-view'),
            dcc.Graph(id='pda-spectrum', config=graph_config, responsive=True,
                      className='pda-spectrum'),
        ], className='pda-plots'),
        dcc.Store(id='pda-preview'),
        dcc.Store(id='pda-main-cursor'),
        dcc.Store(id='pda-context'),
        dcc.Store(id='pda-cursor-event'),
        dcc.Store(id='pda-heatmap-event'),
        # Colour map is chosen from the heatmap's right-click menu (pda-colormap-menu.js) and remembered.
        dcc.Store(id='pda-colormap', storage_type='local'),
        html.Div(id='pda-colormap-options', hidden=True, **{'data-options': json.dumps(HEATMAP_COLORMAPS)}),
        dcc.Store(id='pda-cursor-sync'),
        dcc.Store(id='pda-cross-sync'),
    ], className='pda-explorer')
