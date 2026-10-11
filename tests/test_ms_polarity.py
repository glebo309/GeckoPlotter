"""MS filters affect detector modes without changing UV visibility or source data."""
from types import SimpleNamespace
import dash
from services.ms_polarity import filter_ms_polarity, polarity_options, entry_polarity


def entries():
    return {'lcms': [(name, {'record': {'id': name, 'type': role}, 'metadata': meta})
                    for name, role, meta in [
                        ('positive', 'ms_positive', {}), ('negative', 'ms_negative', {}),
                        ('UV', 'vwd_a', {}), ('unknown MS', 'primary', {'ionization_mode': 'unknown'})]]}


def test_filter_keeps_uv_unknown_and_original_arrays_for_both_modes():
    source = entries()
    for polarity, wanted in [('positive', ['positive', 'UV', 'unknown MS']),
                             ('negative', ['negative', 'UV', 'unknown MS'])]:
        filtered = filter_ms_polarity(source, polarity)
        assert [name for name, _ in filtered['lcms']] == wanted
        assert filtered['lcms'][0][1] is source['lcms'][0 if polarity == 'positive' else 1][1]
    assert filter_ms_polarity(source, 'both') is source
    assert len(source['lcms']) == 4


def test_metadata_is_authoritative_for_legacy_misclassified_ms_component():
    assert entry_polarity({'record': {'type': 'ms_positive'},
                           'metadata': {'ionization_mode': 'negative'}}) == 'negative'
    assert entry_polarity({'record': {'type': 'vwd_a'},
                           'metadata': {'ionization_mode': 'negative'}}) is None


def test_unavailable_modes_disabled_and_no_ms_hides_control():
    options = polarity_options({'lcms': entries()['lcms'][:1] + entries()['lcms'][2:]})
    assert [(o['value'], o['disabled']) for o in options] == [('positive', False), ('negative', True), ('both', True)]
    assert polarity_options({'uv': [entries()['lcms'][2]]}) == []


def test_control_edits_only_its_current_raw_figure(monkeypatch):
    from callbacks import ms_polarity_callbacks as module
    from test_file_controls import component
    from services.data_store import DataStore, Bundle, BundleType, ComponentRole
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=[
        component('positive', ComponentRole.MS_POSITIVE), component('negative', ComponentRole.MS_NEGATIVE),
        component('uv', ComponentRole.VWD_A)]))
    app = dash.Dash(__name__)
    module.register_ms_polarity_callbacks(app, store)
    cb = next(c['callback'].__wrapped__ for c in app.callback_map.values())
    tabs = [{'id': 'raw', 'type': 'raw'}]
    settings = {'_context_key': 'shared:raw:raw', 'layout_mode': 'overlay'}
    monkeypatch.setattr(module, 'ctx', SimpleNamespace(triggered_id='ms-polarity-control'))
    out = cb('negative', settings, 'raw', tabs, 'positive', store.get_loaded_files_list(), settings['_context_key'])
    assert out[4]['ms_polarity'] == 'negative'
    assert out[4]['layout_mode'] == 'overlay'
    assert store.visibility_state == {}
    assert cb('negative', settings, 'raw', tabs, 'positive', store.get_loaded_files_list(), 'shared:raw:other')[4] is dash.no_update
    monkeypatch.setattr(module, 'ctx', SimpleNamespace(triggered_id='active-plot-tab'))
    out = cb('negative', settings, 'publication', [{'id': 'publication', 'type': 'publication'}],
             'positive', store.get_loaded_files_list(), settings['_context_key'])
    assert out[0] == {'display': 'none'}
    assert out[4] is dash.no_update


def test_raw_render_filters_ms_before_building_axes_and_peak_overlays(monkeypatch):
    from test_render_tab_performance import App
    from test_file_controls import component
    from services.data_store import DataStore, Bundle, BundleType, ComponentRole
    from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
    import callbacks.viz_callbacks as module
    import src.ingestion.types as types
    import sys
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=[
        component('positive', ComponentRole.MS_POSITIVE), component('negative', ComponentRole.MS_NEGATIVE),
        component('uv', ComponentRole.VWD_A)]))
    group = module._get_active_file_group(store, 'negative')
    app = App(); module.register_viz_callbacks(app, store)
    monkeypatch.setattr(dash, 'callback_context', SimpleNamespace(triggered=[{'prop_id': 'current-plot-settings.data'}]))
    called = []
    original = module.overlay_peaks_on_figure
    monkeypatch.setattr(module, 'overlay_peaks_on_figure', lambda *args, **kwargs: called.append(True) or original(*args, **kwargs))
    for mode in ('overlay', 'stacked'):
        settings = {**DEFAULT_PLOT_SETTINGS, '_context_key': 'shared:raw:raw', 'ms_polarity': 'positive', 'layout_mode': mode}
        args = ['raw', None, 'negative', settings, 0, {}, [], [], [], 0, True, 'independent',
                store.get_loaded_files_list(), [{'id': 'raw', 'type': 'raw', 'group_key': list(group)}],
                None, None, None, {}, {}, None, [], None, ['peaks'], []]
        figure = app.functions['master_render'](*args)[0]
        assert {trace.meta['file_id'] for trace in figure.data if isinstance(trace.meta, dict)} == {'positive', 'uv'}
    assert called == [], 'A filtered-out active signal must not add its peak fills back into the figure'


