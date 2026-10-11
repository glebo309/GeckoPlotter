import copy
import pytest
from callbacks.calibration_callbacks import add_peak_rows, fit_calibration_form
from services.calibration_service import CalibrationService


def candidate(key, position=5., signal='uv:280'):
    return dict(id=key, file_id=key, peak_id='p', sample=key, peak_name='Peak 1',
                position=position, response=20., height=4., signal_key=signal,
                x_units='min', response_units='mAU min', height_units='mAU')


def test_add_selected_peaks_preserves_concentration_and_avoids_duplicates():
    rows = [dict(id='a', sample_name='A', concentration=2, area=20, position=5.)]
    result = add_peak_rows(rows, ['a', 'b'], [candidate('a'), candidate('b')], 'area')
    assert len(result) == 2
    assert result[0]['concentration'] == 2
    assert result[1]['concentration'] is None
    assert result[1]['signal_key'] == 'uv:280'


def test_do_not_mix_uv_channels_in_standards():
    rows = add_peak_rows([], ['a'], [candidate('a')], 'area')
    with pytest.raises(ValueError, match='signal'):
        add_peak_rows(rows, ['b'], [candidate('b', signal='uv:250')], 'area')


def form_rows():
    rows = add_peak_rows([], ['a', 'b', 'c'], [candidate('a'),candidate('b'),candidate('c')], 'area')
    for row, concentration in zip(rows, [1, 2, 3]):
        row.update(concentration=concentration, area=concentration*10+2)
    return rows


def test_fit_form_creates_matching_model_and_keeps_unchecked_points():
    svc = CalibrationService()
    model = fit_calibration_form(svc, None, form_rows(), [0,1], name='Caffeine',units='mM',
        fit_type='linear',force_zero=False,response_type='area',position=5.,tolerance=.2,auto_apply=True)
    assert model.coefficients == pytest.approx([10,2])
    assert model.match_position == 5
    assert model.signal_key == 'uv:280'
    assert model.standards[2].included is False
    assert model.standards[0].source_id == 'a'


def test_invalid_fit_does_not_replace_previous_calibration():
    svc = CalibrationService()
    kwargs=dict(name='Test',units='mM',fit_type='linear',force_zero=False,response_type='area',position=5.,tolerance=.2,auto_apply=True)
    model = fit_calibration_form(svc, None, form_rows(), [0,1,2], **kwargs)
    saved=copy.deepcopy(svc.serialize())
    rows=form_rows(); rows[1]['concentration']='not a number'
    with pytest.raises(ValueError):
        fit_calibration_form(svc, model.model_id, rows, [0,1,2], **kwargs)
    assert svc.serialize() == saved


def test_nonstandard_blank_rows_can_be_excluded():
    svc=CalibrationService(); rows=form_rows(); rows[2]['concentration']=None
    model=fit_calibration_form(svc,None,rows,[0,1],name='Test',units='mM',fit_type='linear',force_zero=False,response_type='area',position=5.,tolerance=.2,auto_apply=True)
    assert len(model.standards)==2


def test_loaded_standard_positions_must_belong_to_matching_peak():
    svc=CalibrationService(); rows=form_rows();rows[1]['position']=8
    with pytest.raises(ValueError, match='tolerance'):
        fit_calibration_form(svc,None,rows,[0,1],name='Test',units='mM',fit_type='linear',force_zero=False,response_type='area',position=5.,tolerance=.2,auto_apply=True)


def test_refit_updates_model_in_place_without_ambiguous_duplicates():
    svc=CalibrationService()
    kwargs=dict(name='Test',units='mM',fit_type='linear',force_zero=False,response_type='area',position=5.,tolerance=.2,auto_apply=True)
    model=fit_calibration_form(svc,None,form_rows(),[0,1,2],**kwargs)
    refit=fit_calibration_form(svc,model.model_id,form_rows(),[0,1,2],**kwargs)
    assert refit.model_id == model.model_id
    assert len(svc.get_all_models())==1
