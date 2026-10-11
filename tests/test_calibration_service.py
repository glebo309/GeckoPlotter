import json
from copy import deepcopy
import numpy as np
import pytest
from services.calibration_service import CalibrationService, CalibrationPoint


def measured(service, fit_type='linear', xs=(0,1,2), ys=(1,3,5), force_zero=False):
    model=service.create_model('Analyte','group',fit_type,force_zero,units='mM')
    for i,(x,y) in enumerate(zip(xs,ys)):
        service.add_standard(model.model_id,str(i),x,y)
    return model


def test_model_response_matching_options_roundtrip_and_old_defaults():
    s=CalibrationService()
    m=s.create_model('A','g',response_type='height',response_units='mAU',match_position=4.2,
        match_tolerance=.15,signal_key='UV280',x_units='min',auto_apply=False)
    exported=s.export_model(m.model_id)
    restored=CalibrationService();restored.deserialize(s.serialize());m2=restored.get_model(m.model_id)
    assert (m2.response_type,m2.response_units,m2.match_position,m2.match_tolerance,m2.signal_key,m2.x_units,m2.auto_apply)==('height','mAU',4.2,.15,'UV280','min',False)
    for key in ('response_type','response_units','match_position','match_tolerance','signal_key','x_units','auto_apply'):
        exported.pop(key)
    old=restored.import_calibrations(exported)[0]
    assert old.response_type=='area' and old.auto_apply is True and old.match_position is None


@pytest.mark.parametrize('fit_type,force_zero,xs,ys',[
    ('linear',False,[1,1,1],[1,2,3]), ('linear',True,[0,0],[1,2]),
    ('quadratic',False,[0,1],[1,2]), ('quadratic',False,[0,1,1],[1,2,3]),
    ('quadratic',True,[0,1],[0,2]), ('power',False,[1,1],[1,2]),
    ('linear',False,[-1,1],[1,3]), ('linear',False,[0,np.nan],[1,3]),
    ('linear',False,[0,1],[1,np.inf]), ('linear',False,[0,1],[2,2]),
])
def test_invalid_standards_cannot_create_a_fit(fit_type,force_zero,xs,ys):
    s=CalibrationService();m=measured(s,fit_type,xs,ys,force_zero)
    with pytest.raises(ValueError):s.fit_model(m.model_id)
    assert m.coefficients is None


@pytest.mark.parametrize('fit_type,zero,xs,ys,expected',[
    ('linear',False,[0,1,2],[1,3,5],[2,1]),
    ('linear',True,[0,1,2],[0,3,6],[3,0]),
    ('quadratic',False,[0,1,2],[1,4,9],[1,2,1]),
    ('quadratic',True,[1,2,3],[3,8,15],[1,2,0]),
    ('power',False,[1,2,3],[2,8,18],[2,2]),
])
def test_valid_fits_remain_accurate(fit_type,zero,xs,ys,expected):
    s=CalibrationService();m=measured(s,fit_type,xs,ys,zero);s.fit_model(m.model_id)
    assert m.coefficients==pytest.approx(expected)
    assert m.r_squared==pytest.approx(1)


def test_update_standards_invalidates_fit_and_copies_input():
    s=CalibrationService();m=measured(s);s.fit_model(m.model_id)
    points=[CalibrationPoint('new',1,4)]
    s.update_standards(m.model_id,points);points[0].area=999
    assert m.coefficients is None and m.r_squared is None and m.residuals is None
    assert m.standards[0].area==4


def test_quadratic_inversion_uses_unique_calibrated_root_and_rejects_ambiguity():
    s=CalibrationService();m=measured(s,'quadratic',[3,4,5],[1,4,9]);s.fit_model(m.model_id)
    assert s.predict_concentration(m.model_id,1)==pytest.approx(3) # roots 1 and 3
    m.standards=[CalibrationPoint('low',0,4),CalibrationPoint('high',4,4)]
    assert s.predict_concentration(m.model_id,1) is None # both roots within range
    m.standards=[]
    assert s.predict_concentration(m.model_id,1) is None
    assert s.predict_concentration(m.model_id,0)==pytest.approx(2) # repeated root


def test_nonfinite_or_negative_prediction_is_not_reported_as_concentration():
    s=CalibrationService();m=measured(s);s.fit_model(m.model_id)
    for response in (np.nan,np.inf,-10):assert s.predict_concentration(m.model_id,response) is None


def test_portable_import_refits_real_points_instead_of_trusting_coefficients():
    s=CalibrationService();m=measured(s);s.fit_model(m.model_id)
    payload=s.export_calibrations([m.model_id]);assert payload['format']=='geckoplotter-calibrations' and payload['version']==1
    payload['models'][0]['coefficients']=[1000,500]
    restored=CalibrationService();models=restored.import_calibrations(json.dumps(payload))
    assert models[0].coefficients==pytest.approx([2,1])
    assert restored.predict_concentration(models[0].model_id,5)==pytest.approx(2)
    assert len(restored.import_calibrations(restored.serialize()))==1
    assert len(restored.get_all_models())==2 # importing never overwrites a live model


def legacy():
    return {'standards':{'g':{'name':'Caffeine','sample1':1,'sample2':2}},
            'calibration_models':{'g':{'name':'Caffeine','rt':4.2,'model_type':'linear',
                'parameters':{'slope':10,'intercept':2},'r_squared':.99,'units':'mg/L','force_zero':False,
                'standards':{'sample1':1,'sample2':2}}}}


