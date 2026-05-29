"""
Axis Mapping Component for Publication-Quality Plots
"""

from dash import html, dcc
import dash
import dash_mantine_components as dmc

OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]

SECTION_COLORS = {
    'x': {'main': '#2196F3', 'light': '#E3F2FD', 'border': '#1976D2'},
    'y1': {'main': '#FF9800', 'light': '#FFF3E0', 'border': '#F57C00'},
    'y2': {'main': '#4CAF50', 'light': '#E8F5E9', 'border': '#388E3C'},
}


def section_style(color_key, active=False):
    colors = SECTION_COLORS[color_key]
    return {
        'padding': '6px 8px',
        'marginBottom': '6px',
        'backgroundColor': colors['light'] if active else 'white',
        'border': f"2px solid {colors['border']}" if active else f"1px solid {colors['light']}",
        'borderRadius': '4px',
        'transition': 'all 0.15s'
    }


def selector_button_style(color_key, active=False):
    colors = SECTION_COLORS[color_key]
    base = {
        'padding': '4px 10px',
        'fontSize': '11px',
        'borderRadius': '4px',
        'cursor': 'pointer',
        'transition': 'all 0.15s'
    }
    if active:
        return {**base,
            'border': f"2px solid {colors['main']}",
            'backgroundColor': colors['light'],
            'color': colors['main'],
            'fontWeight': '600',
        }
    return {**base,
        'border': '1px solid #CCC',
        'backgroundColor': '#F5F5F5',
        'color': '#666',
        'fontWeight': '500',
    }


