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
from components.spectrum_polarity_control import create_spectrum_polarity_control
from components.calibration_panel import create_calibration_panel
from dash import dcc, html, dash_table, Input, Output, State, ClientsideFunction, clientside_callback
import dash_mantine_components as dmc
from dash_iconify import DashIconify
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
from callbacks.ms_context_menu_callbacks import register_ms_context_menu_callbacks
from callbacks.figure_actions_callbacks import register_figure_actions_callbacks
from callbacks.plot_context_menu_callbacks import register_plot_context_menu_callbacks
from callbacks.deconvolution_callbacks import register_deconvolution_callbacks
from callbacks.export_callbacks import register_export_callbacks
from callbacks.calibration_callbacks import register_calibration_callbacks
from components.research_export import create_research_export
from components.pda_explorer import create_pda_explorer
from services.themes import DEFAULT_THEME, theme_options
from components.popup_menu import popup_menu, menu_item, menu_divider
from services.plot_settings_service import DEFAULT_PALETTE, palette_options
from callbacks.research_export_callbacks import register_research_export_callbacks, register_provenance_capture
from components.paper_mock import create_paper_mock
from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
from components.session_controls import create_session_header_controls, create_session_banner, create_session_support

# App setup
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='src/assets', update_title=None)
from services.output_dedupe import install as _install_output_dedupe
_install_output_dedupe(app)
app.config.suppress_callback_exceptions = True
app.title = 'GeckoPlotter'

# Global data store (Bundle-first architecture)
data_manager = DataStore()


@app.server.before_request
def start_empty_workspace_on_reload():
    from flask import request
    # Dash fetches the initial layout once per document load. Normal callbacks,
    # plot tab switches and asset requests must leave the workspace intact.
    if request.path == '/_dash-layout' and request.method == 'GET':
        data_manager.reset_workspace()


def _figure_actions(context, menu=True):
    constructor = menu_item if menu else html.Button
    return [constructor(label, n_clicks=0, id={'type': 'figure-action', 'context': context, 'action': action},
                        **{'data-figure-action': action})
            for label, action in [('Send to publication', 'publication'), ('Quick export SVG', 'export')]]

def _icon(name, width=16, height=16, **kw):
    color = kw.pop('color', None)
    style = dict(kw.pop('style', {}) or {})
    if color:
        style['color'] = color
    return DashIconify(icon=name, width=width, height=height, style=style, **kw)

