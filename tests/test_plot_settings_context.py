import dash
import pytest

from callbacks.plot_settings_callbacks import register_plot_settings_callbacks, _save_settings
from callbacks.lcms_callbacks import register_lcms_callbacks
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore


@pytest.fixture
def settings_callbacks():
    store = DataStore()
    store._shared_plot_settings = {}
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=[
        Component('tic', ComponentRole.MS_POSITIVE, 'tic.csv'),
        Component('uv', ComponentRole.VWD_A, 'uv.csv'),
    ]))
    app = dash.Dash(__name__)
    register_plot_settings_callbacks(app, store)
    hydrate = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                   if cb['inputs'] == [{'id': 'active-plot-context', 'property': 'data'}])
    resolve = app.callback_map['active-plot-context.data']['callback'].__wrapped__
    return store, hydrate, resolve


def test_saved_overlay_survives_selecting_another_bundle_component(settings_callbacks):
    store, hydrate, _ = settings_callbacks
    _save_settings(store, 'shared:raw:lcms', {'layout_mode': 'overlay', 'line_width': 3})
    for component_id in ('tic', 'uv'):
        settings = hydrate('shared:raw:lcms', component_id)[0]
        assert settings['layout_mode'] == 'overlay'
        assert settings['line_width'] == 3


def test_new_lcms_context_still_starts_separate(settings_callbacks):
    _, hydrate, _ = settings_callbacks
    assert hydrate('shared:raw:lcms', 'tic')[0]['layout_mode'] == 'stacked'


def test_component_selection_does_not_rehydrate_same_plot_context(settings_callbacks):
    _, _, resolve = settings_callbacks
    assert resolve('uv', 'raw', 'data-overview', 'lcms', 'shared:raw:lcms') is dash.no_update
    assert resolve('uv', 'raw', 'data-overview', 'spectra', 'shared:raw:lcms') == 'shared:raw:spectra'


@pytest.mark.parametrize('selected', ['tic', 'uv', 'sample'])
def test_lcms_selection_callbacks_cannot_override_user_layout(settings_callbacks, selected):
    store, _, _ = settings_callbacks
    app = dash.Dash(__name__)
    register_plot_settings_callbacks(app, store)
    register_lcms_callbacks(app, store)
    mode = 'overlay'
    # Exercise every direct layout writer subscribed to file selection, including
    # the LC-MS callbacks that are registered alongside the settings callbacks.
    for entry in app.callback_map.values():
        outputs = entry['output'] if isinstance(entry['output'], list) else [entry['output']]
        if (any(output.component_id == 'pt-layout-mode' for output in outputs)
                and {'id': 'active-file', 'property': 'data'} in entry['inputs']):
            try:
                result = entry['callback'].__wrapped__(selected, mode)
            except dash.exceptions.PreventUpdate:
                continue
            if result is not dash.no_update:
                mode = result
    assert mode == 'overlay'


def test_settings_carry_their_owner_and_publication_controls(settings_callbacks):
    store, hydrate, _ = settings_callbacks
    _save_settings(store, 'shared:raw:publication-a', {'layout_mode':'stacked', 'subplot_rows':2,
        'subplot_cols':3, 'figure_width_mm':123.5, 'figure_height_mm':72.5, 'link_x':False, 'y_scope':'global'})
    settings = hydrate('shared:raw:publication-a', None)[0]
    assert settings['_context_key'] == 'shared:raw:publication-a'
    assert settings['figure_width_mm'] == 123.5
    other = hydrate('shared:raw:publication-b', None)[0]
    assert other['figure_width_mm'] == 84
    assert other['subplot_rows'] == 1


def test_late_settings_response_is_persisted_to_its_own_figure(settings_callbacks):
    store, _, _ = settings_callbacks
    app = dash.Dash(__name__)
    register_plot_settings_callbacks(app, store)
    callback = next(cb['callback'].__wrapped__ for cb in app.callback_map.values()
                    if cb.get('callback') and cb['callback'].__wrapped__.__name__ == 'persist_plot_settings')
    callback({'_context_key':'shared:raw:a', 'layout_mode':'overlay'}, 'shared:raw:b')
    assert store._shared_plot_settings['shared:raw:a']['layout_mode'] == 'overlay'
    assert 'shared:raw:b' not in store._shared_plot_settings
