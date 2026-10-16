"""The About window (components/about_window): version, source, packages and folders (services/about)."""
import dash
from dash import Input, Output, html

from services import about


def _rows(pairs, path=False):
    return [html.Tr([html.Td(label), html.Td(value, className='about-path' if path else None)]) for label, value in pairs]


def register_about_callbacks(app, store=None):

    @app.callback(
        [Output('about-modal', 'opened'), Output('about-body', 'children'), Output('about-copy', 'content'),
         Output('about-repo', 'href'), Output('about-peak', 'children'),
         Output('about-status', 'children', allow_duplicate=True),
         Output('about-status', 'className', allow_duplicate=True),
         Output('about-update', 'children', allow_duplicate=True),
         Output('about-update-confirm', 'hidden', allow_duplicate=True)],
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
                'Checking GitHub…', 'about-status checking', '', True)

    @app.callback(
        [Output('about-status', 'children'), Output('about-status', 'className'), Output('about-update', 'children'),
         Output('about-status', 'disabled'), Output('about-status', 'title')],
        Input('about-modal', 'opened'),
        prevent_initial_call=True,
    )
    def check_update(opened):
        if not opened:
            raise dash.exceptions.PreventUpdate
        from services.self_update import can_update
        latest = about.latest_sha()
        sha = about.VERSION.get('sha', '')
        if latest is None:
            return 'GitHub not reachable', 'about-status offline', '', True, None
        if latest == sha:
            return f'Up to date with {about.BRANCH}', 'about-status ok', '', True, None
        if can_update():
            return (f'Update to {latest[:7]}', 'about-status newer clickable', '', False,
                    'A newer version is on GitHub: click to update')
        return (f'Newer version: {latest[:7]}', 'about-status newer', '', True,
                'This copy runs from a git checkout: update it with git pull')

    @app.callback(
        Output('about-update-confirm', 'hidden'),
        [Input('about-status', 'n_clicks'), Input('about-update-cancel', 'n_clicks')],
        prevent_initial_call=True,
    )
    def ask_update(update_clicks, cancel_clicks):
        return dash.ctx.triggered_id != 'about-status'

    @app.callback(
        [Output('about-update', 'children', allow_duplicate=True),
         Output('about-update-confirm', 'hidden', allow_duplicate=True)],
        Input('about-update-go', 'n_clicks'),
        running=[(Output('about-update-go', 'className'), 'about-btn primary busy', 'about-btn primary'),
                 (Output('about-update-go', 'disabled'), True, False)],
        prevent_initial_call=True,
    )
    def update_now(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        from services.self_update import can_update, restart_to_update
        if not can_update():
            return 'This copy cannot update itself (it runs from a git checkout).', True
        restart_to_update(store)
        return ('Updating: GeckoPlotter opens again in a new tab within a minute. You can close this tab.', True)

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
        apps = [(name, found[key]) for key, name, _restart in claude_connect.APPS if found[key]]
        if not apps:
            return 'No AI app found on this computer (Claude Desktop, Claude Code, Codex or Gemini CLI).'
        listed = ' · '.join(name + (' ✓' if state == 'connected' else '') for name, state in apps)
        if all(state == 'connected' for _name, state in apps):
            return listed + '. Connected: ask the agent to open your data.'
        return listed + '. Connect so an agent can open your data, integrate and export.'

    @app.callback(
        Output('about-claude-status', 'children', allow_duplicate=True),
        Input('about-claude-connect', 'n_clicks'),
        running=[(Output('about-claude-connect', 'className'), 'about-btn busy', 'about-btn'),
                 (Output('about-claude-connect', 'disabled'), True, False),
                 (Output('about-claude-status', 'className'), 'about-claude-status working', 'about-claude-status')],
        prevent_initial_call=True,
    )
    def connect_claude(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        from services import claude_connect
        done = claude_connect.connect()
        if not done['results']:
            return done['message']
        # The same line as before connecting, then what to do so each app sees it, then any failure on its own line.
        listed = ' · '.join(r['app'] + (' ✓' if r['ok'] else ' ✗') for r in done['results'])
        restarts = [r['restart'] for r in done['results'] if r['restart']]
        note = ('Connected. To use it: ' + '; '.join(restarts) + '.') if restarts else 'Connected: ask the agent to open your data.'
        failed = [html.Div(f"{r['app']} could not be connected: {r['error']}", className='about-claude-error')
                  for r in done['results'] if not r['ok']]
        failed += [html.Div(f"{r['app']}: {r['error']}", className='about-claude-error')
                   for r in done['results'] if r['ok'] and r['error']]
        return [html.Div(listed + '.'), html.Div(note), *failed]

    @app.callback(
        Output('about-modal', 'opened', allow_duplicate=True),
        Input('about-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_about(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        return False
