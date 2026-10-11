from types import SimpleNamespace as NS
import pytest
from services.calibration_service import CalibrationService
from services.calibration_workflow import peak_candidates, apply_calibrations


def fixture():
    peaks = {}
    entries = {}
    dm = NS(peak_service=NS(get_all_peaks=lambda: peaks), calibration_service=CalibrationService(),
            get_data_by_id=lambda fid: entries.get(fid))
    def add(fid, position=5., area=20., wavelength=280, polarity=None, x='Time (min)', y='Absorbance (mAU)', category='chromatogram'):
        peak = NS(peak_id='peak', file_id=fid, name='Analyte', label='', rt=position,
                  rt_start=4., rt_end=6., area=area, height=10., concentration=None, calibration_id=None)
        peaks[fid] = [peak]
        metadata = {'wavelength_nm': wavelength} if wavelength else {}
        if polarity: metadata['ionization_mode'] = polarity
        entries[fid] = {'record': {'name': fid}, 'metadata': metadata,
                        'standardized': NS(x_columns=[x], y_columns=[y], source_category=category, metadata={})}
        return peak
    return dm, add


def model(dm, row, name='Compound'):
    calibration = dm.calibration_service.create_model(name, '', units='mM')
    for key, value in dict(response_type='area', signal_key=row['signal_key'], x_units=row['x_units'],
                           response_units=row['response_units'], match_position=row['position'],
                           match_tolerance=.1, auto_apply=True).items():
        setattr(calibration, key, value)
    dm.calibration_service.add_standard(calibration.model_id, 'low', 1., 10.)
    dm.calibration_service.add_standard(calibration.model_id, 'high', 3., 30.)
    dm.calibration_service.fit_model(calibration.model_id)
    return calibration


def test_candidates_have_stable_identity_and_apex_coordinate_not_sample_name_matching():
    dm, add = fixture(); add('standard'); add('unknown', position=5.03)
    rows = peak_candidates(dm)
    assert [r['id'] for r in rows] == ['standard:peak', 'unknown:peak']
    assert rows[0]['signal_key'] == rows[1]['signal_key']
    assert rows[1]['position'] == 5.03 and rows[1]['position_source'] == 'apex'
    assert rows[0]['x_units'] == 'min' and rows[0]['response_units'] == 'mAU·min'
    assert rows[0]['response'] == 20. and rows[0]['height'] == 10.


def test_unique_compatible_model_predicts_only_same_position_signal_and_units():
    dm, add = fixture(); peak = add('standard'); good = add('unknown', position=5.04)
    wrong_rt = add('other peak', position=7.); wrong_uv = add('250nm', wavelength=250)
    wrong_unit = add('AU', y='Absorbance (AU)')
    cal = model(dm, peak_candidates(dm)[0]); result = apply_calibrations(dm)
    assert good.concentration == pytest.approx(2.) and good.calibration_id == cal.model_id
    assert result['unknown:peak']['status'] == 'Calibrated'
    assert result['unknown:peak']['units'] == 'mM'
    assert all(p.concentration is None for p in (wrong_rt, wrong_uv, wrong_unit))


def test_ms_modes_and_spectral_channels_are_distinct():
    dm, add = fixture()
    add('positive', wavelength=None, polarity='positive', y='Ion Count')
    add('negative', wavelength=None, polarity='negative', y='Ion Count')
    add('spectrumA', wavelength=None, category='spectrum', x='Wavelength (nm)', y='Channel A (AU)')
    add('spectrumB', wavelength=None, category='spectrum', x='Wavelength (nm)', y='Channel B (AU)')
    assert len({r['signal_key'] for r in peak_candidates(dm)}) == 4
    model(dm, peak_candidates(dm)[0]); result = apply_calibrations(dm)
    assert result['negative:peak']['concentration'] is None


