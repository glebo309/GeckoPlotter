"""Consistent polarity buttons for single-spectrum analysis views."""
from dash import html
import dash_mantine_components as dmc


def create_spectrum_polarity_control(prefix):
    wrapper_id = prefix + ('-polarity-wrapper' if prefix == 'peak-mass' else '-polarity-toggle-wrapper')
    label = {'ms': 'MS scan polarity', 'eic': 'EIC polarity', 'peak-mass': 'Peak mass polarity'}[prefix]
    return html.Div(
        dmc.SegmentedControl(id=prefix + '-polarity-toggle', value='positive', size='xs',
            data=[{'label': '+', 'value': 'positive', 'disabled': True},
                  {'label': '−', 'value': 'negative', 'disabled': True}],
            **{'aria-label': label}),
        id=wrapper_id, className='plot-toolbar-group',
        style={'display': 'none', 'alignItems': 'center', 'gap': '2px'},
        title='No mass spectral data available')
