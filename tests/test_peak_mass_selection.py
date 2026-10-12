"""Peak selection links the views; dismissing handles keeps the spectrum open."""
from types import SimpleNamespace
import dash
import pytest
from test_lcms_peak_table import App
from test_peak_owner_aliases import setup, add
from src.services.data_store import BundleType
from callbacks import lcms_callbacks


def fixture(monkeypatch, trigger):
    store = setup(BundleType.LCMS)
    first = add(store.peak_service, 'component')
    second = store.peak_service.add_baseline_peak(file_id='component', area=8., height=4., apex_x=4.,
        poly_x=[3,4,5,5,4,3], poly_y=[0,4,0,0,0,0], p_line=[(3,0),(5,0)], q1=(3,0), q2=(5,0))
    uv = add(store.peak_service, 'other')
    app = App(); lcms_callbacks.register_lcms_callbacks(app, store)
    monkeypatch.setattr(lcms_callbacks, 'callback_context', SimpleNamespace(triggered=[{'prop_id': trigger}]))
    return app.functions['sync_peak_mass_to_click'], first, second, uv, app, store


def test_dropdown_selection_updates_highlight_and_requests_render(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    selector, selected, owner, render = cb(first.peak_id, second.peak_id, 'component', 8, 'raw')
    assert selector is dash.no_update
    assert selected == second.peak_id
    assert owner is dash.no_update
    assert render == 9
    dependencies = app.registrations['sync_peak_mass_to_click'][1]
    assert {dep.component_id for dep in dependencies} == {'selected-peak-idx', 'peak-mass-selector'}


def test_selecting_bundle_peak_activates_its_real_component_owner(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    out = cb(first.peak_id, uv.peak_id, 'component', 8, 'raw')
    assert out[1:] == (uv.peak_id, 'other', 9)
    assert store.peak_service.get_peaks('other') == [uv]


def test_chromatogram_click_updates_dropdown_without_second_render(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'selected-peak-idx.data')
    out = cb(second.peak_id, first.peak_id, 'component', 8, 'raw')
    assert out[0] == second.peak_id
    assert all(value is dash.no_update for value in out[1:])


def test_echo_stops_and_removed_or_foreign_peak_cannot_change_selection(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    assert all(value is dash.no_update for value in cb(first.peak_id, first.peak_id, 'component', 8, 'raw'))
    assert all(value is dash.no_update for value in cb(first.peak_id, 'foreign-or-removed', 'component', 8, 'raw'))
    assert all(value is dash.no_update for value in cb(first.peak_id, second.peak_id, 'component', 8, 'publication'))


def test_deselecting_chromatogram_preserves_last_spectrum(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'selected-peak-idx.data')
    out = cb(None, first.peak_id, 'component', 8, 'raw')
    assert all(value is dash.no_update for value in out)
    # Choosing another peak still replaces the retained spectrum.
    assert cb(second.peak_id, first.peak_id, 'component', 8, 'raw')[0] == second.peak_id


def test_clearing_dropdown_clears_highlight_and_rerenders(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    out = cb(first.peak_id, None, 'component', 8, 'raw')
    assert out[1] is None and out[3] == 9


def test_uv_to_tic_dropdown_owner_change_keeps_selection_through_hydration(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    out = cb(uv.peak_id, second.peak_id, 'other', 8, 'raw')
    assert out[1:] == (second.peak_id, 'component', 9)
    # The owner change refreshes selector options; the selected TIC ID remains
    # present and the resulting selected-store echo must not reset or rerender.
    options = app.functions['update_peak_mass_selector'](0, 'component')
    assert second.peak_id in {option['value'] for option in options}
    monkeypatch.setattr(lcms_callbacks, 'callback_context', SimpleNamespace(
        triggered=[{'prop_id': 'selected-peak-idx.data'}]))
    assert all(value is dash.no_update for value in cb(second.peak_id, second.peak_id, 'component', 9, 'raw'))
    assert store.peak_service.get_peaks('other') == [uv]


def test_fitted_components_use_separate_apex_scans_with_shared_fit_bounds(monkeypatch):
    import numpy as np
    from services.lcms_service import LCMSService
    peaks = [SimpleNamespace(peak_id=str(i), name=f'Peak {i}', label='',
        source='deconvolved', rt=center, rt_start=.35, rt_end=1.15,
        fit_params={'sigma': .04, 'gamma': 40., 'amplitude': 10.})
        for i, center in enumerate((.55, .80))]
    data = {'data': {'Time (min)': np.array([.4, .6, .85, 1.1]),
                    'Intensity': np.ones(4),
                    'mass_values': np.array([100., 200., 300., 400.]),
                    'intensity_values': np.array([1., 20., 30., 1.]),
                    'scan_index': np.arange(4)}}
    store = SimpleNamespace(peak_service=SimpleNamespace(get_peaks=lambda _: peaks),
                            lcms_service=LCMSService())
    monkeypatch.setattr(lcms_callbacks, '_polarity_spectral_entry', lambda *args: ('ms', data))
    app = App(); lcms_callbacks.register_lcms_callbacks(app, store)
    results = [app.functions['show_peak_mass'](p.peak_id, 'positive', 'uv') for p in peaks]
    assert results[0][0].data[0].x[0] == 200.
    assert results[1][0].data[0].x[0] == 300.
    assert '0.600 min' in results[0][1] and '0.850 min' in results[1][1]
    assert 'apex' in results[0][1].lower()
    assert 'mixed' in results[0][1].lower()
    labels = [o['label'] for o in app.functions['update_peak_mass_selector'](0, 'uv')]
    assert labels[0] != labels[1] and all('apex' in label.lower() for label in labels)
    # Never substitute a later scan when MS acquisition starts after the apex.
    data['data']['Time (min)'] = np.array([1., 1.05, 1.1, 1.15])
    figure, _ = app.functions['show_peak_mass']('0', 'positive', 'uv')
    assert not figure.data
    assert 'apex' in figure.layout.annotations[0].text.lower()


def test_non_ms_plot_selection_is_not_cleared_by_hidden_mass_selector(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'peak-mass-selector.value')
    monkeypatch.setattr(lcms_callbacks, '_lcms_bundle', lambda *_: None)
    assert all(value is dash.no_update for value in cb(first.peak_id, None, 'component', 8, 'raw'))
