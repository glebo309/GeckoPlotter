"""Removal is a reversible workspace action, independent of peak undo."""
from dataclasses import replace

import dash
import pytest

from callbacks.file_tree_callbacks import register_file_tree_callbacks
from services.data_store import Bundle, BundleType, DataStore
from services.peak_service import Peak
from test_file_controls import component


def populated():
    store = DataStore()
    store.peak_service.clear_all_peaks()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS,
                            component_list=[component('tic'), component('uv')]))
    store.add_bundle(Bundle('other', 'Other', BundleType.GENERIC,
                            component_list=[component('other-data')]))
    store.file_ui_state['tic'] = {'plot_settings': {'layout_mode': 'overlay', 'xmin': 4}}
    store.visibility_state['tic'] = False
    store.collapse_state['sample'] = 'expanded'
    store.peak_service._peaks['tic'] = [Peak('p1', 'tic', 'Peak 1', 1, 0, 2, 3, 3, 2)]
    return store


def test_disclosure_has_no_selection_callback():
    app = dash.Dash(__name__)
    register_file_tree_callbacks(app, DataStore())
    for cb in app.callback_map.values():
        if any('expand-btn' in value['id'] for value in cb['inputs']):
            outputs = cb['output'] if isinstance(cb['output'], list) else [cb['output']]
            assert all(out.component_id != 'active-file' for out in outputs)


def test_remove_and_undo_bundle_restore_data_peaks_settings_without_peak_undo():
    store = populated()
    signal = store.get_data_by_id('tic')['data']
    removal = store.file_removal_service.remove('sample', active_file='tic')
    assert removal.label == 'Sample'
    assert store.get_bundle('sample') is None
    assert 'tic' not in store.peak_service._peaks
    assert 'tic' not in store.file_ui_state
    assert store.peak_service.can_undo is False
    # Later edits on another dataset must survive undo removal.
    store.file_ui_state['other-data'] = {'changed': True}
    restored = store.file_removal_service.undo()
    assert restored.active_file == 'tic'
    assert store.get_data_by_id('tic')['data'] is signal  # no duplicate large arrays
    assert store.file_ui_state['tic']['plot_settings']['xmin'] == 4
    assert store.visibility_state['tic'] is False
    assert store.collapse_state['sample'] == 'expanded'
    assert store.peak_service._peaks['tic'][0].peak_id == 'p1'
    assert store.file_ui_state['other-data'] == {'changed': True}
    assert list(store.all_bundles()) == ['sample', 'other']


def test_undo_component_keeps_sibling_edits_and_new_files():
    store = populated()
    store.file_removal_service.remove('tic', active_file='tic')
    store.get_bundle('sample').component_list[0].metadata['edited'] = True
    store.add_bundle(Bundle('new', 'New', BundleType.GENERIC, component_list=[component('new-data')]))
    store.file_removal_service.undo()
    assert [c.component_id for c in store.get_bundle('sample').component_list] == ['tic', 'uv']
    assert store.get_bundle('sample').component_list[1].metadata['edited'] is True
    assert store.get_bundle('new') is not None


def test_remove_all_and_undo_preserve_temp_source_files(tmp_path):
    store = populated()
    path = tmp_path / 'source.dx'
    path.write_bytes(b'source data')
    store.temp_files.append(str(path))
    store.file_removal_service.remove_all(active_file='tic')
    assert store.get_loaded_files_list() == []
    assert path.exists()
    store.file_removal_service.undo()
    assert len(store.get_loaded_files_list()) == 2
    assert store.get_data_by_id('tic') is not None
    assert store.peak_service._peaks['tic'][0].name == 'Peak 1'