def test_spectrum_peak_coordinate_matches_without_retention_time_assumption():
    dm, add = fixture(); add('standard', position=450., wavelength=None, category='spectrum', x='Wavelength (nm)', y='Absorbance (AU)')
    unknown = add('unknown', position=450.02, area=40., wavelength=None, category='spectrum', x='Wavelength (nm)', y='Absorbance (AU)')
    model(dm, peak_candidates(dm)[0]); result = apply_calibrations(dm)
    assert unknown.concentration == pytest.approx(4.)
    assert result['unknown:peak']['status'] == 'Outside calibration range'


def test_multiple_matching_models_are_ambiguous_and_clear_previous_prediction():
    dm, add = fixture(); peak = add('unknown'); row = peak_candidates(dm)[0]
    model(dm, row, 'A'); apply_calibrations(dm); assert peak.concentration is not None
    model(dm, row, 'B'); result = apply_calibrations(dm)
    assert peak.concentration is None and peak.calibration_id is None
    assert result[row['id']]['status'] == 'Ambiguous calibration'


def test_removed_or_invalidated_model_clears_stale_concentration():
    dm, add = fixture(); peak = add('unknown'); cal = model(dm, peak_candidates(dm)[0])
    apply_calibrations(dm); dm.calibration_service.add_standard(cal.model_id, 'new', 4., 40.)
    result = apply_calibrations(dm)
    assert peak.concentration is None and peak.calibration_id is None
    assert result['unknown:peak']['status'] == 'No matching calibration'


def test_missing_apex_uses_explicit_midpoint_and_invalid_response_is_not_predicted():
    dm, add = fixture(); peak = add('unknown', position=None)
    row = peak_candidates(dm)[0]; assert row['position'] == 5. and row['position_source'] == 'midpoint'
    model(dm, row); peak.area = float('nan'); result = apply_calibrations(dm)
    assert peak.concentration is None
    assert result['unknown:peak']['status'] == 'Invalid response'


def test_two_close_peaks_in_one_signal_are_ambiguous_instead_of_both_quantified():
    dm, add = fixture(); first = add('unknown'); row = peak_candidates(dm)[0]
    second = NS(**vars(first)); second.peak_id = 'nearby'; second.rt = 5.04
    dm.peak_service.get_all_peaks()['unknown'].append(second)
    model(dm, row); result = apply_calibrations(dm)
    assert first.concentration is None and second.concentration is None
    assert result['unknown:peak']['status'] == 'Ambiguous peak match'


def test_height_calibration_uses_height_and_height_units():
    dm, add = fixture(); peak = add('unknown', area=1000.)
    row = peak_candidates(dm)[0]; cal = model(dm, row)
    cal.response_type = 'height'; cal.response_units = row['height_units']
    result = apply_calibrations(dm)
    assert peak.concentration == pytest.approx(1.)
    assert result[row['id']]['concentration'] == pytest.approx(1.)


def test_disabled_model_and_unit_changes_do_not_apply_or_keep_stale_values():
    dm, add = fixture(); peak = add('unknown'); row = peak_candidates(dm)[0]; cal = model(dm, row)
    apply_calibrations(dm); cal.auto_apply = False
    assert apply_calibrations(dm)[row['id']]['concentration'] is None
    cal.auto_apply = True; cal.x_units = 's'
    assert apply_calibrations(dm)[row['id']]['concentration'] is None


def test_peaks_table_exposes_read_only_calibration_values_and_refresh_dependency():
    from test_lcms_peak_table import fixture as table_fixture
    from test_peak_owner_aliases import add
    dm, app, table = table_fixture(); peak = add(dm.peak_service, 'component')
    row = peak_candidates(dm)[0]; cal = model(dm, row)
    data, columns, _, _ = table('component', 1, 0, 0, 'peak-analysis', 1, [])
    displayed = next(r for r in data if r['peak_id'] == peak.peak_id)
    assert displayed['Concentration'] == pytest.approx(.5)
    assert displayed['Concentration units'] == 'mM'
    assert displayed['Calibration'] == 'Compound'
    assert displayed['Calibration status'] == 'Outside calibration range'
    assert all(not c['editable'] for c in columns if c['id'].startswith('Calib') or c['id'].startswith('Concentration'))
    assert any(dep.component_id == 'cal-revision' for dep in app.registrations['update_peak_analysis_tab'][1])


