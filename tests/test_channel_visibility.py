import json
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from src.ingestion.types import ColumnRole, SourceCategory, StandardizedResult, FileIdentity


def signal(identifier, wavelength=None, role=ComponentRole.PRIMARY, category=SourceCategory.CHROMATOGRAM):
    frame = pd.DataFrame({'Time (min)': [0., 1., 2.], 'Absorbance (mAU)': [0., 3., 0.]})
    roles = {frame.columns[0]: ColumnRole.X, frame.columns[1]: ColumnRole.Y}
    metadata = {'wavelength_nm': wavelength} if wavelength else {}
    sr = StandardizedResult(frame, roles, FileIdentity(identifier+'.txt', 'txt', 'fixture', 2),
                            source_category=category, metadata=metadata)
    return Component(identifier, role, identifier+'.txt', dataframe=frame, column_roles=roles,
                     metadata=metadata, source_category=category, standardized=sr)


def samples():
    store = DataStore()
    for name in ('a', 'b'):
        store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM,
            component_list=[signal(name+'250', 250), signal(name+'263', 263)]))
    return store


def test_channel_toggle_spans_samples_preserving_other_channel_and_peaks():
    from services.channel_visibility import channel_controls, toggle_channel
    store = samples()
    from services.peak_service import Peak
    store.peak_service._peaks['a250'] = [Peak('peak', 'a250', 'P1', 1, 0, 2, 3, 3, 2)]
    before = store.peak_service.serialize()
    assert [c['label'] for c in channel_controls(store, ['a', 'b'])] == ['250 nm', '263 nm']
    toggle_channel(store, ['a', 'b'], 'uv:250')
    assert all(store.visibility_state[f'{name}250'] is False for name in ('a','b'))
    assert all(store.visibility_state.get(f'{name}263', True) for name in ('a','b'))
    assert store.peak_service.serialize() == before
    controls = channel_controls(store, ['a','b'])
    assert controls[0]['state'] == 'false'
    assert controls[1]['state'] == 'true'


def test_mixed_channel_becomes_all_visible_without_touching_other_group():
    from services.channel_visibility import channel_controls, toggle_channel
    store = samples()
    store.visibility_state['a250'] = False
    store.add_bundle(Bundle('other', 'other', BundleType.CHROMATOGRAM,
                            component_list=[signal('other250', 250)]))
    store.visibility_state['other250'] = False
    assert channel_controls(store, ['a','b'])[0]['state'] == 'mixed'
    toggle_channel(store, ['a','b'], 'uv:250')
    assert store.visibility_state['a250'] and store.visibility_state['b250']
    assert not store.visibility_state['other250']


def test_lcms_channels_use_polarity_and_wavelength_independent_of_name():
    from services.channel_visibility import channel_controls, toggle_channel
    store = DataStore()
    for name in ('a','b'):
        items = [signal(name+'pos', role=ComponentRole.MS_POSITIVE, category=SourceCategory.LCMS_MS),
                 signal(name+'neg', role=ComponentRole.MS_NEGATIVE, category=SourceCategory.LCMS_MS),
                 signal(name+'uv', 280, ComponentRole.VWD_A, SourceCategory.LCMS_UV)]
        for item in items:
            item.metadata['display_name'] = 'renamed data'
        store.add_bundle(Bundle(name, name, BundleType.LCMS, component_list=items))
    controls = channel_controls(store, ['a','b'])
    assert {c['label'] for c in controls} == {'+TIC','−TIC','280 nm'}
    toggle_channel(store, ['a','b'], 'ms:positive')
    assert not store.visibility_state['apos'] and not store.visibility_state['bpos']
    assert store.visibility_state.get('aneg', True) and store.visibility_state.get('auv', True)


def find(nodes, predicate):
    for node in nodes if isinstance(nodes, (list,tuple)) else [nodes]:
        if hasattr(node, 'to_plotly_json'):
            if predicate(node):
                return node
            found = find(getattr(node, 'children', []), predicate)
            if found is not None:
                return found
    return None


