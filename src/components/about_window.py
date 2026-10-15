"""About GeckoPlotter: opened by clicking the logo in the header (callbacks/about_callbacks fills it)."""
import dash_mantine_components as dmc
from dash import dcc, html


def create_about_window():
    return dmc.Modal(
        id='about-modal', title='About GeckoPlotter', opened=False, size='lg', zIndex=4100,
        children=[
            html.Div(id='about-body'),
            html.Div(id='about-update', className='about-update'),
            dmc.Group([
                html.A('GeckoPlotter on GitHub', id='about-repo', href='', target='_blank', className='about-link'),
                html.Div(style={'flex': 1}),
                html.Div([dcc.Clipboard(id='about-copy', content='', className='about-copy-icon'),
                          html.Span('Copy details')], className='about-copy', title='Copy these details as text'),
                dmc.Button('Close', id='about-close', size='xs', variant='default'),
            ], mt='md', gap='sm'),
        ],
    )
