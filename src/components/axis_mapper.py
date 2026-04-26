"""
Axis Mapping Component for Publication-Quality Plots
Handles X, Y1 (multiple series), and Y2 axis selection and configuration
"""

from dash import html, dcc
import dash

# Okabe-Ito colorblind-friendly palette
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]

# Color schemes for each axis
SECTION_COLORS = {
    'x': {'main': '#2196F3', 'light': '#E3F2FD', 'border': '#1976D2'},
    'y1': {'main': '#FF9800', 'light': '#FFF3E0', 'border': '#F57C00'},
    'y2': {'main': '#4CAF50', 'light': '#E8F5E9', 'border': '#388E3C'},
}


def section_style(color_key, active=False):
    """Generate section styling"""
    colors = SECTION_COLORS[color_key]
    return {
        'padding': '12px',
        'marginBottom': '10px',
        'backgroundColor': colors['light'] if active else 'white',
        'border': f"2px solid {colors['border']}" if active else f"1px solid {colors['light']}",
        'borderRadius': '8px',
        'transition': 'all 0.2s'
    }


def selector_button_style(color_key, active=False):
    """Generate selector button styling"""
    colors = SECTION_COLORS[color_key]
    base_style = {
        'padding': '8px 14px',
        'fontSize': '11px',
        'borderRadius': '6px',
        'cursor': 'pointer',
        'marginRight': '6px',
        'marginBottom': '6px',
        'transition': 'all 0.15s'
    }
    
    if active:
        return {**base_style,
            'border': f"2px solid {colors['main']}",
            'backgroundColor': colors['light'],
            'color': colors['main'],
            'fontWeight': '600',
            'boxShadow': f"0 0 8px {colors['light']}"
        }
    else:
        return {**base_style,
            'border': '1px solid #CCC',
            'backgroundColor': '#F5F5F5',
            'color': '#666',
            'fontWeight': '500',
            'boxShadow': 'none'
        }