def test_removing_selected_polarity_falls_back_to_available_mode(monkeypatch):
    from callbacks import ms_polarity_callbacks as module
    from test_file_controls import component
    from services.data_store import DataStore, Bundle, BundleType, ComponentRole
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS,
                            component_list=[component('positive', ComponentRole.MS_POSITIVE)]))
    app = dash.Dash(__name__); module.register_ms_polarity_callbacks(app, store)
    cb = next(c['callback'].__wrapped__ for c in app.callback_map.values())
    monkeypatch.setattr(module, 'ctx', SimpleNamespace(triggered_id='loaded-files'))
    settings = {'_context_key': 'shared:raw:raw', 'ms_polarity': 'negative'}
    out = cb('negative', settings, 'raw', [{'id': 'raw', 'type': 'raw'}], 'positive',
             store.get_loaded_files_list(), settings['_context_key'])
    assert out[2] == 'positive'
    assert out[4]['ms_polarity'] == 'positive'


def polarity_pipeline(monkeypatch):
    from test_render_tab_performance import App
    from test_file_controls import component
    from services.data_store import DataStore, Bundle, BundleType, ComponentRole
    from callbacks import ms_polarity_callbacks as polarity
    from callbacks import viz_callbacks as viz
    from callbacks import plot_settings_callbacks as settings_module
    import src.ingestion.types as types
    import sys
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    store=DataStore()
    for bundle_id,offset in [('first',0),('second',20)]:
        components=[component(bundle_id+'-'+name,role) for name,role in [
            ('positive',ComponentRole.MS_POSITIVE),('negative',ComponentRole.MS_NEGATIVE),('uv',ComponentRole.VWD_A)]]
        for comp in components:comp.dataframe['time']+=offset
        store.add_bundle(Bundle(bundle_id,bundle_id,BundleType.LCMS,component_list=components))
    app=App();polarity.register_ms_polarity_callbacks(app,store)
    viz.register_viz_callbacks(app,store);settings_module.register_plot_settings_callbacks(app,store)
    loaded=store.get_loaded_files_list()
    tabs,_=app.functions['sync_plot_tabs'](loaded,[],None,'first-positive')
    def tab_for(fid):
        return next(t for t in tabs if tuple(t['group_key'])==viz._get_active_file_group(store,fid))
    def hydrate(fid):
        tab=tab_for(fid)
        context='shared:raw:'+tab['id']
        return app.functions['hydrate_plot_settings'](context,fid,tab['id'],{})[0]
    def control(value,settings,fid,trigger='ms-polarity-control',owner=None):
        monkeypatch.setattr(polarity,'ctx',SimpleNamespace(triggered_id=trigger))
        return app.functions['sync_polarity'](value,settings,tab_for(fid)['id'],tabs,fid,loaded,owner or settings['_context_key'])
    def render(settings,fid):
        monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered=[{'prop_id':'current-plot-settings.data'}]))
        args=[tab_for(fid)['id'],None,fid,settings,0,{},[],[],[],0,True,'independent',loaded,tabs,
              None,None,None,{}, {},None,[],None,['peaks'],[]]
        figure=app.functions['master_render'](*args)[0]
        return {tr.meta['file_id'] for tr in figure.data if isinstance(tr.meta,dict) and tr.meta.get('file_id')}
    return store,app,hydrate,control,render


def test_actual_controls_drive_both_positive_negative_and_restore_uv_without_mutation(monkeypatch):
    store,app,hydrate,control,render=polarity_pipeline(monkeypatch)
    settings=hydrate('first-positive')
    shown=control(None,settings,'first-positive','active-plot-tab')
    assert shown[2]=='both'
    assert render(settings,'first-positive')=={'first-positive','first-negative','first-uv'}
    for mode,ids in [('positive',{'first-positive','first-uv'}),
                     ('negative',{'first-negative','first-uv'}),
                     ('both',{'first-positive','first-negative','first-uv'})]:
        out=control(mode,settings,'first-positive')
        assert out[2]==mode and out[4] is not dash.no_update
        settings=out[4]
        assert render(settings,'first-positive')==ids
    assert store.visibility_state=={}
    assert len(store.get_bundle('first').component_list)==3


def test_polarity_is_saved_per_plot_tab_and_stale_control_hydration_cannot_overwrite_it(monkeypatch):
    store,app,hydrate,control,render=polarity_pipeline(monkeypatch)
    first=hydrate('first-positive')
    first=control('negative',first,'first-positive')[4]
    app.functions['persist_plot_settings'](first,first['_context_key'])
    second=hydrate('second-positive')
    assert control('negative',second,'second-positive','active-plot-tab')[2]=='both'
    second=control('positive',second,'second-positive')[4]
    app.functions['persist_plot_settings'](second,second['_context_key'])
    first=hydrate('first-negative')
    restored=control('positive',first,'first-negative','active-plot-tab',second['_context_key'])
    assert restored[2]=='negative' and restored[4] is dash.no_update
    assert render(first,'first-negative')=={'first-negative','first-uv'}
    assert render(hydrate('second-negative'),'second-negative')=={'second-positive','second-uv'}


def test_opening_peaks_results_keeps_same_raw_figure_polarity_context(monkeypatch):
    store,app,hydrate,control,render=polarity_pipeline(monkeypatch)
    first=hydrate('first-positive')
    first=control('negative',first,'first-positive')[4]
    app.functions['persist_plot_settings'](first,first['_context_key'])
    context=first['_context_key'];tab=context.removeprefix('shared:raw:')
    for panel in ('peak-analysis','data-overview','across-samples','metadata'):
        result=app.functions['resolve_plot_context']('first-positive','raw',panel,tab,context)
        assert result is dash.no_update, 'Opening a results pane must not reset the shown plot polarity/layout settings'
        restored=hydrate('first-positive')
        assert restored['ms_polarity']=='negative'
        assert restored['layout_mode']==first['layout_mode']
    assert render(restored,'first-positive')=={'first-negative','first-uv'}
