"""Integrating while the PDA live preview is on keeps the previewed wavelength as real channels."""
import dash
import pandas as pd
import pytest
from dash.exceptions import PreventUpdate
from test_lcms_peak_table import App
from test_pda_service import setup
from callbacks import baseline_callbacks, workspace_callbacks
from callbacks.viz_callbacks import _get_active_file_group
from services.data_store import Bundle, BundleType, Component, ComponentRole

PREVIEW = {'source_id': 'source', 'owner_id': 'sibling', 'wavelength_nm': 280.}


def two_samples():
    store = setup()
    pda = {'time_min': [0., .5, 1.], 'wavelength_nm': [200., 220., 280.],
           'absorbance_mau': [[1., 2., 30.], [4., 5., 60.], [7., 8., 90.]]}
    source = Component('source2', ComponentRole.PRIMARY, 'b.txt',
        dataframe=pd.DataFrame({'Time (min)': [0., .5, 1.], 'Absorbance (mAU)': [30., 60., 90.]}),
        metadata={'pda': pda, 'sample_name': 'Sample B'})
    sibling = Component('sibling2', ComponentRole.GENERIC, 'b.txt',
        dataframe=source.dataframe.copy(), metadata={'pda_source_id': 'source2'})
    store.add_bundle(Bundle('bundle2', 'Sample B', BundleType.GENERIC, component_list=[source, sibling]))
    return store


def figure(owners=('sibling', 'sibling2'), preview=True):
    return {'data': [{'meta': ({'pda_preview': True, 'pda_source_id': 'x', 'pda_owner_id': o} if preview
                               else {'file_id': o})} for o in owners], 'layout': {'meta': {'gecko_tab_id': 'raw'}}}


@pytest.fixture(autouse=True)
def trigger(monkeypatch):
    monkeypatch.setattr(baseline_callbacks, 'callback_context',
                        type('C', (), {'triggered': [{'prop_id': 'manual-draw-line-store.data'}]})())


def draw(store, file_id, preview, fig, mode='draw', active='sibling', **line):
    app = App()
    baseline_callbacks.register_baseline_callbacks(app, store)
    tabs = [{'id': 'raw', 'type': 'raw', 'group_key': list(_get_active_file_group(store, 'sibling'))}]
    payload = {'x0': 0., 'y0': 0., 'x1': 1., 'y1': 0., 'file_id': file_id, 'tab_id': 'raw', **line}
    return app.functions['handle_relayout'](None, payload, mode, False, active, fig, 0, None, 0,
                                            {'layout_mode': 'overlay'}, [], tabs, 'raw', 7, preview)


def test_drawing_on_a_preview_keeps_the_wavelength_and_integrates_the_new_channel_of_that_sample():
    store = two_samples()
    before = {c.component_id for b in store.iter_bundles() for c in b.component_list}
    out = draw(store, 'sibling2', PREVIEW, figure())
    new = {c.component_id for b in store.iter_bundles() for c in b.component_list} - before
    assert len(new) == 2  # one extracted channel per PDA sample
    channel = next(c for c in new if store.get_bundle_for_component(c).bundle_id == 'bundle2')
    other = next(c for c in new if c != channel)
    assert store.get_data_by_id(channel)['metadata']['wavelength_nm'] == 280.
    # the peak is on the new channel of the integrated sample, nowhere else
    assert len(store.peak_service.get_peaks(channel)) == 1
    assert not store.peak_service.get_peaks(other)
    assert not store.peak_service.get_peaks('sibling2') and not store.peak_service.get_peaks('sibling')
    assert store.peak_service.get_peaks(channel)[0].height == 90.  # sample B's own 280 nm data
    figure_out, peaks, _, _, render, loaded, live, active, status = out
    assert figure_out is dash.no_update and peaks == 1 and render == 8
    assert live is False  # preview switched off so the figure shows the real channels
    assert loaded == store.get_loaded_files_list()
    assert active == other  # the selected sample (A) follows its own new channel
    assert '280 nm' in status


def test_selected_sample_follows_its_new_channel():
    store = two_samples()
    out = draw(store, 'sibling', PREVIEW, figure())
    channel = out[7]
    assert channel not in ('sibling', dash.no_update)
    assert store.get_data_by_id(channel)['metadata']['pda_extracted'] is True
    assert len(store.peak_service.get_peaks(channel)) == 1


def test_existing_channel_at_the_previewed_wavelength_is_reused():
    store = two_samples()
    draw(store, 'sibling', PREVIEW, figure())
    count = sum(len(b.component_list) for b in store.iter_bundles())
    draw(store, 'sibling', PREVIEW, figure())
    assert sum(len(b.component_list) for b in store.iter_bundles()) == count


def test_without_a_preview_nothing_is_materialised():
    store = two_samples()
    before = sum(len(b.component_list) for b in store.iter_bundles())
    out = draw(store, 'sibling', None, figure(('sibling',), preview=False))
    assert sum(len(b.component_list) for b in store.iter_bundles()) == before
    assert len(store.peak_service.get_peaks('sibling')) == 1
    assert out[0] is dash.no_update and out[5:] == (dash.no_update,) * 4  # extras untouched
    assert out[4] == 8  # ordinary full render, exactly as before


def test_stale_preview_figure_without_preview_state_is_still_ignored():
    store = two_samples()
    with pytest.raises(PreventUpdate):
        draw(store, 'sibling', None, figure())
    assert not store.peak_service.get_peaks('sibling')


def test_non_preview_trace_in_a_previewing_plot_integrates_normally():
    store = two_samples()
    fig = figure(('sibling',)); fig['data'].append({'meta': {'file_id': 'source2'}})
    before = sum(len(b.component_list) for b in store.iter_bundles())
    out = draw(store, 'source2', PREVIEW, fig)
    assert sum(len(b.component_list) for b in store.iter_bundles()) == before
    assert len(store.peak_service.get_peaks('source2')) == 1 and out[6] == dash.no_update


def test_shape_edits_on_a_preview_are_still_ignored(monkeypatch):
    store = two_samples()
    app = App()
    baseline_callbacks.register_baseline_callbacks(app, store)
    monkeypatch.setattr(baseline_callbacks, 'callback_context',
                        type('C', (), {'triggered': [{'prop_id': 'main-shape-relayout.data'}]})())
    with pytest.raises(PreventUpdate):
        app.functions['handle_relayout']({'shapes[0].y0': 1.}, None, 'edit', False, 'sibling', figure(), 0, None, 0,
                                         {}, [], [], 'raw', 0, PREVIEW)


def test_integrate_tool_stays_enabled_while_previewing():
    app = App()
    workspace_callbacks.register_workspace_callbacks(app, setup())
    raw = {'data': [{'type': 'scatter', 'name': 'PDA 280 nm · preview',
                     'meta': {'pda_preview': True, 'pda_source_id': 'source', 'pda_owner_id': 'sibling'}, 'x': [0, 1], 'y': [1, 2]}]}
    out = app.functions['describe_figure'](raw, None, 'raw', [{'id': 'raw', 'type': 'raw', 'label': 'Raw'}],
                                           {'_context_key': 'x:raw'}, None)
    assert out[8] is False and 'previewed wavelength' in out[9]