def test_group_collapse_survives_rerender_and_channel_icons_use_category():
    from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    store = samples()
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
    app = App(); register_file_tree_callbacks(app,store)
    tree = render_file_tree_with_bundles_selected(store.get_loaded_files_list(),store)
    disclosure = find(tree, lambda n: isinstance(getattr(n,'id',None),dict) and n.id.get('type')=='group-collapse-btn')
    assert disclosure is not None
    group_id = disclosure.id['index']
    trigger = SimpleNamespace(triggered=[{'prop_id': json.dumps(disclosure.id)+'.n_clicks', 'value': 1}])
    with patch('callbacks.file_tree_callbacks.callback_context',trigger):
        result = app.functions['toggle_group_expansion'](1, {'display':'block'})
    assert result[1]['display'] == 'none'
    tree = render_file_tree_with_bundles_selected(store.get_loaded_files_list(),store)
    container = find(tree, lambda n: getattr(n,'id',None)=={'type':'file-group','index':group_id})
    assert container.style['display'] == 'none'
    # Generic PRIMARY component roles still receive chromatogram graphics.
    assert 'tabler:file-question' not in str(tree)
    row = find(tree, lambda n: getattr(n,'id',None)=={'type':'file-tree-item','index':'a250'})
    assert row is not None
    assert find(tree, lambda n: getattr(n,'id',None)=={'type':'file-tree-item','index':'a263'}) is None
    assert find(row, lambda n: n.__class__.__name__=='Img') is not None


def test_single_channel_selection_switches_all_samples_then_combine_retains_both():
    from services.channel_visibility import choose_channel, visible_component_id
    store = samples()
    choose_channel(store, ['a','b'], 'uv:263', combine=False)
    assert not store.visibility_state['a250'] and not store.visibility_state['b250']
    assert store.visibility_state['a263'] and store.visibility_state['b263']
    assert visible_component_id(store, store.get_bundle('a'), 'a250') == 'a263'
    choose_channel(store, ['a','b'], 'uv:250', combine=True)
    assert all(store.visibility_state[x] for x in ('a250','a263','b250','b263'))


def test_sample_hide_show_preserves_channel_choice_even_if_choice_changes_while_hidden():
    from services.channel_visibility import choose_channel, set_sample_visibility
    store = samples()
    choose_channel(store, ['a','b'], 'uv:250', combine=False)
    set_sample_visibility(store, 'a', False)
    choose_channel(store, ['a','b'], 'uv:263', combine=False)
    assert not store.visibility_state['a']
    assert not store.visibility_state['a250'] and not store.visibility_state['a263']
    assert not store.visibility_state['b250'] and store.visibility_state['b263']
    set_sample_visibility(store, 'a', True)
    assert not store.visibility_state['a250'] and store.visibility_state['a263']


def test_new_import_uses_one_channel_and_follows_existing_selection():
    from services.channel_visibility import initialize_imported_channels, choose_channel, visible_component_id
    store = samples()
    initial = list(store.iter_bundles())
    initialize_imported_channels(store, initial)
    assert all(store.visibility_state[name+'250'] for name in ('a','b'))
    assert not any(store.visibility_state[name+'263'] for name in ('a','b'))
    choose_channel(store, ['a','b'], 'uv:263')
    previous = dict(store.visibility_state)
    imported = Bundle('c', 'c', BundleType.CHROMATOGRAM,
                      component_list=[signal('c250',250), signal('c263',263)])
    store.add_bundle(imported)
    initialize_imported_channels(store, [imported])
    assert store.visibility_state['c263'] and not store.visibility_state['c250']
    assert visible_component_id(store, imported) == 'c263'
    assert all(store.visibility_state[key] == value for key,value in previous.items())