def test_remove_well_changes_real_dataframe_and_undo_restores_it():
    from src.ingestion.types import ColumnRole, PlotHint
    store = populated()
    trace = component('plate')
    trace.dataframe = trace.dataframe.rename(columns={'signal': 'A1'})
    trace.dataframe['B1'] = [1, 2, 3]
    trace.column_roles = {'time': ColumnRole.X, 'A1': ColumnRole.Y, 'B1': ColumnRole.Y}
    trace.metadata = {'filled_wells': ['A1', 'B1']}
    trace.standardized = replace(trace.standardized, data=trace.dataframe,
                                 column_roles=trace.column_roles, plot_hint=PlotHint.MULTI_Y,
                                 metadata=trace.metadata)
    store.add_bundle(Bundle('plate-bundle', 'Plate', BundleType.PLATE_READER, component_list=[trace]))
    store.file_removal_service.remove('plate|A1', active_file='plate|A1')
    assert 'A1' not in store.get_data_by_id('plate')['data'].columns
    assert 'A1' not in store.get_data_by_id('plate')['standardized'].y_columns
    store.file_removal_service.undo()
    assert list(store.get_data_by_id('plate')['data'].columns) == ['time', 'A1', 'B1']


def test_unknown_removal_does_not_replace_available_undo():
    store = populated()
    store.file_removal_service.remove('tic')
    assert store.file_removal_service.remove('missing') is None
    assert store.file_removal_service.undo().label == 'tic'


def test_remove_callback_exposes_undo_and_undo_restores_selection(monkeypatch):
    import json
    from types import SimpleNamespace
    from callbacks import file_tree_callbacks
    store = populated()
    app = dash.Dash(__name__)
    register_file_tree_callbacks(app, store)
    callbacks = {cb['callback'].__wrapped__.__name__: cb['callback'].__wrapped__
                 for cb in app.callback_map.values()}
    monkeypatch.setattr(file_tree_callbacks, 'callback_context', SimpleNamespace(
        triggered=[{'prop_id': json.dumps({'type': 'delete-btn', 'index': 'sample'}) + '.n_clicks', 'value': 1}]))
    result = callbacks['handle_file_deletion']([1], store.get_loaded_files_list(), 'tic', 2)
    assert result[8] == {'display': 'flex'}
    assert 'Sample' in result[9]
    assert result[10] is False
    restored = callbacks['undo_file_removal'](1, 3)
    assert restored[3] == 'tic'
    assert restored[2] == 4
    assert restored[10] is True
    assert 'Restored' in restored[9]
    assert 'tic' in restored[11]


def test_bundle_visibility_includes_primary_without_selecting(monkeypatch):
    import json
    from types import SimpleNamespace
    from callbacks import file_tree_callbacks
    store = populated()
    store.visibility_state.clear()
    app = dash.Dash(__name__)
    register_file_tree_callbacks(app, store)
    callback = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                    if cb['callback'].__wrapped__.__name__ == 'handle_visibility_toggles')
    monkeypatch.setattr(file_tree_callbacks, 'callback_context', SimpleNamespace(
        triggered=[{'prop_id': json.dumps({'type': 'visibility-btn', 'index': 'sample'}) + '.n_clicks', 'value': 1}]))
    _, hidden = callback([1], [{'type': 'visibility-btn', 'index': 'sample'}], 3)
    assert set(hidden) == {'sample', 'tic', 'uv'}


def test_clear_all_callback_is_removed():
    from callbacks.upload_callbacks import register_clear_callbacks
    app = dash.Dash(__name__)
    register_clear_callbacks(app, populated())
    assert all(dep['id'] != 'clear-files-btn' for cb in app.callback_map.values() for dep in cb['inputs'])


def test_tree_rows_are_keyboard_selectable_and_controls_announce_expansion():
    from callbacks.upload_callbacks import render_bundle_item_selected
    store = populated()
    item = render_bundle_item_selected({'id': 'sample', 'name': 'Sample', 'children': []}, data_manager=store)
    def walk(component):
        if isinstance(component, (list, tuple)):
            for child in component:
                yield from walk(child)
        elif hasattr(component, 'to_plotly_json'):
            props = component.to_plotly_json()['props']
            yield props
            yield from walk(props.get('children', []))
    props = list(walk(item))
    row = next(p for p in props if p.get('id') == {'type': 'file-tree-item', 'index': 'sample'})
    assert row['tabIndex'] == 0
    assert row['role'] == 'button'
    disclosure = next(p for p in props if p.get('id') == {'type': 'expand-btn', 'index': 'sample'})
    assert disclosure['aria-expanded'] == 'true'
    assert disclosure['className'] == 'tree-disclosure-btn'


