"""Exercise the registered editor callback, including its hydration echoes."""
import base64
import copy
import json
from types import SimpleNamespace

import dash
import pytest
from callbacks.calibration_callbacks import register_calibration_callbacks
from test_calibration_workflow import fixture


class Editor:
    fields = ['name', 'units', 'fit_type', 'force_zero', 'response_type', 'position', 'tolerance', 'auto_apply']

    def __init__(self, monkeypatch):
        self.dm, add = fixture()
        add('low', area=10.).height = 5.
        add('high', area=30.).height = 15.
        add('unknown', area=20.).height = 10.
        app = dash.Dash(__name__)
        register_calibration_callbacks(app, self.dm)
        self.callbacks = {item['callback'].__wrapped__.__name__: item['callback'].__wrapped__
                          for item in app.callback_map.values()}
        self.monkeypatch = monkeypatch
        self.values = dict(name='', units='mM', fit_type='linear', force_zero=False,
                           response_type='area', position=None, tolerance=.2, auto_apply=True)
        self.model_id = None
        self.rows = []
        self.included = []
        self.revision = 0
        self.picked = []
        self.upload = None
        self.import_peaks = None

    @property
    def model(self):
        return self.dm.calibration_service.get_model(self.model_id)

    def run(self, trigger):
        self.monkeypatch.setattr(dash, 'ctx', SimpleNamespace(triggered_id=trigger))
        result = self.callbacks['edit_calibration'](1, 1, 1, 1, self.upload, self.model_id,
            1, self.included, 1, *[self.values[field] for field in self.fields],
            self.import_peaks, self.rows, self.picked, self.revision)
        if result[1] is not dash.no_update:
            self.model_id = result[1]
        if result[2] is not dash.no_update:
            self.rows = copy.deepcopy(result[2])
        if result[3] is not dash.no_update:
            self.included = list(result[3])
        for field, value in zip(self.fields, result[4:12]):
            if value is not dash.no_update:
                self.values[field] = value
        if result[-2] is not dash.no_update:
            self.revision = result[-2]
        return result

    def fitted(self, with_unknown=False):
        self.run('cal-new-btn')
        self.picked = ['low:peak', 'high:peak'] + (['unknown:peak'] if with_unknown else [])
        self.run('cal-add-peaks-btn')
        self.rows[0]['concentration'] = 1.
        self.rows[1]['concentration'] = 3.
        self.included = [0, 1]
        self.run('cal-standards-table')
        return self.run('cal-fit-btn')


def test_full_registered_workflow_fits_and_hydration_echo_does_not_invalidate(monkeypatch):
    editor = Editor(monkeypatch); result = editor.fitted()
    assert editor.model.coefficients == pytest.approx([10., 0.])
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.)
    assert result[-1] is False
    for trigger in ('cal-active-model', 'cal-analyte-name', 'cal-units', 'cal-response-type',
                    'cal-fit-type', 'cal-force-zero', 'cal-match-position', 'cal-match-tolerance',
                    'cal-auto-apply', 'cal-standards-table'):
        editor.run(trigger)
        assert editor.model.coefficients == pytest.approx([10., 0.]), trigger


def test_refitting_does_not_create_duplicate_models_or_ambiguous_predictions(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted(); model_id = editor.model_id
    for _ in range(3):
        editor.run('cal-fit-btn')
    assert editor.model_id == model_id
    assert len(editor.dm.calibration_service.get_all_models()) == 1
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.)


def test_dirty_concentration_clears_prediction_and_save_then_refit_restores(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted(); old_revision = editor.revision
    editor.rows[0]['concentration'] = 2.
    result = editor.run('cal-standards-table')
    assert editor.model.coefficients is None and result[-1] is True
    assert editor.revision > old_revision
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration is None
    editor.run('cal-fit-btn')
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.5)


