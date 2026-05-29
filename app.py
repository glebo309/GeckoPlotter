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
import dash_mantine_components as dmc
import plotly.graph_objects as go

if os.environ.get("GP_DEBUG", "") != "1":
    # Temporarily disable print suppression for debugging
    pass  # builtins.print = lambda *args, **kwargs: None

log = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Import our modular components
from services.data_store import DataStore
from callbacks.upload_callbacks import register_upload_callbacks, register_clear_callbacks
from callbacks.viz_callbacks import register_viz_callbacks
from callbacks.file_tree_callbacks import register_file_tree_callbacks
from components.axis_mapper import create_axis_mapper_layout
from components.data_table_editor import create_data_table_editor
from components.table_styles import TABLE_STYLE_CELL, TABLE_STYLE_HEADER, TABLE_STYLE_DATA
from callbacks.publication_callbacks import register_publication_callbacks
from callbacks.integration_callbacks import register_integration_callbacks
from callbacks.baseline_callbacks import register_baseline_callbacks
from callbacks.context_menu_callbacks import register_context_menu_callbacks
from callbacks.export_callbacks import register_export_callbacks
from callbacks.calibration_callbacks import register_calibration_callbacks

# App setup
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='src/assets')
app.config.suppress_callback_exceptions = True
app.title = 'GeckoPlotter'

