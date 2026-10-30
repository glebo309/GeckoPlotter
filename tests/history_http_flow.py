import sys
sys.path[:0] = ['.', 'src', 'tests']
import app
from components.workspace_layout import walk
from session_helpers import load_files, chromatogram_csv
from services.workspace_history import history_for

client = app.app.server.test_client()
assert client.get('/_dash-layout').status_code == 200
store = app._workspace_registry.for_session(client.get_cookie('gecko_sid').value)
bundle = load_files(store, [('undo-test.csv', chromatogram_csv([2]))])[0]
browser = {}
for node in walk(app._layout_body):
    if isinstance(getattr(node, 'id', None), str):
        for prop in ('data', 'value', 'checked', 'n_clicks'):
            browser[node.id+'.'+prop] = getattr(node, prop, None)
key = 'shared:raw:tab-chromatogram_time'
browser.update({'active-file.data': bundle.bundle_id, 'active-plot-context.data': key,
                'active-plot-tab.data': 'tab-chromatogram_time', 'plot-settings-miss.data': key,
                'loaded-files.data': store.get_loaded_files_list()})

def invoke(name, changed):
    output, cb = next((k, c) for k, c in app.app.callback_map.items()
                     if c.get('callback') and c['callback'].__wrapped__.__name__ == name)
    def deps(items):
        return [{**d, 'value': browser.get(d['id']+'.'+d['property'])} for d in items]
    outputs = cb['output']
    outputs = ([{'id':o.component_id,'property':o.component_property} for o in outputs] if isinstance(outputs,list)
               else {'id':outputs.component_id,'property':outputs.component_property})
    response = client.post('/_dash-update-component', json={'output':output,'outputs':outputs,
        'inputs':deps(cb['inputs']), 'state':deps(cb['state']), 'changedPropIds':[changed]})
    assert response.status_code in (200,204), response.get_data(as_text=True)[:1000]
    result=response.get_json() if response.status_code == 200 else {}
    for section in ('response','sideUpdate'):
        for component, props in result.get(section,{}).items():
            for prop,value in props.items(): browser[component+'.'+prop]=value
    return result

invoke('hydrate_plot_settings','plot-settings-miss.data')
assert not history_for(store).past
browser['pt-show-legend.checked']=False
invoke('user_edit_settings','pt-show-legend.checked')
browser['plot-settings-persist.data']=browser['current-plot-settings.data']
invoke('persist_plot_settings','plot-settings-persist.data')
assert store._shared_plot_settings[key]['show_legend'] is False
assert len(history_for(store).past)==1, [x[0] for x in history_for(store).past]
browser['undo-trigger.data']=1
invoke('handle_workspace_history','undo-trigger.data')
invoke('hydrate_plot_settings','plot-settings-miss.data')
assert browser['pt-show-legend.checked'] is True
browser['plot-settings-persist.data']=browser['current-plot-settings.data']
invoke('persist_plot_settings','plot-settings-persist.data')
assert len(history_for(store).future)==1, 'hydration destroyed redo'
browser['redo-trigger.data']=2
invoke('handle_workspace_history','redo-trigger.data')
invoke('hydrate_plot_settings','plot-settings-miss.data')
assert browser['pt-show-legend.checked'] is False
print('PASS: real app HTTP callbacks toggle legend, undo, restore checkbox, preserve redo through hydration, redo.')
from services import table_store
frame = bundle.primary.dataframe.copy()
source = table_store.remember(frame)
browser['pub-table-source.data'] = source
browser['pub-data-store.data'] = source
browser['pub-table.page_size'] = 50
browser['active-tab.data'] = 'data-overview'
browser['add-column.n_clicks'] = 1
invoke('add_new_column','add-column.n_clicks')
assert 'New_Column_1' in table_store.frame(browser['pub-data-store.data']).columns
browser['undo-trigger.data']=3
invoke('handle_workspace_history','undo-trigger.data')
assert 'New_Column_1' not in table_store.frame(browser['pub-table-source.data']).columns
browser['redo-trigger.data']=4
invoke('handle_workspace_history','redo-trigger.data')
assert 'New_Column_1' in table_store.frame(browser['pub-table-source.data']).columns
print('PASS: table column edit, undo and redo restore the editable table source.')