TYPE_ICONS = {
    'table': 'tabler:table',
    'structured': 'tabler:layout-grid',
    'image': 'tabler:photo',
    'chromatogram': 'tabler:chart-line',
    'spectrum': 'tabler:chart-area-line',
    'spectra': 'tabler:chart-area-line',
    'uvvis_csv': 'tabler:flask',
    'text': 'tabler:file-text',
    'binary': 'tabler:file-code',
    'unknown': 'tabler:file-question',
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
        icon_name = TYPE_ICONS.get(record.get('type'), TYPE_ICONS['unknown'])
        tree_items.append(
            html.Div(
                [
                    html.Span(_icon(icon_name, color='#666'), style={'marginRight': '8px', 'display': 'inline-flex'}),
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
        # Per-plot settings cache: switching plots applies stored settings in the browser.
        dcc.Store(id='plot-settings-cache', data={}),  # {context_key: settings}, filled from current-plot-settings
        dcc.Store(id='plot-settings-miss', data=None),  # context the browser has no settings for -> server hydrate
        dcc.Store(id='plot-settings-persist', data=None),  # changed settings only -> server persist
        dcc.Store(id='plot-panel-sync', data=0),  # ticks while a context-menu panel is open
        dcc.Store(id='plot-settings-figure-key', data={}),  # {_context_key, layout_mode} for describe_figure
        dcc.Store(id='toolbox-tab', data='plot-tools'),
        dcc.Store(id='dev-settings', data={'show': False}),
        dcc.Store(id='pub-data-store'),  # Store for publication plotter data
        dcc.Store(id='pub-plot-figure'),  # Store for the publication plot figure
        dcc.Store(id='pub-plot-trigger'),  # Trigger to update main plot
        dcc.Store(id='custom-plot-figures', data={}),  # Maps custom tab_id → figure dict
        dcc.Store(id='custom-plot-counter', data=0),  # Auto-incrementing counter for plot names
        dcc.Store(id='tab-rename-event', data=None),  # {tab_id, new_label} from JS
        dcc.Store(id='dataset-name-edit'),
        dcc.Store(id='legend-position-edit'),
        dcc.Store(id='plot-export-data'),  # Export data from publication plot
        dcc.Store(id='peak-shared-selections', data={}),  # Shared selections for peak-analysis tab
        dcc.Store(id='cross-shared-selections', data={}),  # Shared selections for across-samples tab
        dcc.Store(id='peak-table-store', data=None),  # Mirror of peak-table data (JSON split) — always in layout
        dcc.Store(id='cross-sample-table-store', data=None),  # Mirror of cross-sample-table data (JSON split) — always in layout
        # Baseline integration stores (p-line drawing)
        dcc.Store(id='baseline-mode', data='navigate'),  # 'draw' | 'edit' | 'navigate' | 'deconvolve'
        dcc.Store(id='context-menu-store', data=None),  # {peak_id, x, y, ts} from right-click
        dcc.Store(id='context-menu-close-store', data=0),  # bumped on outside click to close menu
        dcc.Store(id='axis-context-menu-store', data=None),  # {axis, x, y, subplot, ts} from axis right-click
        dcc.Store(id='axis-context-menu-close-store', data=0),  # bumped on outside click to close axis editor
        dcc.Store(id='legend-context-menu-store', data=None),  # {x, y, ts} from legend right-click
        dcc.Store(id='legend-context-menu-close-store', data=0),  # bumped on outside click to close legend editor
        dcc.Store(id='trace-context-menu-store', data=None),  # {curve_number, trace_name, x, y, ts} from trace right-click
        dcc.Store(id='trace-context-menu-close-store', data=0),  # bumped on outside click to close trace editor
        dcc.Store(id='title-context-menu-store', data=None),  # {target, x, y, ts} from title right-click
        dcc.Store(id='title-context-menu-close-store', data=0),  # bumped on outside click to close title editor
        dcc.Store(id='label-context-menu-store', data=None),  # {axis, x, y, ts} from axis label right-click
        dcc.Store(id='label-context-menu-close-store', data=0),  # bumped on outside click to close label editor
        dcc.Store(id='ms-active-subplot-idx', data={'file_id': None}),  # spectral source identity for the scan cursor
        dcc.Store(id='ms-plot-context-menu-store', data=None),  # {source, x, y, ts} from MS graph right-click
        dcc.Store(id='ms-plot-context-menu-close-store', data=0),
        dcc.Store(id='figure-action-event', data=None),
        dcc.Store(id='figure-context-close', data=0),
        dcc.Store(id='deconv-markers', data=[]),  # [{x, y}, ...] peak-center markers
        dcc.Store(id='deconv-result', data=None),  # serialized DeconvResult (preview/accept)
        dcc.Store(id='deconv-marker-click-store', data=None),  # browser-side marker click {x, ts}
        dcc.Store(id='selected-peak-idx', data=None),  # Index of peak being edited
        html.Div(id='selected-peak-keyboard-state', children='', style={'display': 'none'}),
        dcc.Store(id='clear-shapes-trigger', data=0),  # Counter to trigger shape clearing
        dcc.Store(id='cal-import-peaks', data=None),
        dcc.Store(id='peak-change-trigger', data=0),  # Counter to refresh tables/overlays after peak edits
        dcc.Store(id='peak-name-persist-trigger', data=None),
        dcc.Store(id='cross-sample-name-trigger', data=None),
        dcc.Store(id='plot-peak-click-store', data=None),  # Browser-side peak hit-test selection
        dcc.Store(id='manual-draw-line-store', data=None),  # Browser-side custom integration line
        dcc.Store(id='interaction-action-store', data=None),  # Last action for future undo/redo
        dcc.Input(id='ms-scan-client-input', type='number', value=None, style={'display': 'none'}),
        dcc.Store(id='render-trigger', data=0),  # Counter bumped to trigger master render of main-plot
        dcc.Store(id='zoom-state', data=None),  # Persisted user zoom ranges across figure rebuilds
        dcc.Store(id='main-shape-relayout', data=None),  # relayoutData filtered to shape edits (peak/deconvolution callbacks)
        dcc.Store(id='plot-tabs', data=[]),  # List of plot tab descriptors [{id, label, type, group_key}]
        dcc.Store(id='active-plot-tab', data=None),  # ID of currently displayed plot tab
        dcc.Store(id='rendered-plot-tabs', data=[]),  # Raw figures retained in this browser workspace
        dcc.Store(id='tab-file-memory', data={}),  # Maps tab_id → last selected file_id
        dcc.Store(id='tab-panel-memory', data={}),  # Maps tab_id → last active bottom panel
        dcc.Store(id='tab-zoom-memory', data={}),  # Maps tab_id → saved zoom ranges
        dcc.Store(id='file-order', data={}),  # Per-group file ordering {group_id: {sort_dir: 'asc'|'desc'|null, order: [id, ...]}}
        dcc.Store(id='file-reorder-event', data=None),  # JS drag-and-drop event {group_id, order: [id, ...]}
        dcc.Store(id='keyboard-delete-trigger', data=0),  # Counter bumped by JS on Backspace/Delete keypress
        dcc.Store(id='undo-trigger', data=0),
        dcc.Store(id='redo-trigger', data=0),
        dcc.Store(id='keyboard-action-trigger', data=None),  # {action: 'escape'|'prev_peak'|'next_peak'|'toggle_layout', ts}
        dcc.Store(id='undo-state', data={'can_undo': False, 'can_redo': False}),
        dcc.Store(id='hidden-files', data=[]),  # List of hidden file IDs for CSS dimming
        dcc.Store(id='group-collapse-state', data={}),  # {group_id: bool} collapse state
        dcc.Store(id='group-move-event', data=None),  # {file_id, source_group, target_group|null}
        dcc.Store(id='file-multi-selection', data=[]),  # File-tree row keys picked with Cmd/Ctrl/Shift-click (written by file-tree-ui.js)
        dcc.Store(id='pub-custom-dims', data={}),  # Per-preset custom W/H {preset: {w, h}}
        html.Button(id='plot-empty-click-trigger', n_clicks=0, style={'display': 'none'}),
        html.Div(id='clear-transient-shapes-output', style={'display': 'none'}),
        html.Div(id='selected-shapes-sync-output', style={'display': 'none'}),
        html.Div(id='dummy-output', style={'display': 'none'}),  # For clientside callbacks
        create_session_support(),  # project (.gecko) stores, download target, dialogs

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
                                html.Span('🦎', style={'fontSize': '18px'}),
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
                        create_session_header_controls(),
                    ],
                ),

                html.Div(
                    className='content-wrapper',
                    children=[
                        html.Div(
                            id='left-column',
                            className='left-column',
                            style={'display': 'flex', 'flexDirection': 'column', 'minWidth': '260px', 'width': '24%'},
                            children=[
                                html.Div(
                                    id='left-top-panel',
                                    className='panel',
                                    style={'height': '35%', 'display': 'flex', 'flexDirection': 'column', 'overflow': 'hidden'},
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
                                                            _icon('tabler:trash', width=14, height=14, color='#888'),
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
                                                'border': '1.5px dashed rgba(0, 0, 0, 0.2)',
                                                'backgroundColor': 'rgba(0, 0, 0, 0.02)',
                                            },
                                            children=html.Div(
                                                className='panel-content',
                                                style={
                                                    'flex': '1',
                                                    'overflowY': 'auto',
                                                    'minHeight': '0',
                                                },
                                                children=[
                                                    # No dcc.Loading wrapper: it is flagged dashChildrenUpdate (slows every
                                                    # renderer update) and its spinner only delayed the tree.
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
                                    className='divider divider-vertical',
                                    **{'data-label-above': 'File Explorer',
                                       'data-label-below': 'Toolbox'},
                                    children=[html.Span(className='divider-label')],
                                ),
                                html.Div(
                                    id='left-bottom-panel',
                                    className='panel',
                                    style={'height': '65%', 'display': 'flex', 'flexDirection': 'column'},
                                    children=[
                                        html.Div('Toolbox', className='panel-header'),
                                        # Toolbox tabs (DMC). keepMounted keeps inactive panels mounted so
                                        # callbacks reading controls in other panels keep working off-tab.
                                        dmc.Tabs(
                                            id='toolbox-tabs',
                                            value='plot-tools',
                                            keepMounted=True,
                                            className='toolbox-tabs',
                                            style={'display': 'flex', 'flexDirection': 'column',
                                                   'flex': '1', 'overflow': 'hidden'},
                                            children=[
                                            dmc.TabsList([
                                                dmc.TabsTab("Figure", value="plot-tools"),
                                                dmc.TabsTab("Data", value="pub-plotter"),
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
                                                                        'padding': '4px 0', 'borderBottom': '1px solid rgba(0, 0, 0, 0.1)'}),

                                                        # -- 0. Layout Mode (Raw only) --
                                                        html.Div(id='pt-raw-layout-wrapper', children=[
                                                            html.Div('Trace Layout', className='toolbox-section-title'),
                                                            dmc.RadioGroup(
                                                                id='pt-layout-mode',
                                                                value='overlay',
                                                                size='xs',
                                                                mb=10,
                                                                children=dmc.Group([
                                                                    dmc.Radio(label='Overlay', value='overlay'),
                                                                    dmc.Radio(label='Separate', value='stacked'),
                                                                ], gap='md'),
                                                            ),
                                                            html.Div(id='pt-subplot-spacing-wrapper', children=[
                                                                html.Label('Subplot spacing', className='form-label',
                                                                           style={'marginBottom': '2px'}),
                                                                dcc.Slider(id='pt-subplot-spacing', min=0.02, max=0.25,
                                                                           step=0.01, value=0.08,
                                                                           marks={0.02: '2%', 0.08: '8%', 0.15: '15%', 0.25: '25%'},
                                                                           tooltip={'placement': 'bottom', 'always_visible': False}),
                                                            ], style={'marginBottom': '10px'}),
                                                        ], style={'display': 'none'}),

                                                        # -- Subplot Grid --
                                                        html.Div('Subplot Grid', className='toolbox-section-title'),
                                                        html.Div([
                                                            html.Div([
                                                                html.Div([html.Label('Rows', className='form-label'),
                                                                          dmc.NumberInput(id='pub-subplot-rows', debounce=True, clampBehavior='blur', allowDecimal=False, value=1, min=1, max=20, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Span('×', style={'fontSize': '14px', 'color': '#555', 'alignSelf': 'flex-end', 'paddingBottom': '6px'}),
                                                                html.Div([html.Label('Cols', className='form-label'),
                                                                          dmc.NumberInput(id='pub-subplot-cols', debounce=True, clampBehavior='blur', allowDecimal=False, value=1, min=1, max=20, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '6px', 'alignItems': 'center'}),
                                                        ], style={'marginBottom': '10px'}),

                                                        # -- Figure Dimensions (Publication tab only) --
                                                        html.Div(id='pt-pub-dimensions-wrapper', style={'display': 'none'}, children=[
                                                            html.Div('Figure Dimensions', className='toolbox-section-title'),
                                                            html.Div([
                                                                html.Div([html.Label('Width', className='form-label'),
                                                                          dmc.NumberInput(id='pub-fig-width-mm', debounce=True, clampBehavior='blur', value=84, min=1, step=1,
                                                                                          size='xs', style={'width': '100%'}, suffix=' mm')],
                                                                         style={'flex': '1'}),
                                                                html.Span('×', style={'fontSize': '14px', 'color': '#555', 'alignSelf': 'flex-end', 'paddingBottom': '6px'}),
                                                                html.Div([html.Label('Height', className='form-label'),
                                                                          dmc.NumberInput(id='pub-fig-height-mm', debounce=True, clampBehavior='blur', value=63, min=1, step=1,
                                                                                          size='xs', style={'width': '100%'}, suffix=' mm')],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '6px', 'alignItems': 'center', 'marginBottom': '10px'}),
                                                        ]),

                                                        # -- Smoothing --
                                                        html.Div('Smoothing', className='toolbox-section-title'),
                                                        html.Div([
                                                            dcc.Slider(id='pt-smooth-window', min=0, max=151, step=1,
                                                                       marks={0: 'Off', 9: '9', 21: '21', 51: '51', 101: '101', 151: '151'},
                                                                       value=0, updatemode='drag'),
                                                        ], style={'marginBottom': '10px'}),

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
                                                            # Themes are no longer user-facing: palette and the Plot/Paper
                                                            # backgrounds cover them. The control stays for saved settings.
                                                            html.Div(dmc.Select(id='pt-theme', value=DEFAULT_THEME, size='xs',
                                                                                data=theme_options(), clearable=False,
                                                                                allowDeselect=False), style={'display': 'none'}),
                                                        ]),
                                                        html.Div([
                                                            html.Label('Color palette', className='form-label'),
                                                            dmc.Select(id='pt-palette', value=DEFAULT_PALETTE, size='xs',
                                                                       data=palette_options(),
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
                                                        html.Div([
                                                            html.Div([html.Label('X axis', className='form-label'),
                                                                      dmc.TextInput(id='pt-x-label', value='Retention Time (min)', placeholder='Leave empty for none', size='xs')],
                                                                     style={'flex': '1'}),
                                                            html.Div([html.Label('Y axis', className='form-label'),
                                                                      dmc.TextInput(id='pt-y-label', value='Signal (mAU)', placeholder='Leave empty for none', size='xs')],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '6px', 'marginBottom': '6px'}),
                                                        dmc.Switch(id='pt-shared-axis-labels', label='Shared axis labels',
                                                                   checked=True, size='sm', mb=6),

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
                                                            html.Div(id='pt-title-size-wrapper', children=[
                                                                html.Label('Title size', className='form-label'),
                                                                dmc.NumberInput(id='pt-title-font-size', value=14, min=10, max=32, step=1,
                                                                                size='xs', style={'width': '100%'}),
                                                            ], style={'flex': '1'}),
                                                            html.Div([html.Label('Tick size', className='form-label'),
                                                                      dmc.NumberInput(id='pt-tick-font-size', value=10, min=6, max=18, step=1,
                                                                                      size='xs', style={'width': '100%'})],
                                                                     style={'flex': '1'}),
                                                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        html.Div(id='pt-bold-title-wrapper', children=[
                                                            dmc.Switch(id='pt-bold-title', label='Bold title', checked=True,
                                                                       size='sm', mb=10),
                                                        ]),

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
                                                                dmc.Checkbox(label='Minor ticks', value='minor_ticks'),
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
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                            html.Div([
                                                                html.Div([html.Label('Frame width', className='form-label'),
                                                                          dmc.NumberInput(id='pt-frame-width', value=1, min=0.5, max=5, step=0.5,
                                                                                          size='xs', style={'width': '100%'}, decimalScale=1)],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Tick length', className='form-label'),
                                                                          dmc.NumberInput(id='pt-tick-length', value=5, min=1, max=15, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                                                        ]),
                                                    ],
                                                ),
                                            ]),
                                            # Integration Tab
                                            dmc.TabsPanel(value="integration", style={'flex': '1', 'overflow': 'auto'}, children=[
                                                html.Div(id='integration-container', className='toolbox-tab-content integration-panel', children=[
                                                    html.Div(id='int-detection-target', className='integration-target', children='Select a signal in Files'),
                                                    html.Section(className='integration-section', children=[
                                                        html.Label('Baseline', className='toolbox-section-title', title='For new integrations. Automatic detection splits overlapping peaks vertically at valleys.'),
                                                        dmc.SegmentedControl(
                                                            id='integration-baseline', value='linear', fullWidth=True, size='xs',
                                                            data=[{'label': 'Straight line', 'value': 'linear'},
                                                                  {'label': 'Zero (y = 0)', 'value': 'zero'}],
                                                        ),
                                                    ]),
                                                    # Legacy callback targets; drawing lives in the plot toolbar.
                                                    html.Div(style={'display': 'none'}, children=[
                                                        html.Div(className='integration-actions', children=[
                                                            html.Button('Draw', id='baseline-draw-btn', className='btn btn-secondary', title='Draw an integration baseline on the plot'),
                                                            html.Button('Edit', id='baseline-edit-btn', style={'display': 'none'}),
                                                            html.Button('Nav', id='baseline-nav-btn', className='btn btn-secondary', style={'display': 'none'}),
                                                            html.Button('Clear', id='baseline-clear-btn', className='btn btn-secondary',
                                                                        title='Delete the selected peak, or all manual peaks in this signal if none is selected'),
                                                        ]),
                                                        html.Div(id='baseline-mode-indicator', style={'display': 'none'}),
                                                        html.Div(id='ctx-status', className='integration-help'),
                                                    ]),
                                                    html.Section(className='integration-section integration-detect', children=[
                                                        html.Div('Automatic detection', className='toolbox-section-title'),
                                                        html.Div(className='integration-field-head', children=[
                                                            html.Label('Sensitivity', className='form-label'),
                                                            html.Div(id='int-sensitivity-help', className='integration-help integration-value'),
                                                        ]),
                                                        dmc.Slider(id='int-detection-sensitivity', value=50, min=0, max=100, step=1,
                                                                   updatemode='mouseup', size='sm', thumbSize=16,
                                                                   thumbLabel='Peak detection sensitivity',
                                                                   className='integration-slider'),
                                                        html.Div([html.Span('Fewer peaks'), html.Span('More peaks')],
                                                                 className='integration-slider-labels'),
                                                        html.Div(className='integration-actions integration-actions-row', children=[
                                                            dmc.Button('Detect peaks', id='int-detect-btn', size='xs', variant='default', disabled=True),
                                                            dmc.Button('Clear detected', id='int-clear-btn', size='xs', variant='default', disabled=True,
                                                                       attributes={'title': 'Remove detected peaks from this signal only'}),
                                                            dmc.Button('Deconvolve…', id='deconv-btn', size='xs', variant='default',
                                                                       attributes={'title': 'Fit exponentially modified Gaussian components to the selected peak'}),
                                                        ]),
                                                    ]),
                                                    html.Section(className='integration-section integration-display', children=[
                                                        html.Div('Peak display and matching', className='toolbox-section-title'),
                                                        html.Div(className='integration-inline-row', children=[
                                                            dmc.CheckboxGroup(id='int-display-opts', value=['peaks'], children=[
                                                                dmc.Checkbox(label='Show integrated areas', value='peaks', size='xs'),
                                                            ]),
                                                            html.Div(className='integration-tolerance', children=[
                                                                html.Label('Match RT', className='form-label', htmlFor='int-rt-tolerance',
                                                                           title='Match retention time within this tolerance'),
                                                                dmc.NumberInput(id='int-rt-tolerance', value=0.3,
                                                                                min=0.05, max=1.0, step=0.05, decimalScale=2, size='xs',
                                                                                prefix='± ', suffix=' min', hideControls=True,
                                                                                className='integration-tolerance-input',
                                                                                **{'aria-label': 'Match retention time (± min)'}),
                                                            ]),
                                                        ]),
                                                    ]),
                                                    html.Section(className='integration-section integration-deconv', children=[
                                                        html.Div('Peak deconvolution', className='toolbox-section-title'),
                                                        html.Div(id='deconv-results-container', className='integration-help', title='Shift-click the plot to add a component. Drag a dotted line to set its apex and refit. Use × to remove a component.'),
                                                        html.Div(id='deconv-accept-cancel-row', className='integration-actions', children=[
                                                            dmc.Button('Accept fit', id='deconv-accept-btn', size='xs', variant='default', style={'display': 'none'}),
                                                            dmc.Button('Cancel', id='deconv-cancel-btn', size='xs', variant='default', style={'display': 'none'}),
                                                        ]),
                                                    ]),
                                                ]),
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
                                                            html.Label('Preset', className='form-label'),
                                                            dmc.Select(id='exp-preset', value='current', size='xs',
                                                                       data=[
                                                                           {'label': 'Keep current figure', 'value': 'current'},
                                                                           {'label': 'Single-column (84 mm)', 'value': 'single-col'},
                                                                           {'label': 'Full-width (174 mm)', 'value': 'full-width'},
                                                                           {'label': 'Presentation (16:9)', 'value': 'presentation'},
                                                                           {'label': 'Custom', 'value': 'custom'},
                                                                       ],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div([
                                                            html.Label('Format', className='form-label'),
                                                            dmc.Select(id='exp-fig-format', value='png', size='xs',
                                                                       data=[{'label': f.upper(), 'value': f} for f in ['png', 'svg', 'html', 'pdf', 'tiff']],
                                                                       clearable=False, allowDeselect=False),
                                                        ], style={'marginBottom': '6px'}),
                                                        html.Div(id='exp-custom-dims', children=[
                                                            html.Div([
                                                                html.Div([html.Label('Width (mm)', className='form-label'),
                                                                          dmc.NumberInput(id='exp-width', value=84, min=1, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                                html.Div([html.Label('Height (mm)', className='form-label'),
                                                                          dmc.NumberInput(id='exp-height', value=63, min=1, step=1,
                                                                                          size='xs', style={'width': '100%'})],
                                                                         style={'flex': '1'}),
                                                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
                                                        ], style={'display': 'none'}),
                                                        html.Div([
                                                            html.Label('Resolution', className='form-label'),
                                                            dmc.NumberInput(id='exp-dpi', min=72, max=1200, step=50, value=300, suffix=' DPI', debounce=True, size='xs'),
                                                        ], style={'marginBottom': '10px'}),
                                                        html.Div(id='exp-preset-info',
                                                                 style={'fontSize': '11px', 'color': '#666', 'marginBottom': '6px'}),
                                                        dmc.Button('Export Figure', id='exp-fig-btn', className='btn btn-primary', size='xs',
                                                                    style={'width': '100%', 'marginBottom': '6px'}),
                                                        dcc.Download(id='exp-fig-download'),
                                                        html.Button(
                                                            'Send Current Plot to Publication',
                                                            id='exp-open-pub-btn',
                                                            className='btn btn-secondary',
                                                            style={
                                                                'width': '100%',
                                                                'marginBottom': '10px',
                                                                'color': '#1a1a1a',
                                                                'backgroundColor': '#f5f5f5',
                                                                'border': '1px solid #c8c8c8',
                                                            },
                                                        ),
                                                        create_research_export(),
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
                            className='divider divider-horizontal',
                            **{'data-label-left': 'Sidebar',
                               'data-label-right': 'Plot'},
                            children=[html.Span(className='divider-label')],
                        ),
                        html.Div(
                            id='right-column',
                            className='right-column',
                            style={'display': 'flex', 'flexDirection': 'column', 'width': '76%'},
                            children=[
                                html.Div(
                                    id='right-top-panel',
                                    className='panel content-panel',
                                    style={'display': 'flex', 'flexDirection': 'column', 'overflow': 'hidden'},
                                    children=[
                                        html.Div(id='plot-toolbar', className='plot-toolbar', role='toolbar',
                                                 **{'aria-label': 'Plot tools'}, children=[
                                            html.Div(className='plot-toolbar-group', children=[
                                                html.Button('Overlay', id='plot-tool-overlay', n_clicks=0,
                                                            className='plot-tool active', title='Draw signals in the same pane'),
                                                html.Button('Separate', id='plot-tool-separate', n_clicks=0,
                                                            className='plot-tool', title='Draw each signal in its own pane'),
                                            ]),
                                            dmc.Checkbox(id='pub-zoom-sync', label='Link X axes', checked=True, size='xs'),
                                            html.Div(className='plot-toolbar-group', children=[
                                                html.Span('Y scaling', className='plot-toolbar-label'),
                                                dmc.SegmentedControl(id='plot-y-scope', value='independent', size='xs',
                                                    data=[{'label': 'Independent', 'value': 'independent'},
                                                          {'label': 'Shared', 'value': 'global'}]),
                                            ], title='Global scaling links signals with the same measurement units'),
                                            html.Button(html.Span(className='integration-tool-icon', **{'aria-hidden': 'true'}),
                                                        id='plot-tool-integrate', n_clicks=0,
                                                        className='plot-tool plot-tool-icon', title='Integrate peaks — drag across a peak. Shortcut: Shift-drag.',
                                                        **{'aria-pressed': 'false', 'aria-label': 'Integrate peaks'}),
                                            html.Button(_icon('tabler:pencil', width=20, height=20),
                                                        id='plot-tool-edit-text', className='plot-tool plot-tool-icon',
                                                        title='Edit text — click a name, title, axis label, or legend. Esc to finish.',
                                                        **{'aria-pressed': 'false', 'aria-label': 'Edit text'}),
                                            html.Div(id='plot-toolbar-sync', style={'display': 'none'}),
                                        ]),
                                        html.Div(
                                            className='panel-content viz-container',
                                            style={'position': 'relative'},
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
                                                            margin=dict(l=0, r=0, t=0, b=0),
                                                            annotations=[dict(
                                                                text='🦎  Drop files here to get started',
                                                                xref='paper', yref='paper',
                                                                x=0.5, y=0.5, showarrow=False,
                                                                font=dict(size=15, color='#bbb'),
                                                            )],
                                                        )
                                                    ),
                                                    responsive=True,
                                                    style={'display': 'none'},
                                                    config={
                                                        'responsive': True,
                                                        'displayModeBar': False,
                                                        'displaylogo': False,
                                                        'doubleClick': 'reset+autosize',
                                                        'scrollZoom': True,
                                                        'edits': {'shapePosition': True},
                                                    },
                                                ),
                                                html.Div(id='plot-workspace', style={
                                                    'width': '100%', 'height': '100%', 'position': 'relative'}),
                                                html.Div(id='plot-workspace-sync', style={'display': 'none'}),
                                                html.Div(
                                                    id='lcms-scan-cursor-overlay',
                                                    style={
                                                        'position': 'absolute',
                                                        'display': 'none',
                                                        'top': '0px',
                                                        'left': '0px',
                                                        'height': '0px',
                                                        'width': '18px',
                                                        'borderLeft': '2px dotted #111',
                                                        'zIndex': 30,
                                                        'pointerEvents': 'auto',
                                                        'cursor': 'col-resize',
                                                    },
                                                ),
                                                html.Div(id='pda-scan-cursor-overlay', style={
                                                    'position':'absolute', 'display':'none', 'top':'0px', 'left':'0px',
                                                    'height':'0px', 'width':'18px', 'borderLeft':'2px dotted #111',
                                                    'zIndex':30, 'pointerEvents':'none', 'cursor':'col-resize'}),
                                                create_paper_mock(),
                                                create_session_banner(),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id='right-vertical-divider',
                                    className='divider divider-vertical',
                                    **{'data-label-above': 'Plot',
                                       'data-label-below': 'Analysis'},
                                    children=[html.Span(className='divider-label')],
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
                                                        dmc.TabsTab("MS Scan", value="ms-scan"),
                                                        dmc.TabsTab("EIC", value="ms-eic"),
                                                        dmc.TabsTab("Peak Mass", value="ms-peak-mass"),
                                                        dmc.TabsTab("PDA", value="pda"),
                                                    ]),
                                                    dmc.TabsPanel(create_pda_explorer(), value="pda", style={'flex':'1', 'height':'100%', 'minHeight':0, 'overflow':'auto'}),
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
                                                                    page_size=50,
                                                                    page_action='native',
                                                                    style_table={'display': 'none'},
                                                                ),
                                                                html.Div(
                                                                    [
                                                                        _icon('tabler:table', width=36, height=36, color='#bbb'),
                                                                        html.H4('Select a file to view data', className='empty-state__title'),
                                                                        html.P(
                                                                            'Select a dataset in Files to view its table.',
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
                                                                style_cell={**TABLE_STYLE_CELL, 'minWidth':'72px', 'maxWidth':'180px', 'padding':'6px 8px'},
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
                                                        html.Div(id='peak-group-selector-wrapper', style={'display': 'none'}, children=[
                                                            html.Label("Peak group",
                                                                       style={'fontWeight': 'bold', 'marginBottom': '5px',
                                                                              'marginTop': '0', 'display': 'block', 'fontSize': '12px'}),
                                                            dcc.Dropdown(id='peak-group-selector', value=0,
                                                                         style={'marginBottom': '10px'}),
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
                                                            style_cell={**TABLE_STYLE_CELL, 'minWidth':'72px', 'maxWidth':'180px', 'padding':'6px 8px'},
                                                            style_header=TABLE_STYLE_HEADER,
                                                            style_header_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            style_data=TABLE_STYLE_DATA,
                                                            style_cell_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                            style_data_conditional=[{'if': {'column_id': '_row_id'}, 'display': 'none'}],
                                                        ),
                                                        html.Div([
                                                            dmc.Button('Calibrate selected peaks', id='cross-use-calibration-btn',
                                                                       size='xs', variant='default', disabled=True),
                                                            dmc.TextInput(id='group-label-input', size='xs',
                                                                          placeholder='Group label'),
                                                            dmc.Button('Apply to selected', id='apply-group-btn',
                                                                       size='xs', variant='default'),
                                                            dmc.Button('Clear groups', id='clear-groups-btn',
                                                                       size='xs', variant='default'),
                                                            html.Span(id='cross-calibration-feedback', role='status',
                                                                      style={'fontSize': '12px'}),
                                                        ], className='analysis-group-actions'),
                                                        # Static components that survive across-samples-container
                                                        # children replacement by update_across_samples_tab
                                                        html.Div(id='retention-slider-wrapper', style={'display': 'none'}, children=[
                                                            html.Label("Match peaks within (± min)",
                                                                       style={'fontWeight': 'bold', 'marginBottom': '5px',
                                                                              'display': 'block', 'fontSize': '14px'}),
                                                            dcc.Slider(id='retention-time-slider', min=0.05, max=1.0,
                                                                       step=0.05, value=0.2,
                                                                       marks={0.05: '0.05', 0.2: '0.2', 0.5: '0.5', 1.0: '1.0'},
                                                                       tooltip={"placement": "bottom", "always_visible": True}),
                                                        ]),
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
                                                                        _icon('tabler:info-circle', width=36, height=36, color='#bbb'),
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
                                                    dmc.TabsPanel(value="calibration", style={'flex':'1','minHeight':0,'overflow':'auto'},
                                                                  children=create_calibration_panel()),
                                                    # ── MS Scan tab ──
                                                    dmc.TabsPanel(value="ms-scan", style={'flex': '1', 'minHeight': 0, 'overflow': 'auto'}, children=[
                                                    html.Div(className="tab-content analysis-graph-content", style={
                                                        'display': 'flex', 'flexDirection': 'column', 'padding': '10px 14px',
                                                        'height': '100%', 'minHeight': 0, 'boxSizing': 'border-box', 'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div([
                                                            html.Div('MS scan', style={
                                                                'fontWeight': 'bold', 'fontSize': '12px'}),
                                                            create_spectrum_polarity_control('ms'),
                                                        ], style={
                                                            'display': 'flex', 'justifyContent': 'space-between',
                                                            'alignItems': 'center', 'margin': '0 0 4px 2px'}),
                                                        html.Div(id='ms-scan-label',
                                                                 children='No scan selected',
                                                                 style={'fontSize': '11px', 'color': '#555',
                                                                        'marginBottom': '2px', 'marginLeft': '2px'}),
                                                        html.Div([
                                                            dcc.Slider(id='ms-scan-slider',
                                                                       min=0, max=1, step=1, value=0,
                                                                       updatemode='drag',
                                                                       marks=None,
                                                                       tooltip={'placement': 'bottom', 'always_visible': False}),
                                                        ], style={'padding': '0 4px 4px 4px'}),
                                                        dcc.Graph(id='ms-spectrum-graph',
                                                                  figure=go.Figure(layout=go.Layout(
                                                                      template='plotly_white',
                                                                      margin=dict(l=50, r=20, t=10, b=38),
                                                                      xaxis=dict(visible=False),
                                                                      yaxis=dict(visible=False),
                                                                      annotations=[dict(
                                                                          text='Click TIC/EIC or extract a target ion',
                                                                          xref='paper', yref='paper',
                                                                          x=0.5, y=0.5, showarrow=False,
                                                                          font=dict(size=13, color='#999'),
                                                                      )])),
                                                                  responsive=True,
                                                                  className='analysis-graph',
                                                                  style={'width': '100%', 'height': '0px',
                                                                         'minHeight': '140px', 'flex': '1 0 140px'},
                                                                  config={
                                                                      'responsive': True,
                                                                      'displayModeBar': False,
                                                                      'displaylogo': False,
                                                                      'doubleClick': 'reset+autosize',
                                                                      'scrollZoom': True,
                                                                  }),
                                                        html.Div(id='ms-spectrum-info',
                                                                 style={'fontSize': '12px', 'padding': '6px 8px',
                                                                        'backgroundColor': 'rgba(0,0,0,0.02)',
                                                                        'borderRadius': '6px', 'marginTop': '4px',
                                                                        'minHeight': '20px'}),
                                                    ]),
                                                    ]),
                                                    # ── EIC tab ──
                                                    dmc.TabsPanel(value="ms-eic", style={'flex': '1', 'minHeight': 0, 'overflow': 'auto'}, children=[
                                                    html.Div(className="tab-content analysis-graph-content", style={
                                                        'display': 'flex', 'flexDirection': 'column', 'padding': '10px 14px',
                                                        'height': '100%', 'minHeight': 0, 'boxSizing': 'border-box', 'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div([
                                                            html.Div('Extracted ion chromatogram', style={
                                                                'fontWeight': 'bold', 'fontSize': '12px'}),
                                                            create_spectrum_polarity_control('eic'),
                                                        ], style={
                                                            'display': 'flex', 'justifyContent': 'space-between',
                                                            'alignItems': 'center', 'margin': '0 0 4px 2px'}),
                                                        html.Div([
                                                            html.Div([
                                                                html.Label('Target m/z', className='form-label'),
                                                                dcc.Input(id='eic-mz-input', type='number',
                                                                          placeholder='e.g. 294.1',
                                                                          className='form-input',
                                                                          style={'width': '100%'}),
                                                            ], style={'flex': '2', 'minWidth': '120px'}),
                                                            html.Div([
                                                                html.Label('Tolerance', className='form-label'),
                                                                dcc.Input(id='eic-tolerance-input', type='number',
                                                                          value=0.5, step=0.1,
                                                                          className='form-input',
                                                                          style={'width': '100%'}),
                                                            ], style={'flex': '1', 'minWidth': '90px'}),
                                                            html.Div([
                                                                html.Button('Extract', id='eic-extract-btn',
                                                                            className='btn btn-primary',
                                                                            style={'width': '100%'}),
                                                            ], style={'flex': '1', 'minWidth': '90px', 'paddingTop': '18px'}),
                                                            html.Div([
                                                                html.Button('Clear', id='eic-clear-btn',
                                                                            className='btn',
                                                                            style={'width': '100%'}),
                                                            ], style={'flex': '0.7', 'minWidth': '72px', 'paddingTop': '18px'}),
                                                        ], style={'display': 'flex', 'gap': '8px',
                                                                  'alignItems': 'flex-start',
                                                                  'flexWrap': 'wrap'}),
                                                        html.Div(id='eic-active-list', style={
                                                            'marginTop': '8px', 'display': 'flex',
                                                            'flexWrap': 'wrap', 'gap': '4px'}),
                                                        dcc.Graph(id='eic-graph',
                                                                  figure=go.Figure(layout=go.Layout(
                                                                      template='plotly_white',
                                                                      margin=dict(l=50, r=20, t=10, b=36),
                                                                      xaxis=dict(visible=False),
                                                                      yaxis=dict(visible=False),
                                                                      annotations=[dict(
                                                                          text='Extract an EIC to view it here',
                                                                          xref='paper', yref='paper',
                                                                          x=0.5, y=0.5, showarrow=False,
                                                                          font=dict(size=13, color='#999'),
                                                                      )])),
                                                                  responsive=True,
                                                                  className='analysis-graph',
                                                                  style={'width': '100%', 'height': '0px',
                                                                         'minHeight': '140px', 'flex': '1 0 140px'},
                                                                  config={
                                                                      'responsive': True,
                                                                      'displayModeBar': False,
                                                                      'displaylogo': False,
                                                                      'doubleClick': 'reset+autosize',
                                                                      'scrollZoom': True,
                                                                  }),
                                                    ]),
                                                    ]),
                                                    # ── Peak Mass tab ──
                                                    dmc.TabsPanel(value="ms-peak-mass", style={'flex': '1', 'minHeight': 0, 'overflow': 'auto'}, children=[
                                                    html.Div(className="tab-content analysis-graph-content", style={
                                                        'display': 'flex', 'flexDirection': 'column', 'padding': '10px 14px',
                                                        'height': '100%', 'minHeight': 0, 'boxSizing': 'border-box', 'overflowY': 'auto'
                                                    }, children=[
                                                        html.Div([
                                                            html.Div('Peak mass spectrum', style={
                                                                'fontWeight': 'bold', 'fontSize': '12px'}),
                                                            create_spectrum_polarity_control('peak-mass'),
                                                        ], style={
                                                            'display': 'flex', 'justifyContent': 'space-between',
                                                            'alignItems': 'center', 'marginBottom': '6px'}),
                                                        dmc.Select(
                                                            id='peak-mass-selector',
                                                            placeholder='Select a peak...',
                                                            data=[],
                                                            size='xs',
                                                            clearable=True,
                                                            style={'marginBottom': '8px'},
                                                        ),
                                                        dcc.Graph(id='peak-mass-graph',
                                                                  figure=go.Figure(layout=go.Layout(
                                                                      template='plotly_white',
                                                                      margin=dict(l=50, r=20, t=10, b=38),
                                                                      xaxis=dict(visible=False),
                                                                      yaxis=dict(visible=False),
                                                                      annotations=[dict(
                                                                          text='Select a peak to view its mass spectrum',
                                                                          xref='paper', yref='paper',
                                                                          x=0.5, y=0.5, showarrow=False,
                                                                          font=dict(size=13, color='#999'),
                                                                      )])),
                                                                  responsive=True,
                                                                  className='analysis-graph',
                                                                  style={'width': '100%', 'height': '0px',
                                                                         'minHeight': '140px', 'flex': '1 0 140px'},
                                                                  config={
                                                                      'responsive': True,
                                                                      'displayModeBar': False,
                                                                      'displaylogo': False,
                                                                      'doubleClick': 'reset+autosize',
                                                                      'scrollZoom': True,
                                                                  }),
                                                        html.Div(id='peak-mass-info',
                                                                 style={'fontSize': '12px', 'padding': '6px 8px',
                                                                        'backgroundColor': 'rgba(0,0,0,0.02)',
                                                                        'borderRadius': '6px', 'marginTop': '4px',
                                                                        'minHeight': '20px'}),
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
                                'background': 'none', 'border': '1px solid rgba(255,255,255,0.2)',
                                'color': 'rgba(255,255,255,0.4)', 'fontSize': '10px', 'padding': '1px 8px',
                                'cursor': 'pointer', 'borderRadius': '4px', 'marginLeft': '10px',
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

        dcc.Upload(
            id='global-drop-zone',
            multiple=True,
            disable_click=True,
            className='global-drop-zone',
            className_active='global-drop-zone global-drop-zone--armed global-drop-zone--active',
            className_reject='global-drop-zone global-drop-zone--armed global-drop-zone--reject',
            children=html.Div(
                className='global-drop-zone__hint',
                children=[
                    html.Div('Drop files to import', className='global-drop-zone__title'),
                    html.Div('Agilent exports, CSV, Excel, text, images', className='global-drop-zone__subtitle'),
                ],
            ),
        ),

        html.Div(id='resize-init-trigger', style={'display': 'none'}),
        html.Div(id='plot-layout-sync-trigger', style={'display': 'none'}),

        # -- Right-click context menu (peaks) --
        # Fixed anchor moved to the cursor by a callback; the portal dropdown
        # opens relative to it. Dismissal (outside-click / Escape) is native.
        html.Div(
            id='context-menu-anchor',
            style={'position': 'fixed', 'left': '0px', 'top': '0px',
                   'width': '1px', 'height': '1px', 'zIndex': 4000,
                   'pointerEvents': 'none'},
            children=popup_menu('context-menu', [
                menu_item('Delete Peak', id='ctx-delete-item'),
                menu_item('Rename Peak', id='ctx-rename-item'),
                menu_item('Baseline y = 0', id='ctx-zero-baseline-item'),
                menu_item('Auto-deconvolve', id='ctx-deconvolve-item'),
                menu_item('Show Mass', id='ctx-show-mass-item'),
                menu_item('Integrate in All Files', id='ctx-integrate-item'),
            ]),
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

        # -- MS plot right-click context menu (Open as new plot) --
        html.Div(
            id='ms-plot-context-menu-anchor',
            style={'position': 'fixed', 'left': '0px', 'top': '0px',
                   'width': '1px', 'height': '1px', 'zIndex': 4000,
                   'pointerEvents': 'none'},
            children=popup_menu('ms-plot-context-menu', [
                menu_item('Open as new plot', id='ms-ctx-open-new-plot'),
                menu_divider(),
                *_figure_actions('ms'),
            ]),
        ),
        # -- Right-click plot customization panel (axis editor) --
        html.Div(id='figure-context-anchor',
            style={'position': 'fixed', 'left': '0px', 'top': '0px',
                   'width': '1px', 'height': '1px', 'zIndex': 4000, 'pointerEvents': 'none'},
            children=popup_menu('figure-context-menu', _figure_actions('figure'))),
        html.Div(
            id='axis-context-panel',
            className='axis-context-panel',
            style={'display': 'none'},
            children=[
                html.Div(
                    className='axis-context-panel__header',
                    children=[
                        html.Div(id='axis-ctx-title', className='axis-context-panel__title',
                                 children='X-axis'),
                        html.Button('×', id='axis-ctx-close',
                                    className='axis-context-panel__close',
                                    title='Close'),
                    ],
                ),
                html.Div('Axes', className='axis-context-panel__section'),
                dmc.Switch(id='axis-ctx-auto-range', label='Auto range',
                           checked=True, size='sm', mb=8),
                html.Div(
                    id='axis-ctx-range-row',
                    className='axis-context-panel__range-row',
                    children=[
                        html.Div([
                            html.Label('X min', id='axis-ctx-min-label',
                                       className='form-label'),
                            dmc.NumberInput(id='axis-ctx-x-min', size='xs',
                                            disabled=True, style={'width': '100%'}),
                        ], style={'flex': '1'}),
                        html.Div([
                            html.Label('X max', id='axis-ctx-max-label',
                                       className='form-label'),
                            dmc.NumberInput(id='axis-ctx-x-max', size='xs',
                                            disabled=True, style={'width': '100%'}),
                        ], style={'flex': '1'}),
                    ],
                ),
                html.Div(id='axis-ctx-label', style={'display': 'none'}),
                html.Div(id='axis-ctx-label-size', style={'display': 'none'}),
                html.Div([
                    html.Div([
                        html.Label('Scale', className='form-label'),
                        dmc.Select(
                            id='axis-ctx-scale',
                            value='linear',
                            size='xs',
                            data=[
                                {'label': 'Linear', 'value': 'linear'},
                                {'label': 'Log', 'value': 'log'},
                            ],
                            clearable=False,
                            allowDeselect=False,
                            comboboxProps={'withinPortal': True, 'zIndex': 5000},
                        ),
                    ], style={'flex': '1'}),
                    html.Div([
                        html.Label('Tick length', className='form-label'),
                        dmc.NumberInput(id='axis-ctx-tick-length', value=5,
                                        min=1, max=15, step=1, size='xs',
                                        style={'width': '100%'}),
                    ], style={'flex': '1'}),
                ], className='axis-context-panel__range-row'),
                html.Div([
                    html.Label('Tick direction', className='form-label'),
                    dmc.Select(
                        id='axis-ctx-tick-dir',
                        value='outside',
                        size='xs',
                        data=[
                            {'label': 'Outside', 'value': 'outside'},
                            {'label': 'Inside', 'value': 'inside'},
                            {'label': 'None', 'value': 'none'},
                        ],
                        clearable=False,
                        allowDeselect=False,
                        comboboxProps={'withinPortal': True, 'zIndex': 5000},
                    ),
                ], style={'marginTop': '8px'}),
                dmc.Switch(id='axis-ctx-grid', label='Grid lines',
                           checked=False, size='sm', mt=10, mb=6),
                dmc.Switch(id='axis-ctx-minor-ticks', label='Minor ticks',
                           checked=False, size='sm'),
            ],
        ),

        html.Div(
            id='legend-context-panel',
            className='axis-context-panel',
            style={'display': 'none'},
            children=[
                html.Div(
                    className='axis-context-panel__header',
                    children=[
                        html.Div('Legend', className='axis-context-panel__title'),
                        html.Button('×', id='legend-ctx-close',
                                    className='axis-context-panel__close',
                                    title='Close'),
                    ],
                ),
                dmc.NumberInput(id='legend-ctx-font-size', label='Font size', min=6, max=48, step=1, value=10, size='xs', debounce=True, mb=8),
                dmc.Switch(id='legend-ctx-show', label='Show legend',
                           checked=True, size='sm', mb=8),
                html.Div([
                    html.Label('Position', className='form-label'),
                    dmc.Select(
                        id='legend-ctx-pos',
                        value='top-right',
                        size='xs',
                        data=[
                            {'label': 'Top Right', 'value': 'top-right'},
                            {'label': 'Top Left', 'value': 'top-left'},
                            {'label': 'Bottom Right', 'value': 'bottom-right'},
                            {'label': 'Bottom Left', 'value': 'bottom-left'},
                        ],
                        clearable=False,
                        allowDeselect=False,
                        comboboxProps={'withinPortal': True, 'zIndex': 5000},
                    ),
                ]),
            ],
        ),

        # -- Right-click trace editor --
        html.Div(
            id='trace-context-panel',
            className='axis-context-panel',
            style={'display': 'none'},
            children=[
                html.Div(
                    className='axis-context-panel__header',
                    children=[
                        html.Div(id='trace-ctx-title',
                                 className='axis-context-panel__title',
                                 children='Trace'),
                        html.Button('×', id='trace-ctx-close',
                                    className='axis-context-panel__close',
                                    title='Close'),
                    ],
                ),
                html.Div('Style', className='axis-context-panel__section'),
                html.Div([
                    html.Div([
                        html.Label('Color', className='form-label'),
                        dmc.ColorInput(
                            id='trace-ctx-color',
                            size='xs',
                            format='hex',
                            swatches=[
                                '#E69F00', '#56B4E9', '#009E73', '#F0E442',
                                '#0072B2', '#D55E00', '#CC79A7', '#1d1d1f',
                            ],
                        ),
                    ], style={'flex': '2'}),
                    html.Div([
                        html.Label('Opacity', className='form-label'),
                        dmc.NumberInput(id='trace-ctx-opacity', value=1.0,
                                        min=0.1, max=1.0, step=0.1, size='xs',
                                        decimalScale=1,
                                        style={'width': '100%'}),
                    ], style={'flex': '1'}),
                ], className='axis-context-panel__range-row'),
                html.Div([
                    html.Label('Mode', className='form-label'),
                    dmc.Select(
                        id='trace-ctx-mode',
                        value='lines',
                        size='xs',
                        data=[
                            {'label': 'Line', 'value': 'lines'},
                            {'label': 'Markers', 'value': 'markers'},
                            {'label': 'Line + Markers', 'value': 'lines+markers'},
                        ],
                        clearable=False,
                        allowDeselect=False,
                        comboboxProps={'withinPortal': True, 'zIndex': 5000},
                    ),
                ], style={'marginTop': '8px'}),
                html.Div(
                    id='trace-ctx-line-section',
                    children=[
                        html.Div([
                            html.Div([
                                html.Label('Line width', className='form-label'),
                                dmc.NumberInput(id='trace-ctx-line-width', value=1.5,
                                                min=0.5, max=8, step=0.5, size='xs',
                                                style={'width': '100%'}),
                            ], style={'flex': '1'}),
                            html.Div([
                                html.Label('Line style', className='form-label'),
                                dmc.Select(
                                    id='trace-ctx-line-style',
                                    value='solid',
                                    size='xs',
                                    data=[
                                        {'label': 'Solid', 'value': 'solid'},
                                        {'label': 'Dash', 'value': 'dash'},
                                        {'label': 'Dot', 'value': 'dot'},
                                        {'label': 'Dash-dot', 'value': 'dashdot'},
                                    ],
                                    clearable=False,
                                    allowDeselect=False,
                                    comboboxProps={'withinPortal': True, 'zIndex': 5000},
                                ),
                            ], style={'flex': '1'}),
                        ], className='axis-context-panel__range-row'),
                    ],
                    style={'marginTop': '8px'},
                ),
                html.Div(
                    id='trace-ctx-marker-section',
                    children=[
                        html.Div([
                            html.Div([
                                html.Label('Marker size', className='form-label'),
                                dmc.NumberInput(id='trace-ctx-marker-size', value=6,
                                                min=1, max=20, step=1, size='xs',
                                                style={'width': '100%'}),
                            ], style={'flex': '1'}),
                            html.Div([
                                html.Label('Marker', className='form-label'),
                                dmc.Select(
                                    id='trace-ctx-marker-symbol',
                                    value='circle',
                                    size='xs',
                                    data=[
                                        {'label': 'Circle', 'value': 'circle'},
                                        {'label': 'Square', 'value': 'square'},
                                        {'label': 'Diamond', 'value': 'diamond'},
                                        {'label': 'Cross', 'value': 'cross'},
                                        {'label': 'X', 'value': 'x'},
                                    ],
                                    clearable=False,
                                    allowDeselect=False,
                                    comboboxProps={'withinPortal': True, 'zIndex': 5000},
                                ),
                            ], style={'flex': '1'}),
                        ], className='axis-context-panel__range-row'),
                    ],
                    style={'marginTop': '8px', 'display': 'none'},
                ),
                dmc.Button('Reset to default', id='trace-ctx-reset',
                           variant='subtle', size='xs', color='gray',
                           mt=10, fullWidth=True),
            ],
        ),

        # -- Right-click title / axis label editor --
        html.Div(
            id='title-context-panel',
            className='axis-context-panel',
            style={'display': 'none'},
            children=[
                html.Div(
                    className='axis-context-panel__header',
                    children=[
                        html.Div(id='title-ctx-header',
                                 className='axis-context-panel__title',
                                 children='Title'),
                        html.Button('×', id='title-ctx-close',
                                    className='axis-context-panel__close',
                                    title='Close'),
                    ],
                ),
                html.Div('Title', className='axis-context-panel__section'),
                dmc.TextInput(id='title-ctx-title', size='xs',
                              placeholder='Plot title'),
                html.Div([
                    html.Div([
                        html.Label('Font size', className='form-label'),
                        dmc.NumberInput(id='title-ctx-title-size', value=12,
                                        min=8, max=32, step=1, size='xs',
                                        style={'width': '100%'}),
                    ], style={'flex': '1'}),
                    html.Div([
                        html.Label('Font', className='form-label'),
                        dmc.Select(
                            id='title-ctx-font',
                            value='Arial',
                            size='xs',
                            data=[
                                {'label': 'Arial', 'value': 'Arial'},
                                {'label': 'Helvetica', 'value': 'Helvetica'},
                                {'label': 'Times New Roman', 'value': 'Times New Roman'},
                                {'label': 'Courier New', 'value': 'Courier New'},
                                {'label': 'Georgia', 'value': 'Georgia'},
                                {'label': 'Calibri', 'value': 'Calibri'},
                            ],
                            clearable=False,
                            allowDeselect=False,
                            comboboxProps={'withinPortal': True, 'zIndex': 5000},
                        ),
                    ], style={'flex': '1'}),
                ], className='axis-context-panel__range-row',
                   style={'marginTop': '8px'}),
                dmc.Switch(id='title-ctx-bold', label='Bold',
                           checked=True, size='sm', mt=8),
                html.Div(id='title-ctx-label-size', style={'display': 'none'}),
            ],
        ),

        # -- Right-click axis label editor --
        html.Div(
            id='label-context-panel',
            className='axis-context-panel',
            style={'display': 'none'},
            children=[
                html.Div(
                    className='axis-context-panel__header',
                    children=[
                        html.Div(id='label-ctx-header',
                                 className='axis-context-panel__title',
                                 children='X-Axis Label'),
                        html.Button('×', id='label-ctx-close',
                                    className='axis-context-panel__close',
                                    title='Close'),
                    ],
                ),
                html.Div('Label', className='axis-context-panel__section'),
                dmc.TextInput(id='label-ctx-text', size='xs',
                              placeholder='Axis label'),
                html.Div([
                    html.Div([
                        html.Label('Font size', className='form-label'),
                        dmc.NumberInput(id='label-ctx-font-size', value=14,
                                        min=6, max=24, step=1, size='xs',
                                        style={'width': '100%'}),
                    ], style={'flex': '1'}),
                    html.Div([
                        html.Label('Font', className='form-label'),
                        dmc.Select(
                            id='label-ctx-font',
                            value='Arial',
                            size='xs',
                            data=[
                                {'label': 'Arial', 'value': 'Arial'},
                                {'label': 'Helvetica', 'value': 'Helvetica'},
                                {'label': 'Times New Roman', 'value': 'Times New Roman'},
                                {'label': 'Courier New', 'value': 'Courier New'},
                                {'label': 'Georgia', 'value': 'Georgia'},
                                {'label': 'Calibri', 'value': 'Calibri'},
                            ],
                            clearable=False,
                            allowDeselect=False,
                            comboboxProps={'withinPortal': True, 'zIndex': 5000},
                        ),
                    ], style={'flex': '1'}),
                ], className='axis-context-panel__range-row',
                   style={'marginTop': '8px'}),
            ],
        ),
    ]
)

# DMC 2.x requires a MantineProvider ancestor for any DMC component to render.
def _add_figure_actions_to_editors(component):
    children = getattr(component, 'children', None)
    if getattr(component, 'id', None) in (
            'legend-context-panel', 'trace-context-panel', 'title-context-panel'):
        component.children = [*(children or []), html.Div(
            _figure_actions(component.id, menu=False), className='figure-editor-actions')]
        return
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, 'children'):
            _add_figure_actions_to_editors(child)


_add_figure_actions_to_editors(_layout_body)


def _commit_numeric_inputs_on_enter(component):
    if isinstance(component, dmc.NumberInput):
        component.debounce = True
    children = getattr(component, 'children', None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if child is not None:
            _commit_numeric_inputs_on_enter(child)


from components.workspace_layout import arrange_workspace
arrange_workspace(_layout_body)

_commit_numeric_inputs_on_enter(_layout_body)

app.layout = dmc.MantineProvider(
    theme={"primaryColor": "dark"},
    children=[_layout_body],
)

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
register_plot_context_menu_callbacks(app, data_manager)
register_deconvolution_callbacks(app, data_manager)
register_export_callbacks(app, data_manager)
register_research_export_callbacks(app, data_manager)
register_provenance_capture(app, data_manager)
register_publication_preview_callbacks(app, data_manager)
register_calibration_callbacks(app, data_manager)
register_plot_settings_callbacks(app, data_manager)
register_lcms_callbacks(app, data_manager)
from callbacks.pda_callbacks import register_pda_callbacks
register_pda_callbacks(app, data_manager)
register_ms_context_menu_callbacks(app, data_manager)
register_figure_actions_callbacks(app)
from callbacks.axis_inspector_callbacks import register_axis_inspector_callbacks
register_axis_inspector_callbacks(app)
from callbacks.workspace_callbacks import register_workspace_callbacks
register_workspace_callbacks(app, data_manager)
from callbacks.ms_polarity_callbacks import register_ms_polarity_callbacks
register_ms_polarity_callbacks(app, data_manager)
from callbacks.session_callbacks import register_session_callbacks
register_session_callbacks(app, data_manager)

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
    target = toolbox_tab or 'plot-tools'
    if target != tab_value:
        return target
    return dash.no_update

clientside_callback(
    ClientsideFunction(namespace='publicationWorkspace', function_name='update'),
    Output('pub-workspace-sync', 'children'),
    [Input('pub-preview-graph', 'data'), Input('active-plot-tab', 'data'),
     Input('plot-tabs', 'data'), Input('pub-preset', 'value'), Input('pub-view-mode', 'value')],
)

# Clientside callback for resize functionality
clientside_callback(
    ClientsideFunction(namespace='plotToolbar', function_name='update'),
    Output('plot-toolbar-sync', 'children'),
    [Input('plot-tool-overlay', 'n_clicks'), Input('plot-tool-separate', 'n_clicks'),
     Input('plot-tool-integrate', 'n_clicks'), Input('current-plot-settings', 'data'),
     Input('baseline-mode', 'data')],
)

clientside_callback(
    ClientsideFunction(namespace='plotWorkspace', function_name='update'),
    Output('plot-workspace-sync', 'children'),
    [Input('main-plot', 'figure'), Input('active-plot-tab', 'data'), Input('plot-tabs', 'data')],
)

clientside_callback(
    ClientsideFunction(namespace='resize', function_name='initializeResizeHandlers'),
    Output('resize-init-trigger', 'children'),
    Input('resize-init-trigger', 'id'),
)

clientside_callback(
    ClientsideFunction(namespace='resize', function_name='syncPlotTabLayout'),
    Output('plot-layout-sync-trigger', 'children'),
    [Input('active-plot-tab', 'data'),
     Input('plot-tabs', 'data')],
)

# File-tree selection highlight + hidden-file dimming via clientside callback
clientside_callback(
    """
    function(activeFile, hiddenFiles, _treeChildren) {
        requestAnimationFrame(function() {
            if (window._geckoApplyActiveFile) window._geckoApplyActiveFile(activeFile);
            if (window._geckoApplyHiddenFiles) window._geckoApplyHiddenFiles(hiddenFiles || []);
        });
        return '';
    }
    """,
    Output('dummy-output', 'children'),
    [Input('active-file', 'data'),
     Input('hidden-files', 'data'),
     Input('file-tree', 'children')],
)

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
    [Output('plot-tabs', 'data', allow_duplicate=True),
     Output('active-plot-tab', 'data', allow_duplicate=True),
     Output('custom-plot-figures', 'data', allow_duplicate=True),
     Output('toolbox-tab', 'data', allow_duplicate=True)],
    Input('exp-open-pub-btn', 'n_clicks'),
    [State('plot-tabs', 'data'),
     State('active-plot-tab', 'data'),
     State('main-plot', 'figure'),
     State('custom-plot-figures', 'data'),
     State('current-plot-settings', 'data')],
    prevent_initial_call=True,
)
def open_publication_preview(n_clicks, tabs, active_plot_tab, main_figure, figures, plot_settings):
    if not n_clicks or not active_plot_tab:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    tabs = tabs or []
    figures = dict(figures or {})
    source_tab = next((t for t in tabs if t.get('id') == active_plot_tab), None)
    if not source_tab:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    idx = 1 + sum(1 for t in tabs if t.get('type') == 'publication')
    pub_id = f'publication-{idx}-{n_clicks}'
    source_label = source_tab.get('label') or 'Plot'
    pub_tab = {'id': pub_id, 'label': f'Publication {idx}', 'type': 'publication'}

    entry = {
        'source_plot_tab': active_plot_tab,
        'source_label': source_label,
        'figure': main_figure,
    }
    if source_tab.get('type') == 'raw':
        entry['source_group_key'] = source_tab.get('group_key')
    elif source_tab.get('type') == 'custom':
        entry['figure'] = (figures.get(active_plot_tab) or {}).get('figure', main_figure)

    from services.figure_actions import publication_plot_settings
    entry['plot_settings'] = publication_plot_settings(entry.get('figure') or {}, plot_settings)
    figures[pub_id] = entry
    return [*tabs, pub_tab], pub_id, figures, 'plot-tools'


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
    """Sync the bottom panel when switching plot tabs.

    Custom plot tabs always switch to their source panel (e.g. across-samples).
    Raw plot tabs restore the user's last panel choice, defaulting to
    data-overview on first visit.
    """
    if not plot_tab:
        return dash.no_update
    if figures and plot_tab in figures:
        target = figures[plot_tab].get('source_tab')
        if target and target != current_panel:
            return target
        return dash.no_update
    memory = memory or {}
    target = memory.get(plot_tab, 'data-overview')
    if target and target != current_panel:
        return target
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

# Show figure-dimensions section only when Publication tab is active
clientside_callback(
    """
    function(activeTab) {
        if (activeTab && activeTab.indexOf('publication') === 0) {
            return {};
        }
        return {display: 'none'};
    }
    """,
    Output('pt-pub-dimensions-wrapper', 'style'),
    Input('active-plot-tab', 'data'),
)

if __name__ == '__main__':
    log.info("Starting GeckoPlotter V2...")
    log.info("Upload TXT chromatograms or CSV UV-Vis files to get started!")
    app.run(debug=True, port=8052)
