from types import SimpleNamespace
import dash
import pytest
from test_lcms_peak_table import App
from test_pda_service import setup
from callbacks import pda_callbacks


def callbacks(monkeypatch, trigger):
    store = setup()
    app = App()
    pda_callbacks.register_pda_callbacks(app, store)
    monkeypatch.setattr(pda_callbacks, 'callback_context', SimpleNamespace(triggered=[{'prop_id': trigger}]))
    return store, app.functions


def invoke(fn, **kw):
    defaults = dict(active_file='sibling', wavelength=220., time=.5, heat_click=None,
        spectrum_click=None, main_click=None, selected_peak=None,
        analysis_tab='pda', colormap='Viridis', context={'source_id': 'source', 'wavelength_nm': 220., 'time_min': .5},
        main_figure={}, view_mode='raw')
    defaults.update(kw)
    return fn(**defaults)


def test_heatmap_updates_both_measured_slices_and_retains_zoom_key(monkeypatch):
    store, fns = callbacks(monkeypatch, 'pda-heatmap.clickData')
    out = invoke(fns['update_pda_views'], heat_click={'points': [{'x': .62, 'y': 273.}]})
    assert out[2:4] == (280., .5)
    assert list(out[1].data[0].y) == [4., 5., 6.]
    assert out[0].layout.uirevision == 'pda-source-heatmap'
    assert out[8] == {'source_id': 'source', 'wavelength_nm': 280., 'time_min': .5, 'heatmap_ready': True, 'colormap': 'Viridis'}