def create_axis_mapper_layout():
    return html.Div([
        # Data tools
        html.Div([
            html.Button("↔ Transpose", id='transpose-data',
                       style={'padding': '4px 10px', 'fontSize': '11px'}),
            html.Button("+ Row", id='add-row',
                       style={'padding': '4px 10px', 'fontSize': '11px'}),
            html.Button("+ Col", id='add-column',
                       style={'padding': '4px 10px', 'fontSize': '11px'}),
        ], style={'display': 'flex', 'gap': '6px', 'marginBottom': '10px'}),

        # X-Axis
        html.Div('X-Axis', className='toolbox-section-title'),
        html.Div([
            html.Div([
                html.Label('Label', className='form-label'),
                dmc.TextInput(id='x-label-input', value='X', size='xs', style={'width': '100%'}),
            ], style={'flex': '1'}),
            html.Div([
                html.Label('Data', className='form-label'),
                html.Button("Select cells", id='btn-x-data', style=selector_button_style('x')),
            ], style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
        html.Button("✕ Clear", id='clear-x',
            style={'padding': '2px 8px', 'fontSize': '10px', 'marginBottom': '10px',
                   'border': '1px solid #ccc', 'borderRadius': '3px', 'cursor': 'pointer',
                   'backgroundColor': 'white', 'color': '#999'}),

        # Y-Axis (Primary)
        html.Div('Y-Axis (Primary)', className='toolbox-section-title'),
        html.Div([
            html.Div([
                html.Label('Label', className='form-label'),
                dmc.TextInput(id='y1-label-input', value='Y1', size='xs', style={'width': '100%'}),
            ], style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
        html.Div(id='y1-series-container'),
        html.Div([
            html.Button("+ Series", id='add-y1-series',
                       style={'padding': '4px 10px', 'fontSize': '11px'}),
            html.Button("− Series", id='remove-y1-series',
                       style={'padding': '4px 10px', 'fontSize': '11px'}),
            html.Span(id='y1-count', children="1 series",
                      style={'fontSize': '11px', 'color': '#999'}),
        ], style={'display': 'flex', 'gap': '6px', 'alignItems': 'center', 'marginBottom': '6px'}),
        html.Div([
            html.Label('Error', className='form-label'),
            html.Button("Select cells", id='btn-y1-error', style=selector_button_style('y1')),
        ], style={'marginBottom': '6px'}),
        html.Div([
            dmc.CheckboxGroup(id='y1-stats', value=[], children=dmc.Stack([
                dmc.Checkbox(label='Mean ± SD', value='mean_sd'),
                dmc.Checkbox(label='Mean ± SEM', value='mean_sem'),
                dmc.Checkbox(label='Median ± IQR', value='median_iqr'),
            ], gap=4)),
            dmc.Switch(id='show-raw-points', label='Show raw points',
                       checked=False, size='sm', mt=2),
        ], style={'marginBottom': '6px'}),
        html.Button("✕ Clear", id='clear-y1',
            style={'padding': '2px 8px', 'fontSize': '10px', 'marginBottom': '10px',
                   'border': '1px solid #ccc', 'borderRadius': '3px', 'cursor': 'pointer',
                   'backgroundColor': 'white', 'color': '#999'}),

        # Y₂-Axis (Secondary)
        html.Div([
            html.Span('Y₂-Axis (Secondary)', style={'fontSize': '14px', 'fontWeight': '600', 'color': '#333'}),
            dmc.Switch(id='y2-enable', label='Enable', checked=False, size='sm',
                       style={'display': 'inline-block', 'marginLeft': '10px'}),
        ], className='toolbox-section-title'),
        html.Div([
            html.Div([
                html.Label('Label', className='form-label'),
                dmc.TextInput(id='y2-label-input', value='Y₂', size='xs', style={'width': '100%'}),
            ], style={'flex': '1', 'marginBottom': '6px'}),
            html.Div([
                html.Label('Data', className='form-label'),
                html.Button("Select cells", id='btn-y2-data', style=selector_button_style('y2')),
            ], style={'marginBottom': '6px'}),
            html.Div([
                html.Label('Error', className='form-label'),
                html.Button("Select cells", id='btn-y2-error', style=selector_button_style('y2')),
            ]),
        ], id='y2-controls', style={'display': 'none'}),
        html.Button("✕ Clear", id='clear-y2',
            style={'padding': '2px 8px', 'fontSize': '10px', 'marginBottom': '10px',
                   'border': '1px solid #ccc', 'borderRadius': '3px', 'cursor': 'pointer',
                   'backgroundColor': 'white', 'color': '#999'}),

        # Hidden plot type (controlled from Plot Settings)
        html.Div(dmc.RadioGroup(id='plot-type', value='bar', children=dmc.Group([
            dmc.Radio(label='Bar', value='bar'),
            dmc.Radio(label='Line', value='line'),
            dmc.Radio(label='Scatter', value='scatter'),
        ], gap='md')), style={'display': 'none'}),

        # Plot button
        html.Div('Plot', className='toolbox-section-title'),
        html.Button("Create Plot", id='create-plot-btn',
            style={'padding': '6px 12px', 'fontSize': '13px', 'fontWeight': '600',
                   'width': '100%', 'backgroundColor': '#1976D2', 'color': 'white',
                   'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer',
                   'marginBottom': '10px'}),

        # Tools
        html.Div('Tools', className='toolbox-section-title'),
        html.Div([
            html.Button("Save Map", id='save-mapping',
                style={'padding': '4px 10px', 'fontSize': '11px', 'flex': '1'}),
            dcc.Download(id='download-mapping'),
            html.Button("Load Map", id='load-mapping',
                style={'padding': '4px 10px', 'fontSize': '11px', 'flex': '1'}),
            dcc.Upload(id='upload-mapping', style={'display': 'none'}),
            html.Button("Clear All", id='clear-all',
                style={'padding': '4px 10px', 'fontSize': '11px', 'flex': '1'}),
        ], style={'display': 'flex', 'gap': '6px'}),

        # Stores
        dcc.Store(id='pub-selections', data=get_empty_selections()),
        dcc.Store(id='active-selector', data=None),
        dcc.Store(id='y1-series-count', data=1),
    ])


def get_empty_selections(y1_count=1):
    return {
        'x': {'data': {'row_ids': [], 'column_id': None}},
        'y1': {'series': [{'row_ids': [], 'column_id': None} for _ in range(y1_count)],
               'error': {'row_ids': [], 'column_id': None}},
        'y2': {'data': {'row_ids': [], 'column_id': None},
               'error': {'row_ids': [], 'column_id': None}},
        'y2_enabled': False
    }
