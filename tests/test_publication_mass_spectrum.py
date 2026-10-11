"""Publication mass spectra retain sticks, raw hover data and compact labels."""
from copy import deepcopy
import numpy as np
import pytest
from test_mass_spectrum_labels import build
from services.figure_actions import publication_snapshot
from services.publication_figure import editable_publication_figure
from services.publication_presets import publication_preset_settings


def legacy_mass_figure():
    return {'data':[
        {'type':'scatter','mode':'lines','x':[211.62,211.62,None,308.68,308.68,None],
         'y':[0,100,None,0,90,None], 'hoverinfo':'skip','showlegend':False},
        {'type':'scatter','mode':'markers','x':[211.62,308.68],'y':[100,90],
         'marker':{'size':3,'color':'blue'},'customdata':[200,180],
         'hovertemplate':'m/z: %{x:.4g}<br>Intensity: %{customdata:.4g}<br>Relative: %{y:.1f}%<extra></extra>',
         'showlegend':False}],
        'layout':{'xaxis':{'title':{'text':'m/z'}},'yaxis':{'title':{'text':'Relative Intensity (%)'}},
                  'annotations':[{'x':308.68,'y':90,'text':'308.68','showarrow':False,
                                  'font':{'size':10,'color':'#333333'}}]}}


@pytest.mark.parametrize('preset',['single-col','full-width','presentation'])
@pytest.mark.parametrize('kind',['scan','average','legacy'])
def test_publication_spectrum_never_creates_marker_signal_and_labels_follow_preset(preset,kind):
    source=legacy_mass_figure() if kind=='legacy' else build(kind,np.array([211.62,308.68]),np.array([200.,180.])).to_dict()
    before=deepcopy(source)
    _,tab,figures=publication_snapshot(source,[],{})
    entry=figures[tab]
    settings={**entry['plot_settings'],**publication_preset_settings(preset), 'marker_size':25}
    fig=editable_publication_figure(entry['figure'],settings,entry['plot_settings'])
    assert len(fig.data)==1
    assert fig.data[0].mode=='lines'
    assert list(fig.data[0].customdata[1::3])==[200,180]
    assert all(a.font.size <= fig.layout.xaxis.tickfont.size for a in fig.layout.annotations)
    assert all(a.font.color=='#333333' for a in fig.layout.annotations)
    assert len(source['data'])==len(before['data'])
    if kind=='legacy':assert source==before


def test_legacy_cleanup_does_not_remove_an_unrelated_marker_signal():
    from services.figure_sanitization import clean_figure_for_output
    source=legacy_mass_figure()
    source['data'][1]['x']=[210.,310.]
    cleaned=clean_figure_for_output(source)
    assert len(cleaned['data'])==2
