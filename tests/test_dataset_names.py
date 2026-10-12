from test_file_controls import component
from services.data_store import DataStore, Bundle, BundleType, ComponentRole


def test_rename_dataset_updates_tree_sample_and_trace_source_without_changing_identity():
    store=DataStore();c=component('uv');store.add_bundle(Bundle('sample','pink.csv',BundleType.GENERIC,component_list=[c]))
    original=c.dataframe
    assert store.rename_dataset('sample','Sample 1.5')
    assert store.get_bundled_tree_items()[0]['name']=='Sample 1.5'
    assert store.loaded_data['sample']['record']['name']=='Sample 1.5'
    assert store.get_data_by_id('uv')['metadata']['sample_name']=='Sample 1.5'
    assert c.dataframe is original and c.original_filename=='uv.csv'
    assert not store.rename_dataset('sample','  ')
    assert not store.rename_dataset('gone','Lost')


def test_rename_lcms_signal_does_not_rename_sibling_or_parent_sample():
    store=DataStore();uv=component('uv',ComponentRole.VWD_A);tic=component('tic',ComponentRole.MS_POSITIVE)
    store.add_bundle(Bundle('sample','Injection A',BundleType.LCMS,component_list=[uv,tic]))
    assert store.rename_dataset('uv','UV assay')
    assert store.loaded_data['uv']['record']['name']=='UV assay'
    assert store.loaded_data['tic']['record']['name']=='+TIC'
    assert store.get_bundle('sample').name=='Injection A'
    assert store.get_bundled_tree_items()[0]['children'][0]['name']=='UV assay'


def test_renaming_keeps_the_signal_style_and_publication_name():
    from services.dataset_names import rename_style_settings, update_named_figures
    settings={'trace_overrides':{'id:sample:pink':{'color':'#ff0000'}}}
    assert rename_style_settings(settings,{'sample':('pink','Sample 1.5')})['trace_overrides']['id:sample:Sample 1.5']['color']=='#ff0000'
    store=DataStore();store.add_bundle(Bundle('sample','pink',BundleType.GENERIC,component_list=[component('uv')]))
    store.rename_dataset('sample','Sample 1.5')
    figures={'pub':{'figure':{'data':[{'name':'pink','meta':{'file_id':'sample'}}]}}}
    assert update_named_figures(figures,store)['pub']['figure']['data'][0]['name']=='Sample 1.5'


def test_chromatogram_legend_identifies_sample_and_channel_after_sample_rename():
    from test_chromatogram_bundle import multichannel
    from services.bundling_service import assign_bundles
    from callbacks.viz_callbacks import _collect_visible_files
    store = DataStore()
    bundle, = assign_bundles([('run.txt', b'raw', multichannel())])
    store.add_bundle(bundle)
    groups = _collect_visible_files(store, bundle.primary.component_id)
    names = [name for files in groups.values() for name, _ in files]
    assert names == ['Sample A · UV 254 nm (Ch 1)', 'Sample A · UV 280 nm (Ch 2)']
    assert store.rename_dataset(bundle.bundle_id, 'Alanine 10 mM')
    groups = _collect_visible_files(store, bundle.primary.component_id)
    assert all(name.startswith('Alanine 10 mM · ') for files in groups.values() for name, _ in files)


def test_channel_legend_edit_targets_sample_without_changing_detector_identity(monkeypatch):
    import sys
    import src.ingestion.types as ingestion_types
    monkeypatch.setitem(sys.modules, 'ingestion.types', ingestion_types)
    import plotly.graph_objects as go
    from services.plot_manager import PlotManager
    from test_chromatogram_bundle import multichannel
    from services.bundling_service import assign_bundles
    store = DataStore()
    bundle, = assign_bundles([('run.txt', b'raw', multichannel())])
    store.add_bundle(bundle)
    figure = go.Figure()
    PlotManager()._add_traces(figure, 'Sample A · UV 254 nm (Ch 1)', store.get_data_by_id(bundle.primary.component_id))
    assert figure.data[0].meta['rename_file_id'] == bundle.bundle_id
    assert figure.data[0].meta['rename_label'] == 'Sample A'


def test_saved_channel_figure_rename_updates_next_edit_label():
    from services.dataset_names import update_named_figures
    from services.bundling_service import assign_bundles
    from test_chromatogram_bundle import multichannel
    store = DataStore()
    bundle, = assign_bundles([('run.txt', b'raw', multichannel())])
    store.add_bundle(bundle)
    figure = {'p': {'data': [{'name': 'Sample A · UV 254 nm (Ch 1)',
        'meta': {'file_id': bundle.primary.component_id, 'rename_file_id': bundle.bundle_id, 'rename_label': 'Sample A'}}]}}
    store.rename_dataset(bundle.bundle_id, 'Renamed')
    trace = update_named_figures(figure, store)['p']['data'][0]
    assert trace['name'] == 'Renamed · UV 254 nm (Ch 1)'
    assert trace['meta']['rename_label'] == 'Renamed'
