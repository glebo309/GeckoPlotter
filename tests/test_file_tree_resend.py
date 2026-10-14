"""The file tree is not sent again when the browser already shows the same tree."""
import json
from types import SimpleNamespace

import dash
from dash import html
from dash.exceptions import PreventUpdate
from plotly.utils import PlotlyJSONEncoder

import callbacks.file_tree_callbacks as file_tree
import callbacks.upload_callbacks as upload


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


def as_shown(tree):
    return json.loads(json.dumps(tree, cls=PlotlyJSONEncoder))


def test_same_tree_compares_with_what_the_browser_sends_back():
    tree = [html.Div([html.Button('x', id={'type': 'file-tree-item', 'index': 'a'}, n_clicks=0)], className='g')]
    shown = as_shown(tree)
    assert file_tree.same_tree(tree, shown)
    shown[0]['props']['children'][0]['props']['n_clicks'] = 1
    assert not file_tree.same_tree(tree, shown)


def test_unchanged_tree_is_not_sent_again(monkeypatch):
    calls = []

    def render(records, dm, active, active_plot_tab=None, file_order=None):
        calls.append(active_plot_tab)
        return [html.Div(f'{active}:{active_plot_tab}')]

    monkeypatch.setattr(upload, 'render_file_tree_with_bundles_selected', render)
    app = App()
    file_tree.register_file_tree_callbacks(app, SimpleNamespace(collapse_state={}, group_overrides={}))
    sync = app.functions['sync_file_tree_selection']
    monkeypatch.setattr(dash, 'callback_context', SimpleNamespace(triggered=[{'prop_id': 'active-plot-tab.data'}]))
    shown = as_shown([html.Div('f:tab')])
    try:
        sync([{'id': 'f'}], 'tab', {}, 'f', shown)
        raise AssertionError('the same tree was sent again')
    except PreventUpdate:
        pass
    assert sync([{'id': 'f'}], 'other', {}, 'f', shown)[0].children == 'f:other'
    assert sync([{'id': 'f'}], 'tab', {}, 'f', None)[0].children == 'f:tab'
