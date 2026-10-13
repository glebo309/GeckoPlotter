from types import SimpleNamespace
from unittest.mock import Mock
from flask import Flask, Response
from callbacks import research_export_callbacks as callbacks


def capture_app(monkeypatch, name='delete_peak', module='callbacks.context_menu_callbacks'):
    server = Flask(__name__)
    fn = lambda: None
    fn.__name__, fn.__module__ = name, module
    app = SimpleNamespace(server=server, callback_map={'target': {'callback': fn}})
    store = SimpleNamespace(all_bundles=lambda: [1])
    record = Mock()
    monkeypatch.setattr(callbacks, 'record_analysis_state', record)
    callbacks.register_provenance_capture(app, store)
    return server, record, server.after_request_funcs[None][0]


def test_plot_render_does_not_reparse_response_or_rescan_scientific_state(monkeypatch):
    server, record, capture = capture_app(monkeypatch, 'master_render', 'callbacks.viz_callbacks')
    response = Response('{}', mimetype='application/json')
    response.get_json = Mock(side_effect=AssertionError('Large figure must not be reparsed'))
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output':'target', 'outputs': {'id':'main-plot','property':'figure'},
            'changedPropIds':['render-trigger.data']}):
        assert capture(response) is response
    response.get_json.assert_not_called()
    record.assert_not_called()


def test_mutation_captures_state_without_parsing_unrelated_response(monkeypatch):
    server, record, capture = capture_app(monkeypatch)
    response = Response('{}', mimetype='application/json')
    response.get_json = Mock(side_effect=AssertionError('No settings output'))
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output':'target', 'outputs': [{'id':'render-trigger','property':'data'}],
            'changedPropIds':['delete-peak.n_clicks']}):
        capture(response)
    response.get_json.assert_not_called()
    assert record.call_count == 1
    assert record.call_args.args[1:] == (None, ['delete-peak.n_clicks'])


def test_settings_response_is_captured_with_scientific_parameters(monkeypatch):
    server, record, capture = capture_app(monkeypatch, 'user_edit_settings')
    response = Response('{"response":{"current-plot-settings":{"data":{"smooth_window":21}}}}', mimetype='application/json')
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output':'target', 'outputs': {'id':'current-plot-settings','property':'data'},
            'changedPropIds':['pt-smooth-window.value']}):
        capture(response)
    assert record.call_args.args[1] == {'smooth_window':21}


def test_pattern_outputs_do_not_skip_provenance_capture(monkeypatch):
    server, record, capture = capture_app(monkeypatch, 'edit_peak')
    response = Response('{}', mimetype='application/json')
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output': 'target', 'outputs': [[{'id': {'type': 'signal-style', 'index': 'a'}, 'property': 'value'}],
                                           {'id': 'render-trigger', 'property': 'data'}],
            'changedPropIds': ['edit-peak.data']}):
        capture(response)
    assert record.call_count == 1


import ast
from pathlib import Path
import pytest

SKIPPED = [('toggle_group_sort', 'callbacks.file_tree_callbacks'), ('handle_drag_reorder', 'callbacks.file_tree_callbacks'),
           ('handle_visibility_toggles', 'callbacks.file_tree_callbacks'),
           ('check_last_session', 'callbacks.session_callbacks'), ('autosave_project', 'callbacks.session_callbacks'),
           ('show_peak_table_empty_state', 'callbacks.tab_callbacks'),
           ('persist_plot_settings', 'callbacks.plot_settings_callbacks'),
           ('sync_polarity_toggle', 'callbacks.lcms_callbacks')]


@pytest.mark.parametrize('name,module', SKIPPED)
def test_display_only_callbacks_do_not_rescan_scientific_state(monkeypatch, name, module):
    server, record, capture = capture_app(monkeypatch, name, module)
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output': 'target', 'outputs': {'id': 'x', 'property': 'y'}, 'changedPropIds': ['x.y']}):
        capture(Response('{}', mimetype='application/json'))
    record.assert_not_called()


@pytest.mark.parametrize('name,module', [('delete_peak_table_rows', 'callbacks.tab_callbacks'),
                                         ('update_peak_analysis_tab', 'callbacks.tab_callbacks'),
                                         ('hydrate_plot_settings', 'callbacks.plot_settings_callbacks'),
                                         ('open_project', 'callbacks.session_callbacks'),
                                         ('rename_dataset', 'callbacks.file_tree_callbacks')])
def test_state_changing_callbacks_are_still_recorded(monkeypatch, name, module):
    server, record, capture = capture_app(monkeypatch, name, module)
    with server.test_request_context('/_dash-update-component', method='POST', json={
            'output': 'target', 'outputs': {'id': 'x', 'property': 'y'}, 'changedPropIds': ['x.y']}):
        capture(Response('{}', mimetype='application/json'))
    assert record.call_count == 1


def test_every_allowlisted_name_exists_in_its_module():
    root = Path(callbacks.__file__).parent
    for module, names in callbacks._READ_ONLY_CALLBACKS.items():
        tree = ast.parse((root / (module.split('.')[-1] + '.py')).read_text())
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert names <= defined, (module, names - defined)
