"""The Data table stays on the server: the browser gets a reference and one page, edits land on the full table."""
import json
from types import SimpleNamespace

import dash
import pandas as pd

import callbacks.publication_callbacks as publication
from components.data_table_editor import create_data_table_editor
from components.workspace_layout import walk
from services import table_store


def big(rows=24001):
    return pd.DataFrame({'_row_id': range(rows), 'Time': [i * 0.025 for i in range(rows)],
                         'Signal': [float(i % 97) for i in range(rows)]})


def test_reference_is_small_and_gives_back_the_full_table():
    df = big()
    ref = table_store.remember(df)
    assert len(json.dumps(ref)) < 200
    assert ref['rows'] == 24001 and ref['columns'] == ['_row_id', 'Time', 'Signal']
    back = table_store.frame(ref)
    pd.testing.assert_frame_equal(back, df)
    back.loc[0, 'Signal'] = -1.0                       # a copy: readers cannot change the stored table
    assert table_store.frame(ref).loc[0, 'Signal'] == 0.0


def test_frame_still_reads_split_json_and_unknown_references_are_empty():
    df = pd.DataFrame({'_row_id': [0, 1], 'Area': [1.5, 2.5]})
    assert table_store.frame(df.to_json(orient='split'))['Area'].tolist() == [1.5, 2.5]
    assert table_store.frame({'table_ref': 'gone'}) is None
    assert table_store.frame(None) is None
    assert json.loads(table_store.as_json(table_store.remember(df)))['data'] == [[0, 1.5], [1, 2.5]]


def test_page_is_one_page_of_the_sorted_table_and_clamped():
    ref = table_store.remember(big(120))
    rows, count, current = table_store.page(ref, 1, 50)
    assert (len(rows), count, current) == (50, 3, 1)
    assert rows[0]['_row_id'] == 50
    rows, _, current = table_store.page(ref, 9, 50)
    assert current == 2 and len(rows) == 20
    rows, _, _ = table_store.page(ref, 0, 50, [{'column_id': 'Time', 'direction': 'desc'}])
    assert rows[0]['_row_id'] == 119


def test_page_edits_change_only_those_cells_of_the_full_table():
    ref = table_store.remember(big(120))
    previous, _, _ = table_store.page(ref, 1, 50)
    edited = [dict(row) for row in previous]
    edited[3]['Signal'] = '7.5'
    new = table_store.apply_page_edits(ref, edited, previous)
    df = table_store.frame(new)
    assert len(df) == 120
    assert df.loc[df['_row_id'] == 53, 'Signal'].item() == 7.5
    assert df['Signal'].drop(index=53).equals(table_store.frame(ref)['Signal'].drop(index=53))


def test_deleted_rows_leave_the_rest_of_the_table_and_a_new_page_is_not_an_edit():
    ref = table_store.remember(big(120))
    previous, _, _ = table_store.page(ref, 0, 50)
    new = table_store.apply_page_edits(ref, previous[:10] + previous[11:], previous)
    df = table_store.frame(new)
    assert len(df) == 119 and 10 not in set(df['_row_id'])
    other_page, _, _ = table_store.page(ref, 1, 50)
    assert table_store.apply_page_edits(ref, other_page, previous) is None
    assert table_store.apply_page_edits(ref, previous, previous) is None


def test_deleted_column_is_removed_from_the_full_table():
    ref = table_store.remember(big(10))
    new = table_store.drop_columns(ref, ['_row_id', 'Time'])
    assert list(table_store.frame(new).columns) == ['_row_id', 'Time']
    assert table_store.drop_columns(ref, ['_row_id', 'Time', 'Signal']) is None


def test_editor_sends_no_rows_and_pages_on_the_server():
    df = big()
    editor = create_data_table_editor(df, table_id='pub-table')
    nodes = {getattr(n, 'id', None): n for n in walk(editor)}
    table = nodes['pub-table']
    assert table.data == [] and table.page_action == 'custom' and table.sort_action == 'custom'
    assert table.page_count == 481
    assert table_store.frame(nodes['pub-table-source'].data)['_row_id'].tolist() == df['_row_id'].tolist()
    assert len(json.dumps(editor.to_plotly_json(), default=str)) < 20000


