"""Diagnostic controls, local browser event endpoint and operation/error reporting."""
import logging
import re
import time

import dash
from dash import Input, Output, dcc
from flask import g, request

from services import diagnostics
from services.workspaces import current_session_id


def _files(store):
    try:
        return list(dict.fromkeys(c.original_filename for b in store.iter_bundles() for c in b.component_list))[:30]
    except Exception:
        return []


def register_diagnostics_callbacks(app):
    @app.callback([Output('diagnostics-share', 'checked'), Output('diagnostics-share', 'disabled'),
                   Output('diagnostics-status', 'children')], Input('about-modal', 'opened'),
                  prevent_initial_call=True)
    def diagnostic_status(opened):
        if not opened:
            raise dash.exceptions.PreventUpdate
        report = diagnostics.reporter()
        return report.enabled, not report.configured, report.status() + ' Report ID: ' + report.installation_id[:8]

    @app.callback(Output('diagnostics-status', 'children', allow_duplicate=True),
                  Input('diagnostics-share', 'checked'), prevent_initial_call=True)
    def share_diagnostics(checked):
        report = diagnostics.reporter()
        report.set_enabled(checked)
        return report.status() + ' Report ID: ' + report.installation_id[:8]

    @app.callback(Output('diagnostics-download', 'data'), Input('diagnostics-download-btn', 'n_clicks'),
                  prevent_initial_call=True)
    def download_diagnostics(clicks):
        if not clicks:
            raise dash.exceptions.PreventUpdate
        return dcc.send_string(diagnostics.reporter().log_text(), 'GeckoPlotter-diagnostics.jsonl')


def install_diagnostics(app, store, report=None):
    report = report or diagnostics.reporter()
    app.server.extensions['gecko_diagnostics'] = report

    def context():
        return {'filenames': _files(store), 'session_id': current_session_id()}

    @app.server.post('/_gecko/diagnostics/event')
    def browser_event():
        if request.content_length and request.content_length > 2048:
            return '', 413
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return '', 403
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or body.get('event') not in {'ui_action', 'client_error', 'page_loaded'}:
            return '', 400
        props = context()
        control = body.get('control')
        if isinstance(control, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,80}', control):
            props['control'] = control
        if body.get('action') in {'click', 'change'}:
            props['action'] = body['action']
        name = body.get('error_type')
        if isinstance(name, str) and re.fullmatch(r'[A-Za-z]+Error', name):
            props['error_type'] = name
        agent = request.user_agent.string
        match = re.search(r'(Edg|Firefox|Chrome|Version)/(\d+)', agent)
        props['browser'] = (match[1] + ' ' + match[2]) if match else 'Other'
        report.record(body['event'], **props)
        return '', 204

    @app.server.before_request
    def begin_operation():
        if request.path == '/_dash-update-component':
            g.diagnostics_start = time.monotonic()

    @app.server.after_request
    def finish_operation(response):
        if request.path != '/_dash-update-component':
            return response
        try:
            body = request.get_json(silent=True) or {}
            callback = app.callback_map.get(body.get('output'), {}).get('callback')
            operation = getattr(callback, '__name__', '')
            if 'diagnostic' in operation:
                return response
            tracked = any(word in operation for word in ('save_project', 'open_project', 'upload', 'integrat',
                          'export', 'calibration', 'toggle_group_channel', 'workspace_history', 'persist_plot_settings'))
            if not tracked and response.status_code < 400:
                return response
            outcome = 'failed' if response.status_code >= 400 else 'no_change' if response.status_code == 204 else 'completed'
            if operation == 'save_project' and response.status_code == 200:
                if len(response.data) > 1_000_000:
                    outcome = 'download_ready'
                else:
                    result = (response.get_json(silent=True) or {}).get('response', {})
                    kind = result.get('session-stamp', {}).get('data', {}).get('kind')
                    outcome = 'failed' if kind == 'failed' else 'download_ready' if 'session-download' in result else 'name_required'
            props = context()
            dependencies = body.get('inputs', []) + body.get('state', [])
            for dep in (item for dependency in dependencies
                        for item in (dependency if isinstance(dependency, list) else [dependency])):
                if dep.get('property') == 'filename':
                    names = dep.get('value')
                    props['filenames'] += names if isinstance(names, list) else [names] if isinstance(names, str) else []
            report.record('callback_finished', operation=operation, outcome=outcome,
                          http_status=response.status_code,
                          duration_ms=round(1000 * (time.monotonic() - getattr(g, 'diagnostics_start', time.monotonic()))),
                          **props)
        except Exception:
            pass  # Diagnostics must never break the user's operation.
        return response

    class ExceptionReports(logging.Handler):
        def emit(self, record):
            if record.exc_info and isinstance(record.exc_info[1], BaseException):
                try:
                    report.exception(record.exc_info[1], **context())
                except Exception:
                    pass

    handler = ExceptionReports(level=logging.ERROR)
    logging.getLogger().addHandler(handler)
    return report
