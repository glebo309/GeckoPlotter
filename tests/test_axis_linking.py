import plotly.graph_objects as go
from plotly.subplots import make_subplots
from services.axis_linking import apply_axis_linking


def test_linking_x_axes_and_global_y_respects_different_units():
    fig = make_subplots(rows=3, cols=1)
    for row, label in enumerate(['Ion Count', 'Absorbance (mAU)', 'Ion Count'], 1):
        fig.add_trace(go.Scatter(x=[0,1], y=[row,2*row]), row=row, col=1)
        fig.update_yaxes(title_text=label, row=row, col=1)
    apply_axis_linking(fig, True, True)
    assert fig.layout.xaxis2.matches == 'x'
    assert fig.layout.xaxis3.matches == 'x'
    assert fig.layout.yaxis3.matches == 'y'
    assert fig.layout.yaxis2.matches is None
    apply_axis_linking(fig, False, False)
    assert fig.layout.xaxis2.matches is None
    assert fig.layout.xaxis2.showticklabels
    assert fig.layout.yaxis3.matches is None
