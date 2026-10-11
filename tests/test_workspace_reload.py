"""A page reload is a new empty workspace, including server-side state."""
import subprocess
import sys


def test_reload_clears_server_data_and_followup_upload_stays_fresh():
    script = r'''
import base64
import json
import app as module
from services.data_store import Bundle, BundleType, Component, ComponentRole
from components.workspace_layout import walk

client = module.app.server.test_client()
dm = module.data_manager
client.get('/_dash-layout')
original_peak_service = dm.peak_service
original_cal_service = dm.calibration_service
component = Component('old-signal', ComponentRole.PRIMARY, 'old.csv')
dm.add_bundle(Bundle('old', 'Old', BundleType.GENERIC, component_list=[component]))
dm.file_ui_state['old'] = {'plot_settings': {'title': 'Old title'}}
dm.peak_service.save_undo()
dm.calibration_service._models['old'] = object()
dm.integration_service.update_settings('old', smooth_window=9)
dm.lcms_service._eic_cache['old'] = object()
dm._shared_plot_settings['old'] = {'title': 'Old title'}
dm.file_removal_service.remove('old')
# A remaining file must also be forgotten by reload.
dm.add_bundle(Bundle('remaining', 'Remaining', BundleType.GENERIC,
                     component_list=[Component('remaining-signal', ComponentRole.PRIMARY, 'remaining.csv')]))
response = client.get('/_dash-layout')
assert response.status_code == 200
assert dm.get_loaded_files_list() == [], 'Reload retained server-side files'
assert dm.file_removal_service.can_undo is False
assert dm.file_ui_state == {}
assert dm._shared_plot_settings == {}
assert dm.peak_service is original_peak_service, 'Registered callbacks still hold this object'
assert dm.calibration_service is original_cal_service
assert not dm.peak_service.can_undo
assert dm.calibration_service.get_all_models() == {}
assert dm.integration_service.serialize() == {}
assert dm.lcms_service._eic_cache == {}
layout = response.get_json()
def find(node, target):
    if isinstance(node, dict):
        if node.get('props', {}).get('id') == target: return node['props']
        for value in node.values():
            found = find(value, target)
            if found is not None: return found
    elif isinstance(node, list):
        for value in node:
            found = find(value, target)
            if found is not None: return found
assert find(layout, 'loaded-files')['data'] == []
assert find(layout, 'plot-tabs')['data'] == []
assert find(layout, 'custom-plot-figures')['data'] == {}
callback = next(v for v in module.app.callback_map.values()
    if v.get('callback') and v['callback'].__name__ == 'handle_file_upload')
contents = 'data:text/csv;base64,' + base64.b64encode(b'Time,Signal\n0,1\n1,2\n2,1\n').decode()
result = callback['callback'].__wrapped__([contents], ['new.csv'], [0], [], 0)
assert len(dm.get_loaded_files_list()) == 1
assert dm.get_loaded_files_list()[0]['name'] != 'Remaining'
# A callback or dependencies request must not reset the active workspace.
client.get('/_dash-dependencies')
assert len(dm.get_loaded_files_list()) == 1
client.get('/_dash-layout')
assert dm.get_loaded_files_list() == []
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_new_store_does_not_restore_or_write_hidden_state(tmp_path, monkeypatch):
    from services.data_store import DataStore
    state = tmp_path / 'file_state.json'
    state.write_text('{"integration_settings":{"old":{"smooth_window":51}}}')
    monkeypatch.setenv('GECKO_ENABLE_SESSION_PERSISTENCE', '1')
    monkeypatch.setattr(DataStore, '_STATE_FILE', str(state))
    store = DataStore()
    assert store.integration_service.serialize() == {}
    before = state.read_text()
    store.persist_services()
    assert state.read_text() == before


def test_stores_do_not_share_plot_settings():
    from services.data_store import DataStore
    first, second = DataStore(), DataStore()
    first._shared_plot_settings['old'] = {'title': 'Old'}
    assert second._shared_plot_settings == {}
