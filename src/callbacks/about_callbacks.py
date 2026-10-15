"""The About window (components/about_window): version, source, packages and folders (services/about)."""
import dash
from dash import Input, Output, html

from services import about


def _rows(pairs, path=False):
    return html.Table(className='about-table', children=[html.Tbody([
        html.Tr([html.Td(label, className='about-label'),
                 html.Td(value, className='about-path' if path else None)]) for label, value in pairs])])


def register_about_callbacks(app):

    @app.callback(
        [Output('about-modal', 'opened'), Output('about-body', 'children'), Output('about-copy', 'content'),
         Output('about-repo', 'href'), Output('about-update', 'children', allow_duplicate=True)],
        Input('app-logo', 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_about(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        data = about.info()
        version = html.A(data['version'], href=data['commit_url'], target='_blank', className='about-link') \
            if data['commit_url'] else data['version']
        body = [
            html.Div(className='about-head', children=[
                html.Span('🦎', className='about-gecko'),
                html.Div([html.Div(['GeckoPlotter ', html.Span(['version ', version], className='about-version')],
                                   className='about-name'),
                          html.Div(data['subject'], className='about-subject') if data['subject'] else None]),
            ]),
            _rows(data['details']),
            html.Div('Folders', className='about-section'),
            _rows(data['folders'], path=True),
        ]
        return True, body, about.as_text(data), data['repo_url'], 'Comparing with the newest version on GitHub…'

    @app.callback(
        Output('about-update', 'children'),
        Input('about-modal', 'opened'),
        prevent_initial_call=True,
    )
    def check_update(opened):
        if not opened:
            raise dash.exceptions.PreventUpdate
        return about.update_status(about.latest_sha())

    @app.callback(
        Output('about-modal', 'opened', allow_duplicate=True),
        Input('about-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_about(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        return False