def test_upload_activates_visible_channel_instead_of_hidden_primary():
    import base64
    from callbacks.upload_callbacks import register_upload_callbacks
    from services.channel_visibility import choose_channel
    store = samples()
    choose_channel(store, ['a','b'], 'uv:263')
    imported = Bundle('c', 'c', BundleType.CHROMATOGRAM,
                      component_list=[signal('c250',250), signal('c263',263)])
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
    app = App(); register_upload_callbacks(app,store)
    content = 'data:text/plain;base64,' + base64.b64encode(b'fixture').decode()
    with patch('ingestion.ingest_file', return_value=imported.primary.standardized, create=True), \
         patch('services.bundling_service.assign_bundles',return_value=[imported]):
        result = app.functions['handle_file_upload']([content], ['fixture.txt'], [0], [], 0)
    try:
        assert result[2] == 'c263'
    finally:
        import os
        for path in store.temp_files:
            if os.path.exists(path): os.unlink(path)


def test_clear_workspace_resets_channel_mode_and_hidden_masks():
    store = samples()
    from services.channel_visibility import set_sample_visibility
    store._channel_combine_modes = {'group-chromatogram': True}
    set_sample_visibility(store, 'a', False)
    store.clear()
    assert not getattr(store, '_channel_combine_modes', {})
    assert not getattr(store, '_hidden_sample_channels', {})


def test_legend_show_after_hiding_sample_releases_hidden_sample_mask():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from services.channel_visibility import set_sample_visibility, choose_channel
    store = samples()
    choose_channel(store,['a','b'],'uv:250')
    set_sample_visibility(store,'a',False)
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
    app = App(); register_file_tree_callbacks(app,store)
    trigger = SimpleNamespace(triggered=[{'prop_id': json.dumps({'type':'visibility-btn','index':'a250'})+'.n_clicks','value':1}])
    with patch('callbacks.file_tree_callbacks.callback_context',trigger):
        app.functions['handle_visibility_toggles']([1],[{'type':'visibility-btn','index':'a250'}],0)
    assert store.visibility_state['a']
    choose_channel(store,['a','b'],'uv:263')
    assert store.visibility_state['a263'] and not store.visibility_state['a250']


def test_toolbar_channels_toggle_independently_without_combine_mode():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
    from services.channel_visibility import initialize_imported_channels
    store=samples();initialize_imported_channels(store,list(store.iter_bundles()))
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn):self.functions[fn.__name__]=fn;return fn
            return wrap
    app=App();register_file_tree_callbacks(app,store)
    files=store.get_loaded_files_list()
    tree=render_file_tree_with_bundles_selected(files,store,'a250')
    group=find(tree,lambda n:isinstance(getattr(n,'id',None),dict) and n.id.get('type')=='group-collapse-btn').id['index']
    controls=app.functions['update_plot_channel_controls'](tree,group,'raw')
    assert find(controls,lambda n:isinstance(getattr(n,'id',None),dict) and n.id.get('type')=='group-channel-mode') is None
    button=find(controls,lambda n:getattr(n,'id',None)=={'type':'group-channel-btn','group':group,'channel':'uv:263'})
    assert button.role=='checkbox'
    trigger=SimpleNamespace(triggered=[{'prop_id':json.dumps(button.id)+'.n_clicks','value':1}])
    with patch('callbacks.file_tree_callbacks.callback_context',trigger):
        app.functions['toggle_group_channel']([1],0,files,'a250',group,None)
    assert all(store.visibility_state[c] for c in ('a250','a263','b250','b263'))
    with patch('callbacks.file_tree_callbacks.callback_context',trigger):
        app.functions['toggle_group_channel']([2],1,files,'a250',group,None)
    assert not store.visibility_state['a263'] and store.visibility_state['a250']


def test_undo_clear_all_preserves_channel_choice_for_hidden_samples():
    from services.channel_visibility import choose_channel,set_sample_visibility
    store=samples();choose_channel(store,['a','b'],'uv:263')
    store._channel_combine_modes={'scope':True}
    set_sample_visibility(store,'a',False)
    service=store.file_removal_service
    service.remove_all(active_file='b263')
    service.undo()
    set_sample_visibility(store,'a',True)
    assert store.visibility_state['a263'] and not store.visibility_state['a250']
    assert store._channel_combine_modes=={'scope':True}