class App:
    def __init__(self):
        self.functions = {}

    def callback(self, *args, **kwargs):
        def register(f):
            self.functions[f.__name__] = f
            return f
        return register

    def clientside_callback(self, *args, **kwargs):
        pass


def callbacks(monkeypatch, *triggers):
    app = App()
    publication.register_publication_callbacks(app, SimpleNamespace())
    monkeypatch.setattr(publication, 'callback_context',
                        SimpleNamespace(triggered=[{'prop_id': t, 'value': 1} for t in triggers]))
    return app.functions


def test_data_tab_closed_sends_nothing_and_open_sends_one_page(monkeypatch):
    ref = table_store.remember(big())
    f = callbacks(monkeypatch, 'pub-table-source.data')
    assert f['serve_table_page'](ref, 'peak-analysis', 0, [], None, None, [], None, 50, 'peak-analysis') \
        == (dash.no_update,) * 5
    f = callbacks(monkeypatch, 'analysis-tabs.value')
    rows, count, current, source, store = f['serve_table_page'](ref, 'data-overview', 0, [], None, None,
                                                                [], None, 50, 'data-overview')
    assert len(rows) == 50 and count == 481
    assert source is dash.no_update and store is dash.no_update


def test_cell_edit_on_a_page_updates_the_full_table_and_the_plot_data(monkeypatch):
    ref = table_store.remember(big())
    previous, _, _ = table_store.page(ref, 2, 50)
    rows = [dict(row) for row in previous]
    rows[0]['Signal'] = '123'
    f = callbacks(monkeypatch, 'pub-table.data_timestamp')
    data, count, current, source, store = f['serve_table_page'](ref, 'data-overview', 2, [], 1, None,
                                                                rows, previous, 50, 'data-overview')
    assert data is dash.no_update                      # the page already shows it
    assert source == store
    df = table_store.frame(source)
    assert len(df) == 24001 and df.loc[df['_row_id'] == 100, 'Signal'].item() == 123.0


def test_add_row_extends_the_full_table_and_shows_the_last_page(monkeypatch):
    ref = table_store.remember(big())
    f = callbacks(monkeypatch, 'add-row.n_clicks')
    source, store, page = f['add_new_row'](1, ref, 50)
    df = table_store.frame(source)
    assert len(df) == 24002 and df['_row_id'].iloc[-1] == 24001
    assert store == source and page == 480


def test_column_selection_maps_every_filled_row_of_the_full_table(monkeypatch):
    df = big(200)
    df.loc[5, 'Signal'] = None
    ref = table_store.remember(df)
    page, _, _ = table_store.page(ref, 0, 50)
    f = callbacks(monkeypatch, 'pub-table.selected_columns')
    from components.axis_mapper import get_empty_selections
    selections, data = f['update_selections'](None, ['Signal'], None, False, None, page, [], ref,
                                              ['y1', 'data', 0], get_empty_selections(), 1, 'file', 'data-overview')
    ids = selections['y1']['series'][0]['row_ids']
    assert len(ids) == 199 and 5 not in ids
    assert data == ref


def test_cell_click_maps_the_row_of_the_shown_page(monkeypatch):
    ref = table_store.remember(big(200))
    page, _, _ = table_store.page(ref, 3, 50)
    f = callbacks(monkeypatch, 'pub-table.active_cell')
    from components.axis_mapper import get_empty_selections
    selections, _ = f['update_selections'](None, None, {'row': 2, 'column_id': 'Time'}, False, None, page, [], ref,
                                           ['x', 'data'], get_empty_selections(), 1, 'file', 'data-overview')
    assert selections['x']['data'] == {'row_ids': [152], 'column_id': 'Time'}
