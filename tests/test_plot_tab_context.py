from types import SimpleNamespace
from dash import no_update
import callbacks.viz_callbacks as callbacks


class App:
    def __init__(self):self.functions={}
    def callback(self,*args,**kwargs):
        def register(f):self.functions[f.__name__]=f;return f
        return register
    def clientside_callback(self,*args,**kwargs):pass


def setup(monkeypatch):
    groups={'control':('chromatogram','Time (min)'), 'lys':('chromatogram','Time (min)'),
            'blue':('spectrum','Wavelength (nm)')}
    monkeypatch.setattr(callbacks,'_get_active_file_group',lambda dm,fid:groups.get(fid))
    data={key:{'standardized':object(),'record':{'name':key}} for key in groups}
    dm=SimpleNamespace(loaded_data=data,visibility_state={},get_data_by_id=lambda key:data.get(key))
    app=App();callbacks.register_viz_callbacks(app,dm)
    tabs=[{'id':'chrom','type':'raw','group_key':['chromatogram','Time (min)']},
          {'id':'spectra','type':'raw','group_key':['spectrum','Wavelength (nm)']},
          {'id':'publication-1','type':'publication'}]
    return dm,app.functions,tabs


def test_tab_without_memory_selects_existing_member_and_restores_its_zoom(monkeypatch):
    dm,functions,tabs=setup(monkeypatch)
    restore=functions['restore_file_on_tab_switch']
    result=restore('chrom',{},'blue',{'chrom':{'xaxis.range':[5,9]}},tabs)
    assert result==('control',{'xaxis.range':[5,9]})


def test_stale_or_wrong_group_memory_cannot_keep_previous_table(monkeypatch):
    dm,functions,tabs=setup(monkeypatch)
    restore=functions['restore_file_on_tab_switch']
    assert restore('chrom',{'chrom':'deleted'},'blue',{},tabs)[0]=='control'
    assert restore('chrom',{'chrom':'blue'},'blue',{},tabs)[0]=='control'
    assert restore('spectra',{'spectra':'blue'},'control',{},tabs)[0]=='blue'


def test_existing_selection_and_hidden_remembered_member_are_retained(monkeypatch):
    dm,functions,tabs=setup(monkeypatch)
    restore=functions['restore_file_on_tab_switch']
    assert restore('chrom',{},'lys',{},tabs)[0] is no_update
    dm.visibility_state={'lys':False}
    assert restore('chrom',{'chrom':'lys'},'blue',{},tabs)[0]=='lys'
    dm.visibility_state={'control':False}
    assert restore('chrom',{},'blue',{},tabs)[0]=='lys'


def test_publication_tab_does_not_change_data_or_raw_zoom_context(monkeypatch):
    dm,functions,tabs=setup(monkeypatch)
    result=functions['restore_file_on_tab_switch']('publication-1',{'publication-1':'blue'},'control',{},tabs)
    assert result[0] is no_update
    assert result[1] is no_update


def test_tab_selection_refreshes_data_overview_for_that_file(monkeypatch):
    import pandas as pd
    import json
    dm,functions,tabs=setup(monkeypatch)
    dm.get_bundle_by_id=lambda key:None
    monkeypatch.setattr(callbacks,'prepare_table_data',lambda data,file_id=None:
        pd.DataFrame({'Time (min)' if file_id=='control' else 'Wavelength (nm)':[1,2]}))
    monkeypatch.setattr(callbacks,'create_data_table_editor',lambda data,**kwargs:list(data.columns))
    monkeypatch.setattr(callbacks,'create_data_table',lambda data:'metadata')
    file_id,_=functions['restore_file_on_tab_switch']('chrom',{},'blue',{},tabs)
    table,data,metadata=functions['sync_table_to_active_file'](file_id,'data-overview')
    assert table==['Time (min)']
    assert json.loads(data)['columns']==['Time (min)']


def test_cleared_selection_cannot_leave_previous_data_table_visible(monkeypatch):
    dm,functions,tabs=setup(monkeypatch)
    table,data,metadata=functions['sync_table_to_active_file'](None,'data-overview')
    assert table is not no_update
    assert data is None
    assert metadata is not no_update