def test_response_switch_after_fit_uses_measured_heights_and_preserves_concentrations(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted()
    editor.values['response_type'] = 'height'; editor.run('cal-response-type')
    assert [row['area'] for row in editor.rows] == [5., 15.]
    assert [row['concentration'] for row in editor.rows] == [1., 3.]
    assert editor.model.coefficients is None
    editor.run('cal-fit-btn')
    assert editor.model.response_type == 'height'
    assert editor.model.coefficients == pytest.approx([5., 0.])
    assert editor.model.response_units == 'mAU'
    editor.values['response_type'] = 'area'; editor.run('cal-response-type')
    assert [row['area'] for row in editor.rows] == [10., 30.]


def test_blank_unknown_row_excluded_from_fit_but_receives_matching_prediction(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted(with_unknown=True)
    assert len(editor.model.standards) == 2
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.)


def test_json_save_load_preserves_coefficients_and_editor_state(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted()
    saved = editor.callbacks['save_calibration'](1, editor.model_id)
    payload = json.loads(saved['content'])
    restored = Editor(monkeypatch)
    restored.upload = 'data:application/json;base64,' + base64.b64encode(json.dumps(payload).encode()).decode()
    restored.run('cal-load-upload')
    assert restored.model.coefficients == pytest.approx(editor.model.coefficients)
    assert restored.values == editor.values
    assert [r['concentration'] for r in restored.rows] == [1., 3.]
    assert restored.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.)
    restored.run('cal-response-type')
    assert restored.model.coefficients is not None


def test_legacy_import_links_to_reference_without_refitting_and_reports_active_match(monkeypatch):
    from test_calibration_service import legacy
    editor = Editor(monkeypatch)
    editor.upload = 'data:application/json;base64,' + base64.b64encode(json.dumps(legacy()).encode()).decode()
    editor.run('cal-load-upload'); before = list(editor.model.coefficients)
    editor.picked = ['unknown:peak']; result = editor.run('cal-link-peak-btn')
    assert editor.model.coefficients == before
    assert editor.model.auto_apply and editor.model.match_position == 5.
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(1.8)
    assert 'between 4.8 and 5.2 min' in result[-3]
    assert 'Add a measured reference' not in result[-3]
    editor.run('cal-response-type')
    assert editor.model.coefficients == before


def test_drafts_survive_model_switch_without_corrupting_other_fitted_model(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted(); first = editor.model_id
    editor.rows[0]['concentration'] = 2.; editor.run('cal-standards-table')
    editor.run('cal-new-btn'); second = editor.model_id
    assert second != first
    editor.model_id = first; editor.run('cal-active-model')
    assert editor.rows[0]['concentration'] == 2.
    assert editor.model.coefficients is None


def test_peak_picker_handles_legacy_peak_without_position(monkeypatch):
    editor = Editor(monkeypatch)
    peak = editor.dm.peak_service.get_all_peaks()['unknown'][0]
    peak.rt = peak.rt_start = peak.rt_end = None
    data = editor.callbacks['available_peaks'](1, [], 'calibration', 'area')
    label = next(row['label'] for row in data if row['value'] == 'unknown:peak')
    assert 'unavailable' in label.lower()


def test_matching_controls_preserve_fit_but_refresh_predictions(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted(); coefficients = list(editor.model.coefficients)
    editor.values['position'] = 8.; editor.run('cal-match-position')
    assert editor.model.coefficients == coefficients
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration is None
    editor.values['position'] = 5.; editor.run('cal-match-position')
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(2.)
    editor.values['auto_apply'] = False; editor.run('cal-auto-apply')
    assert editor.model.coefficients == coefficients
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration is None


def test_invalid_json_and_missing_selected_peak_leave_existing_model_unchanged(monkeypatch):
    editor = Editor(monkeypatch); editor.fitted()
    before = editor.dm.calibration_service.serialize()
    editor.upload = 'data:application/json;base64,' + base64.b64encode(b'{').decode()
    result = editor.run('cal-load-upload')
    assert editor.dm.calibration_service.serialize() == before
    assert isinstance(result[-4], str) and result[-4]
    editor.picked = ['removed:peak']; result = editor.run('cal-add-peaks-btn')
    assert editor.dm.calibration_service.serialize() == before
    assert 'no longer available' in result[-4]


def test_legacy_matching_tolerance_and_auto_apply_keep_imported_curve(monkeypatch):
    from test_calibration_service import legacy
    editor = Editor(monkeypatch)
    editor.upload = 'data:application/json;base64,' + base64.b64encode(json.dumps(legacy()).encode()).decode()
    editor.run('cal-load-upload'); coefficients = list(editor.model.coefficients)
    editor.picked = ['unknown:peak']; editor.run('cal-link-peak-btn')
    editor.values['tolerance'] = .4; editor.run('cal-match-tolerance')
    assert editor.model.match_tolerance == .4 and editor.model.coefficients == coefficients
    assert editor.model.response_units == 'mAU·min'
    editor.values['auto_apply'] = False; editor.run('cal-auto-apply')
    assert editor.model.coefficients == coefficients
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration is None
    editor.values['auto_apply'] = True; editor.run('cal-auto-apply')
    assert editor.model.coefficients == coefficients
    assert editor.dm.peak_service.get_all_peaks()['unknown'][0].concentration == pytest.approx(1.8)


def test_peak_without_position_can_still_be_added_as_manually_matched_standard(monkeypatch):
    editor = Editor(monkeypatch); editor.run('cal-new-btn')
    peak = editor.dm.peak_service.get_all_peaks()['unknown'][0]
    peak.rt = peak.rt_start = peak.rt_end = None
    editor.picked = ['unknown:peak']; editor.run('cal-add-peaks-btn')
    assert editor.rows[0]['id'] == 'unknown:peak'
    assert editor.values['position'] is None


def test_compare_samples_selection_starts_new_calibration_with_measured_rows(monkeypatch):
    editor=Editor(monkeypatch); editor.fitted(); previous=editor.model_id
    editor.import_peaks={'ids':['high:peak','unknown:peak'],'ts':'unique'}
    result=editor.run('cal-import-peaks')
    assert editor.model_id != previous
    assert [r['id'] for r in editor.rows]==['high:peak','unknown:peak']
    assert [r['area'] for r in editor.rows]==[30.,20.]
    assert [r['concentration'] for r in editor.rows]==[None,None]
    assert editor.values['position']==5.
    assert editor.included==[0,1]
    assert '4.8' in result[-3] and '5.2' in result[-3]


def test_cell_commit_does_not_echo_table_and_overwrite_next_cell_being_typed(monkeypatch):
    editor = Editor(monkeypatch)
    editor.fitted()
    editor.rows[0]['concentration'] = 2.
    result = editor.run('cal-standards-table')
    assert result[2] is dash.no_update
    assert all(value is dash.no_update for value in result[3:12])
    # The edited draft still survives switching to another model and back.
    original = editor.model_id
    editor.run('cal-new-btn')
    editor.model_id = original
    editor.run('cal-active-model')
    assert editor.rows[0]['concentration'] == 2.


def test_field_edit_does_not_replace_uncommitted_table_input(monkeypatch):
    editor = Editor(monkeypatch)
    editor.fitted()
    editor.values['name'] = 'Edited analyte'
    result = editor.run('cal-analyte-name')
    assert result[2] is dash.no_update
    assert all(value is dash.no_update for value in result[3:12])


def test_editor_has_no_diagnostic_outputs_or_calculation_but_curve_keeps_r_squared(monkeypatch):
    editor = Editor(monkeypatch)
    monkeypatch.setattr(editor.dm.calibration_service, 'create_residual_figure',
                        lambda *_: pytest.fail('Removed residual diagnostics must not be computed'))
    result = editor.fitted()
    assert len(result) == 17
    assert 'fit_summary' not in editor.callbacks
    assert any('R²' in annotation.text for annotation in result[12].layout.annotations)
    app = dash.Dash(__name__)
    register_calibration_callbacks(app, editor.dm)
    assert not any(name in key for key in app.callback_map
                   for name in ('cal-residual-graph','cal-results-info','cal-fit-summary'))


def test_editor_fit_prefers_named_peak_and_excludes_other_standard_peaks(monkeypatch):
    editor = Editor(monkeypatch)
    peaks = editor.dm.peak_service.get_all_peaks()
    for items in peaks.values():
        items[0].rt = 5.04
        other = copy.deepcopy(items[0])
        other.peak_id = 'other'; other.name = 'main peak'; other.rt = 5.
        items.append(other)
    result = editor.fitted()
    assert all(items[0].concentration is not None and items[1].concentration is None for items in peaks.values())
    assert '3 matching peak(s)' in result[-4]
