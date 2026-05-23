#!/usr/bin/env python3
"""
GeckoPlotter V2 - Clean Scientific Data Visualization
Run with: python app.py
"""

import os
import sys
import json
import logging

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import dash
from dash import dcc, html, dash_table, Input, Output, State, ClientsideFunction, clientside_callback
import plotly.graph_objects as go

if os.environ.get("GP_DEBUG", "") != "1":
    # Temporarily disable print suppression for debugging
    pass  # builtins.print = lambda *args, **kwargs: None

logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Import our modular components
from services.storage_manager import DataManager
from callbacks.upload_callbacks import register_upload_callbacks, register_clear_callbacks
from callbacks.viz_callbacks import register_viz_callbacks
from callbacks.file_tree_callbacks import register_file_tree_callbacks
from components.axis_mapper import create_axis_mapper_layout
from components.data_table_editor import create_data_table_editor
from callbacks.publication_callbacks import register_publication_callbacks
from callbacks.integration_callbacks import register_integration_callbacks
from callbacks.baseline_callbacks import register_baseline_callbacks
from callbacks.export_callbacks import register_export_callbacks
from callbacks.calibration_callbacks import register_calibration_callbacks

# App setup
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='src/assets')
app.config.suppress_callback_exceptions = True
app.title = 'GeckoPlotter'

# Global data manager
data_manager = DataManager()

# Type icons for file tree
TYPE_ICONS = {
    'table': '📊',
    'structured': '🧩',
    'image': '🖼️',
    'chromatogram': '🌊',
    'spectra': '📈',
    'uvvis_csv': '🧪',
    'text': '📄',
    'binary': '💾',
    'unknown': '❓',
}

def render_file_tree(records):
    """Render file tree from records."""
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    tree_items = []
    for record in records:
        icon = TYPE_ICONS.get(record.get('type'), TYPE_ICONS['unknown'])
        tree_items.append(
            html.Div(
                [
                    html.Span(icon, style={'marginRight': '8px'}),
                    html.Div(
                        [
                            html.Div(record.get('name'), style={'fontWeight': '500'}),
                            html.Div(
                                f"{record.get('type', 'unknown').capitalize()} · {record.get('size_display')}",
                                style={'fontSize': '12px', 'color': '#666'},
                            ),
                        ],
                    ),
                ],
                style={
                    'padding': '8px',
                    'cursor': 'pointer',
                    'borderRadius': '4px',
                    'margin': '2px 0',
                    'display': 'flex',
                    'alignItems': 'center',
                    'transition': 'background-color 0.2s',
                },
                className='file-tree-item',
                id=f"file-item-{record.get('id')}",
                **{'data-file-id': record.get('id')},
            )
        )
    return tree_items

