from services.figure_actions import publication_snapshot
import dash
import pytest


def test_actual_figure_menu_buttons_have_a_dash_click_callback():
    from callbacks.figure_actions_callbacks import register_figure_actions_callbacks
    app = dash.Dash(__name__)
    register_figure_actions_callbacks(app)
    assert any('figure-action' in inp['id'] and inp['property'] == 'n_clicks'
               for entry in app.callback_map.values() for inp in entry['inputs'])


@pytest.mark.parametrize('layout_mode,domains', [
    ('overlay', ([0, 1], [0, 1])),
    ('stacked', ([0.55, 1], [0, 0.45])),
])
def test_send_to_publication_preserves_layout_and_axis_assignments(layout_mode, domains):
    from callbacks.figure_actions_callbacks import register_figure_actions_callbacks
    from callbacks.plot_settings_callbacks import register_plot_settings_callbacks
    from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
    from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore

    store = DataStore()
    store._shared_plot_settings = {}
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=[
        Component('tic', ComponentRole.MS_POSITIVE, 'tic.csv'),
        Component('uv', ComponentRole.VWD_A, 'uv.csv'),
    ]))
    app = dash.Dash(__name__)
    register_figure_actions_callbacks(app)
    register_plot_settings_callbacks(app, store)
    register_publication_preview_callbacks(app, store)
    send = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                if cb['inputs'] == [{'id': 'figure-action-event', 'property': 'data'}])
    hydrate = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                   if cb.get('callback') and cb['callback'].__wrapped__.__name__ == 'hydrate_plot_settings')
    preview = app.callback_map['pub-preview-graph.data']['callback'].__wrapped__
    figure = {'data': [{'x': [0, 1], 'y': [0, 5e6], 'name': 'TIC', 'yaxis': 'y'},
                       {'x': [0, 1], 'y': [0, 250], 'name': 'UV', 'yaxis': 'y2'}],
              'layout': {'xaxis': {'range': [0.25, 1]},
                         'yaxis': {'domain': domains[0], 'title': {'text': 'Ion Count'}},
                         'yaxis2': {'domain': domains[1], 'title': {'text': 'Absorbance (mAU)'},
                                    **({'overlaying': 'y', 'side': 'right'} if layout_mode == 'overlay' else {})}}}
    settings = {'layout_mode': layout_mode, 'line_width': 3}
    tabs, tab_id, figures, _, status = send({'action': 'publication', 'figure': figure},
                                  [{'id': 'lcms', 'type': 'raw'}], {}, settings)
    assert 'created' in status
    loaded = hydrate('shared:raw:' + tab_id, 'tic', tab_id, figures)[0]
    assert loaded['layout_mode'] == layout_mode
    assert loaded['line_width'] == 3
    result = preview(tab_id, loaded, 'two-col', 0, 'tic', 1, 1, True, 0, [],
                     tabs, {}, ['peaks'], figures)
    assert list(result.layout.yaxis.domain) == domains[0]
    assert list(result.layout.yaxis2.domain) == domains[1]
    assert result.layout.yaxis2.overlaying == ('y' if layout_mode == 'overlay' else None)
    assert [trace.yaxis for trace in result.data] == ['y', 'y2']
    assert list(result.layout.xaxis.range) == [0.25, 1]


def test_publication_snapshot_keeps_the_clicked_figure_and_leaves_source_untouched():
    figure = {'data':[{'x':[100,200],'y':[30,100]}],
              'layout':{'xaxis':{'title':{'text':'m/z'},'range':[100,200]}}}
    tabs = [{'id':'lcms','label':'LC-MS','type':'raw'}]
    next_tabs, active, figures = publication_snapshot(figure,tabs,{},'Peak Mass')
    assert next_tabs[-1]['type'] == 'publication'
    assert figures[active]['figure'] == figure
    figures[active]['figure']['data'][0]['y'][0] = 0
    assert figure['data'][0]['y'][0] == 30
    assert len(tabs) == 1


def test_publication_preview_keeps_spectrum_axis_units():
    import dash
    from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
    from services.data_store import DataStore
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    callback = app.callback_map['pub-preview-graph.data']['callback'].__wrapped__
    figure = {'data':[{'x':[100,200],'y':[30,100]}],
              'layout':{'xaxis':{'title':{'text':'m/z'}},
                        'yaxis':{'title':{'text':'Relative Intensity (%)'}}}}
    result = callback('publication-1',{},'two-col',0,None,1,1,True,0,[],
        [{'id':'publication-1','type':'publication'}],{},['peaks'],
        {'publication-1':{'figure':figure}})
    assert result.layout.xaxis.title.text == 'm/z'
    assert result.layout.yaxis.title.text == 'Relative Intensity (%)'


def test_publication_preview_respects_unlinked_x_axes():
    import dash
    from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
    from services.data_store import DataStore
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    callback = app.callback_map['pub-preview-graph.data']['callback'].__wrapped__
    figure = {'data': [{'x': [0, 1], 'y': [1, 2]},
                       {'x': [0, 1], 'y': [3, 4], 'xaxis': 'x2', 'yaxis': 'y2'}],
              'layout': {'xaxis': {'range': [0, 1]}, 'xaxis2': {'matches': 'x'},
                         'yaxis': {}, 'yaxis2': {}}}
    result = callback('publication-1', {}, 'two-col', 0, None, 1, 1, False, 0, [],
                      [{'id': 'publication-1', 'type': 'publication'}], {}, ['peaks'],
                      {'publication-1': {'figure': figure}})
    assert result.layout.xaxis2.matches is None
