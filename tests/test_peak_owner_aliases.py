from dataclasses import replace
import pytest
from test_data_store import make_component
from src.services.data_store import Bundle, BundleType, ComponentRole, DataStore


def setup(kind=BundleType.GENERIC):
    dm=DataStore()
    primary=make_component('component','blue.csv')
    secondary=make_component('other','other.csv',role=ComponentRole.VWD_A)
    dm.add_bundle(Bundle(bundle_id='bundle',name='blue',bundle_type=kind,
                         component_list=[primary] if kind==BundleType.GENERIC else [primary,secondary]))
    return dm


def add(service,file_id='bundle'):
    return service.add_baseline_peak(file_id=file_id,area=5.,height=3.,apex_x=1.,
        poly_x=[0,1,2,2,1,0],poly_y=[0,3,0,0,0,0],p_line=[(0,0),(2,0)],q1=(0,0),q2=(2,0))


def test_bundle_draw_is_visible_and_editable_when_primary_component_is_selected():
    dm=setup();p=add(dm.peak_service)
    assert dm.peak_service.get_peaks('component')==[p]
    assert len(dm.peak_service.peaks_to_table('component'))==1
    assert len(dm.peak_service.to_dataframe('component'))==1
    assert dm.peak_service.rename_peak('component',p.peak_id,'UV band')
    assert dm.peak_service.get_peaks('bundle')[0].name=='UV band'
    assert dm.peak_service.remove_peak('component',p.peak_id)
    assert dm.peak_service.get_peaks('bundle')==[]


def test_component_integration_and_bundle_selection_use_one_storage_owner():
    dm=setup();p=add(dm.peak_service,'component')
    assert p.file_id=='bundle'
    assert dm.peak_service.get_peaks('bundle')==[p]
    dm.peak_service.clear_manual_peaks('component')
    assert dm.peak_service.get_peaks('bundle')==[]


def test_legacy_component_keyed_peaks_migrate_without_discarding_identity():
    dm=setup();p=add(dm.peak_service)
    snapshot=dm.peak_service.serialize()
    item=snapshot['peaks'].pop('bundle')[0];item['file_id']='component'
    snapshot['peaks']['component']=[item]
    dm.peak_service.deserialize(snapshot)
    restored=dm.peak_service.get_peaks('bundle')
    assert len(restored)==1
    assert restored[0].peak_id==p.peak_id
    assert restored[0].file_id=='bundle'
    assert set(dm.peak_service.get_all_peaks())=={'bundle'}


def test_chromeleon_primary_alias_does_not_merge_secondary_signal():
    dm=setup(BundleType.CHROMELEON);p=add(dm.peak_service,'component');other=add(dm.peak_service,'other')
    assert p.file_id=='bundle';assert other.file_id=='other'
    assert dm.peak_service.get_peaks('bundle')==[p]
    assert dm.peak_service.get_peaks('other')==[other]


def test_lcms_channels_keep_independent_peak_owners():
    dm=setup(BundleType.LCMS);p=add(dm.peak_service,'component');other=add(dm.peak_service,'other')
    assert p.file_id=='component';assert other.file_id=='other'
    assert dm.peak_service.get_peaks('component')==[p]
    assert dm.peak_service.get_peaks('other')==[other]


def test_owner_resolver_survives_empty_workspace_reset():
    dm=setup();dm.reset_workspace()
    dm.add_bundle(Bundle(bundle_id='bundle',name='blue',bundle_type=BundleType.GENERIC,component_list=[make_component('component')]))
    p=add(dm.peak_service,'component')
    assert dm.peak_service.get_peaks('bundle')==[p]
