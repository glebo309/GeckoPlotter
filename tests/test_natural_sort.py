"""Samples sort by the value of their numbers, in the file tree and in the stacked plot alike."""
from services.natural_sort import natural_key


def test_concentrations_sort_by_value_not_as_text():
    names = ['l-alanine 10mM', 'blank', 'l-alanine 2.5mM', 'l-alanine 0.31.mM', 'l-alanine 1.25mM', 'CONTROL 4', '4']
    assert sorted(names, key=natural_key) == ['4', 'blank', 'CONTROL 4', 'l-alanine 0.31.mM', 'l-alanine 1.25mM',
                                               'l-alanine 2.5mM', 'l-alanine 10mM']


def test_the_plot_stacks_samples_in_the_trees_dragged_order():
    from services.data_store import Bundle, BundleType
    from callbacks.viz_callbacks import _collect_visible_files, _get_active_file_group, _tab_id_from_group
    from test_channel_visibility import signal
    from services.data_store import DataStore
    store = DataStore()
    for name in ('a 1mM', 'b 2mM', 'c 3mM'):
        store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM, component_list=[signal(name + '-uv', 250)]))
    group = _get_active_file_group(store, 'a 1mM-uv')
    tab = _tab_id_from_group(group)
    order = {tab: {'order': ['c 3mM', 'a 1mM', 'b 2mM']}}       # dragged in the tree: sample (bundle) ids
    files = _collect_visible_files(store, 'a 1mM-uv', store.get_loaded_files_list(), file_order=order)[group]
    assert [name.split(' · ')[0] for name, _ in files] == ['c 3mM', 'a 1mM', 'b 2mM']