# Global data store (Bundle-first architecture)
data_manager = DataStore()

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
_layout_body = html.Div(
    [
        dcc.Store(id='loaded-files', data=[]),
        dcc.Store(id='active-file', data=None),
        dcc.Store(id='file-ui-state', data={}),
        dcc.Store(id='active-tab', data='data-overview'),
        dcc.Store(id='view-mode', data='raw'),
        dcc.Store(id='active-plot-context', data=None),
        dcc.Store(id='current-plot-settings', data={}),
        dcc.Store(id='toolbox-tab', data='pub-plotter'),
        dcc.Store(id='dev-settings', data={'show': False}),
        dcc.Store(id='pub-data-store'),  # Store for publication plotter data
        dcc.Store(id='pub-plot-figure'),  # Store for the publication plot figure
        dcc.Store(id='pub-plot-trigger'),  # Trigger to update main plot
        dcc.Store(id='custom-plot-figures', data={}),  # Maps custom tab_id → figure dict
        dcc.Store(id='custom-plot-counter', data=0),  # Auto-incrementing counter for plot names
        dcc.Store(id='tab-rename-event', data=None),  # {tab_id, new_label} from JS
        dcc.Store(id='plot-export-data'),  # Export data from publication plot
        dcc.Store(id='peak-shared-selections', data={}),  # Shared selections for peak-analysis tab
        dcc.Store(id='cross-shared-selections', data={}),  # Shared selections for across-samples tab
        dcc.Store(id='peak-table-store', data=None),  # Mirror of peak-table data (JSON split) — always in layout
        dcc.Store(id='cross-sample-table-store', data=None),  # Mirror of cross-sample-table data (JSON split) — always in layout
        # Baseline integration stores (p-line drawing)
        dcc.Store(id='baseline-mode', data='navigate'),  # 'draw' | 'edit' | 'navigate'
        dcc.Store(id='context-menu-store', data=None),  # {peak_id, x, y, ts} from right-click
        dcc.Store(id='selected-peak-idx', data=None),  # Index of peak being edited
        dcc.Store(id='clear-shapes-trigger', data=0),  # Counter to trigger shape clearing
        dcc.Store(id='peak-change-trigger', data=0),  # Counter to refresh tables/overlays after peak edits
        dcc.Store(id='peak-name-persist-trigger', data=None),
        dcc.Store(id='cross-sample-name-trigger', data=None),
        dcc.Store(id='plot-peak-click-store', data=None),  # Browser-side peak hit-test selection
        dcc.Store(id='manual-draw-line-store', data=None),  # Browser-side custom integration line
        dcc.Store(id='interaction-action-store', data=None),  # Last action for future undo/redo
        dcc.Store(id='render-trigger', data=0),  # Counter bumped to trigger master render of main-plot
        dcc.Store(id='zoom-state', data=None),  # Persisted user zoom ranges across figure rebuilds
        dcc.Store(id='plot-tabs', data=[]),  # List of plot tab descriptors [{id, label, type, group_key}]
        dcc.Store(id='active-plot-tab', data=None),  # ID of currently displayed plot tab
        dcc.Store(id='tab-file-memory', data={}),  # Maps tab_id → last selected file_id
        dcc.Store(id='tab-panel-memory', data={}),  # Maps tab_id → last active bottom panel
        dcc.Store(id='tab-zoom-memory', data={}),  # Maps tab_id → saved zoom ranges
        dcc.Store(id='file-order', data={}),  # Per-group file ordering {group_id: {sort_dir: 'asc'|'desc'|null, order: [id, ...]}}
        dcc.Store(id='file-reorder-event', data=None),  # JS drag-and-drop event {group_id, order: [id, ...]}
        dcc.Store(id='keyboard-delete-trigger', data=0),  # Counter bumped by JS on Backspace/Delete keypress
        dcc.Store(id='hidden-files', data=[]),  # List of hidden file IDs for CSS dimming
        dcc.Store(id='group-collapse-state', data={}),  # {group_id: bool} collapse state
        dcc.Store(id='group-move-event', data=None),  # {file_id, source_group, target_group|null}
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
                            id='plot-tab-bar',
                            className='plot-tab-bar',
                            children=[],
                        ),
                        html.Button('Raw Data', id='raw-mode-btn', style={'display': 'none'}, n_clicks=0),
                        html.Button('Analysis Plot', id='analysis-mode-btn', style={'display': 'none'}, n_clicks=0),
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
                                        # Toolbox tabs (DMC). keepMounted keeps inactive panels mounted so
                                        # callbacks reading controls in other panels keep working off-tab.
                                        dmc.Tabs(
                                            id='toolbox-tabs',
                                            value='pub-plotter',
                                            keepMounted=True,
                                            className='toolbox-tabs',
                                            style={'display': 'flex', 'flexDirection': 'column',
                                                   'flex': '1', 'overflow': 'hidden'},
                                            children=[
                                            dmc.TabsList([
                                                dmc.TabsTab("Data Selector", value="pub-plotter"),
                                                dmc.TabsTab("Plot Settings", value="plot-tools"),
                                                dmc.TabsTab("Integration", value="integration"),
                                                dmc.TabsTab("Export", value="export"),
                                            ]),
                                            # Data Selector Tab
                                            dmc.TabsPanel(value="pub-plotter", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                html.Div(
                                                    id='pub-plotter-container',
                                                    className='toolbox-tab-content active',
                                                    style={'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=create_axis_mapper_layout(),
                                                ),
                                            ]),
                                            # Plot Settings Tab
                                            dmc.TabsPanel(value="plot-tools", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                html.Div(
                                                    id='plot-tools-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'block', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        # -- Dynamic Header --
                                                        html.Div(id='pt-panel-header', children='Analysis Plot Settings',
                                                                 className='toolbox-section-title',
                                                                 style={'fontSize': '13px', 'fontWeight': '600', 'marginBottom': '8px',
                                                                        'padding': '4px 0', 'borderBottom': '1px solid #ddd'}),

                                                        # -- 0. Layout Mode (Raw only) --
                                                        html.Div(id='pt-raw-layout-wrapper', children=[
                                                            html.Div('Trace Layout', className='toolbox-section-title'),
                                                            dmc.RadioGroup(
                                                                id='pt-layout-mode',
                                                                value='overlay',
                                                                size='xs',
                                                                mb=10,
                                                                children=dmc.Group([
                                                                    dmc.Radio(label='Superposed', value='overlay'),
                                                                    dmc.Radio(label='Subplots', value='stacked'),
                                                                ], gap='md'),
                                                            ),
                                                        ], style={'display': 'none'}),

                                                        # -- 1. Plot Type (Analysis only) --
                                                        html.Div(id='pt-plot-type-wrapper', children=[
                                                            html.Div('Plot Type', className='toolbox-section-title'),
                                                            dmc.RadioGroup(
                                                                id='pt-plot-type',
                                                                value='bar',
                                                                size='xs',
                                                                mb=10,
                                                                children=dmc.Group([
                                                                    dmc.Radio(label='Bar', value='bar'),
                                                                    dmc.Radio(label='Line', value='line'),
                                                                    dmc.Radio(label='Scatter', value='scatter'),
                                                                ], gap='md'),
                                                            ),
                                                        ]),

                                                        # -- 2. Axes (Both) --
                                                        html.Div('Axes', className='toolbox-section-title'),
                                                        dmc.Switch(id='pt-auto-range', label='Auto range', checked=True,
                                                                   size='sm', mb=6),
                                                        dmc.Switch(id='pt-categorical-x', label='Categorical X axis', checked=True,
                                                                   size='sm', mb=6),
                                                        html.Div(id='pt-range-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('X min', className='form-label'),
                                                                          dmc.NumberInput(id='pt-x-min', size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('X max', className='form-label'),
                                                                          dmc.NumberInput(id='pt-x-max', size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}, id='pt-x-range-row'),
                                                            html.Div([
                                                                html.Div([html.Label('Y min', className='form-label'),
                                                                          dmc.NumberInput(id='pt-y-min', size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Y max', className='form-label'),
                                                                          dmc.NumberInput(id='pt-y-max', size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}, id='pt-y-range-row'),
                                                        ], style={'display': 'none'}),
                                                        html.Div([
                                                            html.Div([html.Label('X scale', className='form-label'),
                                                                      dmc.Select(id='pt-x-scale', value='linear', size='xs',
                                                                                 data=[{'label': 'Linear', 'value': 'linear'}, {'label': 'Log', 'value': 'log'}],
                                                                                 clearable=False, allowDeselect=False)],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Y scale', className='form-label'),
                                                                      dmc.Select(id='pt-y-scale', value='linear', size='xs',
                                                                                 data=[{'label': 'Linear', 'value': 'linear'}, {'label': 'Log', 'value': 'log'}],
                                                                                 clearable=False, allowDeselect=False)],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),

                                                        # -- 3. Theme & Colors (Analysis only for now) --
                                                        html.Div(id='pt-theme-wrapper', children=[
                                                            html.Div('Theme & Colors', className='toolbox-section-title'),
                                                            html.Div([
                                                                html.Label('Theme', className='form-label'),
                                                                dmc.Select(id='pt-theme', value='plotly_white', size='xs',
                                                                           data=[{'label': t, 'value': t} for t in
                                                                                 ['plotly_white', 'simple_white', 'plotly', 'ggplot2', 'seaborn',
                                                                                  'plotly_dark', 'presentation', 'none']],
                                                                           clearable=False, allowDeselect=False, searchable=True),
                                                            ], style={'marginBottom': '6px'}),
                                                        ]),
                                                        html.Div([
                                                            html.Label('Color palette', className='form-label'),
                                                            dmc.Select(id='pt-palette', value='okabe_ito', size='xs',
                                                                       data=[{'label': p.replace('_', ' ').title(), 'value': p} for p in
                                                                             ['okabe_ito', 'plotly', 'd3', 'pastel']],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Plot bg', className='form-label'),
                                                                      dmc.ColorInput(id='pt-bg-color', value='#ffffff', format='hex',
                                                                                     size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Paper bg', className='form-label'),
                                                                      dmc.ColorInput(id='pt-paper-color', value='#ffffff', format='hex',
                                                                                     size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),

                                                        # -- 4. Traces --
                                                        html.Div('Traces', className='toolbox-section-title'),
                                                        # Line width: both (raw traces + analysis line/scatter)
                                                        html.Div(id='pt-line-controls-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Line width', className='form-label'),
                                                                          dmc.NumberInput(id='pt-line-width', value=1.5, min=0.5, max=5, step=0.5,
                                                                                          decimalScale=2, size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div(id='pt-line-style-cell', children=[
                                                                    html.Label('Line style', className='form-label'),
                                                                    dmc.Select(id='pt-line-style', value='solid', size='xs',
                                                                               data=[{'label': s.title(), 'value': s} for s in
                                                                                     ['solid', 'dash', 'dot', 'dashdot']],
                                                                               clearable=False, allowDeselect=False),
                                                                ], style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        ]),
                                                        # Marker controls: analysis scatter/line only
                                                        html.Div(id='pt-marker-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Marker size', className='form-label'),
                                                                          dmc.NumberInput(id='pt-marker-size', value=6, min=2, max=16, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Marker shape', className='form-label'),
                                                                          dmc.Select(id='pt-marker-symbol', value='circle', size='xs',
                                                                                     data=[{'label': s.title(), 'value': s} for s in
                                                                                           ['circle', 'square', 'diamond', 'cross', 'x',
                                                                                            'triangle-up', 'triangle-down', 'star']],
                                                                                     clearable=False, allowDeselect=False, searchable=True)],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        ]),
                                                        # Opacity: both
                                                        html.Div([
                                                            html.Div([html.Label('Opacity', className='form-label'),
                                                                      dmc.Slider(id='pt-trace-opacity', min=0.1, max=1.0, step=0.1, value=1.0,
                                                                                 marks=[{'value': 0.1, 'label': '.1'}, {'value': 0.5, 'label': '.5'},
                                                                                        {'value': 1.0, 'label': '1'}])],
                                                                     style={'flex': '1'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        # Bar controls: analysis bar only
                                                        html.Div(id='pt-bar-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Bar gap', className='form-label'),
                                                                          dmc.NumberInput(id='pt-bar-gap', value=0.2, min=0, max=1, step=0.05,
                                                                                          decimalScale=2, size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Group gap', className='form-label'),
                                                                          dmc.NumberInput(id='pt-bar-group-gap', value=0.1, min=0, max=1, step=0.05,
                                                                                          decimalScale=2, size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        ]),

                                                        # -- 5. Labels (Both) --
                                                        html.Div('Labels', className='toolbox-section-title'),
                                                        html.Div([html.Label('Title', className='form-label'),
                                                                   dmc.TextInput(id='pt-title', placeholder='Plot title', size='xs')],
                                                                 style={'marginBottom': '6px'}),

                                                        # -- 6. Typography (Both) --
                                                        html.Div('Typography', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Font', className='form-label'),
                                                                      dmc.Select(id='pt-font', value='Arial', size='xs',
                                                                                 data=[{'label': f, 'value': f} for f in
                                                                                       ['Arial', 'Helvetica', 'Times New Roman', 'Courier New',
                                                                                        'Georgia', 'Verdana', 'Calibri', 'Computer Modern']],
                                                                                 clearable=False, allowDeselect=False, searchable=True)],
                                                                     style={'flex': '2'}),
                                                            html.Div([html.Label('Size', className='form-label'),
                                                                      dmc.NumberInput(id='pt-font-size', value=12, min=8, max=24, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Title size', className='form-label'),
                                                                      dmc.NumberInput(id='pt-title-font-size', value=14, min=10, max=32, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Tick size', className='form-label'),
                                                                      dmc.NumberInput(id='pt-tick-font-size', value=10, min=6, max=18, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        dmc.Switch(id='pt-bold-title', label='Bold title', checked=True,
                                                                   size='sm', mb=10),

                                                        # -- 7. Legend (Both) --
                                                        html.Div('Legend', className='toolbox-section-title'),
                                                        dmc.Switch(id='pt-show-legend', label='Show legend', checked=True,
                                                                   size='sm', mb=6),
                                                        html.Div(id='pt-legend-pos-wrapper', children=[
                                                            html.Label('Position', className='form-label'),
                                                            dmc.Select(id='pt-legend-pos', value='top-right', size='xs',
                                                                       data=[{'label': p.replace('-', ' ').title(), 'value': p}
                                                                             for p in ['top-right', 'top-left', 'bottom-right', 'bottom-left']],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '10px'}),

                                                        # -- 8. Grid & Frame (Both) --
                                                        html.Div('Grid & Frame', className='toolbox-section-title'),
                                                        dmc.CheckboxGroup(
                                                            id='pt-layout-opts',
                                                            value=['grid_x', 'grid_y', 'ticks', 'frame'],
                                                            mb=6,
                                                            children=dmc.Stack([
                                                                dmc.Checkbox(label='Grid X', value='grid_x'),
                                                                dmc.Checkbox(label='Grid Y', value='grid_y'),
                                                                dmc.Checkbox(label='Tick marks', value='ticks'),
                                                                dmc.Checkbox(label='Frame (box)', value='frame'),
                                                            ], gap=4),
                                                        ),
                                                        html.Div(id='pt-tick-grid-detail-wrapper', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Tick direction', className='form-label'),
                                                                          dmc.Select(id='pt-tick-dir', value='outside', size='xs',
                                                                                     data=[{'label': d.title(), 'value': d} for d in ['outside', 'inside']],
                                                                                     clearable=False, allowDeselect=False)],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Grid style', className='form-label'),
                                                                          dmc.Select(id='pt-grid-style', value='solid', size='xs',
                                                                                     data=[{'label': s.title(), 'value': s} for s in ['solid', 'dash', 'dot']],
                                                                                     clearable=False, allowDeselect=False)],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        ]),
                                                    ],
                                                ),
                                            ]),
                                            # Integration Tab
                                            dmc.TabsPanel(value="integration", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                html.Div(
                                                    id='integration-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'block', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        # -- Manual Baseline Integration --
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
                                                            dmc.Switch(
                                                                id='easy-integration',
                                                                label='Easy (baseline -> y=0)',
                                                                checked=True,
                                                                size='sm',
                                                            ),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div('Draw: off',
                                                                 id='baseline-mode-indicator',
                                                                 style={'fontSize': '11px', 'color': '#666', 'marginBottom': '10px'}),
                                                        html.Div(id='manual-peak-table-container', style={'marginBottom': '10px'}),
                                                        html.Div([
                                                            html.Label('RT match tolerance (min)', className='form-label'),
                                                            dmc.NumberInput(id='int-rt-tolerance', value=0.3, min=0.05, max=1.0,
                                                                            step=0.05, decimalScale=2, size='xs',
                                                                            style={'width': '100%'}),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div(id='ctx-status',
                                                                 style={'fontSize': '11px', 'color': '#2e7d32', 'marginBottom': '6px'}),
                                                        html.Hr(style={'margin': '10px 0', 'borderColor': '#e0e0e0'}),
                                                        # -- Auto Peak Detection --
                                                        html.Div('Signal Processing', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Smooth window', className='form-label'),
                                                                      dmc.NumberInput(id='int-smooth-window', value=11, min=3, max=51, step=2,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Poly order', className='form-label'),
                                                                      dmc.NumberInput(id='int-smooth-poly', value=3, min=1, max=5, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div('Baseline', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Method', className='form-label'),
                                                            dmc.Select(id='int-baseline-method', value='snip', size='xs',
                                                                       data=[{'label': m, 'value': m} for m in ['snip', 'polynomial', 'none']],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Iterations', className='form-label'),
                                                                      dmc.NumberInput(id='int-baseline-iter', value=40, min=5, max=100, step=5,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Poly order', className='form-label'),
                                                                      dmc.NumberInput(id='int-baseline-poly', value=5, min=1, max=10, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        html.Div('Peak Detection', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([html.Label('Threshold', className='form-label'),
                                                                      dmc.NumberInput(id='int-peak-threshold', value=0.01, min=0.001, max=1, step=0.001,
                                                                                      decimalScale=3, size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Slope cutoff', className='form-label'),
                                                                      dmc.NumberInput(id='int-slope-threshold', value=0.001, min=0.0001, max=0.1, step=0.0001,
                                                                                      decimalScale=4, size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Extension', className='form-label'),
                                                                      dmc.NumberInput(id='int-extension', value=1.1, min=1.0, max=2.0, step=0.05,
                                                                                      decimalScale=2, size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Min width (pts)', className='form-label'),
                                                                      dmc.NumberInput(id='int-min-width', value=3, min=1, max=20, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        html.Div([
                                                            html.Button('Detect Peaks', id='int-detect-btn', className='btn btn-primary',
                                                                        style={'marginRight': '8px'}),
                                                            html.Button('Clear Detected', id='int-clear-btn', className='btn btn-secondary',
                                                                        title='Remove detected peaks only'),
                                                        ], style={'display': 'flex', 'marginBottom': '6px'}),
                                                        dmc.CheckboxGroup(
                                                            id='int-display-opts',
                                                            value=['peaks'],
                                                            children=dmc.Stack([
                                                                dmc.Checkbox(label='Show baseline', value='baseline'),
                                                                dmc.Checkbox(label='Show peak fills', value='peaks'),
                                                                dmc.Checkbox(label='Show corrected signal', value='corrected'),
                                                            ], gap=4),
                                                        ),
                                                    ],
                                                ),
                                            ]),
                                            # Export Tab
                                            dmc.TabsPanel(value="export", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                html.Div(
                                                    id='export-container',
                                                    className='toolbox-tab-content',
                                                    style={'display': 'block', 'padding': '10px', 'overflowY': 'auto', 'maxHeight': 'calc(100% - 40px)'},
                                                    children=[
                                                        html.Div('Figure Export', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Format', className='form-label'),
                                                            dmc.Select(id='exp-fig-format', value='png', size='xs',
                                                                       data=[{'label': f, 'value': f} for f in ['png', 'svg', 'html', 'pdf']],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Div([html.Label('Width (px)', className='form-label'),
                                                                      dmc.NumberInput(id='exp-width', value=800, min=400, max=2400, step=100,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Height (px)', className='form-label'),
                                                                      dmc.NumberInput(id='exp-height', value=500, min=300, max=1600, step=100,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Label('DPI scale', className='form-label'),
                                                            dmc.Slider(id='exp-dpi', min=1, max=6, step=1, value=3,
                                                                       marks=[{'value': 1, 'label': '1x'}, {'value': 2, 'label': '2x'},
                                                                              {'value': 3, 'label': '3x'}, {'value': 4, 'label': '4x'},
                                                                              {'value': 6, 'label': '6x'}]),
                                                        ], style={'marginBottom': '10px'}),
                                                        html.Button('Export Figure', id='exp-fig-btn', className='btn btn-primary',
                                                                    style={'width': '100%', 'marginBottom': '10px'}),
                                                        dcc.Download(id='exp-fig-download'),
                                                        html.Div('Data Export', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Label('Format', className='form-label'),
                                                            dmc.Select(id='exp-data-format', value='csv', size='xs',
                                                                       data=[{'label': f.upper(), 'value': f} for f in ['csv', 'xlsx', 'json']],
                                                                       clearable=False, allowDeselect=False),
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
                                            ]),
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
                                                dcc.Graph(
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
                                                # Analysis tabs (DMC). keepMounted keeps inactive panels mounted so
                                                # callbacks referencing pub-table/peak-table/etc. work off-tab.
                                                dmc.Tabs(
                                                    id='analysis-tabs',
                                                    value='data-overview',
                                                    keepMounted=True,
                                                    className='tab-header',
                                                    style={'display': 'flex', 'flexDirection': 'column',
                                                           'height': '100%', 'overflow': 'hidden'},
                                                    children=[
                                                    dmc.TabsList([
                                                        dmc.TabsTab("Data Overview", value="data-overview"),
                                                        dmc.TabsTab("Peak Analysis", value="peak-analysis"),
                                                        dmc.TabsTab("Across Samples", value="across-samples"),
                                                        dmc.TabsTab("Metadata", value="metadata"),
                                                        dmc.TabsTab("Calibration", value="calibration"),
                                                        dmc.TabsTab("MS Viewer", value="ms-viewer"),
                                                    ]),
                                                    # Data Overview Tab
                                                    dmc.TabsPanel(value="data-overview", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="data-overview-content", className="tab-content active", style={
                                                        'display': 'block',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div(id='mode-indicator', style={'display': 'none'}),
                                                        html.Div(id='table-editor-container', children=[
                                                            # Empty pub-table and sheet store must exist at startup
                                                            # so callbacks referencing them don't crash.
                                                            dcc.Store(id='active-sheet-name', data=None),
                                                            html.Div([
                                                                dash_table.DataTable(
                                                                    id='pub-table',
                                                                    columns=[],
                                                                    data=[],
                                                                    cell_selectable=True,
                                                                    column_selectable='single',
                                                                    sort_action='native',
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
                                                    ]),
                                                    # Peak Analysis Tab
                                                    dmc.TabsPanel(value="peak-analysis", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="peak-analysis-content", className="tab-content", style={
                                                        'display': 'block',
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
                                                                style_cell=TABLE_STYLE_CELL,
                                                                style_header=TABLE_STYLE_HEADER,
                                                                style_header_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data=TABLE_STYLE_DATA,
                                                                style_cell_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                                style_data_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            ),
                                                        ])
                                                    ]),
                                                    ]),
                                                    # Across Samples Tab
                                                    dmc.TabsPanel(value="across-samples", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="across-samples-content", className="tab-content", style={
                                                        'display': 'block',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div([
                                                            dcc.Input(id='group-label-input', type='text',
                                                                      placeholder='Group label...',
                                                                      style={'width': '120px', 'padding': '3px 6px',
                                                                             'fontSize': '11px', 'border': '1px solid #ccc',
                                                                             'borderRadius': '3px'}),
                                                            html.Button('Apply to selected', id='apply-group-btn',
                                                                        style={'padding': '3px 8px', 'fontSize': '11px',
                                                                               'marginLeft': '4px', 'cursor': 'pointer'}),
                                                            html.Button('Clear groups', id='clear-groups-btn',
                                                                        style={'padding': '3px 8px', 'fontSize': '11px',
                                                                               'marginLeft': '4px', 'cursor': 'pointer',
                                                                               'color': '#999'}),
                                                        ], style={'display': 'flex', 'alignItems': 'center',
                                                                  'gap': '2px', 'marginBottom': '6px', 'padding': '4px 0'}),
                                                        # Static components that survive across-samples-container
                                                        # children replacement by update_across_samples_tab
                                                        html.Div(id='peak-group-selector-wrapper', style={'display': 'none'}, children=[
                                                            html.Label("Select Peak Group to Compare:",
                                                                       style={'fontWeight': 'bold', 'marginBottom': '5px',
                                                                              'marginTop': '15px', 'display': 'block', 'fontSize': '14px'}),
                                                            dcc.Dropdown(id='peak-group-selector', value=0,
                                                                         style={'marginBottom': '15px'}),
                                                        ]),
                                                        html.Div(id='retention-slider-wrapper', style={'display': 'none'}, children=[
                                                            html.Label("Peak Matching Time Window (min):",
                                                                       style={'fontWeight': 'bold', 'marginBottom': '5px',
                                                                              'display': 'block', 'fontSize': '14px'}),
                                                            dcc.Slider(id='retention-time-slider', min=0.05, max=1.0,
                                                                       step=0.05, value=0.2,
                                                                       marks={0.05: '0.05', 0.2: '0.2', 0.5: '0.5', 1.0: '1.0'},
                                                                       tooltip={"placement": "bottom", "always_visible": True}),
                                                        ]),
                                                        dash_table.DataTable(
                                                            id='cross-sample-table',
                                                            columns=[], data=[],
                                                            editable=True,
                                                            cell_selectable=True,
                                                            column_selectable='single',
                                                            row_selectable='multi',
                                                            row_deletable=True,
                                                            sort_action='native',
                                                            style_table={'display': 'none'},
                                                            style_cell=TABLE_STYLE_CELL,
                                                            style_header=TABLE_STYLE_HEADER,
                                                            style_header_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            style_data=TABLE_STYLE_DATA,
                                                            style_cell_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            style_data_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                        ),
                                                        html.Div(id='across-samples-container', children=[
                                                            html.P("Load multiple bundles to compare peaks across samples",
                                                                  style={'color': '#666', 'textAlign': 'center', 'padding': '20px'})
                                                        ])
                                                    ]),
                                                    ]),
                                                    # Metadata Tab
                                                    dmc.TabsPanel(value="metadata", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="metadata-content", className="tab-content", style={
                                                        'display': 'block',
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
                                                    ]),
                                                    # Calibration Tab
                                                    dmc.TabsPanel(value="calibration", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="calibration-content", className="tab-content", style={
                                                        'display': 'block',
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
                                                                              dmc.TextInput(id='cal-analyte-name',
                                                                                            placeholder='e.g. Caffeine',
                                                                                            size='xs', style={'width': '100%'})],
                                                                             style={'flex': '2'}),
                                                                    html.Div([html.Label('Units', className='form-label'),
                                                                              dmc.TextInput(id='cal-units',
                                                                                            placeholder='e.g. mg/mL',
                                                                                            size='xs', style={'width': '100%'})],
                                                                             style={'flex': '1'}),
                                                                ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                                                                html.Div([
                                                                    html.Div([html.Label('Fit type', className='form-label'),
                                                                              dmc.Select(id='cal-fit-type', value='linear', size='xs',
                                                                                         data=[{'label': t.title(), 'value': t}
                                                                                               for t in ['linear', 'quadratic', 'power']],
                                                                                         clearable=False, allowDeselect=False)],
                                                                             style={'flex': '1'}),
                                                                    html.Div([html.Label('Peak group', className='form-label'),
                                                                              dmc.Select(id='cal-peak-group', placeholder='Select peak group...',
                                                                                         data=[], size='xs')],
                                                                             style={'flex': '1'}),
                                                                ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
                                                                dmc.Switch(id='cal-force-zero', label='Force through origin',
                                                                           checked=False, size='sm', mb=8),
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
                                                                    dmc.Select(id='cal-active-model', placeholder='No models created yet',
                                                                               data=[], size='xs', mb=8),
                                                                ]),
                                                                html.Div([
                                                                    html.Div([html.Label('Sample', className='form-label'),
                                                                              dmc.TextInput(id='cal-std-sample',
                                                                                            placeholder='Sample name',
                                                                                            size='xs', style={'width': '100%'})],
                                                                             style={'flex': '2'}),
                                                                    html.Div([html.Label('Conc.', className='form-label'),
                                                                              dmc.NumberInput(id='cal-std-conc',
                                                                                              placeholder='0.0',
                                                                                              size='xs', style={'width': '100%'})],
                                                                             style={'flex': '1'}),
                                                                    html.Div([html.Label('Area', className='form-label'),
                                                                              dmc.NumberInput(id='cal-std-area',
                                                                                              placeholder='0.0',
                                                                                              size='xs', style={'width': '100%'})],
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
                                                    ]),
                                                    ]),
                                                    # MS Viewer Tab
                                                    dmc.TabsPanel(value="ms-viewer", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                    html.Div(id="ms-viewer-content", className="tab-content", style={
                                                        'display': 'block',
                                                        'padding': '15px',
                                                        'height': '100%',
                                                        'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div([
                                                            html.Div([
                                                                dcc.Graph(id='ms-spectrum-graph',
                                                                          figure=go.Figure(layout=go.Layout(
                                                                              template='plotly_white',
                                                                              margin=dict(l=50, r=20, t=30, b=40),
                                                                              xaxis=dict(visible=False),
                                                                              yaxis=dict(visible=False),
                                                                              annotations=[dict(
                                                                                  text='Click on the chromatogram to view a mass spectrum',
                                                                                  xref='paper', yref='paper',
                                                                                  x=0.5, y=0.5, showarrow=False,
                                                                                  font=dict(size=13, color='#999'),
                                                                              )])),
                                                                          responsive=True,
                                                                          style={'width': '100%', 'height': '250px'}),
                                                                html.Div(id='ms-spectrum-info',
                                                                         style={'fontSize': '12px', 'padding': '6px 8px',
                                                                                'backgroundColor': '#f8f9fa',
                                                                                'borderRadius': '4px', 'marginTop': '4px',
                                                                                'minHeight': '20px'}),
                                                            ]),
                                                            html.Div([
                                                                html.Div('EIC Extraction', style={
                                                                    'fontWeight': 'bold', 'fontSize': '13px',
                                                                    'marginBottom': '8px', 'marginTop': '12px'}),
                                                                html.Div([
                                                                    html.Div([
                                                                        html.Label('Target m/z', className='form-label'),
                                                                        dcc.Input(id='eic-mz-input', type='number',
                                                                                  placeholder='e.g. 294.1',
                                                                                  className='form-input',
                                                                                  style={'width': '100%'}),
                                                                    ], style={'flex': '2'}),
                                                                    html.Div([
                                                                        html.Label('Tolerance', className='form-label'),
                                                                        dcc.Input(id='eic-tolerance-input', type='number',
                                                                                  value=0.5, step=0.1,
                                                                                  className='form-input',
                                                                                  style={'width': '100%'}),
                                                                    ], style={'flex': '1'}),
                                                                    html.Div([
                                                                        html.Button('Extract', id='eic-extract-btn',
                                                                                    className='btn btn-primary',
                                                                                    style={'marginTop': '20px', 'width': '100%'}),
                                                                    ], style={'flex': '1'}),
                                                                    html.Div([
                                                                        html.Button('Clear', id='eic-clear-btn',
                                                                                    className='btn',
                                                                                    style={'marginTop': '20px', 'width': '100%'}),
                                                                    ], style={'flex': '0.5'}),
                                                                ], style={'display': 'flex', 'gap': '8px',
                                                                          'alignItems': 'flex-start'}),
                                                                html.Div(id='eic-active-list', style={
                                                                    'marginTop': '8px', 'display': 'flex',
                                                                    'flexWrap': 'wrap', 'gap': '4px'}),
                                                            ], style={'padding': '10px', 'backgroundColor': '#f8f9fa',
                                                                      'borderRadius': '6px'}),
                                                        ])
                                                    ]),
                                                    ]),
                                                    ],
                                                ),
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

        # -- Right-click context menu (peaks) --
        # Fixed anchor moved to the cursor by a callback; the portal dropdown
        # opens relative to it. Dismissal (outside-click / Escape) is native.
        html.Div(
            id='context-menu-anchor',
            style={'position': 'fixed', 'left': '0px', 'top': '0px',
                   'width': '1px', 'height': '1px', 'zIndex': 4000,
                   'pointerEvents': 'none'},
            children=dmc.Menu(
                id='context-menu',
                opened=False,
                position='bottom-start',
                offset=2,
                withinPortal=True,
                shadow='md',
                children=[
                    dmc.MenuTarget(html.Div(style={'width': '1px', 'height': '1px'})),
                    dmc.MenuDropdown([
                        dmc.MenuItem('Delete Peak', id='ctx-delete-item'),
                        dmc.MenuItem('Rename Peak', id='ctx-rename-item'),
                        dmc.MenuItem('Integrate in All Files', id='ctx-integrate-item'),
                    ]),
                ],
            ),
        ),
        dmc.Modal(
            id='ctx-rename-modal',
            title='Rename Peak',
            opened=False,
            zIndex=4100,
            children=[
                dmc.TextInput(id='ctx-rename-input', placeholder='Peak name'),
                dmc.Group([
                    dmc.Button('Save', id='ctx-rename-save', size='xs'),
                ], justify='flex-end', mt='sm'),
            ],
        ),
    ]
)

# DMC 2.x requires a MantineProvider ancestor for any DMC component to render.
app.layout = dmc.MantineProvider(children=[_layout_body])

# Register callbacks
from callbacks.tab_callbacks import register_tab_callbacks
from callbacks.table_editor_callbacks import register_table_editor_callbacks
from callbacks.context_callbacks import register_context_callbacks
from callbacks.plot_settings_callbacks import register_plot_settings_callbacks
from callbacks.lcms_callbacks import register_lcms_callbacks

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
register_context_menu_callbacks(app, data_manager)
register_export_callbacks(app, data_manager)
register_calibration_callbacks(app, data_manager)
register_plot_settings_callbacks(app, data_manager)
register_lcms_callbacks(app, data_manager)

# Toolbox tabs (DMC) <-> toolbox-tab store, kept in sync both ways.
# dmc.Tabs owns the visible panel; the store stays the source of truth for
# callbacks that read/write toolbox-tab (e.g. context restore). Classic Dash
# circular sync: prevent_initial_call + no-op guards break the loop.
@app.callback(
    Output('toolbox-tab', 'data', allow_duplicate=True),
    Input('toolbox-tabs', 'value'),
    State('toolbox-tab', 'data'),
    prevent_initial_call=True,
)
def toolbox_tab_to_store(tab_value, current):
    """Mirror a user toolbox-tab click into the toolbox-tab store."""
    if tab_value and tab_value != current:
        return tab_value
    return dash.no_update


@app.callback(
    Output('toolbox-tabs', 'value'),
    Input('toolbox-tab', 'data'),
    State('toolbox-tabs', 'value'),
    prevent_initial_call=True,
)
def store_to_toolbox_tab(toolbox_tab, tab_value):
    """Reflect external toolbox-tab changes (context restore) into the UI."""
    target = toolbox_tab or 'pub-plotter'
    if target != tab_value:
        return target
    return dash.no_update

# Clientside callback for resize functionality
clientside_callback(
    ClientsideFunction(namespace='resize', function_name='initializeResizeHandlers'),
    Output('resize-init-trigger', 'children'),
    Input('resize-init-trigger', 'id'),
)

# File-tree selection highlighting is now rendered server-side from active-file.

# Analysis tabs (DMC) <-> active-tab store, kept in sync both ways.
# dmc.Tabs owns the visible panel; the store stays the source of truth for
# the many callbacks that read/write active-tab (context restore, panel memory).
# Classic Dash circular sync: prevent_initial_call + no-op guards break the loop.
@app.callback(
    Output('active-tab', 'data', allow_duplicate=True),
    Input('analysis-tabs', 'value'),
    State('active-tab', 'data'),
    prevent_initial_call=True,
)
def analysis_tab_to_store(tab_value, current):
    """Mirror a user tab click into the active-tab store."""
    if tab_value and tab_value != current:
        return tab_value
    return dash.no_update


@app.callback(
    Output('analysis-tabs', 'value'),
    Input('active-tab', 'data'),
    State('analysis-tabs', 'value'),
    prevent_initial_call=True,
)
def store_to_analysis_tab(active_tab, tab_value):
    """Reflect external active-tab changes (context restore, panel memory) into the UI."""
    target = active_tab or 'data-overview'
    if target != tab_value:
        return target
    return dash.no_update


@app.callback(
    Output('view-mode', 'data'),
    Input('active-plot-tab', 'data'),
    State('plot-tabs', 'data'),
    prevent_initial_call=True,
)
def derive_view_mode(active_tab_id, tabs):
    """Derive view-mode from the active plot tab type (backwards compat)."""
    if not active_tab_id or not tabs:
        return 'raw'
    tab = next((t for t in tabs if t['id'] == active_tab_id), None)
    if tab and tab.get('type') in ('analysis', 'custom'):
        return 'analysis'
    return 'raw'

@app.callback(
    Output('tab-panel-memory', 'data', allow_duplicate=True),
    [Input('active-tab', 'data')],
    [State('active-plot-tab', 'data'),
     State('tab-panel-memory', 'data')],
    prevent_initial_call=True,
)
def save_panel_per_tab(active_tab, plot_tab, memory):
    """Remember which bottom panel is open for each plot tab."""
    if not plot_tab or not active_tab:
        return dash.no_update
    memory = memory or {}
    if memory.get(plot_tab) == active_tab:
        return dash.no_update
    return {**memory, plot_tab: active_tab}


@app.callback(
    Output('active-tab', 'data', allow_duplicate=True),
    Input('active-plot-tab', 'data'),
    [State('tab-panel-memory', 'data'),
     State('active-tab', 'data'),
     State('custom-plot-figures', 'data')],
    prevent_initial_call=True,
)
def restore_panel_on_tab_switch(plot_tab, memory, current_panel, figures):
    """Auto-switch bottom panel only for custom plot tabs.

    When the user clicks a custom plot tab, switch to its source panel
    (e.g. across-samples).  For all other plot tabs, leave the bottom
    panel alone — avoids overriding the user's manual panel click when
    switch_to_raw_tab_on_panel_change auto-switches the plot tab.
    """
    if not plot_tab:
        return dash.no_update
    if figures and plot_tab in figures:
        target = figures[plot_tab].get('source_tab')
        if target and target != current_panel:
            return target
    return dash.no_update


@app.callback(
    Output('active-plot-tab', 'data', allow_duplicate=True),
    Input('active-tab', 'data'),
    [State('plot-tabs', 'data'),
     State('active-plot-tab', 'data')],
    prevent_initial_call=True,
)
def switch_to_raw_tab_on_panel_change(active_tab, tabs, current_plot_tab):
    """Switch to Chromatograms tab when leaving Across Samples panel."""
    if not tabs or active_tab == 'across-samples':
        return dash.no_update
    current = next((t for t in tabs if t['id'] == current_plot_tab), None)
    if not current or current.get('type') != 'custom':
        return dash.no_update
    raw_tab = next((t for t in tabs if t.get('type') not in ('custom', 'analysis')), None)
    if raw_tab:
        return raw_tab['id']
    return dash.no_update


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
    log.info("Starting GeckoPlotter V2...")
    log.info("Upload TXT chromatograms or CSV UV-Vis files to get started!")
    app.run(debug=True, port=8052)