def test_toolbar_channels_follow_active_plot_even_with_collapsed_file_group():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
    from services.channel_visibility import choose_channel
    store=samples(); choose_channel(store,['a','b'],'uv:263')
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
    app=App(); register_file_tree_callbacks(app,store)
    tree=render_file_tree_with_bundles_selected(store.get_loaded_files_list(),store)
    disclosure=find(tree,lambda n:isinstance(getattr(n,'id',None),dict) and n.id.get('type')=='group-collapse-btn')
    group=disclosure.id['index']; store.collapse_state[group]='collapsed'
    tree=render_file_tree_with_bundles_selected(store.get_loaded_files_list(),store)
    assert find(tree,lambda n:getattr(n,'className',None)=='group-channel-controls') is None
    controls=app.functions['update_plot_channel_controls'](tree,group,'raw')
    button=find(controls,lambda n:getattr(n,'id',None)=={'type':'group-channel-btn','group':group,'channel':'uv:263'})
    assert getattr(button,'aria-checked')=='true'
    assert json.loads(getattr(button,'data-channel-sources'))==['a263','b263']
    assert app.functions['update_plot_channel_controls'](tree,'unrelated-figure','raw')==[]
    assert app.functions['update_plot_channel_controls'](tree,group,'publication')==[]


def test_cross_sample_menu_and_integration_use_matching_channel_owners():
    from callbacks.context_menu_callbacks import register_context_menu_callbacks
    from services.channel_visibility import choose_channel, set_sample_visibility
    store=samples(); choose_channel(store,['a','b'],'uv:263')
    # "All files" includes a hidden sample, without integrating its other channel.
    set_sample_visibility(store,'b',False)
    ps=store.peak_service
    source=ps.add_baseline_peak(file_id='a263',area=3,height=3,apex_x=1,
        poly_x=[0,1,2,0],poly_y=[0,3,0,0],p_line=[(0,0),(2,0)],q1=(0,0),q2=(2,0))
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
    app=App();register_context_menu_callbacks(app,store)
    event={'peak_id':source.peak_id,'x':100,'y':100}
    assert app.functions['open_menu'](event)[2] is False
    result={'area':3,'height':3,'apex_x':1,'poly_x':[0,1,2,0],
        'poly_y':[0,3,0,0],'p_line':[(0,0),(2,0)],'q1':(0,0),'q2':(2,0)}
    with patch.object(ps,'find_matching_peak',return_value=result) as matcher:
        status=app.functions['integrate_all'](1,event,.3,0,0)
    assert [call.args[0] for call in matcher.call_args_list]==['b263']
    assert len(ps.get_peaks('b263'))==1
    assert not ps.get_peaks('b250') and not ps.get_peaks('a250')
    assert '1/1' in status[3]
    store.remove_bundle('b')
    assert app.functions['open_menu'](event)[2] is True


def test_lcms_import_defaults_to_one_uv_and_one_tic():
    from services.channel_visibility import initialize_imported_channels
    store=DataStore()
    bundle=Bundle('run','Run',BundleType.LCMS,component_list=[
        signal('neg',role=ComponentRole.MS_NEGATIVE,category=SourceCategory.LCMS_MS),
        signal('uv250',250,ComponentRole.VWD_A,SourceCategory.LCMS_UV),
        signal('uv280',280,ComponentRole.VWD_B,SourceCategory.LCMS_UV),
        signal('pos',role=ComponentRole.MS_POSITIVE,category=SourceCategory.LCMS_MS)])
    store.add_bundle(bundle);initialize_imported_channels(store,[bundle])
    assert sum(store.visibility_state[c] for c in ('neg','pos'))==1
    assert sum(store.visibility_state[c] for c in ('uv250','uv280'))==1


