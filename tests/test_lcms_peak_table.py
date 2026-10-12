from types import SimpleNamespace
from test_peak_owner_aliases import setup,add
from src.services.data_store import BundleType
from callbacks.tab_callbacks import register_tab_callbacks

class App:
    def __init__(self):self.functions={};self.registrations={}
    def callback(self,*args,**kwargs):
        def register(f):self.functions[f.__name__]=f;self.registrations[f.__name__]=args;return f
        return register
    def clientside_callback(self,*args,**kwargs):pass


def fixture():
    dm=setup(BundleType.LCMS);app=App();register_tab_callbacks(app,dm)
    return dm,app,app.functions['update_peak_analysis_tab']


def test_lcms_channel_selection_shows_all_bundle_peaks_with_separate_signal_identity():
    dm,app,table=fixture();tic=add(dm.peak_service,'component');uv=add(dm.peak_service,'other')
    for fid,p in [('component',tic),('other',uv)]:
        data,columns,style,store=table(fid,1,0,0,'peak-analysis',[])
        assert {row['peak_id'] for row in data}=={tic.peak_id,uv.peak_id}
        assert len({row['Signal'] for row in data})==2
        assert all(row['Relative Area (%)']==100 for row in data)
        assert style.get('display')!='none'
        assert store


def test_selecting_lcms_bundle_shows_channel_labeled_peaks_without_merging_owners():
    dm,app,table=fixture();tic=add(dm.peak_service,'component');uv=add(dm.peak_service,'other')
    data,columns,style,store=table('bundle',1,0,0,'peak-analysis',[])
    assert {row['peak_id'] for row in data}=={tic.peak_id,uv.peak_id}
    assert all(row['Signal'] for row in data)
    assert len(dm.peak_service.get_peaks('component'))==1
    assert len(dm.peak_service.get_peaks('other'))==1


def test_opening_peaks_panel_refreshes_its_table():
    dm,app,table=fixture()
    dependencies=app.registrations['update_peak_analysis_tab'][1]
    assert any(dep.component_id=='active-tab' and dep.component_property=='data' for dep in dependencies)


def test_bundle_table_name_edits_reach_the_correct_lcms_channel():
    dm,app,table=fixture();tic=add(dm.peak_service,'component');uv=add(dm.peak_service,'other')
    result=app.functions['persist_peak_names']([{'peak_id':uv.peak_id,'Peak Name':'UV peak'}],'bundle')
    assert dm.peak_service.get_peaks('other')[0].name=='UV peak'
    assert dm.peak_service.get_peaks('component')[0].name==tic.name


def test_peak_cell_selection_uses_visible_sorted_row_and_its_channel():
    dm,app,table=fixture();tic=add(dm.peak_service,'component');uv=add(dm.peak_service,'other')
    select=app.functions['select_peak_table_row']
    rows=[{'peak_id':tic.peak_id},{'peak_id':uv.peak_id}]
    selected,owner,render=select({'row':0},rows[::-1],rows,'component',4,'raw')
    assert selected==uv.peak_id and owner=='other' and render==5


def test_no_peak_rows_show_actionable_empty_state():
    dm,app,table=fixture()
    empty=app.functions['show_peak_table_empty_state']
    assert empty([]).get('display')!='none'
    assert empty([{'peak_id':'one'}])=={'display':'none'}


def test_peaks_display_precision_does_not_round_underlying_measurements():
    dm,app,table=fixture();peak=add(dm.peak_service,'component')
    peak.area=12.34567890123;peak.height=.0000123456789;peak.rt=1.123456789
    data,columns,style,store=table('component',1,0,0,'peak-analysis',[])
    row=data[0]
    assert row['Area']==peak.area and row['Height']==peak.height and row['RT (min)']==peak.rt
    numeric={col['id']:col for col in columns}
    assert numeric['Area']['type']=='numeric' and numeric['Area']['format']['specifier']=='.5~g'
    assert numeric['RT (min)']['format']['specifier']=='.4~f'
    assert [c['id'] for c in columns].index('Concentration') < [c['id'] for c in columns].index('Area')
    assert style['overflowX']=='auto' and style['maxWidth']=='100%'


