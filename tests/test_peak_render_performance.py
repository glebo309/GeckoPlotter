import sys
from test_channel_visibility import samples
from services.peak_service import Peak
from services.plot_manager import PlotManager
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
from callbacks.viz_callbacks import compose_raw_figure,_get_active_file_group
import services.peak_display as display
import src.ingestion.types as types


def test_peak_geometry_is_refreshed_once_per_figure(monkeypatch):
    monkeypatch.setitem(sys.modules,'ingestion.types',types)
    store=samples()
    for fid in ('a250','a263','b250','b263'):
        peak=Peak(fid+'p',fid,'P',1,0,2,3,3,2)
        peak.poly_x=[0,1,2,2,1,0];peak.poly_y=[0,3,0,0,0,0]
        store.peak_service._peaks[fid]=[peak]
    calls=[]
    original=display.refresh_peak_display
    def counted(fig):
        calls.append(len(fig.data))
        return original(fig)
    monkeypatch.setattr(display,'refresh_peak_display',counted)
    fig=compose_raw_figure(store,PlotManager(),'tab',_get_active_file_group(store,'a250'),
                           DEFAULT_PLOT_SETTINGS,'a250',store.get_loaded_files_list())
    assert len(calls)==1
    assert set(fig.layout.meta['gecko_peak_geometry'])=={'a250p','a263p','b250p','b263p'}
    assert all(any(t.customdata is not None and len(t.customdata) and t.customdata[0]==fid+'p' for t in fig.data)
               for fid in ('a250','a263','b250','b263'))


def test_display_metadata_does_not_embed_full_peak_measurement_arrays():
    import numpy as np
    import plotly.graph_objects as go
    from copy import deepcopy
    x=np.linspace(0,5,12000);y=np.sin(x)+5
    for source in ('detected','deconvolved'):
        peak=Peak('p','s','P',2,0,5,10,6,1)
        peak.source=source
        peak.poly_x=np.r_[x,x[::-1]].tolist()
        peak.poly_y=np.r_[y,np.zeros(len(x))].tolist()
        original=deepcopy((peak.poly_x,peak.poly_y))
        fig=go.Figure()
        display.register_peak_geometry(fig,peak)
        spec=fig.layout.meta['gecko_peak_geometry']['p']
        if source=='detected':assert len(spec['baseline_points'][0])<=410
        else:assert len(spec['fitted_polygon'][0])<=810
        assert (peak.poly_x,peak.poly_y)==original


def test_overlay_retains_hidden_labels_for_other_samples(monkeypatch):
    monkeypatch.setitem(sys.modules,'ingestion.types',types)
    store=samples()
    for fid,top in [('a250',3),('b250',2)]:
        peak=Peak(fid+'p',fid,'P',1,0,2,3,top,2)
        peak.group_id='shared-compound'
        peak.poly_x=[0,1,2,2,1,0];peak.poly_y=[0,top,0,0,0,0]
        store.peak_service._peaks[fid]=[peak]
    fig=compose_raw_figure(store,PlotManager(),'tab',_get_active_file_group(store,'a250'),
                           DEFAULT_PLOT_SETTINGS,'a250',store.get_loaded_files_list())
    labels=[t for t in fig.data if t.mode=='text' and t.meta=='peak_overlay']
    assert len(labels)==2
    assert sum(t.visible is not False for t in labels)==1
    assert all(t.customdata is not None for t in fig.data if t.meta=='peak_overlay')
    assert all('label_group' in spec for spec in fig.layout.meta['gecko_peak_geometry'].values())
