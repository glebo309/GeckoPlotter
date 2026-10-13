"""Project (.gecko) controls: header bar (name, status, Open, Save), stores, dialogs and the restore banner.

Plain HTML buttons and the plain-HTML popup menu only (no Mantine Menu/Tooltip: they slow every renderer update).
Behaviour lives in ``assets/js/session-io.js`` (clientside) and ``callbacks/session_callbacks.py`` (server).
"""
from dash import dcc, html
import dash_mantine_components as dmc

from components.popup_menu import popup_menu, menu_item, menu_divider

DEFAULT_NAME = 'Untitled project'


def create_session_header_controls():
    """Right end of the dark top bar: project name, status text, Open (with recent menu) and Save."""
    return html.Div(
        id='session-bar', className='session-bar',
        children=[
            html.Button(DEFAULT_NAME, id='session-name-btn', type='button', className='session-name',
                        title='Project name - click to rename'),
            html.Span('', id='session-status', className='session-status', role='status',
                      **{'aria-live': 'polite'}),
            html.Div(className='session-open-group', children=[
                dcc.Upload(
                    id='session-open-upload', accept='.gecko,.zip', multiple=False, className='session-open-upload',
                    children=html.Button('Open', id='session-open-btn', type='button', className='session-btn',
                                         title='Open a project (.gecko file, or a FAIR package .zip made by GeckoPlotter) - Cmd/Ctrl+O')),
                html.Button('▾', id='session-open-menu-btn', type='button', className='session-btn session-menu-btn',
                            title='Recent autosaves', **{'aria-haspopup': 'menu', 'aria-label': 'Recent autosaves'}),
                popup_menu('session-open-menu', [
                    menu_item('Open file…', id='session-open-file-item', **{'data-session-action': 'open-file'}),
                    menu_divider(),
                    html.Div('Recent autosaves', className='session-menu-title'),
                    html.Div(id='session-recent-list', className='session-recent-list',
                             children=html.Div('None yet', className='session-menu-empty')),
                ]),
            ]),
            html.Button('Save', id='session-save-btn', type='button', className='session-btn session-btn-save',
                        n_clicks=0, title='Save the project as a .gecko file - Cmd/Ctrl+S'),
        ],
    )


def create_session_banner():
    """Overlay at the top of the plot area: 'Restore last session?' and warnings after opening a project."""
    return html.Div(
        id='session-overlays', className='session-overlays',
        children=[
            html.Div(id='session-banner', className='session-banner', role='region', hidden=True,
                     **{'aria-label': 'Restore last session'}, children=[
                         html.Span('', id='session-banner-text', className='session-banner-text'),
                         html.Button('Restore', id='session-banner-restore', type='button', n_clicks=0,
                                     className='session-banner-btn session-banner-primary'),
                         html.Button('Start fresh', id='session-banner-dismiss', type='button', n_clicks=0,
                                     className='session-banner-btn'),
                     ]),
            # Unsaved-changes guard before opening a project; driven entirely by session-io.js (data-confirm buttons).
            html.Div(id='session-confirm', className='session-banner session-confirm', role='alertdialog', hidden=True,
                     **{'aria-label': 'Unsaved changes'}, children=[
                         html.Span('Opening replaces the current workspace. Unsaved changes will be lost.',
                                   id='session-confirm-text', className='session-banner-text'),
                         html.Button('Save first', type='button', className='session-banner-btn session-banner-primary',
                                     **{'data-confirm': 'save'}),
                         html.Button('Open anyway', type='button', className='session-banner-btn',
                                     **{'data-confirm': 'discard'}),
                         html.Button('Cancel', type='button', className='session-banner-btn',
                                     **{'data-confirm': 'cancel'}),
                     ]),
            html.Div(id='session-message', className='session-message', role='status', hidden=True, children=[
                html.Div(className='session-message-head', children=[
                    html.Span('', id='session-message-title', className='session-message-title'),
                    html.Button('×', id='session-message-close', type='button', n_clicks=0,
                                className='session-message-close', title='Dismiss', **{'aria-label': 'Dismiss'}),
                ]),
                html.Div('', id='session-message-body', className='session-message-body'),
            ]),
        ],
    )


def create_session_support():
    """Stores, the download target and the two dialogs. Not visible by themselves."""
    return html.Div(
        id='session-support', style={'display': 'none'},
        children=[
            dcc.Store(id='session-name', data=''),              # '' = untitled
            dcc.Store(id='session-dirty', data=False),          # changes since the last explicit save / open
            dcc.Store(id='session-stamp', data=None),           # {kind: saved|autosaved|opened|failed, at: 'HH:MM', fired?}
            dcc.Store(id='session-source', data=None),          # {path, name, upload} of the project last opened
            dcc.Store(id='session-upload-handoff', data=None),  # a .gecko arrived through a file-import zone
            dcc.Store(id='session-recent-pick', data=None),     # {path, ts} chosen in the Open menu
            dcc.Store(id='session-autosave-fire', data=None),   # set by session-io.js ~20 s after the last change
            dcc.Store(id='session-autosave-target', data=None),  # newest autosave offered by the banner
            dcc.Store(id='session-restore-late', data=None),    # tells session-io.js to finish applying a restore
            dcc.Store(id='session-late-go', data=None),         # written by session-io.js once the restore has settled
            dcc.Store(id='session-page-load', data=0),
            dcc.Download(id='session-download'),
            dmc.Modal(
                id='session-name-modal', title='Name your project', opened=False, size='sm', zIndex=4100,
                children=[
                    dmc.TextInput(id='session-name-input', placeholder='e.g. Alanine calibration 2026-03',
                                  label='Project name', size='sm'),
                    dmc.Group([
                        dmc.Button('Cancel', id='session-name-cancel', size='xs', variant='default'),
                        dmc.Button('Save', id='session-name-confirm', size='xs', color='dark'),
                    ], justify='flex-end', mt='sm'),
                ]),
            dmc.Modal(
                id='session-missing-modal', title='Some original files were not found', opened=False, size='lg',
                zIndex=4100,
                children=[
                    html.Div('The project was opened without these samples. Point GeckoPlotter at the folder '
                             'that holds the raw data and try again.', className='session-modal-note'),
                    html.Ul(id='session-missing-list', className='session-missing-list'),
                    dmc.TextInput(id='session-search-dir', label='Locate folder…',
                                  placeholder='/Users/you/Data/2026-03', size='sm'),
                    dmc.Group([
                        dmc.Button('Continue without them', id='session-missing-close', size='xs', variant='default'),
                        dmc.Button('Retry', id='session-retry-btn', size='xs', color='dark'),
                    ], justify='flex-end', mt='sm'),
                ]),
        ],
    )
