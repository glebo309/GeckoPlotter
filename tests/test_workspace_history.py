import copy

from services.data_store import DataStore
from session_helpers import load_files, chromatogram_csv
from test_peak_owner_aliases import add


def workspace():
    from services.workspace_history import WorkspaceHistory
    store = DataStore()
    bundle = load_files(store, [('trace.csv', chromatogram_csv([2]))])[0]
    return store, bundle, WorkspaceHistory(store)


def test_legend_visibility_and_peak_edits_share_one_chronological_history():
    store, bundle, history = workspace()
    store._shared_plot_settings['shared:raw'] = {'show_legend': True}
    with history.edit('Figure settings'):
        store._shared_plot_settings['shared:raw']['show_legend'] = False
    with history.edit('Integrate peak'):
        peak = add(store.peak_service, bundle.bundle_id)
    with history.edit('Signal visibility'):
        store.visibility_state[bundle.bundle_id] = False
    assert history.undo() == 'Signal visibility'
    assert store.visibility_state.get(bundle.bundle_id, True)
    assert len(store.peak_service.get_peaks(bundle.bundle_id)) == 1
    assert history.undo() == 'Integrate peak'
    assert not store.peak_service.get_peaks(bundle.bundle_id)
    assert store._shared_plot_settings['shared:raw']['show_legend'] is False
    assert history.undo() == 'Figure settings'
    assert store._shared_plot_settings['shared:raw']['show_legend'] is True
    assert history.redo() == 'Figure settings'
    assert history.redo() == 'Integrate peak'
    assert store.peak_service.get_peaks(bundle.bundle_id)[0].peak_id == peak.peak_id
    assert history.redo() == 'Signal visibility'
    assert not store.visibility_state[bundle.bundle_id]


def test_history_restores_removed_files_and_names_without_copying_raw_arrays():
    store, bundle, history = workspace()
    frame = bundle.primary.dataframe
    raw = bundle.primary.raw_bytes
    with history.edit('Rename sample'):
        bundle.name = 'Renamed'
    with history.edit('Remove sample'):
        store.file_removal_service.remove(bundle.bundle_id)
    history.undo()
    assert store.get_bundle(bundle.bundle_id).name == 'Renamed'
    history.undo()
    restored = store.get_bundle(bundle.bundle_id)
    assert restored.name != 'Renamed'
    assert restored.primary.dataframe is frame
    assert restored.primary.raw_bytes is raw


def test_noop_is_not_an_edit_and_new_edit_clears_redo():
    store, bundle, history = workspace()
    with history.edit('No change'):
        pass
    assert history.undo() is None
    with history.edit('First'):
        store._shared_plot_settings['shared:raw'] = {'show_legend': False}
    history.undo()
    with history.edit('Second'):
        store._shared_plot_settings['shared:raw'] = {'line_width': 3}
    assert history.redo() is None
    assert history.undo() == 'Second'


def test_client_settings_and_calibration_state_restore_without_mutating_history():
    store, bundle, history = workspace()
    history.client = {'file-order': {'tab': ['a', 'b']}, 'area-display-unit': 'mAU·min'}
    before_cal = copy.deepcopy(store.calibration_service.serialize())
    with history.edit('Display settings'):
        history.client['file-order']['tab'].reverse()
        history.client['area-display-unit'] = 'µAU·s'
    history.undo()
    assert history.client['file-order']['tab'] == ['a', 'b']
    assert history.client['area-display-unit'] == 'mAU·min'
    history.redo()
    assert history.client['file-order']['tab'] == ['b', 'a']
    assert store.calibration_service.serialize() == before_cal


