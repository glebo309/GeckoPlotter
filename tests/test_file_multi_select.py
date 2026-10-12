"""Eye and trash buttons act on every row of the Cmd/Shift-click multi-selection."""
import json
from pathlib import Path
from types import SimpleNamespace

import dash

from callbacks import file_tree_callbacks
from callbacks.file_tree_callbacks import _bulk_targets, register_file_tree_callbacks
from services.data_store import Bundle, BundleType, DataStore
from test_file_controls import component


def three_file_store():
    store = DataStore()
    for name in ('one', 'two', 'three'):
        store.add_bundle(Bundle(name, name.title(), BundleType.GENERIC,
                                component_list=[component(f'{name}-data')]))
    store.visibility_state.clear()
    return store


def callbacks_for(store):
    app = dash.Dash(__name__)
    register_file_tree_callbacks(app, store)
    return {cb['callback'].__wrapped__.__name__: cb['callback'].__wrapped__
            for cb in app.callback_map.values()}


def trigger(monkeypatch, kind, file_id):
    prop = json.dumps({'type': kind, 'index': file_id}) + '.n_clicks'
    monkeypatch.setattr(file_tree_callbacks, 'callback_context',
                        SimpleNamespace(triggered=[{'prop_id': prop, 'value': 1}]))


def test_bulk_targets_only_expand_when_clicked_row_is_in_a_multi_selection():
    assert _bulk_targets('a', ['a', 'b']) == ['a', 'b']
    assert _bulk_targets('c', ['a', 'b']) == ['c']      # clicked row outside the selection
    assert _bulk_targets('a', ['a']) == ['a']           # plain single selection
    assert _bulk_targets('a', None) == ['a']
    assert _bulk_targets('a', [None, 3, 'a', 'b']) == ['a', 'b']


def test_eye_on_a_selected_row_hides_every_selected_row(monkeypatch):
    store = three_file_store()
    toggle = callbacks_for(store)['handle_visibility_toggles']
    trigger(monkeypatch, 'visibility-btn', 'one')
    ids = [{'type': 'visibility-btn', 'index': k} for k in ('one', 'two', 'three')]
    counter, hidden = toggle([1, 0, 0], ids, 4, ['one', 'three'])
    assert counter == 5
    assert {'one', 'one-data', 'three', 'three-data'} <= set(hidden)
    assert not {'two', 'two-data'} & set(hidden)
    # Clicking again shows them all again, using the clicked row's state.
    _, hidden = toggle([2, 0, 0], ids, 5, ['one', 'three'])
    assert hidden == []


def test_eye_on_an_unselected_row_ignores_the_selection(monkeypatch):
    store = three_file_store()
    toggle = callbacks_for(store)['handle_visibility_toggles']
    trigger(monkeypatch, 'visibility-btn', 'two')
    _, hidden = toggle([0, 1, 0], [{'type': 'visibility-btn', 'index': 'two'}], 1, ['one', 'three'])
    assert {'two', 'two-data'} <= set(hidden)
    assert not {'one', 'three'} & set(hidden)


def test_eye_without_selection_behaves_as_before(monkeypatch):
    store = three_file_store()
    toggle = callbacks_for(store)['handle_visibility_toggles']
    trigger(monkeypatch, 'visibility-btn', 'one')
    _, hidden = toggle([1], [{'type': 'visibility-btn', 'index': 'one'}], 0)
    assert {'one', 'one-data'} <= set(hidden) and 'two' not in hidden


def test_trash_on_a_selected_row_removes_all_selected_rows_as_one_undo(monkeypatch):
    store = three_file_store()
    cbs = callbacks_for(store)
    trigger(monkeypatch, 'delete-btn', 'two')
    result = cbs['handle_file_deletion']([0, 1, 0], store.get_loaded_files_list(), None, 1, ['one', 'two'])
    assert list(store.all_bundles()) == ['three']
    assert 'One' not in result[9] and '2 items' in result[9]
    assert result[10] is False
    restored = cbs['undo_file_removal'](1, 2)
    assert list(store.all_bundles()) == ['one', 'two', 'three']
    assert '2 items' in restored[9]
    assert store.file_removal_service.can_undo is False


def test_trash_on_an_unselected_row_removes_only_that_row(monkeypatch):
    store = three_file_store()
    cbs = callbacks_for(store)
    trigger(monkeypatch, 'delete-btn', 'three')
    cbs['handle_file_deletion']([0, 0, 1], store.get_loaded_files_list(), None, 1, ['one', 'two'])
    assert list(store.all_bundles()) == ['one', 'two']
    store.file_removal_service.undo()
    assert list(store.all_bundles()) == ['one', 'two', 'three']


def test_multi_selection_store_is_in_the_layout_and_read_as_state():
    # Importing app.py pulls in the whole UI; the store declaration is checked in source.
    source = (Path(__file__).resolve().parents[1] / 'app.py').read_text()
    assert "dcc.Store(id='file-multi-selection'" in source
    for name in ('handle_visibility_toggles', 'handle_file_deletion'):
        store = DataStore()
        a = dash.Dash(__name__)
        register_file_tree_callbacks(a, store)
        entry = next(cb for cb in a.callback_map.values() if cb['callback'].__wrapped__.__name__ == name)
        assert any(s['id'] == 'file-multi-selection' for s in entry['state'])
