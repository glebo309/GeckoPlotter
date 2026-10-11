from test_file_controls import component
from test_render_tab_performance import App
from services.data_store import DataStore, Bundle, BundleType, ComponentRole
from callbacks.viz_callbacks import (
    _get_active_file_group, _collect_visible_files, _tab_id_from_group,
    register_viz_callbacks,
)


def two_runs():
    store = DataStore()
    for run in ('run-a', 'run-b'):
        store.add_bundle(Bundle(run, run.upper(), BundleType.LCMS, component_list=[
            component(run + '-tic', ComponentRole.MS_POSITIVE),
            component(run + '-uv', ComponentRole.VWD_A),
        ]))
    return store


def test_identical_time_ranges_do_not_merge_lcms_runs():
    store = two_runs()
    a = _get_active_file_group(store, 'run-a-tic')
    b = _get_active_file_group(store, 'run-b-tic')
    assert a != b
    assert _get_active_file_group(store, 'run-a-uv') == a
    assert _get_active_file_group(store, 'run-a') == a
    assert _tab_id_from_group(a) != _tab_id_from_group(b)


def test_only_selected_bundle_is_rendered_and_visibility_is_preserved():
    store = two_runs()
    loaded = store.get_loaded_files_list()
    store.visibility_state['run-a-uv'] = False
    for source, expected in [('run-a-tic', {'run-a-tic'}),
                             ('run-b-uv', {'run-b-tic', 'run-b-uv'}),
                             ('run-a', {'run-a-tic'})]:
        groups = _collect_visible_files(store, source, loaded)
        assert {entry['record']['id'] for files in groups.values() for _, entry in files} == expected


def test_bundle_tabs_are_named_and_cached_group_remains_isolated():
    store = two_runs()
    app = App()
    register_viz_callbacks(app, store)
    tabs, active = app.functions['sync_plot_tabs'](store.get_loaded_files_list(), [], None, 'run-b-tic')
    assert len(tabs) == 2
    assert {tab['label'] for tab in tabs} == {'RUN-A', 'RUN-B'}
    assert active == _tab_id_from_group(_get_active_file_group(store, 'run-b-tic'))
    a = _get_active_file_group(store, 'run-a-tic')
    groups = _collect_visible_files(store, 'run-b-tic', store.get_loaded_files_list(), target_group_override=a)
    assert {entry['record']['id'] for files in groups.values() for _, entry in files} == {'run-a-tic', 'run-a-uv'}


def test_explicit_comparison_override_still_groups_chosen_signals():
    store = two_runs()
    comparison = ('lcms_ms', 'time', 'comparison')
    store.group_overrides = {'run-a-tic': comparison, 'run-b-tic': comparison}
    groups = _collect_visible_files(store, 'run-a-tic', store.get_loaded_files_list())
    assert {entry['record']['id'] for files in groups.values() for _, entry in files} == {'run-a-tic', 'run-b-tic'}