def test_removing_last_well_removes_empty_file_and_undo_restores_it():
    from src.ingestion.types import ColumnRole, PlotHint
    store = DataStore()
    trace = component('plate')
    trace.dataframe = trace.dataframe.rename(columns={'signal': 'A1'})
    trace.column_roles = {'time': ColumnRole.X, 'A1': ColumnRole.Y}
    trace.metadata = {'filled_wells': ['A1']}
    trace.standardized = replace(trace.standardized, data=trace.dataframe,
                                 column_roles=trace.column_roles, plot_hint=PlotHint.MULTI_Y,
                                 metadata=trace.metadata)
    store.add_bundle(Bundle('plate-bundle', 'Plate', BundleType.PLATE_READER, component_list=[trace]))
    store.file_removal_service.remove('plate|A1', active_file='plate|A1')
    assert store.get_bundle('plate-bundle') is None
    assert store.get_data_by_id('plate') is None
    store.file_removal_service.undo()
    assert 'A1' in store.get_data_by_id('plate')['data'].columns


def test_showing_one_component_updates_bundle_visibility(monkeypatch):
    import json
    from types import SimpleNamespace
    from callbacks import file_tree_callbacks
    store = populated()
    store.visibility_state.update({'sample': False, 'tic': False, 'uv': False})
    app = dash.Dash(__name__)
    register_file_tree_callbacks(app, store)
    callback = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                    if cb['callback'].__wrapped__.__name__ == 'handle_visibility_toggles')
    monkeypatch.setattr(file_tree_callbacks, 'callback_context', SimpleNamespace(
        triggered=[{'prop_id': json.dumps({'type': 'visibility-btn', 'index': 'tic'}) + '.n_clicks', 'value': 1}]))
    _, hidden = callback([1], [{'type': 'visibility-btn', 'index': 'tic'}], 3)
    assert hidden == ['uv']


def test_removing_last_component_cleans_empty_bundle_state_and_bundle_peaks():
    store = DataStore()
    store.peak_service.clear_all_peaks()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.GENERIC, component_list=[component('tic')]))
    store.file_ui_state['sample'] = {'plot_settings': {'xmin': 4}}
    store.visibility_state['sample'] = False
    store.collapse_state['sample'] = 'expanded'
    store.peak_service._peaks['sample'] = [Peak('p1', 'sample', 'Imported', 1, 0, 2, 3, 3, 2)]
    record = store.file_removal_service.remove('tic', active_file='tic')
    assert {'sample', 'tic'} <= record.removed_ids
    assert store.get_loaded_files_list() == []
    assert 'sample' not in store.file_ui_state
    assert 'sample' not in store.visibility_state
    assert 'sample' not in store.collapse_state
    assert 'sample' not in store.peak_service._peaks
    store.file_removal_service.undo()
    assert store.file_ui_state['sample']['plot_settings']['xmin'] == 4
    assert store.peak_service._peaks['sample'][0].name == 'Imported'


def test_new_upload_after_removal_does_not_restore_removed_files_without_undo():
    from services.bundling_service import assign_bundles
    store = populated()
    store.file_removal_service.remove('sample')
    new = component('new-data')
    for bundle in assign_bundles([(new.original_filename, b'new', new.standardized)]):
        store.add_bundle(bundle)
    assert store.get_bundle('sample') is None
    assert store.get_data_by_id('tic') is None
    assert all(item['id'] != 'sample' for item in store.get_bundled_tree_items())
    assert len(store.get_loaded_files_list()) == 2
    # Only the explicit Undo action restores the removed dataset.
    store.file_removal_service.undo()
    assert store.get_data_by_id('tic') is not None
    assert len(store.get_loaded_files_list()) == 3


def channel_samples():
    from test_channel_visibility import samples
    store=samples()
    for name in ('a','b'):
        bundle=store.get_bundle(name)
        first,second=bundle.component_list
        second.original_filename=first.original_filename
        first.raw_bytes=b'original ASCII'
        first.metadata['pda']={'time_min':[0,1,2],'wavelength_nm':[250,263,280],
                               'absorbance_mau':[[0,0,0],[3,4,5],[0,0,0]]}
        first.metadata['instrument_status']={'pressure':[1,2,3]}
        second.metadata.update(pda_source_id=first.component_id,source_file_id=first.component_id)
        store.peak_service._peaks[first.component_id]=[Peak(name+'peak',first.component_id,'P',1,0,2,3,3,2)]
    return store


