import numpy as np
import pandas as pd
import pytest

from services.pda_service import resolve_pda_source, extract_pda_views, add_pda_chromatogram
from services.data_store import DataStore, Bundle, Component, ComponentRole, BundleType


def setup():
    store = DataStore()
    pda = {'time_min': [0., .5, 1.], 'wavelength_nm': [200., 220., 280.],
           'absorbance_mau': [[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]]}
    source = Component('source', ComponentRole.PRIMARY, 'export.txt',
        dataframe=pd.DataFrame({'Time (min)': [0., .5, 1.], 'Absorbance (mAU)': [3., 6., 9.]}),
        metadata={'pda': pda, 'sample_name': 'Sample A'})
    sibling = Component('sibling', ComponentRole.GENERIC, 'export.txt',
        dataframe=source.dataframe.copy(), metadata={'pda_source_id': 'source'})
    store.add_bundle(Bundle('bundle', 'Sample A', BundleType.GENERIC, component_list=[source, sibling]))
    return store


def test_resolve_pda_from_bundle_or_sibling():
    store = setup()
    assert resolve_pda_source(store, 'sibling')[0] == 'source'
    assert resolve_pda_source(store, 'bundle')[0] == 'source'
    assert resolve_pda_source(store, 'missing') is None


def test_extraction_uses_nearest_measured_axes_without_interpolation():
    store = setup()
    _, pda = resolve_pda_source(store, 'source')
    view = extract_pda_views(pda, 273., .62)
    assert view['wavelength_nm'] == 280.
    assert view['time_min'] == .5
    np.testing.assert_array_equal(view['chromatogram'], [3., 6., 9.])
    np.testing.assert_array_equal(view['spectrum'], [4., 5., 6.])
    assert extract_pda_views(pda, 1000., -5.)['time_min'] == 0.


def test_rejects_misaligned_matrix_and_nonfinite_axes():
    for bad in [
        {'time_min': [0., 1.], 'wavelength_nm': [200., 220.], 'absorbance_mau': [[1., 2.]]},
        {'time_min': [float('nan')], 'wavelength_nm': [200.], 'absorbance_mau': [[1.]]},
    ]:
        with pytest.raises(ValueError):
            extract_pda_views(bad, 220., 0.)


def test_extracted_trace_is_normal_data_deduplicated_by_actual_wavelength():
    store = setup()
    first = add_pda_chromatogram(store, 'sibling', 273.)
    second = add_pda_chromatogram(store, 'source', 279.)
    assert first == second
    entry = store.get_data_by_id(first)
    assert entry['metadata']['pda_source_id'] == 'source'
    assert entry['metadata']['wavelength_nm'] == 280.
    assert 'pda' not in entry['metadata']
    assert entry['metadata']['auto_x'] == 'Time (min)'
    assert entry['metadata']['auto_y'] == ['Absorbance (mAU)']
    assert entry['record']['name'] == 'PDA 280 nm'
    np.testing.assert_array_equal(entry['data']['Absorbance (mAU)'], [3., 6., 9.])
    assert len(store.get_bundle('bundle').component_list) == 3
    assert len(store.analysis_history) == 1
    assert store.analysis_history[0]['parameters']['wavelength_nm'] == 280.


def test_extracted_channel_enters_real_plot_collection_and_links_original_export():
    import io
    import json
    import zipfile
    from callbacks.viz_callbacks import _collect_visible_files
    from services.research_package import build_research_package
    store = setup()
    bundle = store.get_bundle('bundle')
    bundle.bundle_type = BundleType.CHROMATOGRAM
    bundle.primary.raw_bytes = b'[PDA 3D]\noriginal acquisition'
    added = add_pda_chromatogram(store, 'source', 280.)
    visible = _collect_visible_files(store, active_file_id=added, loaded_files=store.get_loaded_files_list())
    entries = [entry for group in visible.values() for _, entry in group]
    assert added in {entry['record']['id'] for entry in entries}
    sr = store.get_data_by_id(added)['standardized']
    assert sr.x_columns == ['Time (min)']
    assert sr.y_columns == ['Absorbance (mAU)']
    package = zipfile.ZipFile(io.BytesIO(build_research_package(store, {}, formats=[])))
    signals = json.loads(package.read('metadata/dataset.json'))['signals']
    source = next(signal for signal in signals if signal['signal_id'] == 'source')
    extracted = next(signal for signal in signals if signal['signal_id'] == added)
    assert source['original_file'] is not None
    assert extracted['original_file'] == source['original_file']
