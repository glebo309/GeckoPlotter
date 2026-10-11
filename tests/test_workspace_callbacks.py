import dash
from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
from services.data_store import DataStore


def test_publication_switch_controls_workspace_visibility_not_callback_graph():
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    entry = next(cb for cb in app.callback_map.values()
                 if any(output.component_id == 'pub-preview-wrapper'
                        for output in (cb['output'] if isinstance(cb['output'], list) else [cb['output']])))
    assert any(output.component_id == 'plot-workspace' for output in entry['output'])
    callback = entry['callback'].__wrapped__
    preview, workspace = callback('raw', [{'id':'raw','type':'raw'}])
    assert preview['display'] == 'none'
    assert workspace.get('display') != 'none'
