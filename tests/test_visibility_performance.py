from copy import deepcopy
from types import SimpleNamespace
import dash
import plotly.graph_objects as go
import callbacks.viz_callbacks as callbacks
from test_render_tab_performance import render_fixture


def prime(monkeypatch):
    app, cache, args = render_fixture(monkeypatch)
    dm = next(cell.cell_contents for cell in app.functions['master_render'].__closure__
              if isinstance(cell.cell_contents, SimpleNamespace) and hasattr(cell.cell_contents, 'visibility_state'))
    monkeypatch.setattr(dash, 'callback_context', SimpleNamespace(triggered=[{'prop_id':'render-trigger.data'}]))
    monkeypatch.setattr(callbacks, 'compose_raw_figure', lambda *a, **kw: go.Figure([
        go.Scatter(x=[0,1,2],y=[0,4,0],meta={'file_id':'source'}),
        go.Scatter(x=[0,1,2],y=[1,2,1],meta={'file_id':'second'})]))
    dm.loaded_data['second'] = {'standardized':object()}
    fig = app.functions['master_render'](*args)[0]
    args[-1] = fig.to_plotly_json()
    monkeypatch.setattr(callbacks, 'compose_raw_figure', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Visibility rebuilt plot')))
    monkeypatch.setattr(dash, 'callback_context', SimpleNamespace(triggered=[{'prop_id':'hidden-files.data'}]))
    return app, cache, args, dm


def test_eye_updates_only_visibility_without_resending_coordinates(monkeypatch):
    app,cache,args,dm = prime(monkeypatch)
    dm.visibility_state['source'] = False
    patch = app.functions['master_render'](*args)[0]
    assert isinstance(patch, dash.Patch)
    operations = patch.to_plotly_json()['operations']
    assert any(op['location']==['data',0,'visible'] and op['params']['value'] is False for op in operations)
    assert len(str(operations)) < 2000
    assert not any(op['location'][-1] in ('x','y') for op in operations)


def test_showing_retained_trace_and_hiding_every_trace_uses_patch(monkeypatch):
    app,cache,args,dm = prime(monkeypatch)
    for visible in (False,True,False):
        dm.visibility_state.update(source=visible,second=visible)
        result=app.functions['master_render'](*args)[0]
        assert isinstance(result,dash.Patch)
        # Acknowledge the previous patch like the browser inspector store.
        for op in result.to_plotly_json()['operations']:
            if op['location'][:2]==['layout','meta']:
                args[-1]['layout']['meta'][op['location'][2]]=op['params']['value']


def test_cold_browser_receives_complete_visibility_figure(monkeypatch):
    app,cache,args,dm = prime(monkeypatch)
    args[-1]={}
    dm.visibility_state['source']=False
    result=app.functions['master_render'](*args)[0]
    assert isinstance(result,go.Figure)
    assert result.data[0].visible is False


def test_eye_callback_does_not_trigger_unrelated_full_renders(monkeypatch):
    from test_channel_visibility import samples
    from callbacks import file_tree_callbacks as tree
    store=samples()
    app=dash.Dash(__name__)
    tree.register_file_tree_callbacks(app,store)
    cb=next(c['callback'].__wrapped__ for c in app.callback_map.values() if c.get('callback') and c['callback'].__wrapped__.__name__=='handle_visibility_toggles')
    monkeypatch.setattr(tree,'callback_context',SimpleNamespace(triggered=[{'prop_id':'{"type":"visibility-btn","index":"a"}.n_clicks','value':1}]))
    render,hidden=cb([1],[],3)
    assert render is dash.no_update
    assert 'a' in hidden


def test_visibility_is_a_render_input(monkeypatch):
    app, _, _ = render_fixture(monkeypatch)
    deps=[d for group in app.registrations['master_render'] if isinstance(group,list) for d in group]
    assert any(isinstance(d,dash.Input) and d.component_id=='hidden-files' for d in deps)


def test_unseen_channel_and_scientific_edits_rebuild(monkeypatch):
    for change in ('channel','data','settings','peaks','stacked'):
        app,cache,args,dm=prime(monkeypatch)
        calls=[]
        monkeypatch.setattr(callbacks,'compose_raw_figure',lambda *a,**kw:calls.append(1) or go.Figure())
        dm.visibility_state['source']=False
        if change=='channel':
            # This component was hidden in the original cached state.
            old,fig=cache._entries['chrom']
            import json
            old=json.loads(old);old['visibility']['unseen']=False;old['signals'].append('unseen')
            cache._entries['chrom']=(cache._key(old),fig)
            dm.loaded_data['unseen']={'standardized':object()}
            dm.visibility_state['unseen']=True
        elif change=='data':args[4]+=1
        elif change=='settings':args[3]={**args[3],'x_scale':'log'}
        elif change=='peaks':args[9]+=1
        else:args[3]={**args[3],'layout_mode':'stacked'}
        app.functions['master_render'](*args)
        assert calls==[1],change


def test_peak_overlays_and_annotations_use_full_composer(monkeypatch):
    for kind in ('peak','annotation','shape'):
        app,cache,args,dm=prime(monkeypatch)
        key,fig=cache._entries['chrom']
        if kind=='peak':fig.add_trace(go.Scatter(x=[1],y=[2],meta='peak_overlay'))
        elif kind=='annotation':fig.add_annotation(x=1,y=2,text='peak')
        else:fig.add_shape(x0=0,x1=1,y0=0,y1=1)
        calls=[]
        monkeypatch.setattr(callbacks,'compose_raw_figure',lambda *a,**kw:calls.append(1) or go.Figure())
        dm.visibility_state['source']=False
        app.functions['master_render'](*args)
        assert calls==[1]


def peak_cache():
    from services.render_cache import RenderCache
    geometry={p:{'file_id':fid,'label_group':'compound','label_top':top,
                 'bounds':[0,2],'baseline':[[0,0],[2,0]],'baseline_points':[[0]*10000,[0]*10000]}
              for p,fid,top in [('pa','a',10),('pb','b',5)]}
    fig=go.Figure([
        go.Scatter(x=[0,1,2],y=[0,10,0],meta={'file_id':'a'}),
        go.Scatter(x=[0,1,2],y=[0,5,0],meta={'file_id':'b'}),
        go.Scatter(x=[0,1,2],y=[0,10,0],fill='toself',meta='peak_overlay',customdata=['pa']*3),
        go.Scatter(x=[1],y=[10],mode='text',meta='peak_overlay',customdata=['pa'],text=['P']),
        go.Scatter(x=[0,1,2],y=[0,5,0],fill='toself',meta='peak_overlay',customdata=['pb']*3),
        go.Scatter(x=[1],y=[5],mode='text',meta='peak_overlay',customdata=['pb'],text=['P'],visible=False)])
    fig.update_layout(meta={'gecko_peak_geometry':geometry,'gecko_render_revision':'base','gecko_visibility_base':'base'},
                      shapes=[dict(type='line',name='baseline:pa',x0=0,x1=2,y0=0,y1=0)])
    inputs={'visibility':{},'signals':['a','b'],'display':['peaks']}
    cache=RenderCache();cache.put('tab',inputs,fig)
    return cache,fig,inputs


def test_peak_visibility_patches_fill_labels_and_handles_without_sending_geometry():
    import json
    cache,fig,inputs=peak_cache()
    patch=cache.visibility_update('tab',{**inputs,'visibility':{'a':False}},'hidden',fig.to_plotly_json())
    assert isinstance(patch,dash.Patch)
    operations={tuple(o['location']):o['params']['value'] for o in patch.to_plotly_json()['operations']}
    assert operations['data',0,'visible'] is False
    assert operations['data',2,'visible'] is False
    assert operations['data',3,'visible'] is False
    assert operations['data',5,'visible'] is True
    assert operations['layout','shapes',0,'visible'] is False
    assert len(json.dumps(patch.to_plotly_json()))<2000
    delivered={'layout':{'meta':{'gecko_render_revision':'hidden'}}}
    patch=cache.visibility_update('tab',inputs,'shown',delivered)
    operations={tuple(o['location']):o['params']['value'] for o in patch.to_plotly_json()['operations']}
    assert operations['data',3,'visible'] is True
    assert operations['data',5,'visible'] is False
    assert operations['layout','shapes',0,'visible'] is True


def test_missing_alternative_label_rebuilds_and_hide_labels_stays_hidden():
    cache,fig,inputs=peak_cache()
    key,stored=cache._entries['tab'];stored.data=stored.data[:-1]
    assert cache.visibility_update('tab',{**inputs,'visibility':{'a':False}},'hidden',fig.to_plotly_json()) is None
    inputs['display']=['peaks','hide-labels']
    cache.put('tab',inputs,fig)
    patch=cache.visibility_update('tab',{**inputs,'visibility':{'a':False}},'hidden',fig.to_plotly_json())
    assert isinstance(patch,dash.Patch)
    current=cache._entries['tab'][1]
    assert current.data[3].visible is False and current.data[5].visible is False