def test_candidate_follows_integrated_channel_override_and_bundle_sample_label():
    dm, add = fixture(); add('channel'); entry = dm.get_data_by_id('channel')
    entry['metadata'].update(auto_y=['Channel B (AU)'], auto_x='Wavelength (nm)', parent_bundle_name='Standard 2 mM')
    entry['record']['name'] = 'UV channel'
    row = peak_candidates(dm)[0]
    assert row['sample'] == 'Standard 2 mM'
    assert row['height_units'] == 'AU' and row['x_units'] == 'nm'
    assert 'channel b' in row['signal_key']


def test_calibration_boundary_roundoff_is_not_flagged_as_extrapolation():
    dm, add = fixture(); add('standard', area=10.); row = peak_candidates(dm)[0]
    model(dm, row)
    assert apply_calibrations(dm)[row['id']]['status'] == 'Calibrated'


@pytest.mark.parametrize('left,right', [
    ('Absorbance Solution #3', 'Absorbance Solution #4'),
    ('Absorbance (Solution #3)', 'Absorbance (Solution #4)'),
])
def test_uv_sample_suffix_does_not_become_signal_identity_or_response_units(left, right):
    dm, add = fixture()
    add('standard', position=450., wavelength=None, x='Wavelength (nm)', y=left, category='spectrum')
    unknown = add('unknown', position=450., wavelength=None, x='Wavelength (nm)', y=right, category='spectrum')
    rows = peak_candidates(dm)
    assert rows[0]['signal_key'] == rows[1]['signal_key']
    assert rows[0]['height_units'] == rows[1]['height_units'] == ''
    assert rows[0]['response_units'] == rows[1]['response_units'] == 'nm'
    model(dm, rows[0]); apply_calibrations(dm)
    assert unknown.concentration == pytest.approx(2.)


def test_retention_time_alias_and_category_case_preserve_same_signal_identity():
    dm, add = fixture()
    add('standard', x='Retention Time (min)', category='CHROMATOGRAM')
    add('unknown', x='Time (min)', category='chromatogram')
    rows = peak_candidates(dm)
    assert rows[0]['signal_key'] == rows[1]['signal_key']
    assert rows[0]['x_units'] == rows[1]['x_units'] == 'min'


def test_normalization_keeps_channels_wavelengths_and_unknown_numbered_names_distinct():
    dm, add = fixture()
    for index, label in enumerate(('Absorbance Channel #3', 'Absorbance Channel #4',
                                   'Absorbance 280 nm Solution #3', 'Absorbance 250 nm Solution #4',
                                   'Transmittance Solution #3')):
        add(str(index), wavelength=None, x='Wavelength (nm)', y=label, category='spectrum')
    assert len({row['signal_key'] for row in peak_candidates(dm)}) == 5


def test_pre_normalization_saved_signal_key_still_matches_same_measurement():
    import json
    dm, add = fixture(); unknown = add('unknown', wavelength=None, x='Time (min)', y='Absorbance Solution #4')
    row = peak_candidates(dm)[0]; cal = model(dm, row)
    old_key = json.loads(cal.signal_key)
    old_key.update(category='CHROMATOGRAM', x='retention time (min)', y=['absorbance solution #3'])
    cal.signal_key = json.dumps(old_key)
    apply_calibrations(dm)
    assert unknown.concentration == pytest.approx(2.)
    # Compatibility must not widen matching to another detector channel.
    old_key['y'] = ['absorbance channel #3']; cal.signal_key = json.dumps(old_key)
    apply_calibrations(dm)
    assert unknown.concentration is None


def test_external_opaque_signal_keys_are_not_reinterpreted():
    from services.calibration_workflow import _canonical_signal_key
    assert _canonical_signal_key('uv280') == 'uv280'
    assert _canonical_signal_key('{invalid') == '{invalid'
    assert _canonical_signal_key('123') == '123'
