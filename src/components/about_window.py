"""About GeckoPlotter: opened by clicking the logo in the header (callbacks/about_callbacks fills it).

The banner's chromatogram is drawn by assets/js/about-window.js each time the window opens.
"""
import dash_mantine_components as dmc
from dash import dcc, html


def create_about_window():
    return dmc.Modal(
        id='about-modal', opened=False, size=560, zIndex=4100, padding=0, radius='lg', withCloseButton=False,
        classNames={'content': 'about-win', 'body': 'about-win-body'},
        children=[
            html.Div(className='about-banner', children=[
                html.Div(className='about-grid'),
                html.Div(className='about-art'),
                html.Div(id='about-peak', className='about-peak'),
                html.Div(className='about-title', children=[
                    html.H1('GeckoPlotter'),
                    html.Div(['Chromatograms · LC-MS mass data', html.Br(), 'spectra · any x/y data'], className='about-tag'),
                    html.Div('Checking GitHub…', id='about-status', className='about-status checking'),
                ]),
            ]),
            html.Div(className='about-main', children=[
                html.Div(id='about-body'),
                html.Div(id='about-update', className='about-update'),
                html.Div(className='about-claude', children=[
                    html.Div([html.Div('Use with Claude', className='about-claude-title'),
                              html.Div(id='about-claude-status', className='about-claude-status')]),
                    html.Button('Connect to Claude', id='about-claude-connect', className='about-btn', n_clicks=0,
                                title='Add GeckoPlotter to Claude Desktop and Claude Code on this computer, so Claude '
                                      'can open your data, integrate and export results'),
                ]),
                html.Div(className='about-foot', children=[
                    html.A('GitHub ↗', id='about-repo', href='', target='_blank'),
                    html.Div(style={'flex': 1}),
                    html.Div([dcc.Clipboard(id='about-copy', content='', className='about-copy-icon'),
                              html.Span('Copy details')], className='about-btn', title='Copy these details as text'),
                    html.Button('Close', id='about-close', className='about-btn primary', n_clicks=0,
                                **{'data-autofocus': True}),  # Mantine focuses this, not the first link
                ]),
            ]),
        ],
    )
