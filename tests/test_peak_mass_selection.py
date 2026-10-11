"""One selection owns the mass dropdown and chromatogram peak handles."""
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


def test_deselecting_chromatogram_clears_dropdown(monkeypatch):
    cb, first, second, uv, app, store = fixture(monkeypatch, 'selected-peak-idx.data')
    out = cb(None, first.peak_id, 'component', 8, 'raw')
    assert out[0] is None
    assert all(value is dash.no_update for value in out[1:])


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
