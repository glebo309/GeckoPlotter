import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services.signal_axis_range import apply_signal_x_bounds


def test_handles_do_not_expand_signal_bounds_or_override_zoom():
    fig=go.Figure(go.Scatter(x=[380,500,950],y=[0,.45,0],mode='lines',meta={'file_id':'uv'}))
    fig.add_trace(go.Scatter(x=[395,635],y=[.06,.01],mode='markers',meta='peak_overlay'))
    fig.update_xaxes(range=[390,650],autorange=False)
    apply_signal_x_bounds(fig)
    assert fig.layout.xaxis.autorangeoptions.to_plotly_json()=={'minallowed':380.,'maxallowed':950.}
    assert list(fig.layout.xaxis.range)==[390,650]
    assert fig.layout.xaxis.autorange is False


def test_linked_panes_share_data_extent_and_independent_panes_keep_their_own():
    fig=make_subplots(rows=2,cols=1)
    fig.add_trace(go.Scatter(x=[1,10],y=[0,1],mode='lines',meta={'file_id':'a'}),row=1,col=1)
    fig.add_trace(go.Scatter(x=[2,20],y=[0,1],mode='lines',meta={'file_id':'b'}),row=2,col=1)
    apply_signal_x_bounds(fig)
    assert fig.layout.xaxis.autorangeoptions.maxallowed==10
    assert fig.layout.xaxis2.autorangeoptions.minallowed==2
    fig.layout.xaxis2.matches='x'
    apply_signal_x_bounds(fig)
    assert fig.layout.xaxis.autorangeoptions.maxallowed==20
    assert fig.layout.xaxis2.autorangeoptions.minallowed==1
