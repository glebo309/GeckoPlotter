"""Detector polarity lives beside the main plot's view controls."""
from dash import html, dcc
import dash_mantine_components as dmc


def create_ms_polarity_control():
    return html.Div([
        html.Span('MS', className='plot-toolbar-label'),
        dmc.SegmentedControl(id='ms-polarity-control', value='both', size='xs',
            data=[{'label': '+', 'value': 'positive'}, {'label': '−', 'value': 'negative'},
                  {'label': 'Both', 'value': 'both'}], **{'aria-label': 'MS polarity'}),
        dcc.Store(id='ms-polarity-owner'),
    ], id='ms-polarity-toolbar', className='plot-toolbar-group', style={'display': 'none'},
       title='Show positive, negative, or both MS modes. UV signals remain visible.')
