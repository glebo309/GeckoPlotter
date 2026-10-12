import numpy as np
from types import SimpleNamespace
import dash
from lmfit.models import ExponentialGaussianModel
from services.deconvolution_service import DeconvolutionService, serialize_result
from callbacks import deconvolution_callbacks as cb
from test_lcms_peak_table import App


def test_dragged_apex_controls_fit_and_session_survives_deselection(monkeypatch):
    x=np.linspace(0,2,300)
    y=sum(ExponentialGaussianModel().eval(x=x,amplitude=a,center=c,sigma=.06,gamma=25.)
          for a,c in [(5.,.6),(3.,1.2)])
    svc=DeconvolutionService()
    fit=svc.fit_peaks(x,y,[(.65,25.),(1.25,20.)],fixed_apices={0:.75})
    assert abs(x[np.argmax(fit.components[0].curve)]-.75)<.01
    payload=serialize_result(fit)
    payload.update(peak_id='original',file_id='uv')
    peak=SimpleNamespace(peak_id='original',rt_start=0.,rt_end=2.)
    store=SimpleNamespace(peak_service=SimpleNamespace(get_all_peaks=lambda:{'uv':[peak]}))
    app=App(); cb.register_deconvolution_callbacks(app,store)
    monkeypatch.setattr(cb,'_extract_peak_region',lambda *args:(x,y))
    monkeypatch.setattr(dash,'callback_context',SimpleNamespace(triggered_id={'type':'deconv-remove','index':1},triggered=[{'value':1}]))
    markers=[{'x':.75,'y':25.,'fixed':True},{'x':1.25,'y':20.}]
    out=app.functions['marker_click_and_refit'](None,None,[0,1],markers,'another-file',None,'deconvolve',0,payload,{})
    assert len(out[1]['components'])==1
    assert out[1]['peak_id']=='original' and out[1]['file_id']=='uv'
    accepted=[]
    monkeypatch.setattr(cb,'_apply_deconv',lambda dm,r,fid,pid:accepted.append((fid,pid)) or 1)
    app.functions['accept'](1,out[1],'another-file',None,0,0)
    assert accepted==[('uv','original')]


def test_component_handles_match_normal_peaks_and_edit_only_the_component(monkeypatch):
    from copy import deepcopy
    from services.peak_service import PeakService
    from callbacks import baseline_callbacks as baseline
    from callbacks.peak_overlay import add_peak_traces
    import plotly.graph_objects as go
    x=np.linspace(0,2,1600)
    params={'amplitude':5.,'center':.6,'sigma':.08,'gamma':15.}
    component=ExponentialGaussianModel().eval(x=x,**params)
    ps=PeakService()
    p=ps.add_baseline_peak(file_id='uv',area=5.,height=float(max(component)),apex_x=.6,
        poly_x=list(x)+list(x[::-1]),poly_y=list(component)+[0.]*len(x),
        p_line=[(0.,0.),(2.,0.)],q1=(0.,0.),q2=(2.,0.),source='deconvolved',fit_params=params)
    sibling=ps.add_baseline_peak(file_id='uv',area=3.,height=4.,apex_x=1.,
        poly_x=[0,1,2,2,1,0],poly_y=[0,4,0,0,0,0],p_line=[(0,0),(2,0)],q1=(0,0),q2=(2,0),source='deconvolved')
    saved=deepcopy(vars(sibling))
    fig=go.Figure(go.Scatter(x=x,y=component+100.,meta={'file_id':'uv'}))
    add_peak_traces(fig,[p],x,component+100.,p.peak_id)
    assert fig.layout.shapes[0].name=='baseline:'+p.peak_id
    assert fig.layout.shapes[0].editable
    handles=next(t for t in fig.data if t.mode=='markers')
    assert handles.marker.size==9 and handles.marker.color=='#ffffff'
    app=App();baseline.register_baseline_callbacks(app,SimpleNamespace(peak_service=ps))
    monkeypatch.setattr(baseline,'get_xy_arrays',lambda *args:(x,component+100.))
    monkeypatch.setattr(baseline,'callback_context',SimpleNamespace(triggered=[{'prop_id':'main-plot.relayoutData'}]))
    cb=app.functions['handle_relayout']
    cb({'shapes[0].x0':.55,'shapes[0].x1':.75},None,'navigate',False,'uv',fig.to_plotly_json(),0,p.peak_id,0,{},[],[],None,0)
    assert 0 < p.area < 5. # Must exclude the other signal's huge contribution.
    first_area=p.area
    fig=go.Figure(go.Scatter(x=x,y=component+100.,meta={'file_id':'uv'}))
    add_peak_traces(fig,[p],x,component+100.,p.peak_id)
    cb({'shapes[0].x0':.55,'shapes[0].x1':.75},None,'navigate',False,'uv',fig.to_plotly_json(),0,p.peak_id,0,{},[],[],None,0)
    assert p.area==first_area # The fitted center must not drift on repeated edits.
    assert vars(sibling)==saved
