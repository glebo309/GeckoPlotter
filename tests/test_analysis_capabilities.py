"""Analysis navigation follows the selected source's actual data capabilities."""
import numpy as np
import pytest
from dash import no_update
from services.data_store import DataStore, Bundle, BundleType, ComponentRole
from test_file_controls import component
from test_workspace_callbacks import App
from callbacks.workspace_callbacks import register_workspace_callbacks


def store_with_scan_bundle(arrays=None):
    store = DataStore()
    ms = component('ms', ComponentRole.MS_POSITIVE)
    ms.metadata['mass_spectral_data'] = arrays if arrays is not None else {
        'mass_values':np.array([100.,200.]), 'intensity_values':np.array([10.,20.]),
        'scan_index':np.array([0,1])}
    store.add_bundle(Bundle('lcms', 'LC-MS', BundleType.LCMS,
                           component_list=[ms, component('uv',ComponentRole.VWD_A)]))
    store.add_bundle(Bundle('spectra', 'UV/Vis', BundleType.GENERIC,
                           component_list=[component('standalone')]))
    return store


def capability_callback(store):
    app = App(); register_workspace_callbacks(app,store)
    assert 'analysis_capabilities' in app.functions
    return app.functions['analysis_capabilities']


@pytest.mark.parametrize('active',['lcms','ms','uv'])
def test_lcms_scan_tabs_available_for_any_component_of_its_bundle(active):
    callback = capability_callback(store_with_scan_bundle())
    result = callback(active,[], 'ms-peak-mass')
    assert all(style.get('display') != 'none' for style in result[:3])
    assert result[3] is no_update


@pytest.mark.parametrize('active',[None,'spectra','standalone','removed'])
def test_other_loaded_ms_files_never_enable_scan_tabs_for_unrelated_source(active):
    callback = capability_callback(store_with_scan_bundle())
    result = callback(active,[], 'ms-peak-mass')
    assert all(style['display']=='none' for style in result[:3])
    assert result[3] == 'metadata'


@pytest.mark.parametrize('arrays',[
    {}, {'scan_times':[0,1]}, {'mass_values':[], 'intensity_values':[], 'scan_index':[]},
    {'mass_values':[100.], 'intensity_values':[10.]},
])
def test_tic_only_or_empty_spectral_metadata_does_not_offer_ms_tools(arrays):
    callback = capability_callback(store_with_scan_bundle(arrays))
    result = callback('uv',[], 'ms-scan')
    assert all(style['display']=='none' for style in result[:3])
    assert result[3]=='metadata'


@pytest.mark.parametrize('tab',['data-overview','peak-analysis','metadata','across-samples','calibration'])
def test_general_analysis_tabs_retain_selection_when_capabilities_change(tab):
    callback = capability_callback(store_with_scan_bundle())
    assert callback('standalone',[],tab)[3] is no_update


def test_opening_lcms_data_with_scans_shows_the_scan_viewer_and_keeps_a_chosen_ms_view():
    from callbacks.workspace_callbacks import side_view_for
    assert side_view_for(True, 'metadata', 'active-file') == 'ms-scan'
    assert side_view_for(True, 'pda', 'loaded-files') == 'ms-scan'
    assert side_view_for(True, 'ms-eic', 'active-file') is no_update          # the user chose EIC: keep it
    assert side_view_for(True, 'metadata', 'side-tabs') is no_update          # the user clicked Metadata: keep it
    assert side_view_for(False, 'ms-scan', 'active-file') == 'metadata'
    assert side_view_for(False, 'metadata', 'active-file') is no_update
