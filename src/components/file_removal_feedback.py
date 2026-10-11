"""Persistent, accessible feedback for reversible file removal."""
from dash import html


def create_file_removal_feedback():
    return html.Div([
        html.Span(id='file-removal-message', style={'flex': '1', 'minWidth': '0'}),
        html.Button('Undo removal', id='undo-file-removal-btn', n_clicks=0,
                    disabled=True, className='btn btn-secondary',
                    title='Restore the last removed file or signal'),
    ], id='file-removal-feedback', className='file-removal-feedback',
       role='status', **{'aria-live': 'polite', 'aria-atomic': 'true'},
       style={'display': 'none'})
