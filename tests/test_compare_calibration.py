import dash
import pytest
from callbacks.tab_callbacks import (register_tab_callbacks, _collect_bundles_with_peaks,
                                    _collect_all_peaks, cross_sample_group_to_dataframe)
from test_lcms_peak_table import App
from test_peak_owner_aliases import setup, add
from test_data_store import make_component
from src.services.data_store import Bundle, BundleType


def fixture():
    dm = setup(); first = add(dm.peak_service)
    dm.add_bundle(Bundle(bundle_id='second', name='blue', bundle_type=BundleType.GENERIC,
                         component_list=[make_component('second-component', 'blue.csv')]))
    second = add(dm.peak_service, 'second')
    app = App(); register_tab_callbacks(app, dm)
    rows = cross_sample_group_to_dataframe(_collect_all_peaks(_collect_bundles_with_peaks(dm, [{'id':'bundle'}, {'id':'second'}]))).to_dict('records')
    return dm, app.functions, rows, first, second


def test_comparison_preserves_real_peak_identity_even_when_samples_share_name():
    dm, functions, rows, first, second = fixture()
    assert {row['id'] for row in rows} == {f'bundle:{first.peak_id}', f'second:{second.peak_id}'}
    assert {row['file_id'] for row in rows} == {'bundle', 'second'}
    assert {row['peak_id'] for row in rows} == {first.peak_id, second.peak_id}


def test_send_sorted_selection_uses_stable_row_id_not_display_position():
    dm, functions, rows, first, second = fixture()
    wanted = f'second:{second.peak_id}'
    payload, tab, feedback = functions['use_cross_sample_peaks_for_calibration'](
        1, [wanted], [wanted], [1], rows[::-1], rows)
    assert payload['ids'] == [wanted] and payload['ts']
    assert tab == 'calibration' and feedback == ''


def test_original_selected_row_fallback_is_not_applied_to_sorted_order():
    dm, functions, rows, first, second = fixture()
    payload, tab, feedback = functions['use_cross_sample_peaks_for_calibration'](
        1, None, None, [0], rows[::-1], rows)
    assert payload['ids'] == [f'bundle:{first.peak_id}']


def test_missing_deleted_peak_does_not_partially_import_selection():
    dm, functions, rows, first, second = fixture()
    ids = [row['id'] for row in rows]
    dm.peak_service.remove_peak('second', second.peak_id)
    payload, tab, feedback = functions['use_cross_sample_peaks_for_calibration'](1, ids, ids, [0,1], rows, rows)
    assert payload is dash.no_update and tab is dash.no_update
    assert 'no longer available' in feedback


def test_empty_selection_disables_button_and_does_not_navigate():
    dm, functions, rows, first, second = fixture()
    assert functions['cross_calibration_disabled']([], [], [], rows, rows) is True
    assert functions['cross_calibration_disabled']([rows[0]['id']], [rows[0]['id']], [0], rows, rows) is False
    result = functions['use_cross_sample_peaks_for_calibration'](1, [], [], [], rows, rows)
    assert result[0] is dash.no_update and result[1] is dash.no_update


def test_filtered_out_selection_is_not_mistaken_for_visible_checked_row():
    dm, functions, rows, first, second = fixture()
    result = functions['use_cross_sample_peaks_for_calibration'](1, [rows[1]['id']], [], [1], rows[:1], rows)
    assert result[0] is dash.no_update and result[1] is dash.no_update


def test_initial_and_regrouped_tables_keep_ids_hidden_but_available_for_selection():
    dm, functions, rows, first, second = fixture()
    dm.get_bundle('second').name = 'Second standard'
    loaded = [{'id':'bundle'}, {'id':'second'}]
    initial = functions['update_across_samples_tab'](loaded, 1)
    assert len(initial[2]) == 2
    assert {row['id'] for row in initial[2]} == {f'bundle:{first.peak_id}', f'second:{second.peak_id}'}
    assert not {'id', 'file_id', 'peak_id', '_row_id'} & {col['id'] for col in initial[3]}
    regrouped = functions['update_selected_peak_group'](0, .2, 0, 0, loaded, initial[2])
    assert {row['id'] for row in regrouped[0]} == {row['id'] for row in initial[2]}
    assert not {'id', 'file_id', 'peak_id', '_row_id'} & {col['id'] for col in regrouped[1]}


