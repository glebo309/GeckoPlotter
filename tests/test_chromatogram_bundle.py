import io
import json
import zipfile
import pandas as pd
from src.ingestion.types import StandardizedResult, FileIdentity, SourceCategory, ColumnRole
from services.bundling_service import assign_bundles
from services.data_store import DataStore
from services.research_package import build_research_package


def multichannel():
    roles={'Time (min)':ColumnRole.X,'Absorbance (mAU)':ColumnRole.Y}
    data=pd.DataFrame({'Time (min)':[0.,1.], 'Absorbance (mAU)':[2.,3.]})
    channels=[{'name':f'UV {wl} nm (Ch {i})','data':data.copy(),'column_roles':roles,
               'metadata':{'wavelength_nm':wl,'detector_channel':f'Ch{i}'}} for i,wl in enumerate([254,280],1)]
    return StandardizedResult(data,roles,FileIdentity('run.txt','txt','test_multichannel',2),
        source_category=SourceCategory.CHROMATOGRAM,sample_name='Sample A',metadata={
        'chromatogram_channels':channels,'acquisition_time':'2026-07-30T13:40:04',
        'pda':{'time_min':[0.,1.],'wavelength_nm':[254.,280.], 'absorbance_mau':[[2.,5.],[3.,6.]]}})


def test_channels_are_independent_signals_and_matrix_is_owned_once():
    sr=multichannel(); bundle,=assign_bundles([('run.txt',b'original',sr)])
    assert bundle.bundle_type.value=='chromatogram'
    assert bundle.name=='Sample A'
    assert len(bundle.component_list)==2
    first,second=bundle.component_list
    assert bundle.component_display_name(first)=='UV 254 nm (Ch 1)'
    assert second.metadata['pda_source_id']==first.component_id
    assert second.metadata['source_file_id']==first.component_id
    assert 'pda' not in second.metadata and 'chromatogram_channels' not in first.metadata
    assert first.raw_bytes==b'original' and not second.raw_bytes
    store=DataStore();store.add_bundle(bundle)
    assert set(store.loaded_data)=={first.component_id,second.component_id}
    assert all(store.peak_owner_id(c.component_id)==c.component_id for c in bundle.component_list)
    assert store.peak_owner_id(bundle.bundle_id)==first.component_id
    assert len(store.get_bundled_tree_items()[0]['children'])==2
    assert store.get_data_by_id(second.component_id)['standardized'].y_columns==['Absorbance (mAU)']
    assert 'chromatogram_channels' in sr.metadata  # parsing result remains untouched


def test_single_channel_retains_identity_when_an_extracted_trace_is_added():
    sr=multichannel();sr.metadata['chromatogram_channels']=sr.metadata['chromatogram_channels'][:1]
    bundle,=assign_bundles([('run.txt',b'original',sr)])
    store=DataStore();store.add_bundle(bundle)
    assert set(store.loaded_data)=={bundle.primary.component_id}
    assert store.peak_owner_id(bundle.primary.component_id)==bundle.primary.component_id


def test_fair_export_includes_full_pda_matrix_with_units_and_source_links():
    bundle,=assign_bundles([('run.txt',b'original',multichannel())])
    store=DataStore();store.add_bundle(bundle)
    z=zipfile.ZipFile(io.BytesIO(build_research_package(store,{},formats=[])))
    document=json.loads(z.read('metadata/dataset.json'))
    first,second=document['signals']
    pda=first['metadata']['pda']
    assert pda['time_unit']=='min' and pda['wavelength_unit']=='nm' and pda['intensity_unit']=='mAU'
    frame=pd.read_csv(io.BytesIO(z.read(pda['matrix_csv'])))
    assert frame.columns.tolist()==['Time (min)','254','280']
    assert frame.iloc[:,1:].values.tolist()==[[2.,5.],[3.,6.]]
    assert 'absorbance_mau' not in pda
    assert second['original_file']==first['original_file']
    assert len([n for n in z.namelist() if n.startswith('raw_data/originals/')])==1


def test_history_records_matrix_identity_without_repeating_all_measurements():
    from services.research_package import record_analysis_state
    bundle,=assign_bundles([('run.txt',b'original',multichannel())])
    store=DataStore();store.add_bundle(bundle)
    record_analysis_state(store)
    pda=store.analysis_history[-1]['changes']['signals']['after'][bundle.primary.component_id]['metadata']['pda']
    assert 'absorbance_mau' not in pda and pda['shape']==[2,2]
    assert len(pda['data_sha256'])==64
    bundle.primary.metadata['pda']['absorbance_mau'][0][0]=9
    record_analysis_state(store)
    later=store.analysis_history[-1]['changes']['signals']['after'][bundle.primary.component_id]['metadata']['pda']
    assert later['data_sha256'] != pda['data_sha256']


def test_metadata_view_summarises_pda_measurements_without_dumping_matrix():
    from callbacks.viz_callbacks import create_data_table
    from components.workspace_layout import walk
    bundle,=assign_bundles([('run.txt',b'original',multichannel())])
    store=DataStore();store.add_bundle(bundle)
    panel=create_data_table(store.get_data_by_id(bundle.primary.component_id))
    text=' '.join(str(n.children) for n in walk(panel) if isinstance(getattr(n,'children',None),str))
    assert '2 time points × 2 wavelengths' in text
    assert '[[2.0, 5.0], [3.0, 6.0]]' not in text