def test_remove_shared_channel_is_one_undo_and_preserves_sibling_edits():
    store=channel_samples()
    frames={c.component_id:c.dataframe for b in store.iter_bundles() for c in b.component_list}
    record=store.file_removal_service.remove_channels(['a','b'],'uv:250',active_file='b250')
    assert record.label=='250 nm channel from 2 samples'
    assert len(store.file_removal_service._history)==1
    assert all(store.get_data_by_id(fid) is None for fid in ('a250','b250'))
    assert all(fid not in store.peak_service._peaks for fid in ('a250','b250'))
    store.get_bundle('a').component_list[0].metadata['display_name']='Edited surviving channel'
    store.file_removal_service.undo()
    assert not store.file_removal_service.can_undo
    assert store.get_bundle('a').component_list[1].metadata['display_name']=='Edited surviving channel'
    for fid,frame in frames.items():
        assert store.get_data_by_id(fid)['data'] is frame
    assert store.peak_service._peaks['b250'][0].peak_id=='bpeak'


def test_remove_pda_owner_keeps_original_payload_and_extraction_then_undo():
    from services.pda_service import resolve_pda_source,add_pda_chromatogram
    store=channel_samples()
    owner=store.get_bundle('a').component_list[0]
    matrix=owner.metadata['pda']
    raw=owner.raw_bytes
    store.file_removal_service.remove_channels(['a'],'uv:250')
    source,payload=resolve_pda_source(store,'a263')
    assert source=='a263' and payload is matrix
    assert store.get_bundle('a').primary.raw_bytes is raw
    assert store.get_bundle('a').primary.metadata['instrument_status'] is owner.metadata['instrument_status']
    added=add_pda_chromatogram(store,'a263',280)
    store.get_bundle('a').component_list[0].metadata['user_note']='keep this'
    store.file_removal_service.undo()
    assert resolve_pda_source(store,added)==('a250',matrix)
    assert resolve_pda_source(store,'a263')==('a250',matrix)
    assert store.get_data_by_id(added) is not None
    siblings=store.get_bundle('a').component_list
    assert siblings[1].metadata['user_note']=='keep this'
    assert siblings[0].raw_bytes is raw
    assert not siblings[1].raw_bytes
    assert 'pda' not in siblings[1].metadata


def test_remove_channel_ignores_unrelated_groups_and_can_remove_final_signal():
    store=channel_samples()
    assert store.file_removal_service.remove_channels(['a'],'uv:999') is None
    assert not store.file_removal_service.can_undo
    store.file_removal_service.remove_channels(['a'],'uv:263')
    assert store.get_data_by_id('b263') is not None
    store.file_removal_service.remove_channels(['a'],'uv:250')
    assert store.get_bundle('a') is None
    store.file_removal_service.undo()
    assert store.get_data_by_id('a250') is not None
    assert store.get_data_by_id('a263') is None


def test_removing_one_lcms_channel_keeps_remaining_peak_owner_and_render_source_stable():
    from test_channel_visibility import signal
    from services.data_store import ComponentRole,SourceCategory
    store=DataStore()
    pos=signal('pos',role=ComponentRole.MS_POSITIVE,category=SourceCategory.LCMS_MS)
    uv=signal('uv',280,role=ComponentRole.VWD_A,category=SourceCategory.LCMS_UV)
    store.add_bundle(Bundle('run','Run',BundleType.LCMS,component_list=[pos,uv]))
    peak=Peak('keep','uv','P',1,0,2,3,3,2)
    store.peak_service._peaks['uv']=[peak]
    store.file_removal_service.remove_channels(['run'],'ms:positive')
    assert store.peak_owner_id('uv')=='uv'
    assert list(store.loaded_data)==['uv']
    assert store.peak_service.get_peaks(store.peak_owner_id('uv'))==[peak]
    store.file_removal_service.undo()
    assert list(store.loaded_data)==['pos','uv']