def test_selected_comparison_payload_reaches_editor_with_exact_unrounded_measurement(monkeypatch):
    from types import SimpleNamespace
    from callbacks.calibration_callbacks import register_calibration_callbacks
    dm, functions, rows, first, second = fixture()
    second.area = 123.456789
    # The comparison display may be rounded or edited; import must use source peak data.
    rows[1]['Area'] = 123.5
    wanted = f'second:{second.peak_id}'
    payload, tab, _ = functions['use_cross_sample_peaks_for_calibration'](1, [wanted], [wanted], [1], rows[::-1], rows)
    app = App(); register_calibration_callbacks(app, dm)
    monkeypatch.setattr(dash, 'ctx', SimpleNamespace(triggered_id='cal-import-peaks'))
    result = app.functions['edit_calibration'](0, 0, 0, 0, None, None, None, [], 0,
        '', '', 'linear', False, 'area', None, .2, True, payload, [], [], 0)
    assert tab == 'calibration'
    assert [row['id'] for row in result[2]] == [wanted]
    assert result[2][0]['area'] == 123.456789
    assert result[2][0]['concentration'] is None
    assert result[3] == [0]


def test_comparison_calculates_prominent_concentration_and_preserves_numeric_precision():
    from services.calibration_workflow import peak_candidates
    from test_calibration_workflow import model
    dm, functions, rows, first, second = fixture()
    dm.get_bundle('second').name = 'Second standard'
    first.area = 12.34567890123; first.rt = 1.0123456789
    model(dm, peak_candidates(dm)[0])
    initial = functions['update_across_samples_tab']([{'id':'bundle'},{'id':'second'}], 1)
    row = next(row for row in initial[2] if row['peak_id'] == first.peak_id)
    assert row['Area'] == first.area and row['RT (min)'] == first.rt
    assert row['Concentration'] == pytest.approx(first.area / 10.)
    assert row['Concentration units'] == 'mM' and row['Calibration status'] == 'Calibrated'
    ids = [col['id'] for col in initial[3]]
    assert ids.index('Concentration') < ids.index('Area')
    concentration = next(col for col in initial[3] if col['id'] == 'Concentration')
    assert concentration['type'] == 'numeric' and concentration['format']['specifier'] == '.5~g'
    assert concentration['editable'] is False
    assert initial[4]['overflowX'] == 'auto' and initial[4]['maxWidth'] == '100%'


def test_calibration_revision_refreshes_current_comparison_rows_without_resetting_group():
    from services.calibration_workflow import peak_candidates
    from test_calibration_workflow import model
    dm, functions, rows, first, second = fixture(); cal = model(dm, peak_candidates(dm)[0])
    rows = rows[::-1]; rows[0]['Group'] = 'keep this label'
    updated, columns, store = functions['refresh_comparison_calibrations'](1, rows)
    assert [r['id'] for r in updated] == [r['id'] for r in rows]
    assert updated[0]['Group'] == 'keep this label'
    assert updated[0]['Concentration'] == pytest.approx(.5)
    cal.coefficients = None
    updated, _, _ = functions['refresh_comparison_calibrations'](2, updated)
    assert all(row['Concentration'] is None for row in updated)
    app = App(); register_tab_callbacks(app, dm)
    dependencies = app.registrations['refresh_comparison_calibrations']
    assert any(getattr(dep,'component_id',None)=='cal-revision' for dep in dependencies)


def test_samples_that_share_a_name_still_form_a_peak_group():
    """Five runs all named 'Phenylethylamine' are five samples: their peaks at one time are one group, labelled
    apart by Sample ID (or a number)."""
    from types import SimpleNamespace
    from callbacks.tab_callbacks import group_peaks_by_retention_time
    bundles = [SimpleNamespace(bundle_id=f'run{i}', name='Phenylethylamine',
                               metadata={'sample_id': f'{mm}mM'} if mm else {}) for i, mm in enumerate((1, 5, 15, None, None))]
    peaks = _collect_all_peaks([{'bundle': b, 'peaks': [{'peak_id': 'p', 'retention_time': 1.74 + i * 0.002}]}
                                for i, b in enumerate(bundles)])
    groups = [g for g in group_peaks_by_retention_time(peaks, 0.2) if len(g) > 1]
    assert len(groups) == 1 and len(groups[0]) == 5
    assert [p['sample_name'] for p in groups[0]] == ['Phenylethylamine (1mM)', 'Phenylethylamine (5mM)',
                                                     'Phenylethylamine (15mM)', 'Phenylethylamine #1',
                                                     'Phenylethylamine #2']
