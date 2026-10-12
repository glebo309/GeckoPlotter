"""Dragging files into custom tree groups moves them to their own figure tab."""
import dash
import pandas as pd

from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult
from callbacks import file_tree_callbacks, viz_callbacks
from callbacks.viz_callbacks import _collect_visible_files, _get_active_file_group, _tab_id_from_group
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore


def chrom_bundle(bid):
    data = pd.DataFrame({'Time (min)': [0., 1., 2.], 'Signal': [1., 3., 1.]})
    result = StandardizedResult(
        data=data, column_roles={'Time (min)': ColumnRole.X, 'Signal': ColumnRole.Y},
        identity=FileIdentity(f'{bid}.txt', 'chromatogram', 'heuristic', 3),
        plot_hint=PlotHint.LINE, source_category=SourceCategory.CHROMATOGRAM)
    comp = Component(f'{bid}-uv', ComponentRole.PRIMARY, f'{bid}.txt', dataframe=data,
                     column_roles=result.column_roles, standardized=result,
                     source_category=SourceCategory.CHROMATOGRAM)
    return Bundle(bid, bid, BundleType.CHROMATOGRAM, component_list=[comp])


def setup():
    store = DataStore()
    for bid in ('a', 'b', 'c'):
        store.add_bundle(chrom_bundle(bid))
    app = dash.Dash(__name__)
    viz_callbacks.register_viz_callbacks(app, store)
    file_tree_callbacks.register_file_tree_callbacks(app, store)
    cbs = {cb['callback'].__wrapped__.__name__: cb['callback'].__wrapped__
           for cb in app.callback_map.values() if 'callback' in cb}
    return store, cbs


def sync(cbs, store, tabs, active_tab, active_file):
    result = cbs['sync_plot_tabs'](store.get_loaded_files_list(), tabs, active_tab, active_file)
    new_tabs = tabs if result[0] is dash.no_update else result[0]
    new_active = active_tab if result[1] is dash.no_update else result[1]
    return new_tabs, new_active


def drawn(store, tab):
    visible = _collect_visible_files(store, None, store.get_loaded_files_list(),
                                     target_group_override=tuple(tab['group_key']))
    return sorted(fd['record']['id'] for files in visible.values() for _, fd in files)


def move(cbs, file_id, target):
    cbs['handle_group_move']({'file_id': file_id, 'source_group': 'x', 'target_group': target},
                             [], 0)


def test_group_move_creates_new_active_tab_and_file_leaves_old_figure():
    store, cbs = setup()
    tabs, active = sync(cbs, store, [], None, 'a-uv')
    assert len(tabs) == 1
    old_tab = tabs[0]
    assert drawn(store, old_tab) == ['a-uv', 'b-uv', 'c-uv']

    move(cbs, 'b', None)                              # drop outside = new custom group
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    assert len(tabs) == 2
    new_tab = next(t for t in tabs if t['id'] != old_tab['id'])
    assert active == new_tab['id']
    assert drawn(store, new_tab) == ['b-uv']
    assert drawn(store, old_tab) == ['a-uv', 'c-uv']
    assert _get_active_file_group(store, 'b') == tuple(new_tab['group_key'])
    assert _get_active_file_group(store, 'b-uv') == tuple(new_tab['group_key'])


def test_moving_back_removes_empty_tab_and_restores_original_figure():
    store, cbs = setup()
    tabs, active = sync(cbs, store, [], None, 'a-uv')
    old_tab = tabs[0]
    move(cbs, 'b', None)
    tabs, active = sync(cbs, store, tabs, active, 'b-uv')
    assert active != old_tab['id']

    move(cbs, 'b', old_tab['id'])
    assert 'b' not in store.group_overrides          # natural group again
    tabs, active = sync(cbs, store, tabs, active, 'b-uv')
    assert [t['id'] for t in tabs] == [old_tab['id']]
    assert active == old_tab['id']
    assert drawn(store, tabs[0]) == ['a-uv', 'b-uv', 'c-uv']


def test_move_between_custom_groups_keeps_both_figures_consistent():
    store, cbs = setup()
    tabs, active = sync(cbs, store, [], None, 'a-uv')
    move(cbs, 'b', None)
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    custom = next(t for t in tabs if t['group_key'][0].startswith('custom_'))
    move(cbs, 'c', custom['id'])
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    assert len(tabs) == 2
    assert drawn(store, custom) == ['b-uv', 'c-uv']
    other = next(t for t in tabs if t['id'] != custom['id'])
    assert drawn(store, other) == ['a-uv']
    # Emptying the original figure drops it; the remaining custom tab is active.
    move(cbs, 'a', custom['id'])
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    assert [t['id'] for t in tabs] == [custom['id']]
    assert active == custom['id']
    assert drawn(store, tabs[0]) == ['a-uv', 'b-uv', 'c-uv']


def test_regrouping_keeps_visibility_and_peaks():
    from services.peak_service import Peak
    store, cbs = setup()
    store.visibility_state['b-uv'] = False
    store.peak_service._peaks['b-uv'] = [Peak('p1', 'b-uv', 'Peak 1', 1, 0, 2, 3, 3, 2)]
    tabs, active = sync(cbs, store, [], None, 'b-uv')
    move(cbs, 'b', None)
    tabs, active = sync(cbs, store, tabs, active, 'b-uv')
    assert store.visibility_state['b-uv'] is False
    assert store.peak_service._peaks['b-uv'][0].peak_id == 'p1'
    assert _get_active_file_group(store, 'b-uv') == tuple(
        next(t for t in tabs if t['id'] == active)['group_key'])