def test_streamlit_coefficients_do_not_fabricate_measured_responses():
    s=CalibrationService();m=s.import_calibrations(legacy())[0]
    assert m.coefficients==[10,2] and m.standards==[] and m.residuals is None
    assert m.reference_concentrations=={'sample1':1,'sample2':2}
    assert m.match_position==4.2 and m.x_units=='min' and m.units=='mg/L'
    assert s.predict_concentration(m.model_id,22)==2
    restored=CalibrationService().import_calibrations(s.export_calibrations())[0]
    assert restored.reference_concentrations==m.reference_concentrations


def test_streamlit_raw_data_is_refitted_and_excluded_points_preserved():
    payload=legacy();payload['standards']['g']['raw_data']=[
        {'sample_name':'a','concentration':0,'area':1},
        {'sample_name':'b','concentration':1,'area':3},
        {'sample_name':'c','concentration':2,'area':999,'included':False}]
    m=CalibrationService().import_calibrations(payload)[0]
    assert m.coefficients==pytest.approx([2,1]) and len(m.standards)==3
    assert m.standards[-1].included is False


@pytest.mark.parametrize('fit_type,params,expected',[
    ('linear',{'m':4,'b':2},[4,2]),('quadratic',{'a':2,'b':3,'c':1},[2,3,1]),
    ('power law',{'a':2,'b':1.5},[2,1.5]),
])
def test_legacy_parameter_names(fit_type,params,expected):
    payload=legacy();payload['calibration_models']['g'].update(model_type=fit_type,parameters=params)
    m=CalibrationService().import_calibrations(payload)[0]
    assert m.coefficients==expected


@pytest.mark.parametrize('change',[
    {'parameters':{'slope':np.inf}}, {'parameters':{'slope':0}}, {'model_type':'arbitrary'},
    {'parameters':{}}, {'rt':np.nan},
])
def test_invalid_import_is_atomic(change):
    s=CalibrationService();existing=s.create_model('Existing','current')
    payload=legacy();payload['calibration_models']['bad']=deepcopy(payload['calibration_models']['g'])
    payload['calibration_models']['bad'].update(change)
    with pytest.raises(ValueError):s.import_calibrations(payload)
    assert list(s.get_all_models())==[existing.model_id]


def test_unknown_portable_version_rejected():
    with pytest.raises(ValueError):CalibrationService().import_calibrations({'format':'geckoplotter-calibrations','version':22,'models':[]})


def test_standard_provenance_survives_portable_roundtrip():
    s=CalibrationService();m=s.create_model('A','g')
    s.update_standards(m.model_id,[CalibrationPoint('a',1,10,source_id='file:peak1',position=4.1),
                                 CalibrationPoint('b',2,20,source_id='file:peak2',position=4.2)])
    result=CalibrationService().import_calibrations(s.export_calibrations())[0]
    assert [(p.source_id,p.position) for p in result.standards]==[('file:peak1',4.1),('file:peak2',4.2)]


def test_response_label_uses_selected_response_and_units():
    s=CalibrationService();m=s.create_model('A','g',response_type='height',response_units='mAU')
    s.update_standards(m.model_id,[CalibrationPoint('a',1,2),CalibrationPoint('b',2,4)])
    s.fit_model(m.model_id)
    assert s.create_calibration_figure(m.model_id).layout.yaxis.title.text=='Peak height (mAU)'


def test_legacy_concentration_references_bound_inverse_without_fabricating_points():
    payload=legacy();payload['standards']['g'].update(sample1=3,sample2=5)
    payload['calibration_models']['g'].update(model_type='quadratic',parameters={'a':1,'b':-4,'c':4},standards={'sample1':3,'sample2':5})
    s=CalibrationService();m=s.import_calibrations(payload)[0]
    assert s.predict_concentration(m.model_id,1)==pytest.approx(3)
    figure=s.create_calibration_figure(m.model_id)
    assert [trace.name for trace in figure.data]==['Fit']
    assert m.standards==[]


def test_replace_model_updates_same_id_atomically_and_detaches_editor_copy():
    s=CalibrationService();m=measured(s);s.fit_model(m.model_id)
    for i in range(3):
        edit=deepcopy(s.get_model(m.model_id));edit.analyte_name=f'Edited {i}'
        saved=s.replace_model(edit)
        assert saved.model_id==m.model_id and len(s.get_all_models())==1
        edit.standards[0].area=999
        assert saved.standards[0].area==1
    before=s.serialize();invalid=deepcopy(saved);invalid.standards[0].concentration=-2
    with pytest.raises(ValueError):s.replace_model(invalid)
    assert s.serialize()==before


@pytest.mark.parametrize('coefficients',['12',{'slope':2},[[2],1],[float('nan'),1],[0,2]])
def test_import_rejects_malformed_coefficient_structure(coefficients):
    s=CalibrationService();record=s.export_model(s.create_model('A','g').model_id)
    record['coefficients']=coefficients
    with pytest.raises(ValueError):CalibrationService().import_calibrations(record)


@pytest.mark.parametrize('change',[
    {'model_type':'power law','parameters':{'a':-1,'b':2}},
    {'model_type':'power law','parameters':{'a':1,'b':0}},
    {'force_zero':True,'parameters':{'slope':1,'intercept':3}},
])
def test_legacy_invalid_inverse_parameters_are_rejected(change):
    payload=legacy();payload['calibration_models']['g'].update(change)
    with pytest.raises(ValueError):CalibrationService().import_calibrations(payload)


def test_legacy_negative_reference_concentrations_are_rejected():
    payload=legacy();payload['calibration_models']['g']['standards']['sample1']=-1
    with pytest.raises(ValueError):CalibrationService().import_calibrations(payload)
