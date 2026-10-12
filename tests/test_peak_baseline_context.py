from dataclasses import asdict
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from services.data_store import DataStore,Bundle,BundleType,Component,ComponentRole
from services.peak_service import Peak
from callbacks.context_menu_callbacks import register_context_menu_callbacks

class App:
    def __init__(self):self.functions={}
    def callback(self,*args,**kwargs):
        def wrap(fn):self.functions[fn.__name__]=fn;return fn
        return wrap

def setup_peak(source='manual'):
    store=DataStore()
    component=Component('channel',ComponentRole.PRIMARY,'sample.csv',
        dataframe=pd.DataFrame({'time':[0.,1.,2.],'signal':[1.,4.,1.]}))
    store.add_bundle(Bundle('sample','Sample',BundleType.CHROMATOGRAM,component_list=[component]))
    peak=Peak('peak','channel','Compound',1.,0.,2.,3.,3.,2.,color='#123456',source=source,
              p_line=[(0.,1.),(2.,1.)],q1=(0.,1.),q2=(2.,1.),poly_x=[0.,1.,2.,2.,1.,0.],poly_y=[1.,4.,1.,1.,1.,1.])
    store.peak_service._peaks['channel']=[peak]
    app=App();register_context_menu_callbacks(app,store)
    return store,peak,app

@pytest.mark.parametrize('source',['manual','detected'])
def test_zero_baseline_reintegrates_selected_peak_and_is_undoable(source):
    store,peak,app=setup_peak(source)
    before=asdict(peak)
    result=app.functions['zero_baseline'](1,{'peak_id':'peak'},5,8)
    assert result==(True,6,9)  # first value hides the popup menu
    assert peak.p_line==[(0.,0.),(2.,0.)]
    assert peak.q1==(0.,0.) and peak.q2==(2.,0.)
    assert peak.area==pytest.approx(5.) and peak.height==4.
    assert (peak.peak_id,peak.color,peak.rt_start,peak.rt_end)==('peak','#123456',0.,2.)
    assert peak.source=='manual'
    assert store.peak_service.undo()
    assert asdict(store.peak_service.get_peaks('channel')[0])==before


def test_zero_baseline_of_fitted_component_uses_its_model_not_neighboring_trace():
    from lmfit.models import ExponentialGaussianModel
    store,peak,app=setup_peak('deconvolved')
    peak.fit_params={'amplitude':2.,'center':.8,'sigma':.1,'gamma':5.,'baseline':[[0.,1.],[2.,1.]]}
    before=asdict(peak)
    app.functions['zero_baseline'](1,{'peak_id':'peak'},0,0)
    x=np.linspace(0.,2.,1600)
    fitted=ExponentialGaussianModel().eval(x=x,amplitude=2.,center=.8,sigma=.1,gamma=5.)+1.
    assert peak.area==pytest.approx(np.trapezoid(fitted,x))
    assert peak.source=='deconvolved' and peak.fit_params['integration_edited']
    assert peak.fit_params['baseline']==[[0.,1.],[2.,1.]]
    assert store.peak_service.undo()
    assert asdict(store.peak_service.get_peaks('channel')[0])==before