def create_axis_mapper_layout():
    """Create the axis mapping control panel for the toolbox"""
    return html.Div([
        html.Div([
            html.H3("Axis Mapping", style={'fontSize': '13px', 'fontWeight': '600', 'margin': '0 0 12px 0'}),
            
            # Data manipulation tools at the top
            html.Div([
                html.Button("↔️ Transpose", id='transpose-data', 
                           style={'padding': '5px 12px', 'fontSize': '10px', 'marginRight': '6px'}, 
                           title="Swap rows and columns"),
                html.Button("➕ Row", id='add-row', 
                           style={'padding': '5px 12px', 'fontSize': '10px', 'marginRight': '6px'}, 
                           title="Add a new row"),
                html.Button("➕ Column", id='add-column', 
                           style={'padding': '5px 12px', 'fontSize': '10px'}, 
                           title="Add a new column"),
            ], style={'marginBottom': '12px', 'display': 'flex', 'gap': '6px', 'paddingBottom': '12px', 'borderBottom': '1px solid #e0e0e0'}),
            
            # X-AXIS (Simplified!)
            html.Div([
                html.Div([
                    html.Span("X-Axis", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['x']['main']}),
                    html.Button("✕", id='clear-x', 
                               style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                      'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                      'backgroundColor': 'white'},
                               title="Clear X selection"),
                ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['x']['light']}"}),
                
                html.Div([
                    html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='x-label-input', value='X', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                ]),
                
                html.Div([
                    html.Label("Data:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                    html.Button("Select cells", id='btn-x-data', style=selector_button_style('x')),
                ]),
            ], id='x-section', style=section_style('x')),
            
            # Y1-AXIS
            html.Div([
                html.Div([
                    html.Span("Y-Axis (Primary)", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['y1']['main']}),
                    html.Button("✕", id='clear-y1', 
                               style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                      'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                      'backgroundColor': 'white'},
                               title="Clear Y1 selections"),
                ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['y1']['light']}"}),
                
                html.Div([
                    html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='y1-label-input', value='Y₁', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                ]),
                
                html.Div(id='y1-series-container'),
                
                html.Div([
                    html.Button("+ Series", id='add-y1-series', 
                               style={'padding': '5px 10px', 'fontSize': '10px', 'marginRight': '6px'}),
                    html.Button("− Series", id='remove-y1-series', 
                               style={'padding': '5px 10px', 'fontSize': '10px', 'marginRight': '6px'}),
                    html.Span(id='y1-count', children="1 series", style={'fontSize': '9px', 'color': '#999'}),
                ], style={'marginBottom': '10px', 'paddingTop': '8px', 'borderTop': '1px solid #EEE'}),
                
                html.Div([
                    html.Label("Error:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                    html.Button("Select cells", id='btn-y1-error', style=selector_button_style('y1')),
                ], style={'marginBottom': '10px'}),
                
                html.Div([
                    html.Label("Stats:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '6px', 'display': 'block'}),
                    dcc.Checklist(
                        id='y1-stats',
                        options=[
                            {'label': ' Mean ± SD', 'value': 'mean_sd'},
                            {'label': ' Mean ± SEM', 'value': 'mean_sem'},
                            {'label': ' Median ± IQR', 'value': 'median_iqr'},
                        ],
                        value=[],
                        style={'fontSize': '10px'}
                    ),
                    dcc.Checklist(
                        id='show-raw-points',
                        options=[{'label': ' Show raw points', 'value': 'show'}],
                        value=[],
                        style={'fontSize': '10px', 'marginTop': '4px'}
                    ),
                ]),
            ], id='y1-section', style=section_style('y1')),
            
            # Y2-AXIS
            html.Div([
                html.Div([
                    html.Span("Y₂-Axis (Secondary)", style={'fontSize': '12px', 'fontWeight': '600', 'color': SECTION_COLORS['y2']['main'], 'marginRight': '8px'}),
                    dcc.Checklist(
                        id='y2-enable',
                        options=[{'label': ' Enable', 'value': 'enable'}],
                        value=[],
                        inline=True,
                        style={'display': 'inline-block', 'fontSize': '10px'}
                    ),
                    html.Button("✕", id='clear-y2', 
                               style={'float': 'right', 'padding': '2px 6px', 'fontSize': '10px', 
                                      'border': '1px solid #CCC', 'borderRadius': '3px', 'cursor': 'pointer',
                                      'backgroundColor': 'white'},
                               title="Clear Y2 selections"),
                ], style={'marginBottom': '8px', 'paddingBottom': '6px', 'borderBottom': f"2px solid {SECTION_COLORS['y2']['light']}"}),
                
                html.Div([
                    html.Div([
                        html.Label("Label:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                        dcc.Input(id='y2-label-input', value='Y₂', style={'width': '100%', 'padding': '5px', 'fontSize': '10px', 'marginBottom': '8px'}),
                    ]),
                    html.Div([
                        html.Label("Data:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                        html.Button("Select cells", id='btn-y2-data', style=selector_button_style('y2')),
                    ], style={'marginBottom': '8px'}),
                    html.Div([
                        html.Label("Error:", style={'fontSize': '10px', 'fontWeight': '600', 'color': '#666', 'marginBottom': '4px'}),
                        html.Button("Select cells", id='btn-y2-error', style=selector_button_style('y2')),
                    ]),
                ], id='y2-controls', style={'display': 'none'}),
            ], id='y2-section', style=section_style('y2')),
            
            # PLOT TYPE — hidden; now controlled from Plot Settings panel (pt-plot-type)
            html.Div([
                dcc.RadioItems(
                    id='plot-type',
                    options=[
                        {'label': ' Bar', 'value': 'bar'},
                        {'label': ' Line', 'value': 'line'},
                        {'label': ' Scatter', 'value': 'scatter'}
                    ],
                    value='bar',
                    inline=True,
                ),
            ], style={'display': 'none'}),
            
            # TOOLS
            html.Div([
                html.Button("Save Map", id='save-mapping', 
                           style={'padding': '6px 12px', 'fontSize': '10px', 'width': '48%', 'marginRight': '4%'}),
                dcc.Download(id='download-mapping'),
                html.Button("Load Map", id='load-mapping', 
                           style={'padding': '6px 12px', 'fontSize': '10px', 'width': '48%'}),
                dcc.Upload(id='upload-mapping', style={'display': 'none'}),
                html.Button("Clear All", id='clear-all', 
                           style={'padding': '6px 12px', 'fontSize': '10px', 'width': '100%', 'marginTop': '8px'}),
            ]),
        ], style={'height': '100%', 'overflowY': 'auto', 'padding': '10px'}),
        
        # Stores for axis mapper state
        dcc.Store(id='pub-selections', data=get_empty_selections()),
        dcc.Store(id='active-selector', data=None),
        dcc.Store(id='y1-series-count', data=1),
        dcc.Store(id='plot-export-data'),
    ])


def get_empty_selections(y1_count=1):
    """Create empty selections structure"""
    return {
        'x': {'data': {'row_ids': [], 'column_id': None}},
        'y1': {'series': [{'row_ids': [], 'column_id': None} for _ in range(y1_count)], 
               'error': {'row_ids': [], 'column_id': None}},
        'y2': {'data': {'row_ids': [], 'column_id': None}, 
               'error': {'row_ids': [], 'column_id': None}},
        'y2_enabled': False
    }