def test_table_delete_removes_service_peak_and_refresh_cannot_restore_it():
    import dash
    dm,app,table=fixture();tic=add(dm.peak_service,'component');uv=add(dm.peak_service,'other')
    rows=table('component',1,0,0,'peak-analysis',0,[])[0]
    remaining=[row for row in rows if row['peak_id'] != uv.peak_id]
    out=app.functions['delete_peak_table_rows'](123,remaining,rows,'component',uv.peak_id,5)
    assert out[0]==6 and out[1] is None
    assert dm.peak_service.get_peaks('other')==[]
    assert {row['peak_id'] for row in table('component',6,0,0,'peak-analysis',0,[])[0]}=={tic.peak_id}
    app.functions['delete_peak_table_rows'](124,[],remaining,'component',None,6)
    assert table('component',7,0,0,'peak-analysis',0,[])[0]==[]
    assert all(not peaks for peaks in dm.peak_service.get_all_peaks().values())


def test_table_navigation_or_renaming_is_not_a_peak_deletion():
    import pytest
    from dash.exceptions import PreventUpdate
    dm,app,table=fixture();peak=add(dm.peak_service,'component')
    delete=app.functions['delete_peak_table_rows']
    before=[{'peak_id':peak.peak_id,'Peak Name':'Original'}]
    for rows in ([{'peak_id':peak.peak_id,'Peak Name':'Renamed'}], [{'peak_id':'another-file'}]):
        with pytest.raises(PreventUpdate):delete(1,rows,before,'component',None,0)
    assert dm.peak_service.get_peaks('component')==[peak]


def test_deleted_instrument_peaks_are_not_reimported_on_table_refresh(monkeypatch):
    dm=setup();app=App();register_tab_callbacks(app,dm)
    peak=add(dm.peak_service,'bundle')
    dm.peak_service.remove_peak('bundle',peak.peak_id)
    bundle=dm.get_bundle('bundle');reads=[]
    monkeypatch.setattr(bundle,'has_integration_data',lambda:True)
    monkeypatch.setattr(bundle,'get_integration_text',lambda:reads.append(True) or '')
    assert app.functions['update_peak_analysis_tab']('bundle',1,0,0,'peak-analysis',0,[])[0]==[]
    assert reads==[]


def test_compare_finds_peaks_stored_under_a_channel_id():
    """Peaks integrated on a detector channel are owned by the channel, not the sample id."""
    from callbacks.tab_callbacks import _bundle_peaks
    dm = setup(BundleType.LCMS)
    bundle = next(dm.iter_bundles())
    channel = bundle.component_list[0].component_id
    dm.peak_service.add_baseline_peak(file_id=channel, area=4, height=9, apex_x=.92, poly_x=[.5, 1, 1, .5],
        poly_y=[0, 9, 0, 0], p_line=[(.5, 0), (1, 0)], q1=(.5, 0), q2=(1, 0))
    found = _bundle_peaks(dm, bundle, bundle.bundle_id)
    assert len(found) == 1 and found[0].file_id == channel


def test_compare_collects_each_sample_once_when_data_is_keyed_by_channel():
    from callbacks.tab_callbacks import _collect_bundles_with_peaks
    dm = setup(BundleType.LCMS)
    bundle = next(dm.iter_bundles())
    for component in bundle.component_list:
        dm.peak_service.add_baseline_peak(file_id=component.component_id, area=4, height=9, apex_x=.92,
            poly_x=[.5, 1, 1, .5], poly_y=[0, 9, 0, 0], p_line=[(.5, 0), (1, 0)], q1=(.5, 0), q2=(1, 0))
    found = _collect_bundles_with_peaks(dm, dm.get_loaded_files_list())
    assert [item['bundle'].bundle_id for item in found] == [bundle.bundle_id]
