from types import SimpleNamespace
import numpy as np
import pytest
from dash import no_update
from dash.exceptions import PreventUpdate
import callbacks.baseline_callbacks as callbacks

class App:
    def __init__(self): self.functions={}
    def callback(self,*args,**kwargs):
        def register(f): self.functions[f.__name__]=f;return f
        return register
    def clientside_callback(self,*args,**kwargs):pass


def setup(monkeypatch):
    saved=[]
    peaks=SimpleNamespace(save_undo=lambda:None,get_peaks=lambda _:[],
        add_baseline_peak=lambda **kw:saved.append(kw),group_peaks_across_samples=lambda **kw:None)
    dm=SimpleNamespace(peak_service=peaks,build_file_overlay_map=lambda:{},get_data_by_id=lambda fid:{} if fid in ['blue','control'] else None)
    monkeypatch.setattr(callbacks,'get_xy_arrays',lambda dm,fid:(np.array([0.,1.,2.]),np.array([0.,3.,0.])))
    monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':'manual-draw-line-store.data'}]))
    monkeypatch.setattr(callbacks,'patch_figure_with_peaks',lambda *args:'patched')
    import callbacks.viz_callbacks as viz
    monkeypatch.setattr(viz,'_get_active_file_group',lambda dm,fid:('spectrum',) if fid=='blue' else ('chromatogram',))
    app=App();callbacks.register_baseline_callbacks(app,dm)
    tabs=[{'id':'spectra','type':'raw','group_key':['spectrum']},{'id':'chrom','type':'raw','group_key':['chromatogram']},{'id':'pub','type':'publication'}]
    def draw(file_id='blue',tab_id='spectra',active_tab='spectra',active_file='control'):
        return app.functions['handle_relayout'](None,{'x0':0.,'y0':0.,'x1':2.,'y1':0.,'file_id':file_id,'tab_id':tab_id},'draw',False,active_file,
            {'data':[{'meta':{'file_id':file_id}}],'layout':{'meta':{'gecko_tab_id':tab_id}}},0,None,0,{'layout_mode':'overlay'},[],tabs,active_tab,0)
    return saved,draw


def test_visible_spectrum_owns_draw_even_before_active_file_restoration(monkeypatch):
    saved,draw=setup(monkeypatch)
    result=draw()
    assert saved[0]['file_id']=='blue'
    assert result[0] is no_update  # canonical render overlays all source peaks, not stale hidden figure
    assert result[4]==1  # render-trigger; later outputs are the PDA-preview extras

@pytest.mark.parametrize('file_id,tab_id,active_tab',[
    ('blue','spectra','chrom'),('control','spectra','spectra'),('missing','spectra','spectra'),('blue','pub','pub')])
def test_stale_wrong_group_missing_and_publication_draws_are_rejected(monkeypatch,file_id,tab_id,active_tab):
    saved,draw=setup(monkeypatch)
    with pytest.raises(PreventUpdate):draw(file_id,tab_id,active_tab)
    assert not saved


def test_owned_draw_does_not_require_stale_active_file(monkeypatch):
    saved,draw=setup(monkeypatch)
    draw(active_file=None)
    assert saved[0]['file_id']=='blue'