# Clean layout with proper CSS classes and structure
app.layout = html.Div(
    [
        dcc.Store(id='resize-state', data={'mainSplit': 30, 'leftSplit': 50, 'rightSplit': 60}),
        dcc.Store(id='loaded-files', data=[]),
        dcc.Store(id='active-file', data=None),
        dcc.Store(id='file-ui-state', data={}),
        dcc.Store(id='active-tab', data='data-overview'),
        dcc.Store(id='view-mode', data='raw'),
        dcc.Store(id='auto-select-trigger', data=None),
        dcc.Store(id='active-plot-context', data=None),
        dcc.Store(id='current-plot-settings', data={}),
        dcc.Store(id='toolbox-tab', data='pub-plotter'),
        dcc.Store(id='dev-settings', data={'show': False}),
        dcc.Store(id='pub-data-store'),  # Store for publication plotter data
        dcc.Store(id='pub-plot-figure'),  # Store for the publication plot figure
        dcc.Store(id='pub-plot-trigger'),  # Trigger to update main plot
        dcc.Store(id='plot-export-data'),  # Export data from publication plot
        dcc.Store(id='peak-shared-selections', data={}),  # Shared selections for peak-analysis tab
        dcc.Store(id='cross-shared-selections', data={}),  # Shared selections for across-samples tab
        dcc.Store(id='peak-table-store', data=None),  # Mirror of peak-table data (JSON split) — always in layout
        dcc.Store(id='cross-sample-table-store', data=None),  # Mirror of cross-sample-table data (JSON split) — always in layout
        dcc.Dropdown(id='peak-group-selector', style={'display': 'none'}),  # Placeholder for dynamically created dropdown
        # Baseline integration stores (p-line drawing)
        dcc.Store(id='baseline-mode', data='navigate'),  # 'draw' | 'edit' | 'navigate'
        dcc.Store(id='selected-peak-idx', data=None),  # Index of peak being edited
        dcc.Store(id='clear-shapes-trigger', data=0),  # Counter to trigger shape clearing
        dcc.Store(id='peak-change-trigger', data=0),  # Counter to refresh tables/overlays after peak edits
        dcc.Store(id='plot-peak-click-store', data=None),  # Browser-side peak hit-test selection
        dcc.Store(id='manual-draw-line-store', data=None),  # Browser-side custom integration line
        dcc.Store(id='interaction-action-store', data=None),  # Last action for future undo/redo
        html.Button(id='plot-empty-click-trigger', n_clicks=0, style={'display': 'none'}),
        html.Div(id='clear-transient-shapes-output', style={'display': 'none'}),
        html.Div(id='selected-shapes-sync-output', style={'display': 'none'}),
        html.Div(id='dummy-output', style={'display': 'none'}),  # For clientside callbacks

        html.Div(
            id='main-container',
            className='app-container',
            children=[
                html.Header(
                    className='app-header',
                    children=[
                        html.Div(
                            className='app-logo',
                            children=[
                                html.Span('🦎', className='logo-icon'),
                                html.Span('GeckoPlotter'),
                            ],
                        ),
                        html.Div(style={'flex': 1}),
                        html.Div(
                            className='view-mode-toggle',
                            children=[
                                html.Button('Raw Data', id='raw-mode-btn', className='mode-btn active', n_clicks=0),
                                html.Button('Analysis Plot', id='analysis-mode-btn', className='mode-btn', n_clicks=0),
                            ],
                            style={'display': 'flex', 'gap': '5px'}
                        ),
                        # Hidden Dev View button (kept for callback compatibility)
                        html.Button('Dev View', id='toggle-dev-panel', style={'display': 'none'}),
                    ],
                ),

                html.Div(
                    className='content-wrapper',
                    children=[
                        html.Div(
                            id='left-column',
                            className='left-column',
                            style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '200px', 'width': '30%'},
                            children=[
                                html.Div(
                                    id='left-top-panel',
                                    className='panel',
                                    style={'height': '50%', 'display': 'flex', 'flexDirection': 'column', 'overflow': 'hidden'},
                                    children=[
                                        html.Div(
                                            className='panel-header',
                                            style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'},
                                            children=[
                                                html.Span('File Explorer'),
                                                html.Div(
                                                    style={'display': 'flex', 'gap': '4px'},
                                                    children=[
                                                        dcc.Upload(
                                                            id='upload-button',
                                                            children=html.Button(
                                                                '+',
                                                                className='btn btn-primary',
                                                                title='Upload files',
                                                                style={'padding': '2px 8px', 'fontSize': '14px', 'lineHeight': '1', 'minWidth': '28px'},
                                                            ),
                                                            multiple=True,
                                                        ),
                                                        html.Button(
                                                            '🗑',
                                                            id='clear-files-btn',
                                                            className='btn btn-secondary',
                                                            title='Clear all files',
                                                            style={'padding': '2px 6px', 'fontSize': '12px', 'lineHeight': '1', 'minWidth': '28px'},
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        dcc.Upload(
                                            id='drop-zone',
                                            multiple=True,
                                            disable_click=True,
                                            style={
                                                'flex': '1',
                                                'minHeight': '0',
                                                'overflow': 'hidden',
                                                'display': 'flex',
                                                'flexDirection': 'column',
                                                'border': '2px dashed transparent',
                                                'borderRadius': '4px',
                                                'transition': 'border-color 0.2s',
                                            },
                                            style_active={
                                                'border': '2px dashed #ff6b35',
                                                'backgroundColor': '#fff5f0',
                                            },
                                            children=html.Div(
                                                className='panel-content',
                                                style={
                                                    'flex': '1',
                                                    'overflowY': 'auto',
                                                    'minHeight': '0',
                                                },
                                                children=[
                                                    html.Div(
                                                        id='file-tree',
                                                        className='file-tree',
                                                        children=render_file_tree([]),
                                                    )
                                                ],
                                            ),
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id='left-vertical-divider',
                                    className='divider divider-vertical'
                                ),
                                html.Div(
                                    id='left-bottom-panel',
                                    className='panel',
                                    style={'height': '50%', 'display': 'flex', 'flexDirection': 'column'},
                                    children=[
                                        html.Div('Toolbox', className='panel-header'),
                                        html.Div(
                                            className='toolbox-tabs',
                                            children=[
                                                html.Button('Data Selector', id='pub-plotter-tab', className='toolbox-tab-button active', n_clicks=0),
                                                html.Button('Plot Settings', id='plot-tools-tab', className='toolbox-tab-button', n_clicks=0, style={'whiteSpace': 'nowrap'}),
                                                html.Button('Integration', id='integration-tab', className='toolbox-tab-button', n_clicks=0),
                                                html.Button('Export', id='export-tab', className='toolbox-tab-button', n_clicks=0),
                                            ],
                                            style={'display': 'flex', 'borderBottom': '1px solid #e0e0e0', 'backgroundColor': '#f8f9fa'}
                                        ),
                                        html.Div(
                                            className='panel-content toolbox-wrapper',
                                            style={'flex': '1', 'overflow': 'auto'},
                                            children=[
                                                # Publication Plotter Tab (NEW - Active by default)
                                                html.Div(
                                                    id='pub-plotter-container',
                                                    className='toolbox-tab-content active',
                                                    children=create_axis_mapper_layout(),
                                                ),
                                                # Plot Settings Tab
                                                html.Div(
                                                    id='plot-tools-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'none', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        # ── Dynamic Header ──
                                                        html.Div(id='pt-panel-header', children='Analysis Plot Settings',
                                                                 className='toolbox-section-title',
                                                                 style={'fontSize': '13px', 'fontWeight': '600', 'marginBottom': '8px',
                                                                        'padding': '4px 0', 'borderBottom': '1px solid #ddd'}),

                                                        # ── 0. Layout Mode (Raw only) ──
                                                        html.Div(id='pt-raw-layout-wrapper', children=[
                                                            html.Div('Trace Layout', className='toolbox-section-title'),
                                                            dcc.RadioItems(
                                                                id='pt-layout-mode',
                                                                options=[
                                                                    {'label': ' Superposed', 'value': 'overlay'},
                                                                    {'label': ' Separate plots', 'value': 'stacked'},
                                                                ],
                                                                value='overlay', inline=True,
                                                                style={'fontSize': '12px', 'marginBottom': '10px'},
                                                            ),
                                                        ], style={'display': 'none'}),

                                                        # ── 1. Plot Type (Analysis only) ──
                                                        html.Div(id='pt-plot-type-wrapper', children=[
                                                            html.Div('Plot Type', className='toolbox-section-title'),
                                                            dcc.RadioItems(
                                                                id='pt-plot-type',
                                                                options=[
                                                                    {'label': ' Bar', 'value': 'bar'},
                                                                    {'label': ' Line', 'value': 'line'},
                                                                    {'label': ' Scatter', 'value': 'scatter'},
                                                                ],
                                                                value='bar', inline=True,
                                                                style={'fontSize': '12px', 'marginBottom': '10px'},
                                                            ),
                                                        ]),

                                                        # ── 2. Axes (Both) ──
                                                        html.Div('Axes', className='toolbox-section-title'),
                                                        dcc.Checklist(id='pt-auto-range', options=[{'label': ' Auto range', 'value': 'auto'}],
                                                                      value=['auto'], style={'marginBottom': '6px', 'fontSize': '12px'}),
                                                        html.Div(id='pt-range-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('X min', className='form-label'),
                                                                          dcc.Input(id='pt-x-min', type='number', className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('X max', className='form-label'),
                                                                          dcc.Input(id='pt-x-max', type='number', className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}, id='pt-x-range-row'),
                                                            html.Div([
                                                                html.Div([html.Label('Y min', className='form-label'),
                                                                          dcc.Input(id='pt-y-min', type='number', className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Y max', className='form-label'),
                                                                          dcc.Input(id='pt-y-max', type='number', className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}, id='pt-y-range-row'),
                                                        ], style={'display': 'none'}),
                                                        html.Div([
                                                            html.Div([html.Label('X scale', className='form-label'),
                                                                      dcc.Dropdown(id='pt-x-scale', value='linear',
                                                                                   options=[{'label': 'Linear', 'value': 'linear'}, {'label': 'Log', 'value': 'log'}],
                                                                                   clearable=False, style={'fontSize': '12px'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Y scale', className='form-label'),
                                                                      dcc.Dropdown(id='pt-y-scale', value='linear',
                                                                                   options=[{'label': 'Linear', 'value': 'linear'}, {'label': 'Log', 'value': 'log'}],
                                                                                   clearable=False, style={'fontSize': '12px'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),

                                                        # ── 3. Theme & Colors (Analysis only for now) ──
                                                        html.Div(id='pt-theme-wrapper', children=[
                                                            html.Div('Theme & Colors', className='toolbox-section-title'),
                                                            html.Div([
                                                                html.Label('Theme', className='form-label'),
                                                                dcc.Dropdown(id='pt-theme', value='plotly_white',
                                                                             options=[{'label': t, 'value': t} for t in
                                                                                      ['plotly_white', 'simple_white', 'plotly', 'ggplot2', 'seaborn',
                                                                                       'plotly_dark', 'presentation', 'none']],
                                                                             clearable=False, style={'fontSize': '12px'}),
                                                            ], style={'marginBottom': '6px'}),
                                                        ]),
                                                        html.Div([
                                                            html.Label('Color palette', className='form-label'),
                                                            dcc.Dropdown(id='pt-palette', value='okabe_ito',
                                                                         options=[{'label': p.replace('_', ' ').title(), 'value': p} for p in
                                                                                  ['okabe_ito', 'plotly', 'd3', 'pastel']],
                                                                         clearable=False, style={'fontSize': '12px'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Plot bg', className='form-label'),
                                                                      dcc.Input(id='pt-bg-color', type='text', value='#ffffff',
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Paper bg', className='form-label'),
                                                                      dcc.Input(id='pt-paper-color', type='text', value='#ffffff',
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),

                                                        # ── 4. Traces ──
                                                        html.Div('Traces', className='toolbox-section-title'),
                                                        # Line width: both (raw traces + analysis line/scatter)
                                                        html.Div(id='pt-line-controls-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Line width', className='form-label'),
                                                                          dcc.Input(id='pt-line-width', type='number', value=1.5, min=0.5, max=5, step=0.5,
                                                                                    className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div(id='pt-line-style-cell', children=[
                                                                    html.Label('Line style', className='form-label'),
                                                                    dcc.Dropdown(id='pt-line-style', value='solid',
                                                                                 options=[{'label': s.title(), 'value': s} for s in
                                                                                          ['solid', 'dash', 'dot', 'dashdot']],
                                                                                 clearable=False, style={'fontSize': '12px'}),
                                                                ], style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        ]),
                                                        # Marker controls: analysis scatter/line only
                                                        html.Div(id='pt-marker-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Marker size', className='form-label'),
                                                                          dcc.Input(id='pt-marker-size', type='number', value=6, min=2, max=16, step=1,
                                                                                    className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Marker shape', className='form-label'),
                                                                          dcc.Dropdown(id='pt-marker-symbol', value='circle',
                                                                                       options=[{'label': s.title(), 'value': s} for s in
                                                                                                ['circle', 'square', 'diamond', 'cross', 'x',
                                                                                                 'triangle-up', 'triangle-down', 'star']],
                                                                                       clearable=False, style={'fontSize': '12px'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        ]),
                                                        # Opacity: both
                                                        html.Div([
                                                            html.Div([html.Label('Opacity', className='form-label'),
                                                                      dcc.Slider(id='pt-trace-opacity', min=0.1, max=1.0, step=0.1, value=1.0,
                                                                                 marks={0.1: '.1', 0.5: '.5', 1.0: '1'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        # Bar controls: analysis bar only
                                                        html.Div(id='pt-bar-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Bar gap', className='form-label'),
                                                                          dcc.Input(id='pt-bar-gap', type='number', value=0.2, min=0, max=1, step=0.05,
                                                                                    className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Group gap', className='form-label'),
                                                                          dcc.Input(id='pt-bar-group-gap', type='number', value=0.1, min=0, max=1, step=0.05,
                                                                                    className='form-input', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        ]),

                                                        # ── 5. Labels (Both) ──
                                                        html.Div('Labels', className='toolbox-section-title'),
                                                        html.Div([html.Label('Title', className='form-label'),
                                                                   dcc.Input(id='pt-title', type='text', placeholder='Plot title', className='form-input')],
                                                                 style={'marginBottom': '6px'}),

                                                        # ── 6. Typography (Both) ──
                                                        html.Div('Typography', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Font', className='form-label'),
                                                                      dcc.Dropdown(id='pt-font', value='Arial',
                                                                                   options=[{'label': f, 'value': f} for f in
                                                                                            ['Arial', 'Helvetica', 'Times New Roman', 'Courier New',
                                                                                             'Georgia', 'Verdana', 'Calibri', 'Computer Modern']],
                                                                                   clearable=False, style={'fontSize': '12px'})],
                                                                     style={'flex': '2'}),
                                                            html.Div([html.Label('Size', className='form-label'),
                                                                      dcc.Input(id='pt-font-size', type='number', value=12, min=8, max=24, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Title size', className='form-label'),
                                                                      dcc.Input(id='pt-title-font-size', type='number', value=14, min=10, max=32, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Tick size', className='form-label'),
                                                                      dcc.Input(id='pt-tick-font-size', type='number', value=10, min=6, max=18, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        dcc.Checklist(id='pt-bold-title', options=[{'label': ' Bold title', 'value': 'bold'}],
                                                                      value=['bold'], style={'fontSize': '12px', 'marginBottom': '10px'}),

                                                        # ── 7. Legend (Both) ──
                                                        html.Div('Legend', className='toolbox-section-title'),
                                                        dcc.Checklist(id='pt-show-legend', options=[{'label': ' Show legend', 'value': 'show'}],
                                                                      value=['show'], style={'fontSize': '12px', 'marginBottom': '6px'}),
                                                        html.Div(id='pt-legend-pos-wrapper', children=[
                                                            html.Label('Position', className='form-label'),
                                                            dcc.Dropdown(id='pt-legend-pos', value='top-right',
                                                                         options=[{'label': p.replace('-', ' ').title(), 'value': p}
                                                                                  for p in ['top-right', 'top-left', 'bottom-right', 'bottom-left']],
                                                                         clearable=False, style={'fontSize': '12px'}),
                                                        ], style={'marginBottom': '10px'}),

                                                        # ── 8. Grid & Frame (Both) ──
                                                        html.Div('Grid & Frame', className='toolbox-section-title'),
                                                        dcc.Checklist(id='pt-layout-opts',
                                                                      options=[
                                                                          {'label': ' Grid X', 'value': 'grid_x'},
                                                                          {'label': ' Grid Y', 'value': 'grid_y'},
                                                                          {'label': ' Tick marks', 'value': 'ticks'},
                                                                          {'label': ' Frame (box)', 'value': 'frame'},
                                                                      ],
                                                                      value=['grid_x', 'grid_y', 'ticks', 'frame'],
                                                                      style={'fontSize': '12px', 'marginBottom': '6px'},
                                                                      labelStyle={'display': 'block', 'marginBottom': '4px'}),
                                                        html.Div(id='pt-tick-grid-detail-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Tick direction', className='form-label'),
                                                                          dcc.Dropdown(id='pt-tick-dir', value='outside',
                                                                                       options=[{'label': d.title(), 'value': d} for d in ['outside', 'inside']],
                                                                                       clearable=False, style={'fontSize': '12px'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Grid style', className='form-label'),
                                                                          dcc.Dropdown(id='pt-grid-style', value='solid',
                                                                                       options=[{'label': s.title(), 'value': s} for s in ['solid', 'dash', 'dot']],
                                                                                       clearable=False, style={'fontSize': '12px'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        ]),
                                                    ],
                                                ),
                                                # Integration Tab
                                                html.Div(
                                                    id='integration-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'none', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        # ── Manual Baseline Integration ──
                                                        html.Div('Manual Integration', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Button('Draw', id='baseline-draw-btn', className='btn btn-secondary',
                                                                        title='Draw baseline between two points',
                                                                        style={'padding': '4px 10px', 'fontSize': '12px'}),
                                                            html.Button('Edit', id='baseline-edit-btn', className='btn btn-secondary',
                                                                        title='Edit existing baseline',
                                                                        style={'display': 'none'}),
                                                            html.Button('Nav', id='baseline-nav-btn', className='btn btn-secondary',
                                                                        title='Pan / zoom (default)',
                                                                        style={'display': 'none'}),
                                                            html.Button('Clear', id='baseline-clear-btn', className='btn btn-secondary',
                                                                        title='Delete selected peak, or all manual peaks if none is selected',
                                                                        style={'padding': '4px 10px', 'fontSize': '12px'}),
                                                        ], style={'display': 'flex', 'gap': '4px', 'marginBottom': '6px', 'flexWrap': 'wrap'}),
                                                        html.Div([
                                                            dcc.Checklist(
                                                                id='easy-integration',
                                                                options=[{'label': ' Easy (baseline → y=0)', 'value': 'easy'}],
                                                                value=['easy'],
                                                                style={'fontSize': '12px'},
                                                                labelStyle={'display': 'inline-flex', 'alignItems': 'center'},
                                                            ),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div('Draw: off',
                                                                 id='baseline-mode-indicator',
                                                                 style={'fontSize': '11px', 'color': '#666', 'marginBottom': '10px'}),
                                                        html.Div(id='manual-peak-table-container', style={'marginBottom': '10px'}),
                                                        html.Hr(style={'margin': '10px 0', 'borderColor': '#e0e0e0'}),
                                                        # ── Auto Peak Detection ──
                                                        html.Div('Signal Processing', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Smooth window', className='form-label'),
                                                                      dcc.Input(id='int-smooth-window', type='number', value=11, min=3, max=51, step=2,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Poly order', className='form-label'),
                                                                      dcc.Input(id='int-smooth-poly', type='number', value=3, min=1, max=5, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div('Baseline', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Method', className='form-label'),
                                                            dcc.Dropdown(id='int-baseline-method', value='snip',
                                                                         options=[{'label': m, 'value': m} for m in ['snip', 'polynomial', 'none']],
                                                                         clearable=False, style={'fontSize': '12px'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Iterations', className='form-label'),
                                                                      dcc.Input(id='int-baseline-iter', type='number', value=40, min=5, max=100, step=5,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Poly order', className='form-label'),
                                                                      dcc.Input(id='int-baseline-poly', type='number', value=5, min=1, max=10, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        html.Div('Peak Detection', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Threshold', className='form-label'),
                                                                      dcc.Input(id='int-peak-threshold', type='number', value=0.01, min=0.001, max=1, step=0.001,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Slope cutoff', className='form-label'),
                                                                      dcc.Input(id='int-slope-threshold', type='number', value=0.001, min=0.0001, max=0.1, step=0.0001,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Extension', className='form-label'),
                                                                      dcc.Input(id='int-extension', type='number', value=1.1, min=1.0, max=2.0, step=0.05,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Min width (pts)', className='form-label'),
                                                                      dcc.Input(id='int-min-width', type='number', value=3, min=1, max=20, step=1,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        html.Div([
                                                            html.Button('Detect Peaks', id='int-detect-btn', className='btn btn-primary',
                                                                        style={'marginRight': '8px'}),
                                                            html.Button('Clear Detected', id='int-clear-btn', className='btn btn-secondary',
                                                                        title='Remove detected peaks only'),
                                                        ], style={'display': 'flex', 'marginBottom': '6px'}),
                                                        dcc.Checklist(id='int-display-opts',
                                                                      options=[
                                                                          {'label': ' Show baseline', 'value': 'baseline'},
                                                                          {'label': ' Show peak fills', 'value': 'peaks'},
                                                                          {'label': ' Show corrected signal', 'value': 'corrected'},
                                                                      ],
                                                                      value=['peaks'],
                                                                      style={'fontSize': '12px'},
                                                                      labelStyle={'display': 'block', 'marginBottom': '4px'}),
                                                    ],
                                                ),
                                                # Export Tab
                                                html.Div(
                                                    id='export-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'none', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        html.Div('Figure Export', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Format', className='form-label'),
                                                            dcc.Dropdown(id='exp-fig-format', value='png',
                                                                         options=[{'label': f, 'value': f} for f in ['png', 'svg', 'html', 'pdf']],
                                                                         clearable=False, style={'fontSize': '12px'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Width (px)', className='form-label'),
                                                                      dcc.Input(id='exp-width', type='number', value=800, min=400, max=2400, step=100,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Height (px)', className='form-label'),
                                                                      dcc.Input(id='exp-height', type='number', value=500, min=300, max=1600, step=100,
                                                                                className='form-input', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Label('DPI scale', className='form-label'),
                                                            dcc.Slider(id='exp-dpi', min=1, max=6, step=1, value=3,
                                                                       marks={1: '1x', 2: '2x', 3: '3x', 4: '4x', 6: '6x'}),
                                                        ], style={'marginBottom': '10px'}),
                                                        html.Button('Export Figure', id='exp-fig-btn', className='btn btn-primary',
                                                                    style={'width': '100%', 'marginBottom': '10px'}),
                                                        dcc.Download(id='exp-fig-download'),
                                                        html.Div('Data Export', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Format', className='form-label'),
                                                            dcc.Dropdown(id='exp-data-format', value='csv',
                                                                         options=[{'label': f.upper(), 'value': f} for f in ['csv', 'xlsx', 'json']],
                                                                         clearable=False, style={'fontSize': '12px'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Button('Export Table Data', id='exp-data-btn', className='btn btn-primary',
                                                                    style={'width': '100%', 'marginBottom': '6px'}),
                                                        html.Button('Export Peak Results', id='exp-peaks-btn', className='btn btn-secondary',
                                                                    style={'width': '100%', 'marginBottom': '6px'}),
                                                        html.Button('Export Calibration', id='exp-cal-btn', className='btn btn-secondary',
                                                                    style={'width': '100%', 'marginBottom': '10px'}),
                                                        dcc.Download(id='exp-data-download'),
                                                        html.Div('Session', className='toolbox-section-title'),
                                                        html.Button('Save Session', id='exp-session-btn', className='btn btn-secondary',
                                                                    style={'width': '100%', 'marginBottom': '6px'}),
                                                        dcc.Upload(html.Button('Load Session', className='btn btn-secondary',
                                                                               style={'width': '100%'}),
                                                                   id='exp-session-upload', style={'width': '100%', 'marginBottom': '6px'}),
                                                        dcc.Download(id='exp-session-download'),
                                                    ],
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            id='main-divider',
                            className='divider divider-horizontal'
                        ),
                        html.Div(
                            id='right-column',
                            className='right-column',
                            style={'display': 'flex', 'flexDirection': 'column', 'width': '70%'},
                            children=[
                                html.Div(
                                    id='right-top-panel',
                                    className='panel content-panel',
                                    style={'display': 'flex', 'flexDirection': 'column', 'overflow': 'hidden'},
                                    children=[
                                        html.Div(
                                            className='panel-content viz-container',
                                            children=[
                                                dcc.Loading(
                                                    id='main-plot-loading',
                                                    type='circle',
                                                    color='#ff6b35',
                                                    delay_show=350,
                                                    parent_className='loading-wrapper',
                                                    children=dcc.Graph(
                                                        id='main-plot',
                                                        figure=go.Figure(
                                                            layout=go.Layout(
                                                                xaxis={'visible': False},
                                                                yaxis={'visible': False},
                                                                template='plotly_white',
                                                                dragmode='zoom',
                                                                uirevision='main-plot',
                                                                autosize=True,
                                                                margin=dict(l=50, r=20, t=30, b=40),
                                                                annotations=[dict(
                                                                    text='Upload files to start visualizing data',
                                                                    xref='paper', yref='paper',
                                                                    x=0.5, y=0.5, showarrow=False,
                                                                    font=dict(size=16, color='#999'),
                                                                )],
                                                            )
                                                        ),
                                                        responsive=True,
                                                        style={'width': '100%', 'height': '100%'},
                                                        config={
                                                            'responsive': True,
                                                            'displayModeBar': False,
                                                            'displaylogo': False,
                                                            'doubleClick': 'reset+autosize',
                                                            'scrollZoom': True,
                                                            'edits': {'shapePosition': True},
                                                        },
                                                    )
                                                )
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id='right-vertical-divider',
                                    className='divider divider-vertical'
                                ),
                                html.Div(
                                    id='right-bottom-panel',
                                    className='panel content-panel',
                                    style={'display': 'flex', 'flexDirection': 'column', 'overflow': 'hidden'},
                                    children=[
                                        html.Div(
                                            className='panel-content',
                                            style={'display': 'flex', 'flexDirection': 'column', 'height': '100%'},
                                            children=[
                                                # Tab Headers (moved up, no panel header)
                                                html.Div([
                                                    html.Button("Data Overview", id="data-overview-tab", className="tab-button active", n_clicks=0, style={'display': 'inline-block', 'marginRight': '10px'}),
                                                    html.Button("Peak Analysis", id="peak-analysis-tab", className="tab-button", n_clicks=0, style={'display': 'inline-block', 'marginRight': '10px'}),
                                                    html.Button("Across Samples", id="across-samples-tab", className="tab-button", n_clicks=0, style={'display': 'inline-block', 'marginRight': '10px'}),
                                                    html.Button("Metadata", id="metadata-tab", className="tab-button", n_clicks=0, style={'display': 'inline-block', 'marginRight': '10px'}),
                                                    html.Button("Calibration", id="calibration-tab", className="tab-button", n_clicks=0, style={'display': 'inline-block', 'marginRight': '10px'}),
                                                ], className="tab-header", style={
                                                    'display': 'flex',
                                                    'borderBottom': '1px solid #e0e0e0',
                                                    'backgroundColor': '#f8f9fa',
                                                    'padding': '0',
                                                    'gap': '10px',
                                                    'marginBottom': '0'
                                                }),
                                                
                                                # Tab Content Container
                                                html.Div([
                                                    # Data Overview Tab (Table Display)
                                                    html.Div(id="data-overview-content", className="tab-content active", style={
                                                        'display': 'block',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(id='mode-indicator', style={
                                                            'padding': '6px 10px', 'fontSize': '11px', 'textAlign': 'center',
                                                            'backgroundColor': '#FFF8E1', 'marginBottom': '8px', 'borderRadius': '4px',
                                                            'minHeight': '20px',
                                                        }),
                                                        html.Div(id='table-editor-container', children=[
                                                            # Empty pub-table must exist at startup so callbacks
                                                            # that reference it don't crash before a file is loaded.
                                                            html.Div([
                                                                dash_table.DataTable(
                                                                    id='pub-table',
                                                                    columns=[],
                                                                    data=[],
                                                                    cell_selectable=True,
                                                                    column_selectable='single',
                                                                    style_table={'display': 'none'},
                                                                ),
                                                                html.Div(
                                                                    [
                                                                        html.Span('📊', className='empty-state__icon'),
                                                                        html.H4('Select a file to view data', className='empty-state__title'),
                                                                        html.P(
                                                                            'Choose a dataset from the File Explorer to display it as a table.',
                                                                            className='empty-state__subtitle'
                                                                        ),
                                                                    ],
                                                                    className='empty-state'
                                                                ),
                                                            ])
                                                        ])
                                                    ]),
                                                    
                                                    # Peak Analysis Tab
                                                    html.Div(id="peak-analysis-content", className="tab-content", style={
                                                        'display': 'none',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(id='peak-analysis-container', children=[
                                                            # peak-table: data updated in-place by tab_callbacks
                                                            dash_table.DataTable(
                                                                id='peak-table',
                                                                columns=[], data=[],
                                                                editable=True,
                                                                cell_selectable=True,
                                                                column_selectable='single',
                                                                row_deletable=True,
                                                                sort_action='native',
                                                                style_table={'display': 'none'},
                                                                style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': '11px', 'fontFamily': 'monospace', 'minWidth': '80px', 'whiteSpace': 'normal'},
                                                                style_header={'backgroundColor': '#37474F', 'color': 'white', 'fontWeight': '600', 'fontSize': '11px', 'padding': '10px', 'cursor': 'pointer', 'textDecoration': 'underline dotted', 'textUnderlineOffset': '3px'},
                                                                style_header_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data={'border': '1px solid #e0e0e0'},
                                                                style_cell_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            ),
                                                        ])
                                                    ]),

                                                    # Across Samples Tab
                                                    html.Div(id="across-samples-content", className="tab-content", style={
                                                        'display': 'none',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(id='across-samples-container', children=[
                                                            # cross-sample-table: data updated in-place by tab_callbacks
                                                            dash_table.DataTable(
                                                                id='cross-sample-table',
                                                                columns=[], data=[],
                                                                editable=True,
                                                                cell_selectable=True,
                                                                column_selectable='single',
                                                                row_deletable=True,
                                                                sort_action='native',
                                                                style_table={'display': 'none'},
                                                                style_cell={'textAlign': 'center', 'padding': '6px', 'fontSize': '11px', 'fontFamily': 'monospace', 'minWidth': '80px', 'whiteSpace': 'normal'},
                                                                style_header={'backgroundColor': '#37474F', 'color': 'white', 'fontWeight': '600', 'fontSize': '11px', 'padding': '10px', 'cursor': 'pointer', 'textDecoration': 'underline dotted', 'textUnderlineOffset': '3px'},
                                                                style_header_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data={'border': '1px solid #e0e0e0'},
                                                                style_cell_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            ),
                                                            html.P("Load multiple bundles to compare peaks across samples",
                                                                  style={'color': '#666', 'textAlign': 'center', 'padding': '20px'})
                                                        ])
                                                    ]),
                                                    
                                                    # Metadata Tab
                                                    html.Div(id="metadata-content", className="tab-content", style={
                                                        'display': 'none',
                                                        'padding': '0',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(
                                                            id='metadata-container',
                                                            style={'padding': '15px', 'width': '100%', 'boxSizing': 'border-box'},
                                                            children=[
                                                                html.Div(
                                                                    [
                                                                        html.Span('🦎', className='empty-state__icon'),
                                                                        html.H4('Select a file to view metadata', className='empty-state__title'),
                                                                        html.P(
                                                                            'Choose a dataset from the file explorer to view its metadata and details.',
                                                                            className='empty-state__subtitle'
                                                                        ),
                                                                    ],
                                                                    className='empty-state'
                                                                )
                                                            ]
                                                        )
                                                    ]),
                                                    
                                                    # Calibration Tab
                                                    html.Div(id="calibration-content", className="tab-content", style={
                                                        'display': 'none',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(id='calibration-container', children=[
                                                            # Model setup
                                                            html.Div([
                                                                html.Div('Create Calibration Model', style={
                                                                    'fontWeight': 'bold', 'fontSize': '14px', 'marginBottom': '10px'}),
                                                                html.Div([
                                                                    html.Div([html.Label('Analyte name', className='form-label'),
                                                                              dcc.Input(id='cal-analyte-name', type='text',
                                                                                        placeholder='e.g. Caffeine',
                                                                                        className='form-input', style={'width': '100%'})],
                                                                             style={'flex': '2'}),
                                                                    html.Div([html.Label('Units', className='form-label'),
                                                                              dcc.Input(id='cal-units', type='text',
                                                                                        placeholder='e.g. mg/mL',
                                                                                        className='form-input', style={'width': '100%'})],
                                                                             style={'flex': '1'}),
                                                                ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                                                                html.Div([
                                                                    html.Div([html.Label('Fit type', className='form-label'),
                                                                              dcc.Dropdown(id='cal-fit-type', value='linear',
                                                                                           options=[{'label': t.title(), 'value': t}
                                                                                                    for t in ['linear', 'quadratic', 'power']],
                                                                                           clearable=False, style={'fontSize': '12px'})],
                                                                             style={'flex': '1'}),
                                                                    html.Div([html.Label('Peak group', className='form-label'),
                                                                              dcc.Dropdown(id='cal-peak-group', placeholder='Select peak group...',
                                                                                           style={'fontSize': '12px'})],
                                                                             style={'flex': '1'}),
                                                                ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                                                                dcc.Checklist(id='cal-force-zero',
                                                                              options=[{'label': ' Force through origin', 'value': 'zero'}],
                                                                              value=[], style={'fontSize': '12px', 'marginBottom': '8px'}),
                                                                html.Button('Create Model', id='cal-create-btn', className='btn btn-primary',
                                                                            style={'width': '100%', 'marginBottom': '15px'}),
                                                            ], style={'padding': '12px', 'backgroundColor': '#f8f9fa',
                                                                      'borderRadius': '6px', 'marginBottom': '15px'}),

                                                            # Standards table
                                                            html.Div([
                                                                html.Div('Standards', style={
                                                                    'fontWeight': 'bold', 'fontSize': '14px', 'marginBottom': '10px'}),
                                                                html.Div([
                                                                    html.Label('Active model', className='form-label'),
                                                                    dcc.Dropdown(id='cal-active-model', placeholder='No models created yet',
                                                                                 style={'fontSize': '12px', 'marginBottom': '8px'}),
                                                                ]),
                                                                html.Div([
                                                                    html.Div([html.Label('Sample', className='form-label'),
                                                                              dcc.Input(id='cal-std-sample', type='text',
                                                                                        placeholder='Sample name',
                                                                                        className='form-input', style={'width': '100%'})],
                                                                             style={'flex': '2'}),
                                                                    html.Div([html.Label('Conc.', className='form-label'),
                                                                              dcc.Input(id='cal-std-conc', type='number',
                                                                                        placeholder='0.0',
                                                                                        className='form-input', style={'width': '100%'})],
                                                                             style={'flex': '1'}),
                                                                    html.Div([html.Label('Area', className='form-label'),
                                                                              dcc.Input(id='cal-std-area', type='number',
                                                                                        placeholder='0.0',
                                                                                        className='form-input', style={'width': '100%'})],
                                                                             style={'flex': '1'}),
                                                                ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                                                                html.Div([
                                                                    html.Button('Add Standard', id='cal-add-std-btn',
                                                                                className='btn btn-primary', style={'marginRight': '8px'}),
                                                                    html.Button('Fit Model', id='cal-fit-btn',
                                                                                className='btn btn-secondary', style={'marginRight': '8px'}),
                                                                    html.Button('Predict All', id='cal-predict-btn',
                                                                                className='btn btn-secondary'),
                                                                ], style={'display': 'flex', 'marginBottom': '10px'}),
                                                                html.Div(id='cal-standards-table', children=[]),
                                                            ], style={'marginBottom': '15px'}),

                                                            # Calibration curve display
                                                            html.Div([
                                                                html.Div('Calibration Curve', style={
                                                                    'fontWeight': 'bold', 'fontSize': '14px', 'marginBottom': '10px'}),
                                                                dcc.Graph(id='cal-curve-graph',
                                                                          figure=go.Figure(layout=go.Layout(
                                                                              template='plotly_white', autosize=True,
                                                                              title='Create a model and add standards')),
                                                                          responsive=True,
                                                                          style={'width': '100%', 'height': '300px'}),
                                                                html.Div(id='cal-results-info',
                                                                         style={'fontSize': '12px', 'padding': '8px',
                                                                                'backgroundColor': '#f8f9fa', 'borderRadius': '4px',
                                                                                'marginTop': '8px'}),
                                                            ]),
                                                        ])
                                                    ])
                                                ], style={'flex': '1', 'overflow': 'hidden'})
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                    style={'display': 'flex'},
                ),

                html.Div(
                    className='status-bar',
                    children=[
                        html.Span(id='status-text', children='Ready'),
                        html.Div(style={'flex': 1}),
                        html.Span(id='file-info', children='No files loaded'),
                        html.Button(
                            'Clear Cache',
                            id='clear-cache-btn',
                            title='Delete saved settings and cached state',
                            style={
                                'background': 'none', 'border': '1px solid #555',
                                'color': '#999', 'fontSize': '11px', 'padding': '1px 8px',
                                'cursor': 'pointer', 'borderRadius': '3px', 'marginLeft': '10px',
                            },
                        ),
                    ],
                ),

                html.Div(
                    id='dev-panel',
                    className='dev-panel',
                    children=[
                        html.Div('Developer Diagnostics', className='dev-panel-header'),
                        html.Pre('[]', id='dev-summary', className='dev-summary'),
                    ],
                    style={'display': 'none'},  # Hidden by default
                ),
            ],
        ),

        html.Div(id='resize-init-trigger', style={'display': 'none'}),
    ]
)

# Register callbacks
from callbacks.tab_callbacks import register_tab_callbacks
from callbacks.table_editor_callbacks import register_table_editor_callbacks
from callbacks.context_callbacks import register_context_callbacks
from callbacks.plot_settings_callbacks import register_plot_settings_callbacks

register_upload_callbacks(app, data_manager)
register_clear_callbacks(app, data_manager)
register_viz_callbacks(app, data_manager)
register_file_tree_callbacks(app, data_manager)
register_tab_callbacks(app, data_manager)
register_table_editor_callbacks(app, data_manager)
register_context_callbacks(app, data_manager)
register_publication_callbacks(app, data_manager)
register_integration_callbacks(app, data_manager)
register_baseline_callbacks(app, data_manager)
register_export_callbacks(app, data_manager)
register_calibration_callbacks(app, data_manager)
register_plot_settings_callbacks(app, data_manager)

def _toolbox_content_style(tab_name: str, active_tab: str) -> dict:
    """Return the correct style for a toolbox tab content container."""
    is_active = tab_name == active_tab
    style_map = {
        'pub-plotter': {
            'display': 'block' if is_active else 'none',
        },
        'plot-tools': {
            'display': 'block' if is_active else 'none',
            'padding': '10px',
            'overflowY': 'auto',
            'maxHeight': 'calc(100% - 40px)',
        },
        'integration': {
            'display': 'block' if is_active else 'none',
            'padding': '10px',
            'overflowY': 'auto',
            'maxHeight': 'calc(100% - 40px)',
        },
        'export': {
            'display': 'block' if is_active else 'none',
            'padding': '10px',
            'overflowY': 'auto',
            'maxHeight': 'calc(100% - 40px)',
        },
    }
    return style_map[tab_name]


def _analysis_content_style(tab_name: str, active_tab: str) -> dict:
    """Return the correct style for an analysis tab content container.

    Only toggles display. Height/overflow are handled by the panel CSS
    and the resize handler — we must NOT override them here.
    """
    is_active = tab_name == active_tab
    return {
        'display': 'block' if is_active else 'none',
        'height': '100%',
        'overflowY': 'auto',
        'padding': '0' if tab_name == 'metadata' else '15px',
    }


@app.callback(
    Output('toolbox-tab', 'data'),
    [Input('pub-plotter-tab', 'n_clicks'),
     Input('plot-tools-tab', 'n_clicks'),
     Input('integration-tab', 'n_clicks'),
     Input('export-tab', 'n_clicks')],
    prevent_initial_call=True,
)
def update_toolbox_tab(_, __, ___, ____):
    """Update toolbox-tab from the clicked button.

    This replaces brittle clientside DOM mutation with a plain Dash callback.
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    tab_map = {
        'pub-plotter-tab': 'pub-plotter',
        'plot-tools-tab': 'plot-tools',
        'integration-tab': 'integration',
        'export-tab': 'export',
    }
    return tab_map.get(triggered_id, dash.no_update)


@app.callback(
    [Output('pub-plotter-tab', 'className'),
     Output('plot-tools-tab', 'className'),
     Output('integration-tab', 'className'),
     Output('export-tab', 'className'),
     Output('pub-plotter-container', 'style'),
     Output('plot-tools-container', 'style'),
     Output('integration-container', 'style'),
     Output('export-container', 'style')],
    Input('toolbox-tab', 'data'),
)
def sync_toolbox_tab_ui(toolbox_tab):
    """Keep toolbox buttons and content in sync with the store."""
    active_tab = toolbox_tab or 'pub-plotter'
    return (
        'toolbox-tab-button active' if active_tab == 'pub-plotter' else 'toolbox-tab-button',
        'toolbox-tab-button active' if active_tab == 'plot-tools' else 'toolbox-tab-button',
        'toolbox-tab-button active' if active_tab == 'integration' else 'toolbox-tab-button',
        'toolbox-tab-button active' if active_tab == 'export' else 'toolbox-tab-button',
        _toolbox_content_style('pub-plotter', active_tab),
        _toolbox_content_style('plot-tools', active_tab),
        _toolbox_content_style('integration', active_tab),
        _toolbox_content_style('export', active_tab),
    )

# Clientside callback for resize functionality
clientside_callback(
    ClientsideFunction(namespace='resize', function_name='initializeResizeHandlers'),
    Output('resize-init-trigger', 'children'),
    Input('resize-init-trigger', 'id'),
)

# File-tree selection highlighting is now rendered server-side from active-file.

@app.callback(
    Output('active-tab', 'data'),
    [Input('data-overview-tab', 'n_clicks'),
     Input('peak-analysis-tab', 'n_clicks'),
     Input('across-samples-tab', 'n_clicks'),
     Input('metadata-tab', 'n_clicks'),
     Input('calibration-tab', 'n_clicks')],
    prevent_initial_call=True,
)
def update_active_tab(_, __, ___, ____, _____):
    """Update active-tab from the clicked analysis tab button."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    tab_map = {
        'data-overview-tab': 'data-overview',
        'peak-analysis-tab': 'peak-analysis',
        'across-samples-tab': 'across-samples',
        'metadata-tab': 'metadata',
        'calibration-tab': 'calibration',
    }
    return tab_map.get(triggered_id, dash.no_update)


@app.callback(
    [Output('data-overview-tab', 'className'),
     Output('peak-analysis-tab', 'className'),
     Output('across-samples-tab', 'className'),
     Output('metadata-tab', 'className'),
     Output('calibration-tab', 'className'),
     Output('data-overview-content', 'style'),
     Output('peak-analysis-content', 'style'),
     Output('across-samples-content', 'style'),
     Output('metadata-content', 'style'),
     Output('calibration-content', 'style')],
    Input('active-tab', 'data'),
)
def sync_active_tab_ui(active_tab):
    """Keep analysis tab buttons and content in sync with the store."""
    selected_tab = active_tab or 'data-overview'
    return (
        'tab-button active' if selected_tab == 'data-overview' else 'tab-button',
        'tab-button active' if selected_tab == 'peak-analysis' else 'tab-button',
        'tab-button active' if selected_tab == 'across-samples' else 'tab-button',
        'tab-button active' if selected_tab == 'metadata' else 'tab-button',
        'tab-button active' if selected_tab == 'calibration' else 'tab-button',
        _analysis_content_style('data-overview', selected_tab),
        _analysis_content_style('peak-analysis', selected_tab),
        _analysis_content_style('across-samples', selected_tab),
        _analysis_content_style('metadata', selected_tab),
        _analysis_content_style('calibration', selected_tab),
    )


@app.callback(
    Output('view-mode', 'data'),
    [Input('raw-mode-btn', 'n_clicks'),
     Input('analysis-mode-btn', 'n_clicks')],
    prevent_initial_call=True,
)
def update_view_mode(_, __):
    """Update view-mode from the clicked toggle button."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    return 'analysis' if triggered_id == 'analysis-mode-btn' else 'raw'


@app.callback(
    [Output('raw-mode-btn', 'className'),
     Output('analysis-mode-btn', 'className')],
    Input('view-mode', 'data'),
)
def sync_view_mode_ui(view_mode):
    """Keep the view-mode buttons in sync with the store."""
    is_raw = (view_mode or 'raw') == 'raw'
    return (
        'mode-btn active' if is_raw else 'mode-btn',
        'mode-btn' if is_raw else 'mode-btn active',
    )

# Status update callbacks
@app.callback(
    [Output('status-text', 'children'),
     Output('file-info', 'children')],
    [Input('loaded-files', 'data')],
)
def update_status(files):
    if not files:
        return 'Ready', 'No files loaded'

    file_count = len(files)
    return f'Loaded {file_count} file{"s" if file_count != 1 else ""}', f'{file_count} file{"s" if file_count != 1 else ""} available'

if __name__ == '__main__':
    print("🚀 Starting GeckoPlotter V2...")
    print("📊 Upload TXT chromatograms or CSV UV-Vis files to get started!")
    app.run(debug=True, port=8052)
