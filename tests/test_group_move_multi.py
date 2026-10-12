"""Multi-file drag: one group-move-event carrying `file_ids` moves every file."""
from test_group_move_figures import setup, sync, drawn


def test_multi_file_new_figure_shares_one_group():
    store, cbs = setup()
    tabs, active = sync(cbs, store, [], None, 'a-uv')
    old_tab = tabs[0]
    cbs['handle_group_move']({'file_id': 'b', 'file_ids': ['b', 'c'], 'source_group': 'x',
                              'target_group': None}, [], 0)
    assert store.group_overrides['b'] == store.group_overrides['c']
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    assert len(tabs) == 2
    new_tab = next(t for t in tabs if t['id'] != old_tab['id'])
    assert drawn(store, new_tab) == ['b-uv', 'c-uv']
    assert drawn(store, old_tab) == ['a-uv']


def test_multi_file_move_into_existing_group_and_legacy_payload():
    store, cbs = setup()
    tabs, active = sync(cbs, store, [], None, 'a-uv')
    old_tab = tabs[0]
    cbs['handle_group_move']({'file_id': 'a', 'source_group': 'x', 'target_group': None}, [], 0)
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    custom = next(t for t in tabs if t['id'] != old_tab['id'])
    cbs['handle_group_move']({'file_id': 'b', 'file_ids': ['b', 'c'], 'source_group': old_tab['id'],
                              'target_group': custom['id']}, [], 0)
    tabs, active = sync(cbs, store, tabs, active, 'a-uv')
    assert drawn(store, custom) == ['a-uv', 'b-uv', 'c-uv']
