"""Deleting peaks from the Compare table removes them from PeakService and the plot."""
import pytest
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate

from callbacks.peak_overlay import add_peak_traces, cleanup_peak_traces
from callbacks.tab_callbacks import (_collect_all_peaks, _collect_bundles_with_peaks,
                                     cross_sample_group_to_dataframe, group_peaks_by_retention_time,
                                     register_tab_callbacks)
from src.services.data_store import Bundle, BundleType, DataStore
from test_data_store import make_component
from test_lcms_peak_table import App


def _peak(ps, fid, rt, source='manual', group=None):
    return ps.add_baseline_peak(
        file_id=fid, area=5., height=3., apex_x=rt,
        poly_x=[rt - .01, rt, rt + .01, rt + .01, rt - .01], poly_y=[0, 3, 0, 0, 0],
        p_line=[(rt - .01, 0), (rt + .01, 0)], q1=(rt - .01, 0), q2=(rt + .01, 0),
        source=source, deconv_group=group)


@pytest.fixture
def compare():
    dm = DataStore()
    for bid in ('s1', 's2'):
        dm.add_bundle(Bundle(bundle_id=bid, name=bid, bundle_type=BundleType.GENERIC,
                             component_list=[make_component(bid + '-c', bid + '.csv')]))
    ps = dm.peak_service
    # sample s1: main peak + two deconvolved shoulders; sample s2: one peak per component
    s1 = {'main': _peak(ps, 's1', 2.24), 'sh1': _peak(ps, 's1', 2.20, 'deconvolved', 'deconv_a'),
          'sh2': _peak(ps, 's1', 2.22, 'deconvolved', 'deconv_b')}
    s2 = {'main': _peak(ps, 's2', 2.24), 'sh1': _peak(ps, 's2', 2.20, 'deconvolved', 'deconv_a')}
    ps.group_peaks_across_samples()
    app = App()
    register_tab_callbacks(app, dm)
    return dm, app, s1, s2


def _compare_rows(dm, group_rt):
    found = _collect_bundles_with_peaks(dm, dm.get_loaded_files_list())
    groups = [g for g in group_peaks_by_retention_time(_collect_all_peaks(found), .01) if len(g) > 1]
    group = next(g for g in groups if abs(g[0]['retention_time'] - group_rt) < .005)
    return cross_sample_group_to_dataframe(group).to_dict('records')


def _figure_peak_ids(dm):
    """What master_render builds: cleanup + add_peak_traces for every file."""
    fig = go.Figure(go.Scatter(x=[0, 1, 2, 3], y=[0, 1, 2, 3]))
    cleanup_peak_traces(fig)
    for fid in ('s1', 's2'):
        add_peak_traces(fig, dm.peak_service.get_peaks(fid), [0, 1, 2, 3], [0, 1, 2, 3])
    ids = set()
    for trace in fig.data:
        if trace.meta == 'peak_overlay' and trace.customdata is not None:
            ids |= {c if isinstance(c, str) else c[0] for c in trace.customdata}
    return ids


def test_deleting_deconvolved_compare_rows_removes_peaks_from_service_and_figure(compare):
    dm, app, s1, s2 = compare
    before = _figure_peak_ids(dm)
    assert {s1['sh1'].peak_id, s2['sh1'].peak_id} <= before
    rows = _compare_rows(dm, 2.20)
    assert {r['peak_id'] for r in rows} == {s1['sh1'].peak_id, s2['sh1'].peak_id}
    # user deletes the s1 shoulder row, then the last row of the group
    trigger, selected = app.functions['delete_cross_sample_table_rows'](
        1, rows[1:], rows, s1['sh1'].peak_id, 7)
    assert trigger == 8 and selected is None
    assert s1['sh1'] not in dm.peak_service.get_peaks('s1')
    assert _figure_peak_ids(dm) == before - {s1['sh1'].peak_id}
    app.functions['delete_cross_sample_table_rows'](2, [], rows[1:], None, 8)
    after = _figure_peak_ids(dm)
    assert not ({s1['sh1'].peak_id, s2['sh1'].peak_id} & after)
    # siblings and the main peaks stay, with their deconvolution tags
    assert {s1['main'].peak_id, s1['sh2'].peak_id, s2['main'].peak_id} <= after
    assert dm.peak_service.get_peaks('s1')[1].deconv_group == 'deconv_b'
    # the next Compare refresh cannot resurrect them
    found = _collect_bundles_with_peaks(dm, dm.get_loaded_files_list())
    listed = {p['peak_id'] for b in found for p in b['peaks']}
    assert not ({s1['sh1'].peak_id, s2['sh1'].peak_id} & listed)


def test_compare_delete_is_one_undo_step(compare):
    dm, app, s1, s2 = compare
    rows = _compare_rows(dm, 2.20)
    app.functions['delete_cross_sample_table_rows'](1, [], rows, None, 0)
    assert dm.peak_service.get_peaks('s2') == [s2['main']]
    assert dm.peak_service.undo()
    restored = {p.peak_id for fid in ('s1', 's2') for p in dm.peak_service.get_peaks(fid)}
    assert {s1['sh1'].peak_id, s2['sh1'].peak_id} <= restored
    assert _figure_peak_ids(dm) >= {s1['sh1'].peak_id, s2['sh1'].peak_id}


def test_compare_edits_that_do_not_remove_rows_are_not_deletions(compare):
    dm, app, s1, s2 = compare
    rows = _compare_rows(dm, 2.20)
    renamed = [dict(r, **{'Peak Name': 'x'}) for r in rows]
    for new, old in [(renamed, rows), (rows, []), (None, rows)]:
        with pytest.raises(PreventUpdate):
            app.functions['delete_cross_sample_table_rows'](1, new, old, None, 0)
    # stale ids that no longer exist in the service do not touch the undo stack
    with pytest.raises(PreventUpdate):
        app.functions['delete_cross_sample_table_rows'](1, [], [{'file_id': 's1', 'peak_id': 'gone'}], None, 0)
    assert not dm.peak_service.can_undo
    assert len(dm.peak_service.get_peaks('s1')) == 3


def test_plot_refreshes_on_peak_change_trigger():
    from types import SimpleNamespace
    import callbacks.viz_callbacks as viz
    app = App()
    viz.register_viz_callbacks(app, SimpleNamespace(loaded_data={}, visibility_state={}))
    inputs = [(d.component_id, d.component_property) for d in app.registrations['master_render'][1]]
    assert ('peak-change-trigger', 'data') in inputs
