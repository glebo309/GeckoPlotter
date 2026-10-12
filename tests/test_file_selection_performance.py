"""A tree selection selects the source; one callback prepares its table."""
import json
from types import SimpleNamespace
import dash
import pandas as pd
import callbacks.viz_callbacks as callbacks
from test_render_tab_performance import App


def fixture(monkeypatch, data=None, source='target'):
    data = data if data is not None else pd.DataFrame({'Time':[0.,1.,2.], 'Signal':[1.,2.,3.]})
    entries={'target':{'data':data, 'metadata':{'auto_x':'Time','auto_y':['Signal']}}}
    memories={}
    dm=SimpleNamespace(loaded_data=entries, lcms_bundles={}, visibility_state={},
        get_data_by_id=lambda fid:entries.get(fid), get_bundle_by_id=lambda fid:None,
        get_publication_memory=lambda fid:memories.get(fid),
        initialise_publication_memory=lambda fid,value:memories.setdefault(fid,value))
    app=App();callbacks.register_viz_callbacks(app,dm)
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{
        'prop_id':json.dumps({'type':'file-tree-item','index':source})+'.n_clicks','value':1}]))
    monkeypatch.setattr(callbacks,'create_data_table',lambda entry:'metadata')
    return app.functions, dm, memories


def test_tree_click_defers_large_table_output_to_single_active_file_owner(monkeypatch):
    functions,dm,memories=fixture(monkeypatch)
    calls=[]
    monkeypatch.setattr(callbacks,'create_data_table_editor',lambda data,**kwargs:calls.append(list(data.columns)) or 'editor')
    result=functions['handle_file_selection']([1],[],'old','data-overview',{},None)
    assert result[1]=='target'
    assert result[2] is None
    assert calls==[]
    assert all(result[index] is dash.no_update for index in (0,3,4,5))
    table,data,metadata=functions['sync_table_to_active_file']('target','data-overview')
    assert calls==[['_row_id','Time','Signal']]
    assert table=='editor' and metadata=='metadata'
    assert json.loads(data)['columns']==['_row_id','Time','Signal']
    assert memories['target']['x']['data']['column_id']=='Time'


def test_single_table_owner_keeps_multiwell_visibility_and_selected_well(monkeypatch):
    from src.ingestion.types import PlotHint
    data=pd.DataFrame({'Time':[0.,1.], 'A':[2.,3.], 'B':[4.,5.]})
    functions,dm,memories=fixture(monkeypatch,data)
    dm.loaded_data['target']['standardized']=SimpleNamespace(plot_hint=PlotHint.MULTI_Y,x_columns=['Time'],y_columns=['A','B'])
    dm.visibility_state={'target|B':False}
    for fid,expected in [('target',['_row_id','Time','A']),('target|B',['_row_id','Time','B'])]:
        table,data,_=functions['sync_table_to_active_file'](fid,'data-overview')
        assert json.loads(data)['columns']==expected

    assert memories['target|B']['y1']['series'][0]['column_id'] == 'B'


def test_stale_sample_row_selects_current_visible_channel(monkeypatch):
    from test_chromatogram_bundle import multichannel
    from services.bundling_service import assign_bundles
    from services.data_store import DataStore
    store = DataStore()
    bundle, = assign_bundles([('run.txt', b'raw', multichannel())])
    store.add_bundle(bundle)
    primary, secondary = bundle.component_list
    store.visibility_state[primary.component_id] = False
    store.visibility_state[secondary.component_id] = True
    app = App()
    callbacks.register_viz_callbacks(app, store)
    monkeypatch.setattr(dash, 'callback_context', SimpleNamespace(triggered=[{
        'prop_id': json.dumps({'type': 'file-tree-item', 'index': primary.component_id}) + '.n_clicks', 'value': 1}]))
    result = app.functions['handle_file_selection']([1], [], None, 'data-overview', {}, None)
    assert result[1] == secondary.component_id
