from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import plotly.graph_objects as go
from callbacks.peak_overlay import add_peak_traces, overlay_peaks_on_figure
from services.plot_smoothing import smooth_plotly_traces
from services.publication_figure import editable_publication_figure

X=np.arange(21,dtype=float)
Y=np.array([1,1,2,1,4,2,7,3,9,5,10,5,9,3,7,2,4,1,2,1,1],dtype=float)


def peak():
    return SimpleNamespace(peak_id='p1',file_id='uv',poly_x=list(X)+list(X[::-1]),
        poly_y=list(Y)+[.5]*len(X),p_line=[(0,.5),(20,.5)],q1=(0,.5),q2=(20,.5),
        color='#0072B2',label='',rt=10.,height=9.5,area=81.,name='Peak 1',source='manual')


def source():
    return go.Figure([go.Scatter(x=X.tolist(),y=Y.tolist(),mode='lines',meta={'file_id':'uv'},name='UV')])


def assert_fill_matches(fig):
    signal=next(t for t in fig.data if isinstance(t.meta,dict) and t.meta.get('file_id')=='uv')
    fill=next(t for t in fig.data if t.meta=='peak_overlay' and t.fill=='toself')
    n=len(fill.x)//2
    np.testing.assert_allclose(fill.y[:n],np.interp(fill.x[:n],signal.x,signal.y))
    assert (fill.xaxis or 'x',fill.yaxis or 'y')==(signal.xaxis or 'x',signal.yaxis or 'y')
    np.testing.assert_allclose(fill.y[n:],.5)


def test_new_integration_fill_follows_smoothed_display_without_changing_measurement():
    p=peak();saved=deepcopy(vars(p));fig=source();smooth_plotly_traces(fig.data,9)
    add_peak_traces(fig,[p],X,Y,selected_peak_id='p1')
    assert_fill_matches(fig)
    assert vars(p)==saved
    assert list(fig.layout.shapes[0].to_plotly_json()[k] for k in ['x0','y0','x1','y1'])==[0,.5,20,.5]


def test_existing_peak_follows_new_smoothing_on_raw_rerender():
    p=peak();fig=overlay_peaks_on_figure([p],source(),X,Y)
    smooth_plotly_traces(fig.data,9)
    fig=overlay_peaks_on_figure([p],fig,X,Y)
    assert_fill_matches(fig)
    assert len([t for t in fig.data if t.fill=='toself'])==1


def test_publication_smoothing_changes_fill_and_can_restore_raw_geometry():
    fig=source();add_peak_traces(fig,[peak()],X,Y)
    snapshot=fig.to_plotly_json();saved=deepcopy(snapshot)
    smoothed=editable_publication_figure(snapshot,{'smooth_window':9},{'smooth_window':0})
    assert_fill_matches(smoothed)
    restored=editable_publication_figure(smoothed.to_plotly_json(),{'smooth_window':0},{'smooth_window':9})
    assert_fill_matches(restored)
    np.testing.assert_allclose(restored.data[0].y,Y)
    assert snapshot.keys()==saved.keys()
    np.testing.assert_allclose(snapshot['data'][1]['y'],saved['data'][1]['y'])


def test_publication_separate_maps_peak_to_its_source_when_original_axes_are_shared():
    fig=go.Figure([go.Scatter(x=X.tolist(),y=(Y*100).tolist(),mode='lines',meta={'file_id':'other'},name='other'),source().data[0]])
    add_peak_traces(fig,[peak()],X,Y,selected_peak_id='p1')
    result=editable_publication_figure(fig.to_plotly_json(),{'layout_mode':'stacked','smooth_window':9},{'layout_mode':'overlay'})
    assert_fill_matches(result)
    assert result.layout.shapes[0].yref=='y2'


def test_existing_publication_snapshot_without_geometry_metadata_is_refreshed():
    fig=source();add_peak_traces(fig,[peak()],X,Y)
    fig.layout.meta={}
    result=editable_publication_figure(fig.to_plotly_json(),{'smooth_window':9},{'smooth_window':0})
    assert_fill_matches(result)


def test_peak_patch_keeps_geometry_metadata_for_later_publication_edits():
    from callbacks.peak_overlay import patch_figure_with_peaks
    patch=patch_figure_with_peaks([peak()],source().to_plotly_json(),X,Y)
    ops=patch.to_plotly_json()['operations']
    metadata=next((op['params']['value'] for op in ops if op['location']==['layout','meta']),{})
    assert metadata['gecko_peak_geometry']['p1']['file_id']=='uv'


def test_publication_plot_type_change_with_source_metadata_does_not_break_peak_geometry():
    fig=source();add_peak_traces(fig,[peak()],X,Y)
    result=editable_publication_figure(fig.to_plotly_json(),{'plot_type':'bar'},{'plot_type':'line'})
    assert result.data[0].type=='bar'
    assert_fill_matches(result)
