"""Precise axis controls populated from the active rendered figure."""
from dash import dcc, html
import dash_mantine_components as dmc
from services.axis_inspector import default_axis_option


def axis_inspector():
    return html.Div([
        dcc.Store(id='axis-inspector-reset'),
        dcc.Store(id='axis-inspector-view'),
        html.Div(id='axis-inspector-cards'),
        html.Div(id='axis-inspector-error', role='status', className='inspector-field-error'),
    ], className='axis-inspector')


def axis_cards(descriptors, settings, owner):
    cards = []
    for descriptor in descriptors:
        option = (settings.get('axis_overrides') or {}).get(
            descriptor['id'], default_axis_option(settings, descriptor['direction']))
        def component_id(field):
            return {'type':'axis-inspector-'+field, 'axis':descriptor['id'], 'owner':owner}
        automatic = option.get('mode', 'auto') == 'auto'
        cards.append(html.Div([
            html.Div([
                html.Span(descriptor['label'], className='axis-inspector-name'),
                html.Span('X axis' if descriptor['direction']=='x' else 'Y axis', className='axis-inspector-dimension'),
            ], className='axis-inspector-heading'),
            dmc.SegmentedControl(id=component_id('mode'), value=option.get('mode','auto'),
                data=[{'label':'Auto','value':'auto'},{'label':'Manual','value':'manual'}], fullWidth=True, size='xs'),
            html.Div([
                dmc.NumberInput(id=component_id('min'), label='Minimum', value=option.get('min'),
                    placeholder='Auto', disabled=automatic, debounce=True, clampBehavior='none', size='xs'),
                dmc.NumberInput(id=component_id('max'), label='Maximum', value=option.get('max'),
                    placeholder='Auto', disabled=automatic, debounce=True, clampBehavior='none', size='xs'),
            ], className='axis-inspector-bounds', style={'display':'grid','gridTemplateColumns':'1fr 1fr','gap':'8px'}),
            dmc.Select(id=component_id('scale'), label='Scale', value=option.get('scale','linear'),
                data=[{'label':'Linear','value':'linear'}, {'label':'Logarithmic','value':'log'}],
                allowDeselect=False, size='xs'),
        ], className='axis-inspector-card', style={'marginBottom':'14px'}))
    if not cards:
        return html.Div('Select a figure to edit its axes.', className='inspector-empty')
    return cards
