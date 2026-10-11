from copy import deepcopy
import plotly.graph_objects as go
import pytest
from services.publication_figure import editable_publication_figure


def source():
    return {'data': [
        {'type':'scatter','mode':'lines','x':list(range(9)), 'y':[0,0,0,10,0,0,0,0,0], 'name':'TIC', 'meta':{'file_id':'tic'}, 'yaxis':'y'},
        {'type':'scatter','mode':'lines','x':list(range(9)), 'y':[0,0,2,0,0,4,0,0,0], 'name':'UV', 'meta':{'file_id':'uv'}, 'yaxis':'y2'}],
        'layout': {'xaxis':{'title':{'text':'Time (min)'},'range':[1,7]},
                   'yaxis':{'title':{'text':'Ion Count'}},
                   'yaxis2':{'title':{'text':'Absorbance (mAU)'},'overlaying':'y','side':'right'},
                   'meta':{'gecko_axis_units':{'yaxis':'Ion Count','yaxis2':'Absorbance (mAU)'}}}}


def test_publication_switches_layout_and_back_without_changing_source():
    original = source(); saved = deepcopy(original)
    separate = editable_publication_figure(original, {'layout_mode':'stacked'}, {'layout_mode':'overlay'})
    assert separate.data[1].xaxis == 'x2'
    assert separate.layout.yaxis.domain != separate.layout.yaxis2.domain
    assert separate.layout.yaxis2.overlaying is None
    overlay = editable_publication_figure(original, {'layout_mode':'overlay'}, {'layout_mode':'overlay'})
    assert overlay.layout.yaxis2.overlaying == 'y'
    assert list(overlay.layout.xaxis.range) == [1,7]
    assert original == saved


def test_publication_grid_smoothing_and_labels_affect_shown_figure():
    fig = editable_publication_figure(source(), {'layout_mode':'stacked', 'subplot_rows':1,
        'subplot_cols':2, 'smooth_window':5,'x_label':'Minutes','y1_label':'Custom signal', 'line_width':4}, {'layout_mode':'overlay'})
    assert fig.layout.xaxis.domain != fig.layout.xaxis2.domain
    assert fig.layout.yaxis.domain == fig.layout.yaxis2.domain
    assert list(fig.data[0].y) != source()['data'][0]['y']
    assert fig.layout.xaxis.title.text == 'Minutes'
    assert fig.layout.yaxis.title.text == 'Custom signal'
    assert fig.data[0].line.width == 4


def test_overlay_groups_equal_units_after_leaving_separate():
    src = source(); src['layout']['yaxis2']['title']['text'] = 'Ion Count'
    src['layout']['yaxis']['domain']=[.55,1]; src['layout']['yaxis2']['domain']=[0,.45]
    src['layout']['yaxis2'].pop('overlaying')
    fig = editable_publication_figure(src, {'layout_mode':'overlay'}, {'layout_mode':'stacked'})
    assert [tr.yaxis for tr in fig.data] == ['y','y']
    assert 'yaxis2' not in fig.layout.to_plotly_json()


def test_smoothing_can_be_turned_off_after_sending_a_smoothed_plot():
    from services.plot_smoothing import smooth_plotly_traces
    original = source()
    smoothed = go.Figure(original)
    smooth_plotly_traces(smoothed.data, 5)
    snapshot = smoothed.to_plotly_json()
    restored = editable_publication_figure(snapshot, {'smooth_window':0}, {'smooth_window':5})
    assert list(restored.data[0].y) == original['data'][0]['y']


def test_manual_ranges_apply_but_auto_range_can_restore_the_full_plot():
    manual = editable_publication_figure(source(), {'auto_range':False,'x_min':2,'x_max':4}, {})
    assert list(manual.layout.xaxis.range) == [2,4]
    assert manual.layout.xaxis.autorange is False
    auto = editable_publication_figure(source(), {'auto_range':True}, {'auto_range':False})
    assert auto.layout.xaxis.autorange is True


def test_separate_gives_every_trace_a_positioned_legend():
    fig = editable_publication_figure(source(), {'layout_mode':'stacked'}, {'layout_mode':'overlay'})
    assert fig.data[1].legend == 'legend2'
    assert fig.layout.legend2.y <= fig.layout.yaxis2.domain[1]
    assert fig.layout.xaxis.showticklabels is False


def test_second_y_axis_is_the_right_frame_edge_not_a_shifted_extra_line():
    original = source()
    original['layout']['yaxis2'].update(anchor='free', autoshift=True, shift=3)
    fig = editable_publication_figure(original, {'layout_mode':'overlay'}, {})
    assert fig.layout.yaxis2.anchor == 'x'
    assert fig.layout.yaxis2.autoshift is False
    assert fig.layout.yaxis2.shift == 0
    assert fig.layout.yaxis2.mirror is False


@pytest.mark.parametrize('bounds,expected', [({'x_min':6},'max'),({'x_max':8},'min'),({},True)])
def test_one_sided_manual_axis_range_keeps_other_boundary_automatic(bounds, expected):
    fig = editable_publication_figure(source(), dict(auto_range=False, **bounds), {})
    assert fig.layout.xaxis.autorange == expected
    assert fig.layout.yaxis.autorange is True
    assert list(fig.layout.xaxis.range) == [bounds.get('x_min'),bounds.get('x_max')]


def test_existing_separate_source_also_gets_per_pane_legends_and_shared_unit_labels():
    src=source()
    src['layout']['yaxis']['domain']=[.55,1]
    src['layout']['yaxis2'].update(domain=[0,.45],title={'text':'Ion Count'})
    src['layout']['yaxis2'].pop('overlaying')
    fig=editable_publication_figure(src, {'layout_mode':'stacked','shared_axis_labels':True}, {})
    assert fig.data[1].legend == 'legend2'
    assert fig.layout.legend2.y <= .45
    labels=[a for a in fig.layout.annotations if a.name == 'gecko-shared-y']
    assert len(labels)==1
    assert labels[0].text == 'Ion Count'
    assert labels[0].y == .5


def test_analysis_publication_can_change_bar_line_and_scatter_without_losing_errors():
    src = {'data':[{'type':'bar','x':['A','B'], 'y':[2,4], 'name':'Yield',
                    'error_y':{'array':[.2,.4], 'visible':True}}], 'layout':{}}
    saved = deepcopy(src)
    line = editable_publication_figure(src, {'plot_type':'line'}, {'plot_type':'bar'})
    assert line.data[0].type == 'scatter'
    assert line.data[0].mode == 'lines+markers'
    assert list(line.data[0].error_y.array) == [.2,.4]
    scatter = editable_publication_figure(src, {'plot_type':'scatter'}, {'plot_type':'bar'})
    assert scatter.data[0].mode == 'markers'
    bars = editable_publication_figure(line.to_plotly_json(), {'plot_type':'bar'}, {'plot_type':'line'})
    assert bars.data[0].type == 'bar'
    assert src == saved


def test_separate_publication_accepts_bar_traces():
    src = {'data':[{'type':'bar','x':['A','B'], 'y':[2,4], 'name':'Yield'},
                   {'type':'bar','x':['A','B'], 'y':[3,5], 'name':'Rate'}], 'layout':{}}
    fig = editable_publication_figure(src, {'layout_mode':'stacked'}, {'layout_mode':'overlay'})
    assert fig.data[1].xaxis == 'x2'
