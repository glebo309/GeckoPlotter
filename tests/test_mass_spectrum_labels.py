"""Mass-spectrum labels identify dominant ions without labeling profile shoulders."""
from types import SimpleNamespace
import numpy as np
import pytest
from callbacks.lcms_callbacks import _build_peak_mass_figure, _build_spectrum_at_scan


def build(kind, mz, intensity):
    if kind == 'average':
        peak = SimpleNamespace(label='Peak 1', name='', peak_id='p1', rt_start=1., rt_end=2.)
        return _build_peak_mass_figure(mz, intensity, peak)[0]
    service = SimpleNamespace(get_scan_count=lambda entry:1,
        get_mass_spectrum=lambda entry,index:(mz,intensity),
        extract_tic=lambda entry:(np.array([1.5]),np.array([100.])))
    return _build_spectrum_at_scan(service,{},0)[0]


@pytest.mark.parametrize('kind',['scan','average'])
def test_labels_show_dominant_local_mz_apices_not_adjacent_profile_points(kind):
    mz = np.array([100.,308.67,308.68,308.69,350.,450.,500.])
    intensity = np.array([0.,80.,100.,90.,0.,60.,0.])
    before = intensity.copy()
    fig = build(kind,mz,intensity)
    annotations = fig.layout.annotations
    assert {a.text for a in annotations} == {'308.68','450.00'}
    assert {a.x for a in annotations} == {308.68,450.}
    assert all(not a.showarrow and a.font.color=='#333333' and a.yanchor=='bottom' for a in annotations)
    assert fig.layout.yaxis.range[1] >= 112
    np.testing.assert_array_equal(intensity,before)
    np.testing.assert_array_equal(fig.data[0].customdata[1::3],before)
    assert fig.layout.xaxis.title.text=='m/z'
    assert fig.layout.yaxis.title.text=='Relative Intensity (%)'


@pytest.mark.parametrize('kind',['scan','average'])
def test_labels_limit_count_and_exclude_small_peaks(kind):
    mz = np.arange(31,dtype=float)*20+100
    intensity = np.zeros(31)
    intensity[1::2] = np.linspace(100,2,15)
    fig = build(kind,mz,intensity)
    annotations=fig.layout.annotations
    assert 1 <= len(annotations) <= 6
    assert all(a.y>=10 for a in annotations)
    assert any(a.text=='120.00' for a in annotations)
    positions=sorted(a.x for a in annotations)
    assert all(b-a>=.055*np.ptp(mz) for a,b in zip(positions,positions[1:]))


@pytest.mark.parametrize('kind',['scan','average'])
def test_nearby_ion_labels_keep_strongest_and_flat_spectrum_has_no_labels(kind):
    fig = build(kind,np.array([100.,200.,210.,220.,500.]),np.array([0.,100.,0.,90.,0.]))
    assert [a.text for a in fig.layout.annotations]==['200.00']
    fig = build(kind,np.array([100.,200.,300.]),np.zeros(3))
    assert not fig.layout.annotations


def test_sparse_centroid_ions_are_distinct_even_if_neighbor_intensity_is_lower():
    from callbacks.lcms_callbacks import _mass_peak_annotations
    labels = _mass_peak_annotations(np.array([211.62,308.68]),np.array([100.,90.]))
    assert {a['text'] for a in labels}=={'211.62','308.68'}


@pytest.mark.parametrize('kind',['scan','average'])
def test_relative_intensity_uses_base_peak_without_erasing_the_smallest_ion(kind):
    mz=np.array([211.62,308.68])
    intensity=np.array([100.,90.])
    fig=build(kind,mz,intensity)
    np.testing.assert_array_equal(fig.data[0].y[1::3],[100.,90.])
    np.testing.assert_array_equal(fig.data[0].customdata[1::3],intensity)
    assert {a.text for a in fig.layout.annotations}=={'211.62','308.68'}
    # Counts are normalized by the base peak, not their range.
    fig=build(kind,mz,np.array([200.,180.]))
    np.testing.assert_array_equal(fig.data[0].y[1::3],[100.,90.])
    np.testing.assert_array_equal(fig.data[0].customdata[1::3],[200.,180.])


@pytest.mark.parametrize('kind',['scan','average'])
def test_mass_display_is_one_plain_stick_trace_with_raw_intensity_hover(kind):
    fig=build(kind,np.array([211.62,308.68]),np.array([200.,180.]))
    assert len(fig.data)==1
    trace=fig.data[0]
    assert trace.mode=='lines'
    assert 'Intensity: %{customdata' in trace.hovertemplate
    assert trace.hoverinfo!='skip'
    assert trace.meta['gecko_mass_spectrum'] is True
    assert all(a.name=='gecko-ms-peak' for a in fig.layout.annotations)


@pytest.mark.parametrize('kind,source',[('scan','ms-spectrum-graph'),('average','peak-mass-graph')])
def test_open_stick_spectrum_as_new_plot_retains_zero_intensity_samples(kind,source,monkeypatch):
    import sys
    import src.ingestion.types as ingestion_types
    monkeypatch.setitem(sys.modules, "ingestion.types", ingestion_types)
    from callbacks.ms_context_menu_callbacks import _extract_xy_from_figure
    mz=np.array([100.,211.62,308.68])
    fig=build(kind,mz,np.array([0.,200.,180.]))
    x,y,xlabel,ylabel=_extract_xy_from_figure(fig.to_dict(),source)
    np.testing.assert_array_equal(x,mz)
    np.testing.assert_array_equal(y,[0.,100.,90.])
