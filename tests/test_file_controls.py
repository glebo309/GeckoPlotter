import json
import sys
from types import SimpleNamespace

import dash
import pandas as pd
import pytest

from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from callbacks import file_tree_callbacks
from services.plot_manager import PlotManager
from services.plot_settings_service import PlotSettingsService


def component(cid, role=ComponentRole.PRIMARY):
    data = pd.DataFrame({'time': [0., 1., 2.], 'signal': [1., 3., 1.]})
    result = StandardizedResult(
        data=data, column_roles={'time': ColumnRole.X, 'signal': ColumnRole.Y},
        identity=FileIdentity(f'{cid}.csv', 'csv', 'heuristic', 3),
        plot_hint=PlotHint.LINE, source_category=SourceCategory.GENERIC,
    )
    return Component(cid, role, f'{cid}.csv', dataframe=data,
                     column_roles=result.column_roles, standardized=result)


def delete_callback(store, monkeypatch, file_id, active):
    app = dash.Dash(__name__)
    file_tree_callbacks.register_file_tree_callbacks(app, store)
    callback = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                    if any('delete-btn' in inp['id'] for inp in cb['inputs']))
    monkeypatch.setattr(file_tree_callbacks, 'callback_context', SimpleNamespace(
        triggered=[{'prop_id': json.dumps({'type': 'delete-btn', 'index': file_id}) + '.n_clicks',
                    'value': 1}]))
    return callback([1], store.get_loaded_files_list(), active, 4)


@pytest.mark.parametrize('bundle_type', [BundleType.LCMS, BundleType.CHROMELEON, BundleType.GENERIC])
def test_delete_bundle_removes_all_components_and_selects_remaining_file(monkeypatch, bundle_type):
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', bundle_type,
                            component_list=[component('tic'), component('uv', ComponentRole.VWD_A)]))
    store.add_bundle(Bundle('other', 'Other', BundleType.GENERIC,
                            component_list=[component('other-data')]))
    result = delete_callback(store, monkeypatch, 'sample', 'tic')
    assert [r['id'] for r in result[0]] == ['other']
    assert result[3] == 'other-data'
    assert store.get_data_by_id('tic') is None
    assert store.get_data_by_id('uv') is None


def test_delete_component_keeps_siblings_and_reselects_primary(monkeypatch):
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS,
                            component_list=[component('tic'), component('uv', ComponentRole.VWD_A)]))
    result = delete_callback(store, monkeypatch, 'tic', 'tic')
    assert store.get_data_by_id('tic') is None
    assert store.get_data_by_id('uv') is not None
    assert store.get_bundle('sample').primary.component_id == 'uv'
    assert result[3] == 'uv'
    assert result[2] == 5


def test_delete_last_component_removes_empty_bundle(monkeypatch):
    store = DataStore()
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=[component('tic')]))
    result = delete_callback(store, monkeypatch, 'tic', 'tic')
    assert result[0] == []
    assert result[3] is None
    assert store.get_bundle('sample') is None


@pytest.mark.parametrize('mode', ['stacked', 'grouped'])
@pytest.mark.parametrize('position', ['top-right', 'bottom-left'])
def test_legends_stay_inside_their_subplots_after_styling(mode, position, monkeypatch):
    import src.ingestion.types as ingestion_types
    monkeypatch.setitem(sys.modules, 'ingestion.types', ingestion_types)
    files = [(f'Trace {i}', {'standardized': c.standardized, 'data': c.dataframe})
             for i in range(4) for c in [component(str(i))]]
    groups = {'one': files} if mode == 'stacked' else {str(i): [f] for i, f in enumerate(files)}
    figure = PlotManager().create_multi_file_plot(groups, 'stacked', subplot_spacing=0.12)
    PlotSettingsService.apply_to_figure(figure, PlotSettingsService.from_dict({'legend_pos': position}))
    for i in range(1, 5):
        suffix = '' if i == 1 else str(i)
        legend = figure.layout['legend' + suffix]
        low, high = figure.layout['yaxis' + suffix].domain
        assert low < legend.y < high
        assert 0 < legend.x < 1
        assert legend.yanchor == ('top' if position.startswith('top') else 'bottom')


def test_new_file_opens_plot_settings():
    assert DataStore().build_default_file_state()['toolbox_tab'] == 'plot-tools'


@pytest.mark.parametrize('visible', [True, False])
def test_visibility_control_exposes_current_state(visible):
    from callbacks.upload_callbacks import _visibility_button
    store = DataStore()
    store.visibility_state['tic'] = visible
    button = _visibility_button('tic', store)
    props = button.to_plotly_json()['props']
    assert props['title'] == ('Hide trace' if visible else 'Show trace')
    assert props['aria-pressed'] == ('true' if visible else 'false')
    icon_props = button.children.to_plotly_json()['props']
    source = 'data-visible-src' if visible else 'data-hidden-src'
    assert icon_props['src'] == icon_props[source]


def hidden_files_sync_callback(store):
    app = dash.Dash(__name__)
    file_tree_callbacks.register_file_tree_callbacks(app, store)
    callbacks = [entry['callback'].__wrapped__ for entry in app.callback_map.values()
                 if any(inp['id']=='loaded-files' for inp in entry['inputs'])
                 and any(output.component_id=='hidden-files' for output in
                         (entry['output'] if isinstance(entry['output'],list) else [entry['output']]))]
    assert len(callbacks) == 1, 'Loading files must publish server visibility to the browser'
    return callbacks[0]


def test_loading_files_syncs_default_hidden_exports_and_existing_hidden_signals():
    store = DataStore()
    store.visibility_state.update({'paired-export':False, 'manual-hidden':False, 'positive-ms':True})
    sync = hidden_files_sync_callback(store)
    hidden = sync([{'id':'bundle'}], ['manual-hidden'])
    assert set(hidden) == {'paired-export','manual-hidden'}
    assert store.visibility_state['positive-ms'] is True


def test_visibility_sync_clears_stale_browser_hiding_and_skips_unchanged_state():
    store = DataStore()
    store.visibility_state.update({'paired-export':False,'positive-ms':True})
    sync = hidden_files_sync_callback(store)
    assert sync([{'id':'bundle'}], ['positive-ms','removed-file']) == ['paired-export']
    assert sync([{'id':'bundle'}], ['paired-export']) is dash.no_update
    store.visibility_state.clear()
    assert sync([], ['paired-export']) == []
