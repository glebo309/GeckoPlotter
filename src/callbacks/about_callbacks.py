"""The About window (components/about_window): version, source, packages and folders (services/about)."""
import dash
from dash import Input, Output, html

from services import about


def _rows(pairs, path=False):
    return [html.Tr([html.Td(label), html.Td(value, className='about-path' if path else None)]) for label, value in pairs]


def register_about_callbacks(app):

    @app.callback(
        [Output('about-modal', 'opened'), Output('about-body', 'children'), Output('about-copy', 'content'),
         Output('about-repo', 'href'), Output('about-peak', 'children'),
         Output('about-status', 'children', allow_duplicate=True),
         Output('about-status', 'className', allow_duplicate=True),
         Output('about-update', 'children', allow_duplicate=True)],
        Input('app-logo', 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_about(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        data = about.info()
        sha = html.A(data['sha'][:12], href=data['commit_url'], target='_blank') if data['commit_url'] else data['version']
        table = html.Table(className='about-table', children=[
            html.Thead(html.Tr([html.Th('Field'), html.Th('Value')])),
            html.Tbody([html.Tr([html.Td('Version'), html.Td(sha, className='about-mono')]), *_rows(data['summary'])]),
        ])
        return (True, table, about.as_text(data), data['repo_url'], data['version'],
                'Checking GitHub…', 'about-status checking', '')

    @app.callback(
        [Output('about-status', 'children'), Output('about-status', 'className'), Output('about-update', 'children')],
        Input('about-modal', 'opened'),
        prevent_initial_call=True,
    )
    def check_update(opened):
        if not opened:
            raise dash.exceptions.PreventUpdate
        latest = about.latest_sha()
        sha = about.VERSION.get('sha', '')
        if latest is None:
            return 'GitHub not reachable', 'about-status offline', ''
        if latest == sha:
            return f'Up to date with {about.BRANCH}', 'about-status ok', ''
        return f'Newer version: {latest[:7]}', 'about-status newer', about.update_status(latest)

    @app.callback(
        Output('about-claude-status', 'children'),
        Input('about-modal', 'opened'),
        prevent_initial_call=True,
    )
    def claude_status(opened):
        if not opened:
            raise dash.exceptions.PreventUpdate
        from services import claude_connect
        found = claude_connect.status()
        apps = [name for name, key in (('Claude Desktop', 'desktop'), ('Claude Code', 'code')) if found[key]]
        if not apps:
            return 'No Claude app found on this computer (claude.ai/download).'
        if found['desktop'] == 'connected':
            return 'Connected to Claude Desktop. ' + ('Claude Code found too.' if found['code'] else '')
        return 'Found: ' + ' and '.join(apps) + '. Connect so Claude can open your data, integrate and export.'

    @app.callback(
        Output('about-claude-status', 'children', allow_duplicate=True),
        Input('about-claude-connect', 'n_clicks'),
        prevent_initial_call=True,
    )
    def connect_claude(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        from services import claude_connect
        return [html.Div(message) for message in claude_connect.connect()]

    @app.callback(
        Output('about-modal', 'opened', allow_duplicate=True),
        Input('about-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_about(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        return False