def test_channel_off_stays_off_when_hidden_sample_is_shown():
    from services.channel_visibility import initialize_imported_channels,set_sample_visibility,toggle_channel
    store=samples();initialize_imported_channels(store,list(store.iter_bundles()))
    set_sample_visibility(store,'a',False)
    toggle_channel(store,['a','b'],'uv:250')
    assert not store.visibility_state['b250']
    set_sample_visibility(store,'a',True)
    assert not store.visibility_state['a250']


def test_channel_overview_removes_shared_channel_and_undo_restores_it():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from callbacks.upload_callbacks import render_file_tree_with_bundles_selected
    store=samples()
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn):self.functions[fn.__name__]=fn;return fn
            return wrap
    app=App();register_file_tree_callbacks(app,store)
    tree=render_file_tree_with_bundles_selected(store.get_loaded_files_list(),store)
    group=find(tree,lambda n:isinstance(getattr(n,'id',None),dict) and n.id.get('type')=='group-collapse-btn').id['index']
    controls=app.functions['update_pda_channel_controls'](tree,group,'raw')
    remove=find(controls,lambda n:getattr(n,'id',None)=={'type':'remove-channel-btn','group':group,'channel':'uv:250'})
    assert remove is not None
    trigger=SimpleNamespace(triggered=[{'prop_id':json.dumps(remove.id)+'.n_clicks','value':1}])
    with patch('callbacks.file_tree_callbacks.callback_context',trigger):
        result=app.functions['remove_group_channel']([1],'a250',0)
    assert store.get_data_by_id('a250') is None and store.get_data_by_id('b250') is None
    assert result[3]=='a263'
    app.functions['undo_file_removal'](1,1)
    assert store.get_data_by_id('a250') is not None and store.get_data_by_id('b250') is not None


def test_lcms_channel_toggles_replace_redundant_polarity_filter():
    from callbacks.ms_polarity_callbacks import register_ms_polarity_callbacks
    from callbacks.viz_callbacks import _get_overlay_group,_tab_id_from_group
    store=DataStore();bundle=Bundle('run','Run',BundleType.LCMS,component_list=[
        signal('uv',280,ComponentRole.VWD_A,SourceCategory.LCMS_UV),
        signal('pos',role=ComponentRole.MS_POSITIVE,category=SourceCategory.LCMS_MS),
        signal('neg',role=ComponentRole.MS_NEGATIVE,category=SourceCategory.LCMS_MS)])
    store.add_bundle(bundle)
    entry=store.get_data_by_id('run');group=_get_overlay_group(entry['metadata'],entry,'run',store)
    tab=_tab_id_from_group(group);context='shared:raw:'+tab
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn):self.functions[fn.__name__]=fn;return fn
            return wrap
    app=App();register_ms_polarity_callbacks(app,store)
    with patch('callbacks.ms_polarity_callbacks.ctx',SimpleNamespace(triggered_id='active-plot-tab')):
        result=app.functions['sync_polarity']('positive',{'_context_key':context,'ms_polarity':'positive'},tab,
        [{'id':tab,'type':'raw','group_key':group}],'uv',store.get_loaded_files_list(),context)
    assert result[0]=={'display':'none'}
    assert result[4]['ms_polarity']=='both'


def test_switching_a_channel_on_keeps_a_hidden_sample_hidden_until_it_is_shown():
    from services.channel_visibility import set_sample_visibility, show_channel
    store = samples()
    store.visibility_state['b263'] = False
    set_sample_visibility(store, 'b', False)            # eye off on sample b
    show_channel(store, 'b263')                         # e.g. "Add 263 nm channel" in the PDA view, for every sample
    assert store.visibility_state['b263'] is False      # b stays out of the plot
    show_channel(store, 'a263')
    assert store.visibility_state['a263'] is True       # visible samples get the channel at once
    set_sample_visibility(store, 'b', True)
    assert store.visibility_state['b263'] is True       # and b shows it when it comes back