def test_http_edits_and_keyboard_undo_restore_settings_and_controls():
    import dash
    from dash import Input, Output, dcc, html
    from callbacks.history_callbacks import register_history_callbacks, register_history_capture
    store, bundle, _ = workspace()
    key = 'shared:raw:tab-chromatogram_time'
    store._shared_plot_settings[key] = {'show_legend': True, '_context_key': key}
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    app.layout = html.Div([dcc.Store(id='test-legend'), html.Div(id='dummy-output')])
    @app.callback(Output('dummy-output', 'children'), Input('test-legend', 'data'))
    def change_legend(value):
        store._shared_plot_settings[key]['show_legend'] = value
        return ''
    register_history_callbacks(app, store)
    register_history_capture(app, store)
    client = app.server.test_client()

    def invoke(name, values):
        output, cb = next((k, c) for k, c in app.callback_map.items()
                          if c.get('callback') and c['callback'].__wrapped__.__name__ == name)
        specs = lambda ds: [{**d, 'value': values.get(d['id'])} for d in ds]
        outputs = cb['output']
        outputs = ([{'id': o.component_id, 'property': o.component_property} for o in outputs]
                   if isinstance(outputs, list) else {'id': outputs.component_id, 'property': outputs.component_property})
        response = client.post('/_dash-update-component', json={
            'output': output, 'outputs': outputs, 'inputs': specs(cb['inputs']),
            'state': specs(cb['state']), 'changedPropIds': [cb['inputs'][0]['id']+'.'+cb['inputs'][0]['property']]})
        assert response.status_code == 200, response.get_data(as_text=True)
        return response.get_json()

    invoke('change_legend', {'test-legend': False})
    assert store._shared_plot_settings[key]['show_legend'] is False
    result = invoke('handle_workspace_history', {'undo-trigger': 1, 'active-file': bundle.bundle_id,
        'active-plot-context': key, 'active-plot-tab': 'tab-chromatogram_time',
        'plot-settings-cache': {key: {'show_legend': False}}, 'loaded-files': store.get_loaded_files_list()})
    assert store._shared_plot_settings[key]['show_legend'] is True
    assert result['sideUpdate']['current-plot-settings']['data']['show_legend'] is True
    assert result['sideUpdate']['plot-settings-cache']['data'][key]['show_legend'] is True
    assert result['sideUpdate']['session-dirty']['data'] is True


def test_application_has_one_workspace_undo_handler():
    import json
    import subprocess
    import sys
    code = '''
import json, app
callbacks = [c['callback'].__wrapped__.__name__ for c in app.app.callback_map.values()
             if c.get('callback') and any(d['id'] == 'undo-trigger' for d in c['inputs'])]
print(json.dumps(callbacks))
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout.splitlines()[-1]) == ['handle_workspace_history']


def test_first_legend_edit_can_be_undone_to_hydrated_default():
    from callbacks.plot_settings_callbacks import register_plot_settings_callbacks
    from services.workspace_history import history_for
    from test_lcms_peak_table import App
    store, bundle, _ = workspace()
    app = App()
    register_plot_settings_callbacks(app, store)
    key = 'shared:raw:tab-chromatogram_time'
    settings = app.functions['hydrate_plot_settings'](key, bundle.bundle_id)[0]
    assert store._shared_plot_settings[key] == settings
    history = history_for(store)
    with history.edit('Figure settings'):
        app.functions['persist_plot_settings']({**settings, 'show_legend': False}, key)
    history.undo()
    assert store._shared_plot_settings[key]['show_legend'] is True


def test_edited_tables_survive_cache_eviction_and_undo_redo():
    import pandas as pd
    from services import table_store
    store, bundle, history = workspace()
    original = pd.DataFrame({'_row_id': [0], 'Signal': [10.]})
    changed = pd.DataFrame({'_row_id': [0], 'Signal': [25.]})
    history.tables = {'pub-table-source': original}
    with history.edit('Edit table'):
        history.tables['pub-table-source'] = changed
    for _ in range(table_store.MAX_TABLES + 1):
        table_store.remember(pd.DataFrame({'x': [1]}))
    history.undo()
    assert history.tables['pub-table-source']['Signal'][0] == 10
    history.redo()
    assert history.tables['pub-table-source']['Signal'][0] == 25


def test_real_app_legend_and_table_edit_undo_redo_through_http():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, 'tests/history_http_flow.py'], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
