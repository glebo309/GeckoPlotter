from types import SimpleNamespace
import dash
import plotly.graph_objects as go
import callbacks.viz_callbacks as callbacks
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
from services.render_cache import RenderCache


class App:
    def __init__(self):self.functions={};self.registrations={}
    def callback(self,*args,**kwargs):
        def register(f):self.functions[f.__name__]=f;self.registrations[f.__name__]=args;return f
        return register
    def clientside_callback(self,*args,**kwargs):pass


def render_fixture(monkeypatch):
    app=App();cache=RenderCache()
    monkeypatch.setattr('services.render_cache.RenderCache',lambda:cache)
    data={'source':{'standardized':object()}}
    dm=SimpleNamespace(loaded_data=data,visibility_state={})
    monkeypatch.setattr(callbacks,'_get_active_file_group',lambda dm,fid:('spectrum','Wavelength (nm)') if fid=='other' else ('chromatogram','Time (min)'))
    callbacks.register_viz_callbacks(app,dm)
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:chrom','axis_label_modes':{'x':'auto','y':'auto'}}
    tab={'id':'chrom','type':'raw','group_key':['chromatogram','Time (min)']}
    args=['chrom',None,'source',settings,0,{},[],[],[],0,True,'independent',[],[tab],None,None,None,{}, {},None,[],None,['peaks'],[]]
    normalized=callbacks._raw_render_settings(settings)
    inputs={'settings':normalized,'render':0,'peaks':0,'order':{},'selected':None,'file':'source',
            'baseline':None,'markers':[],'deconvolution':None,'display':['peaks'],'visibility':{},'files':[],
            'link_x':True,'y_scope':'independent'}
    cache.put('chrom',inputs,go.Figure(go.Scatter(x=[1,2],y=[3,4])))
    return app,cache,args


def test_cached_echo_does_not_copy_or_return_figure(monkeypatch):
    app,cache,args=render_fixture(monkeypatch)
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'current-plot-settings.data'}]))
    monkeypatch.setattr(cache,'get',lambda *args: (_ for _ in ()).throw(AssertionError('Unneeded figure copy')))
    assert app.functions['master_render'](*args)[0] is dash.no_update


def test_cached_tab_uses_browser_cache_but_cold_client_gets_figure(monkeypatch):
    app,cache,args=render_fixture(monkeypatch)
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'active-plot-tab.data'}]))
    args[-1]=['chrom']
    assert app.functions['master_render'](*args)[0] is dash.no_update
    args[-1]=[]
    assert isinstance(app.functions['master_render'](*args)[0],go.Figure)


def test_wrong_group_selection_waits_for_tab_file_restore(monkeypatch):
    app,cache,args=render_fixture(monkeypatch)
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'current-plot-settings.data'}]))
    args[2]='other'
    assert app.functions['master_render'](*args)[0] is dash.no_update


def test_auto_label_hydration_and_export_dpi_do_not_invalidate_raw_figure():
    initial={**DEFAULT_PLOT_SETTINGS,'axis_label_modes':{'x':'auto','y':'auto'}}
    changed={**initial,'x_label':'Wavelength (nm)','y1_label':'Absorbance','pub_dpi':600,'export_format':'svg'}
    assert callbacks._raw_render_settings(initial)==callbacks._raw_render_settings(changed)
    changed['axis_label_modes']={'x':'custom','y':'auto'}
    assert callbacks._raw_render_settings(initial)!=callbacks._raw_render_settings(changed)


def test_warm_browser_rebuilds_after_visibility_changes_while_tab_was_hidden(monkeypatch):
    app,cache,args=render_fixture(monkeypatch)
    calls=[]
    monkeypatch.setattr(callbacks,'_collect_visible_files',lambda *a,**k:calls.append(True) or {})
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'active-plot-tab.data'}]))
    # The same mutable visibility dictionary is used by the service and cache key.
    closure=app.functions['master_render'].__closure__
    dm=next(cell.cell_contents for cell in closure if isinstance(cell.cell_contents,SimpleNamespace) and hasattr(cell.cell_contents,'visibility_state'))
    dm.visibility_state['source']=False
    args[-1]=['chrom']
    assert app.functions['master_render'](*args)[0] is not dash.no_update
    assert calls==[True]


def test_warm_browser_rebuilds_for_new_peaks_and_axis_scale_edits(monkeypatch):
    for modification in ('peaks','scale','bounds','data'):
        app,cache,args=render_fixture(monkeypatch)
        calls=[]
        monkeypatch.setattr(callbacks,'_collect_visible_files',lambda *a,**k:calls.append(True) or {})
        monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'active-plot-tab.data'}]))
        args[-1]=['chrom']
        if modification=='peaks':args[9]=1
        elif modification=='scale':args[3]={**args[3],'x_scale':'log'}
        elif modification=='bounds':args[3]={**args[3],'axis_overrides':{'x:min':{'mode':'manual','min':5,'max':9}}}
        else:args[4]=1
        assert app.functions['master_render'](*args)[0] is not dash.no_update
        assert calls==[True]


def test_axis_toolbar_controls_render_through_their_settings_store_once(monkeypatch):
    app,cache,args=render_fixture(monkeypatch)
    registration=app.registrations['master_render']
    inputs=registration[1];states=registration[2]
    assert 'pub-zoom-sync' not in {item.component_id for item in inputs}
    assert 'plot-y-scope' not in {item.component_id for item in inputs}
    assert {'pub-zoom-sync','plot-y-scope'} <= {item.component_id for item in states}
