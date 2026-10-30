import json


def test_diagnostics_only_sends_approved_metadata_and_filenames(tmp_path):
    from services.diagnostics import Reporter
    sent = []
    reporter = Reporter(tmp_path, {'project_key': 'phc_test', 'host': 'https://eu.i.posthog.com'},
                        sender=lambda url, payload: sent.append((url, payload)), background=False)
    reporter.set_enabled(True)
    reporter.record('ui_action', control='session-name-confirm', action='click',
                    filenames=[r'C:\Users\evely\Research\sample.lcd'],
                    contents='SECRET DATA', measurements=[123.456], project_name='PRIVATE',
                    message='SECRET DATA failed', session_id='0123456789abcdef0123456789abcdef')
    reporter.flush()
    payload = sent[0][1]
    text = json.dumps(payload)
    assert 'sample.lcd' in text and 'session-name-confirm' in text
    assert 'SECRET' not in text and '123.456' not in text and 'PRIVATE' not in text
    assert 'Users' not in text and 'Research' not in text
    assert payload['api_key'] == 'phc_test'
    assert payload['batch'][0]['distinct_id'] == reporter.installation_id
    assert payload['batch'][0]['properties']['$geoip_disable'] is True
    assert payload['batch'][0]['properties']['$process_person_profile'] is False


def test_reports_stay_local_until_sharing_is_enabled_and_configured(tmp_path):
    from services.diagnostics import Reporter
    sent = []
    reporter = Reporter(tmp_path, {'project_key': 'phc_test'}, sender=lambda *args: sent.append(args), background=False)
    reporter.record('ui_action', control='session-name-confirm')
    reporter.flush()
    assert not sent
    assert 'session-name-confirm' in reporter.log_text()
    reporter.set_enabled(True)
    reporter.record('ui_action', control='session-save-btn')
    reporter.set_enabled(False)
    reporter.flush()
    assert not sent
    missing = Reporter(tmp_path / 'missing', {}, sender=lambda *args: sent.append(args), background=False)
    missing.set_enabled(True)
    missing.record('ui_action', control='session-save-btn')
    missing.flush()
    assert not sent


def test_network_failures_do_not_break_app_and_are_visible_in_status(tmp_path):
    from services.diagnostics import Reporter
    def fail(*args):
        raise OSError('unreachable')
    reporter = Reporter(tmp_path, {'project_key': 'phc_test'}, sender=fail, background=False)
    reporter.set_enabled(True)
    reporter.record('callback_finished', operation='save_project', outcome='failed')
    reporter.flush()
    assert 'offline' in reporter.status().lower()
    assert 'save_project' in reporter.log_text()


def test_exception_reports_have_code_locations_but_no_message_or_local_values(tmp_path):
    from services.diagnostics import Reporter
    sent = []
    reporter = Reporter(tmp_path, {'project_key': 'phc_test'}, sender=lambda url, payload: sent.append(payload), background=False)
    reporter.set_enabled(True)
    try:
        raise ValueError('SECRET sample measurement 23.45')
    except ValueError as exc:
        reporter.exception(exc)
    reporter.flush()
    report = sent[0]['batch'][0]
    assert report['event'] == '$exception'
    assert report['properties']['$exception_list'][0]['type'] == 'ValueError'
    assert 'test_diagnostics.py' in json.dumps(report)
    assert 'SECRET' not in json.dumps(report) and '23.45' not in json.dumps(report)


def test_diagnostics_control_is_visible_in_about_window():
    from components.about_window import create_about_window
    from components.workspace_layout import walk
    ids = {getattr(n, 'id', None) for n in walk(create_about_window()) if isinstance(getattr(n, 'id', None), str)}
    assert {'diagnostics-share', 'diagnostics-status', 'diagnostics-download-btn', 'diagnostics-download'} <= ids


def test_browser_event_endpoint_ignores_input_values_and_content(tmp_path):
    from flask import Flask
    from services.diagnostics import Reporter
    from callbacks.diagnostics_callbacks import install_diagnostics
    from services.data_store import DataStore
    from types import SimpleNamespace
    server = Flask(__name__)
    report = Reporter(tmp_path, {}, background=False)
    app = SimpleNamespace(server=server, callback_map={})
    install_diagnostics(app, DataStore(), report)
    result = server.test_client().post('/_gecko/diagnostics/event', json={
        'event': 'ui_action', 'control': 'session-name-confirm', 'action': 'click',
        'value': 'SECRET', 'contents': 'SECRET', 'measurements': [1,2,3]})
    assert result.status_code == 204
    assert 'session-name-confirm' in report.log_text()
    assert 'SECRET' not in report.log_text()


def test_pattern_channel_callback_records_outcome(tmp_path):
    from flask import Flask
    from types import SimpleNamespace
    from services.diagnostics import Reporter
    from callbacks.diagnostics_callbacks import install_diagnostics
    from services.data_store import DataStore
    server = Flask(__name__)
    report = Reporter(tmp_path, {}, background=False)
    def toggle_group_channel():
        return '', 204
    server.add_url_rule('/_dash-update-component', view_func=toggle_group_channel, methods=['POST'])
    app = SimpleNamespace(server=server, callback_map={'channels': {'callback': toggle_group_channel}})
    install_diagnostics(app, DataStore(), report)
    server.test_client().post('/_dash-update-component', json={'output': 'channels', 'inputs': [[
        {'id': {'type': 'group-channel-btn', 'group': 'sample', 'channel': 'uv:250'},
         'property': 'n_clicks', 'value': 1}]], 'state': []})
    events = [json.loads(line) for line in report.log_text().splitlines()]
    assert any(e['properties'].get('operation') == 'toggle_group_channel' and
               e['properties']['outcome'] == 'no_change' for e in events)
