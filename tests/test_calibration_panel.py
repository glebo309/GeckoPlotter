"""The calibration workflow exposes all actions and real editable standards."""
from dash import dash_table, dcc


def nodes():
    from components.calibration_panel import create_calibration_panel
    from components.workspace_layout import walk
    return {node.id:node for node in walk(create_calibration_panel())
            if isinstance(getattr(node,'id',None),str)}


def test_calibration_controls_are_visible_and_callbacks_have_real_components():
    ui=nodes()
    expected={'calibration-content','calibration-container','cal-active-model','cal-new-btn',
              'cal-load-upload','cal-save-btn','cal-download','cal-revision','cal-analyte-name',
              'cal-units','cal-fit-type','cal-force-zero','cal-response-type','cal-peak-picker',
              'cal-add-peaks-btn','cal-add-manual-btn','cal-standards-table','cal-match-position',
              'cal-match-tolerance','cal-match-label','cal-auto-apply','cal-fit-btn',
              'cal-curve-graph','cal-residual-graph','cal-results-info','cal-feedback'}
    assert expected <= ui.keys()
    assert isinstance(ui['cal-load-upload'],dcc.Upload)
    assert isinstance(ui['cal-download'],dcc.Download)
    assert ui['cal-revision'].data==0
    assert ui['cal-peak-picker'].searchable
    assert ui['cal-fit-btn'].children=='Fit calibration'
    assert ui['cal-auto-apply'].checked is True
    assert ui['cal-match-tolerance'].value==.2
    assert ui['cal-feedback'].role=='status'


def test_standard_rows_are_editable_inclusion_selectable_without_fake_data():
    table=nodes()['cal-standards-table']
    assert isinstance(table,dash_table.DataTable)
    assert table.data==[]
    assert table.editable and table.row_deletable
    assert table.row_selectable=='multi'
    assert table.selected_rows==[]
    columns={col['id']:col for col in table.columns}
    assert set(columns)=={'sample_name','position','concentration','area'}
    assert columns['position']['editable'] is False
    assert columns['concentration']['type']=='numeric'
    assert columns['area']['type']=='numeric'


def test_empty_calibration_graphs_are_responsive_and_do_not_invent_a_fit():
    ui=nodes()
    for graph_id in ('cal-curve-graph','cal-residual-graph'):
        graph=ui[graph_id]
        assert graph.responsive
        assert not graph.figure['data']
        assert graph.figure['layout']['annotations']
    assert ui['cal-fit-type'].value=='linear'
    assert ui['cal-response-type'].value=='area'


def test_saved_calibration_can_link_a_measured_peak_without_refitting():
    ui=nodes()
    assert 'cal-link-peak-btn' in ui
    assert ui['cal-link-peak-btn'].children=='Use as matching peak'
    assert 'without refitting' in ui['cal-link-peak-btn'].title
    assert ui['cal-save-btn'].disabled is True
    assert ui['cal-units'].label=='Concentration units'