def test_plot_switches_show_the_tabs_own_channels_and_toggle_them_in_every_run():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
    store = DataStore()
    for name, nm in (('lys', 280), ('blank', 214)):
        items = [signal(name + 'pos', role=ComponentRole.MS_POSITIVE, category=SourceCategory.LCMS_MS),
                 signal(name + 'uv', nm, ComponentRole.VWD_A, SourceCategory.LCMS_UV),
                 signal(name + 'uv250', 250, ComponentRole.VWD_B, SourceCategory.LCMS_UV)]
        store.add_bundle(Bundle(name, name, BundleType.LCMS, component_list=items))
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn): self.functions[fn.__name__] = fn; return fn
            return wrap
    app = App(); register_file_tree_callbacks(app, store)
    entry = store.get_data_by_id('lys')
    tab = _tab_id_from_group(_get_overlay_group(entry['metadata'], entry, 'lys', store))
    controls = app.functions['update_plot_channel_controls']([], tab, 'raw')
    labels = [getattr(n, 'data-channel-label') for n in controls.children]
    assert labels == ['+TIC', '250 nm', '280 nm']                  # no 214 nm: that run is not in this tab
    from services.channel_visibility import group_bundle_ids, toggle_channel
    toggle_channel(store, group_bundle_ids(store, tab), 'uv:250')
    assert store.visibility_state['lysuv250'] == store.visibility_state['blankuv250']


def test_plot_switches_leave_out_the_channels_of_hidden_runs_in_the_tab():
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    from services.channel_visibility import set_sample_visibility
    store = DataStore()
    store.group_overrides = {}
    for name, nm in (('run', 220), ('blank', 214)):
        items = [signal(name + 'pos', role=ComponentRole.MS_POSITIVE, category=SourceCategory.LCMS_MS),
                 signal(name + 'uv', nm, ComponentRole.VWD_A, SourceCategory.LCMS_UV)]
        store.add_bundle(Bundle(name, name, BundleType.LCMS, component_list=items))
        store.group_overrides[name] = ('folder', 'Time (min)', 'Sequence')
    set_sample_visibility(store, 'blank', False)
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn): self.functions[fn.__name__] = fn; return fn
            return wrap
    app = App(); register_file_tree_callbacks(app, store)
    controls = app.functions['update_plot_channel_controls']([], 'tab-folder_time_min_sequence', 'raw')
    assert [getattr(n, 'data-channel-label') for n in controls.children] == ['+TIC', '220 nm']
    set_sample_visibility(store, 'blank', True)
    controls = app.functions['update_plot_channel_controls']([], 'tab-folder_time_min_sequence', 'raw')
    assert [getattr(n, 'data-channel-label') for n in controls.children] == ['+TIC', '214 nm', '220 nm']


def test_new_samples_show_one_uv_channel_the_lowest_wavelength():
    from services.channel_visibility import initialize_imported_channels
    store = DataStore()
    pda = Bundle('ala', 'ala', BundleType.CHROMATOGRAM, component_list=[signal('ala263', 263), signal('ala250', 250)])
    store.add_bundle(pda)
    initialize_imported_channels(store, [pda])
    assert store.visibility_state['ala250'] and not store.visibility_state['ala263']
    runs = []
    for name, wavelengths in (('blank', (254, 214)), ('lys', (280, 250))):
        items = [signal(name + 'pos', role=ComponentRole.MS_POSITIVE, category=SourceCategory.LCMS_MS),
                 signal(name + 'neg', role=ComponentRole.MS_NEGATIVE, category=SourceCategory.LCMS_MS)]
        items += [signal(f'{name}{nm}', nm, ComponentRole.VWD_A, SourceCategory.LCMS_UV) for nm in wavelengths]
        bundle = Bundle(name, name, BundleType.LCMS, component_list=items)
        store.add_bundle(bundle)
        initialize_imported_channels(store, [bundle])
        runs.append(bundle)
    shown = {c.component_id for b in runs for c in b.component_list if store.visibility_state.get(c.component_id, True)}
    assert shown == {'blankpos', 'blank214', 'lyspos', 'lys250'}     # the second run's own lowest wavelength
