import plotly.graph_objects as go
from plotly.subplots import make_subplots
from test_pda_service import setup
from callbacks import viz_callbacks as viz


def figure():
    fig=make_subplots(rows=2, cols=1)
    fig.add_trace(go.Scatter(x=[0,.5,1],y=[3,6,9],name='Original',meta={'file_id':'sibling'}),row=1,col=1)
    fig.add_trace(go.Scatter(x=[0,.5,1],y=[10,20,30],name='Other sample',meta={'file_id':'other'}),row=2,col=1)
    return fig


def test_preview_replaces_only_its_real_owner_and_never_mutates_data():
    store=setup(); fig=figure()
    original=store.get_data_by_id('sibling')['data'].copy()
    replaced=viz._apply_pda_main_preview(fig,store,{'source_id':'source','owner_id':'sibling','wavelength_nm':220.})
    assert replaced=='sibling'
    assert list(fig.data[0].y)==[2,5,8]
    assert fig.data[0].meta['pda_preview'] is True
    assert fig.data[0].meta['pda_source_id']=='source'
    assert fig.data[0].meta['pda_owner_id']=='sibling'
    assert 'file_id' not in fig.data[0].meta
    assert fig.data[0].name=='PDA 220 nm · preview'
    assert list(fig.data[1].y)==[10,20,30]
    assert fig.data[0].xaxis=='x' and fig.data[0].yaxis=='y'
    assert store.get_data_by_id('sibling')['data'].equals(original)


def test_foreign_or_missing_preview_does_not_replace_traces():
    fig=figure(); store=setup()
    assert viz._apply_pda_main_preview(fig,store,{'source_id':'source','owner_id':'other','wavelength_nm':220.}) is None
    assert list(fig.data[0].y)==[3,6,9]


def test_cursor_removes_editable_plotly_shape_and_keeps_ranges():
    fig=figure(); fig.update_xaxes(range=[.2,.8]); fig.update_yaxes(range=[0,40])
    fig.add_shape(type='line',name='pda-time-cursor',x0=.5,x1=.5,y0=0,y1=1)
    viz._apply_pda_main_cursor(fig,{'owner_id':'other','source_id':'source','time_min':.5})
    assert not fig.layout.shapes
    assert tuple(fig.layout.xaxis2.range)==(.2,.8)
    assert tuple(fig.layout.yaxis2.range)==(0,40)
