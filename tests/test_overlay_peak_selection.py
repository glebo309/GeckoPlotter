from copy import deepcopy
from types import SimpleNamespace
import dash
from dash.exceptions import PreventUpdate
import pytest
from test_ms_polarity import polarity_pipeline
from test_render_tab_performance import App
from callbacks import baseline_callbacks as baseline
from callbacks import viz_callbacks as viz


def pipeline(monkeypatch):
    store,app,hydrate,_,_=polarity_pipeline(monkeypatch)
    ids={}
    for fid,height in [('first-positive',2),('first-negative',3),('first-uv',4)]:
        peak=store.peak_service.add_baseline_peak(file_id=fid,area=height,height=height,apex_x=1,
            poly_x=[0,1,2,2,1,0],poly_y=[1,height+1,1,1,1,1],p_line=[(0,1),(2,1)],q1=(0,1),q2=(2,1))
        ids[fid]=peak.peak_id
    settings=hydrate('first-positive')
    loaded=store.get_loaded_files_list();tabs,_=app.functions['sync_plot_tabs'](loaded,[],None,'first-positive')
    tab=next(t for t in tabs if tuple(t['group_key'])==viz._get_active_file_group(store,'first-positive'))
    def render(mode='overlay',selected=None,active='first-positive'):
        monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'render-trigger.data'}]))
        return app.functions['master_render'](tab['id'],None,active,{**settings,'layout_mode':mode},1,{},[],[],[],1,True,'independent',loaded,tabs,None,selected,None,{}, {},None,[],None,['peaks'],[])[0]
    return store,ids,render


def test_overlay_keeps_all_visible_integrations_and_only_selected_owner_handles(monkeypatch):
    store,ids,render=pipeline(monkeypatch)
    fig=render(selected=ids['first-negative'])
    fills=[trace for trace in fig.data if trace.meta=='peak_overlay' and trace.fill=='toself']
    assert {trace.customdata[0] for trace in fills}==set(ids.values())
    assert [shape.name for shape in fig.layout.shapes]==['baseline:'+ids['first-negative']]
    metadata=fig.layout.meta['gecko_peak_geometry']
    for trace in fills:
        source=next(t for t in fig.data if isinstance(t.meta,dict) and t.meta.get('file_id')==metadata[trace.customdata[0]]['file_id'])
        assert (trace.xaxis,trace.yaxis)==(source.xaxis or 'x',source.yaxis or 'y')


def test_separate_uses_real_x_column_instead_of_generic_axis_identity(monkeypatch):
    _,_,render=pipeline(monkeypatch)
    figure=render('stacked')
    assert figure.layout.xaxis3.title.text=='time'
    assert {value['label'] for key,value in figure.layout.meta['gecko_axis_identities'].items() if key.startswith('xaxis')}=={'time'}


def test_overlay_select_and_deselect_request_all_source_render_not_single_source_patch(monkeypatch):
    store,ids,render=pipeline(monkeypatch);fig=render().to_plotly_json()
    app=App();baseline.register_baseline_callbacks(app,store)
    select=app.functions['select_peak_from_browser_hit_test']({'peakId':ids['first-negative']},'first-positive',fig,{'layout_mode':'overlay'},7,'raw')
    assert select[0]==ids['first-negative'] and select[2] is dash.no_update
    assert [shape.name for shape in select[1].layout.shapes] == ['baseline:'+ids['first-negative']]
    deselect=app.functions['deselect_peak_from_empty_plot_click'](1,'first-positive',fig,ids['first-negative'],'navigate',{'layout_mode':'overlay'},8,'raw')
    assert deselect[0] is None and deselect[1] is dash.no_update and deselect[2]==9


def test_selected_peak_owner_follows_visible_peak_and_ignores_old_tab(monkeypatch):
    store,ids,render=pipeline(monkeypatch);fig=render().to_plotly_json()
    app=App();baseline.register_baseline_callbacks(app,store)
    follow=lambda peak_id, figure, active_file, active_tab: app.functions['select_peak_from_browser_hit_test']({'peakId':peak_id},active_file,figure,{'layout_mode':'overlay'},0,'raw',active_tab)[3]
    tab_id=fig['layout']['meta']['gecko_tab_id']
    assert follow(ids['first-negative'],fig,'first-positive',tab_id)=='first-negative'
    with pytest.raises(PreventUpdate):follow(ids['first-negative'],fig,'first-positive','different-tab')


def test_baseline_edit_uses_peak_identity_when_two_overlay_sources_share_an_axis(monkeypatch):
    store,ids,render=pipeline(monkeypatch);fig=render(selected=ids['first-negative']).to_plotly_json()
    app=App();baseline.register_baseline_callbacks(app,store)
    before=deepcopy(store.peak_service.get_peaks('first-positive')[0].p_line)
    monkeypatch.setattr(baseline,'callback_context',SimpleNamespace(triggered=[{'prop_id':'main-plot.relayoutData'}]))
    app.functions['handle_relayout']({'shapes[0].y0':0.2},None,'navigate',False,'first-positive',fig,0,ids['first-negative'],0,
                                    {'layout_mode':'overlay'},store.get_loaded_files_list(),[],fig['layout']['meta']['gecko_tab_id'],0)
    assert store.peak_service.get_peaks('first-negative')[0].p_line[0][1]==0.2
    assert store.peak_service.get_peaks('first-positive')[0].p_line==before


def test_single_click_selects_peak_and_owner_together_in_separate_view(monkeypatch):
    store,ids,render=pipeline(monkeypatch)
    fig=render('stacked',selected=ids['first-positive']).to_plotly_json()
    app=App();baseline.register_baseline_callbacks(app,store)
    selection=app.functions['select_peak_from_browser_hit_test'](
        {'peakId':ids['first-negative']},'first-positive',fig,{'layout_mode':'stacked'},7,'raw')
    assert selection[0] == ids['first-negative']
    assert len(selection) == 4
    assert selection[3] == 'first-negative'


def test_separate_selection_returns_visible_handles_and_preserves_other_peaks(monkeypatch):
    store,ids,render=pipeline(monkeypatch)
    fig=render('stacked',selected=ids['first-positive']).to_plotly_json()
    app=App();baseline.register_baseline_callbacks(app,store)
    result=app.functions['select_peak_from_browser_hit_test'](
        {'peakId':ids['first-negative']},'first-positive',fig,{'layout_mode':'stacked'},7,'raw')
    selected=result[1]
    assert selected is not dash.no_update
    assert [shape.name for shape in selected.layout.shapes] == ['baseline:'+ids['first-negative']]
    fills=[t for t in selected.data if t.meta=='peak_overlay' and t.fill=='toself']
    assert {t.customdata[0] for t in fills} == set(ids.values())
    source=next(t for t in selected.data if isinstance(t.meta,dict) and t.meta.get('file_id')=='first-negative')
    assert selected.layout.shapes[0].yref == source.yaxis
