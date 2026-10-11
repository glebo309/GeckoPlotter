"""Recognize explicit spectral sidecars without discarding imported measurements."""
import numpy as np
import pandas as pd
import pytest
from services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore
from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult


def component(cid, name, spectral=False, x=None, role=ComponentRole.MS_POSITIVE):
    data = pd.DataFrame({'Time (min)': [0., 1., 2.] if x is None else x, 'Ion Count': [1., 10., 2.]})
    metadata = {'mass_spectral_data': {'scan_times': np.array([0., 60., 120.])}} if spectral else {'is_tic_only': True}
    sr = StandardizedResult(data=data, column_roles={'Time (min)': ColumnRole.X, 'Ion Count': ColumnRole.Y},
        identity=FileIdentity(name, 'cdf', 'lcms_cdf', 2), plot_hint=PlotHint.LINE,
        source_category=SourceCategory.LCMS_MS, metadata=metadata)
    return Component(cid, role, name, dataframe=data, column_roles=sr.column_roles,
                     metadata=metadata, standardized=sr)


def test_explicit_pair_shows_spectral_source_and_retains_unhideable_export():
    trace = component('trace', 'Run_MS1 +TIC.cdf')
    spectral = component('spectral', 'Run_MS1 +TIC_spectra.cdf', True, [0., 1.0000004, 2.])
    bundle = Bundle('run', 'Run', BundleType.LCMS, component_list=[trace, spectral])
    store = DataStore(); store.add_bundle(bundle)
    assert store.visibility_state.get('trace', True) is False
    assert store.visibility_state.get('spectral', True) is True
    assert bundle.primary.component_id == 'spectral'
    assert len(bundle.component_list) == 2
    assert store.get_data_by_id('trace')['data'] is trace.dataframe
    store.visibility_state['trace'] = True
    store.add_bundle(bundle)
    assert store.visibility_state['trace'] is True, 'User unhiding survives re-registration/Undo'


@pytest.mark.parametrize('spectral_name,grid,role', [
    ('Other_MS1 +TIC_spectra.cdf', [0., 1., 2.], ComponentRole.MS_POSITIVE),
    ('Run_MS1 +TIC_spectra.cdf', [0., 1.1, 2.], ComponentRole.MS_POSITIVE),
    ('Run_MS1 +TIC_spectra.cdf', [0., 1., 2.], ComponentRole.MS_NEGATIVE),
    ('Run_MS1 +TIC.cdf', [0., 1., 2.], ComponentRole.MS_POSITIVE),
])
def test_no_default_hiding_without_matching_explicit_source_pair(spectral_name, grid, role):
    bundle = Bundle('run', 'Run', BundleType.LCMS, component_list=[
        component('trace', 'Run_MS1 +TIC.cdf'), component('spectral', spectral_name, True, grid, role)])
    store = DataStore(); store.add_bundle(bundle)
    assert store.visibility_state.get('trace', True) is True


def test_spectral_and_chromatogram_exports_have_distinct_labels():
    assert Bundle.component_display_name(component('trace', 'Run_MS1 +TIC.cdf')) == '+TIC (export)'
    assert Bundle.component_display_name(component('ms', 'Run_MS1 +TIC_spectra.cdf', True)) == '+TIC'
    assert Bundle.component_display_name(component('neg', 'Run_MS1 -TIC.cdf', role=ComponentRole.MS_NEGATIVE)) == '-TIC (export)'


def test_aia_ms_parser_keeps_counts_and_never_labels_them_absorbance(monkeypatch):
    from src.ingestion.presets.lcms_cdf import LCMSCDFPreset
    from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader
    data = pd.DataFrame({'Time (min)': [0., 1.], 'Intensity (mAU)': [300., 700.]})
    monkeypatch.setattr(LCMSVWDCDFReader, 'load_file', lambda *args: True)
    monkeypatch.setattr(LCMSVWDCDFReader, 'get_data', lambda *args: data)
    monkeypatch.setattr(LCMSVWDCDFReader, 'get_metadata', lambda *args: {
        'detector_name': 'MS1 +TIC', 'detector_unit': 'Counts', 'detector_channel': 'Unknown'})
    result = LCMSCDFPreset()._parse_aia_chrom('Run_MS1 +TIC.cdf')
    assert list(result['data'].columns) == ['Time (min)', 'Ion Count']
    assert result['column_roles']['Ion Count'] == ColumnRole.Y
    assert list(result['data']['Ion Count']) == [300., 700.]


def test_compact_signal_label_keeps_full_source_filename_in_tooltip():
    from callbacks.upload_callbacks import render_individual_file_item_selected
    from components.workspace_layout import walk
    trace = component('trace', 'Run_MS1 +TIC.cdf')
    spectral = component('spectral', 'Run_MS1 +TIC_spectra.cdf', True)
    store = DataStore(); store.add_bundle(Bundle('run', 'Run', BundleType.LCMS, component_list=[trace, spectral]))
    item = store.get_bundled_tree_items()[0]['children'][1]
    row = render_individual_file_item_selected(item, is_child=True, data_manager=store)
    button = next(node for node in walk(row) if getattr(node, 'id', None) == {'type': 'file-tree-item', 'index': 'spectral'})
    assert button.title == spectral.original_filename