def test_spectrum_click_selects_wavelength(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-spectrum.clickData')
    out = invoke(fns['update_pda_views'], spectrum_click={'points': [{'x': 278.}]})
    assert out[2] == 280.


def test_peak_selection_displays_spectrum_at_peak_apex(monkeypatch):
    store, fns = callbacks(monkeypatch, 'selected-peak-idx.data')
    peak = store.peak_service.add_baseline_peak(file_id='sibling', area=4, height=9,
        apex_x=.92, poly_x=[.5,1,1,.5], poly_y=[0,9,0,0], p_line=[(.5,0),(1,0)], q1=(.5,0), q2=(1,0))
    out = invoke(fns['update_pda_views'], selected_peak=peak.peak_id)
    assert out[3] == 1.
    assert list(out[1].data[0].y) == [7., 8., 9.]


def test_foreign_main_plot_click_cannot_change_spectrum(monkeypatch):
    _, fns = callbacks(monkeypatch, 'main-plot.clickData')
    with pytest.raises(dash.exceptions.PreventUpdate):
        invoke(fns['update_pda_views'], main_click={'points': [{'x': 1., 'curveNumber': 0}]},
            main_figure={'data': [{'meta': {'file_id': 'missing'}}]})


def test_non_pda_selection_hides_tab_and_returns_to_data(monkeypatch):
    _, fns = callbacks(monkeypatch, 'active-file.data')
    style, selected = fns['show_pda_tab']('missing', [], 'pda')
    assert style['display'] == 'none'
    assert selected == 'metadata'


def test_peak_and_channel_selection_in_one_update_uses_selected_apex(monkeypatch):
    store, fns = callbacks(monkeypatch, 'active-file.data')
    peak = store.peak_service.add_baseline_peak(file_id='sibling', area=4, height=9,
        apex_x=.92, poly_x=[.5,1,1,.5], poly_y=[0,9,0,0], p_line=[(.5,0),(1,0)], q1=(.5,0), q2=(1,0))
    out = invoke(fns['update_pda_views'], selected_peak=peak.peak_id)
    assert out[3] == 1.


def test_pda_uses_boxed_axes_without_grid():
    from services.pda_service import extract_pda_views
    payload = setup().get_data_by_id('source')['metadata']['pda']
    heat, spectrum = pda_callbacks.build_pda_figures('source', extract_pda_views(payload))
    for figure in (heat, spectrum):
        for axis in (figure.layout.xaxis, figure.layout.yaxis):
            assert axis.showgrid is False and axis.zeroline is False
            assert axis.showline is True and axis.mirror is True


def test_live_preview_is_temporary_and_leaving_pda_clears_it(monkeypatch):
    store, fns = callbacks(monkeypatch, 'pda-context.data')
    context = {'source_id':'source', 'wavelength_nm':280., 'time_min':.5}
    before = list(store.loaded_data)
    preview, cursor = fns['sync_pda_main_view'](context, True, 'pda', 'sibling', 'navigate')
    assert preview == {'source_id':'source','wavelength_nm':280., 'owner_id':'sibling'}
    assert (cursor['time_minimum'], cursor['time_maximum']) == (0., 1.)
    assert cursor['time_min'] == .5
    assert list(store.loaded_data) == before
    assert fns['sync_pda_main_view'](context, False, 'pda', 'sibling', 'navigate')[0] is None
    assert fns['sync_pda_main_view'](context, True, 'peaks', 'sibling', 'navigate') == (None, None)


def test_add_wavelength_keeps_existing_channels_visible_and_preserves_original_data(monkeypatch):
    store, fns = callbacks(monkeypatch, 'pda-add-chromatogram.n_clicks')
    original = store.get_data_by_id('sibling')['data'].copy()
    out = fns['add_pda_trace'](1, 'sibling', 280., 0)
    assert out[4] is False  # stop preview after keeping the measured wavelength
    assert out[1] != 'sibling'
    assert store.visibility_state.get('sibling', True) is True
    assert store.visibility_state.get('source', True) is True
    assert store.get_data_by_id('sibling')['data'].equals(original)
    assert store.get_data_by_id(out[1])['metadata']['wavelength_nm'] == 280.


def test_preview_blocks_integration_of_underlying_unpreviewed_signal(monkeypatch):
    from callbacks.integration_callbacks import register_integration_callbacks
    from callbacks.baseline_callbacks import register_baseline_callbacks
    store = setup(); app = App()
    register_integration_callbacks(app, store)
    preview = {'source_id':'source', 'owner_id':'sibling', 'wavelength_nm':280.}
    assert app.functions['detection_target']('sibling', [], preview)[1] is True
    out = app.functions['detect_peaks'](1, 90, 'sibling', {}, 0, 'linear', preview)
    assert out[0] is dash.no_update
    assert not store.peak_service.get_peaks('sibling')
    register_baseline_callbacks(app, store)
    figure = {'data':[{'meta':{'pda_preview':True}}]}
    with pytest.raises(dash.exceptions.PreventUpdate):
        app.functions['handle_relayout'](None, {'momentary':True, 'x0':0, 'x1':1, 'y0':0, 'y1':0},
            'navigate', False, 'sibling', figure, 0, None, 0, {}, [], [], None, 0)


def test_hidden_pda_tab_never_builds_or_transmits_matrix_on_file_selection(monkeypatch):
    _, fns = callbacks(monkeypatch, 'active-file.data')
    def forbidden(*args, **kwargs):
        pytest.fail('Hidden PDA view extracted the full matrix')
    monkeypatch.setattr(pda_callbacks, 'extract_pda_views', forbidden)
    with pytest.raises(dash.exceptions.PreventUpdate):
        invoke(fns['update_pda_views'], analysis_tab='data-overview')


def test_wavelength_change_never_resends_the_heatmap(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-wavelength.value')
    initial = invoke(fns['update_pda_views'], context=None)
    def forbidden(*args, **kwargs):
        pytest.fail('Existing heatmap must not be reconstructed')
    monkeypatch.setattr(pda_callbacks.go, 'Heatmap', forbidden)
    updated = invoke(fns['update_pda_views'], wavelength=280., context=initial[8])
    assert updated[0] is dash.no_update  # the cross is a client-side overlay
    assert updated[2] == 280.
    assert list(updated[1].data[0].y) == [4.,5.,6.]


def test_initial_heatmap_transmits_full_precision_typed_matrix_without_boxing():
    import base64
    import numpy as np
    from services.pda_service import extract_pda_views
    payload = setup().get_data_by_id('source')['metadata']['pda']
    heat, _ = pda_callbacks.build_pda_figures('source', extract_pda_views(payload))
    encoded = heat.to_plotly_json()['data'][0]['z']
    assert isinstance(encoded, dict), 'Full matrix should use Plotly typed-array transport'
    actual = np.frombuffer(base64.b64decode(encoded['bdata']), dtype=encoded['dtype'])
    shape = tuple(int(n) for n in encoded['shape'].split(','))
    np.testing.assert_array_equal(actual.reshape(shape), np.asarray(payload['absorbance_mau']).T)


def test_add_action_label_uses_actual_measured_wavelength(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-wavelength.value')
    out = invoke(fns['update_pda_views'], wavelength=273.)
    assert out[11] == 'Add 280 nm channel'


def test_readding_hidden_pda_wavelength_exposes_it_without_hiding_other_channels(monkeypatch):
    store, fns = callbacks(monkeypatch, 'pda-add-chromatogram.n_clicks')
    first = fns['add_pda_trace'](1, 'sibling', 280., 0)[1]
    second = fns['add_pda_trace'](2, first, 220., 1)[1]
    assert store.visibility_state.get(first, True) is True
    store.visibility_state[first] = False
    count = len(store.get_bundle('bundle').component_list)
    result = fns['add_pda_trace'](3, second, 279., 2)
    assert result[1] == first
    assert len(store.get_bundle('bundle').component_list) == count
    assert store.visibility_state[first] is True
    assert store.visibility_state[second] is True
    assert store.visibility_state.get('sibling', True) is True


def test_drag_cursor_snaps_to_measured_time_and_updates_spectrum(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-cursor-event.data')
    out = invoke(fns['update_pda_views'], cursor_event={'source_id':'source','owner_id':'sibling','time_min':.81})
    assert out[3] == 1.
    assert list(out[1].data[0].y) == [7.,8.,9.]
    with pytest.raises(dash.exceptions.PreventUpdate):
        invoke(fns['update_pda_views'], cursor_event={'source_id':'foreign','time_min':.81})


def test_heatmap_defaults_to_plotly_viridis_and_shift_drag_zooms(monkeypatch):
    _, fns = callbacks(monkeypatch, 'active-file.data')
    out = invoke(fns['update_pda_views'], colormap=None)
    assert out[0].layout.dragmode == 'pan'  # Shift + drag becomes box zoom; plain drag is taken for the cross
    assert out[0].data[0].colorscale[0][1] == '#440154'
    assert out[8]['colormap'] == 'Viridis'


def test_right_click_colour_map_redraws_heatmap_instead_of_patching(monkeypatch):
    from services.crameri_colors import SEQUENTIAL
    _, fns = callbacks(monkeypatch, 'pda-colormap.data')
    ctx = {'source_id': 'source', 'wavelength_nm': 220., 'time_min': .5, 'heatmap_ready': True, 'colormap': 'Viridis'}
    out = invoke(fns['update_pda_views'], colormap='Batlow', context=ctx)
    assert not isinstance(out[0], dash.Patch)
    assert out[0].data[0].colorscale[0][1] == SEQUENTIAL['batlow'][0]
    assert out[8]['colormap'] == 'Batlow'


def test_wavelength_is_whole_nanometres(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-wavelength.value')
    out = invoke(fns['update_pda_views'], wavelength=219.6)
    assert out[2] == 220.
    assert out[9] == 'Measured: 220 nm · 0.5 min'
    assert out[11] == 'Add 220 nm channel'


def test_dragging_the_cross_selects_time_and_whole_nm_wavelength(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-heatmap-event.data')
    out = invoke(fns['update_pda_views'], heat_event={'time_min': .62, 'wavelength_nm': 273.4})
    assert out[2:4] == (280., .5)


def test_dragging_the_cross_updates_the_spectrum_without_redrawing_the_heatmap(monkeypatch):
    _, fns = callbacks(monkeypatch, 'pda-heatmap-event.data')
    ctx = {'source_id': 'source', 'wavelength_nm': 220., 'time_min': .5, 'heatmap_ready': True, 'colormap': 'Viridis'}
    out = invoke(fns['update_pda_views'], context=ctx, heat_event={'time_min': .6, 'wavelength_nm': 275.})
    assert out[0] is dash.no_update and out[1].data


@pytest.mark.parametrize('value', ['inf', '-inf', 'nan', '1e999'])
def test_preview_endpoint_rejects_non_finite_wavelengths_with_400(value):
    from flask import Flask
    server = Flask(__name__)
    app = App()
    app.server = server
    pda_callbacks.register_pda_callbacks(app, setup())
    client = server.test_client()
    assert client.get(f'/_pda/chromatograms?owner=bundle&wavelength={value}').status_code == 400
    assert client.get('/_pda/chromatograms?owner=bundle&wavelength=220').status_code == 200


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan')])
def test_extract_pda_views_raises_value_error_for_non_finite_wavelength(value):
    from services.pda_service import extract_pda_views, resolve_pda_source
    _, pda = resolve_pda_source(setup(), 'source')
    with pytest.raises(ValueError):
        extract_pda_views(pda, value)


def test_opening_pda_data_offers_the_pda_view_but_stays_on_metadata(monkeypatch):
    _, fns = callbacks(monkeypatch, 'active-file.data')
    style, selected = fns['show_pda_tab']('sibling', [], 'metadata')
    assert style['display'] == '' and selected is dash.no_update
    assert fns['show_pda_tab']('sibling', [], 'pda')[1] is dash.no_update
    assert fns['show_pda_tab']('sibling', [], 'ms-scan')[1] is dash.no_update
