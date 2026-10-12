import numpy as np
import plotly.graph_objects as go
from services.peak_service import PeakService
from callbacks.peak_overlay import add_peak_traces


def test_detected_symmetric_peak_has_nonzero_area_and_visible_selectable_fill():
    x = np.linspace(0, 10, 501)
    y = 100 * np.exp(-((x - 5) / .4) ** 2)
    peaks = PeakService().detect_peaks('tic', y, x)
    assert len(peaks) == 1
    peak = peaks[0]
    assert peak.rt_start < peak.rt < peak.rt_end
    assert peak.area > 60
    fig = go.Figure(go.Scatter(x=x, y=y, meta={'file_id': 'tic'}))
    add_peak_traces(fig, peaks, x, y)
    fills = [t for t in fig.data if t.fill == 'toself']
    assert len(fills) == 1
    assert set(fills[0].customdata) == {peak.peak_id}


def test_detection_preserves_curved_baseline_when_display_follows_raw_signal():
    x = np.linspace(0, 10, 501)
    signal = 100 * np.exp(-((x - 5.01) / .4) ** 2)
    baseline = 20 + x*x
    peaks = PeakService().detect_peaks('tic', signal, x,
                                     display_signal=signal+baseline, baseline=baseline)
    fig = go.Figure(go.Scatter(x=x, y=signal+baseline, meta={'file_id':'tic'}))
    add_peak_traces(fig, peaks, x, signal+baseline)
    fill = next(t for t in fig.data if t.fill == 'toself')
    n = len(fill.x)//2
    np.testing.assert_allclose(fill.y[n:], np.interp(fill.x[n:], x, baseline))


def test_detection_uses_selected_component_and_clear_preserves_other_signal(monkeypatch):
    from callbacks.integration_callbacks import register_integration_callbacks
    from callbacks import baseline_callbacks
    from test_peak_owner_aliases import setup, add
    from test_lcms_peak_table import App
    from src.services.data_store import BundleType
    dm=setup(BundleType.LCMS)
    manual=add(dm.peak_service,'component')
    other=add(dm.peak_service,'other')
    x=np.linspace(0,10,501)
    y=100*np.exp(-((x-5)/.4)**2)
    sources=[]
    def arrays(store,fid):
        sources.append(fid)
        return x,y
    monkeypatch.setattr(baseline_callbacks,'get_xy_arrays',arrays)
    app=App();register_integration_callbacks(app,dm)
    result=app.functions['detect_peaks'](1,99,'component',{},0)
    assert sources==['component']
    assert result[0]==1 and 'Detected 1 new peaks' in result[1]
    assert dm.peak_service.get_peaks('other')==[other]
    assert len(dm.peak_service.get_peaks('component'))==2
    assert dm.integration_service.get_settings('component').peak_threshold==.01
    label,disabled,_=app.functions['detection_target']('component',[])
    assert label=='Signal: blue' and not disabled
    # A slider move also recovers after a stricter setting found no peaks.
    import dash
    from types import SimpleNamespace
    monkeypatch.setattr(dash, 'ctx', SimpleNamespace(triggered_id='int-detection-sensitivity'))
    dm.peak_service.clear_detected_peaks('component')
    assert app.functions['detect_peaks'](1,99,'component',{},1)[0] == 2
    app.functions['clear_peaks'](1,'component',1)
    assert dm.peak_service.get_peaks('component')==[manual]
    assert dm.peak_service.get_peaks('other')==[other]
    assert app.functions['detect_peaks'](1,99,'component',{},2)[0] is dash.no_update


def test_high_count_peaks_get_distinct_local_bounds_instead_of_whole_run():
    x=np.linspace(0,14,1401)
    y=100000 + 600000*np.exp(-((x-2)/.25)**2) + 900000*np.exp(-((x-7)/.5)**2) + 300000*np.exp(-((x-11)/.3)**2)
    peaks=PeakService().detect_peaks('tic',y,x)
    assert len(peaks)==3
    assert all(0 < p.width < 3 for p in peaks)
    assert peaks[0].rt_end <= peaks[1].rt_start
    assert peaks[1].rt_end <= peaks[2].rt_start
    assert len({round(p.area) for p in peaks})==3


def test_detecting_positive_signal_reveals_it_when_negative_mode_was_visible(monkeypatch):
    from callbacks.integration_callbacks import register_integration_callbacks
    from callbacks import baseline_callbacks
    from test_file_controls import component
    from services.data_store import DataStore,Bundle,BundleType,ComponentRole
    from test_lcms_peak_table import App
    dm=DataStore()
    dm.add_bundle(Bundle('sample','Sample',BundleType.LCMS,component_list=[
        component('positive',ComponentRole.MS_POSITIVE),component('negative',ComponentRole.MS_NEGATIVE)]))
    x=np.linspace(0,10,501);y=100*np.exp(-((x-5)/.4)**2)
    monkeypatch.setattr(baseline_callbacks,'get_xy_arrays',lambda *_:(x,y))
    app=App();register_integration_callbacks(app,dm)
    settings={'ms_polarity':'negative','layout_mode':'stacked','_context_key':'shared:raw:raw'}
    out=app.functions['detect_peaks'](1,99,'positive',settings,0)
    assert out[2]=={**settings,'ms_polarity':'positive'}
    assert dm.peak_service.get_peaks('positive')
    assert not dm.peak_service.get_peaks('negative')


def test_detected_peak_baseline_choice_controls_both_area_and_fill():
    x = np.linspace(0, 10, 501)
    corrected = 100 * np.exp(-((x - 5) / .4) ** 2)
    raw = corrected + 20 + 3*x
    linear = PeakService().detect_peaks('tic', corrected, x, display_signal=raw,
                                       integration_baseline='linear')[0]
    zero = PeakService().detect_peaks('tic', corrected, x, display_signal=raw,
                                     integration_baseline='zero')[0]
    assert linear.area < zero.area
    assert abs(linear.area - 100*.4*np.sqrt(np.pi)) < 1
    assert linear.q1[1] > 20 and linear.q2[1] > linear.q1[1]
    assert zero.q1[1] == zero.q2[1] == 0
    for peak in (linear, zero):
        n = len(peak.poly_x)//2
        xs = np.array(peak.poly_x[:n])
        top = np.array(peak.poly_y[:n])
        bottom = np.array(peak.poly_y[n:][::-1])
        assert np.isclose(peak.area, np.trapezoid(np.maximum(top-bottom, 0), xs))


def test_unresolved_doublet_uses_shared_baseline_and_vertical_valley_split():
    x = np.linspace(0, 10, 1001)
    signal = 100*np.exp(-((x-4.5)/.45)**2) + 70*np.exp(-((x-5.25)/.4)**2)
    raw = signal + 20 + 2*x
    peaks = PeakService().detect_peaks('uv', signal, x, threshold=.01,
                                     display_signal=raw, integration_baseline='linear')
    assert len(peaks) == 2
    left, right = peaks
    assert left.rt_end == right.rt_start
    assert abs(left.q2[1] - right.q1[1]) < 1e-9
    # The valley splits area vertically, rather than becoming the baseline.
    valley_height = np.interp(left.rt_end, x, raw)
    assert valley_height - left.q2[1] > 20
    expected_area = (100*.45 + 70*.4)*np.sqrt(np.pi)
    assert abs(sum(p.area for p in peaks) / expected_area - 1) < .04
    assert left.q1[1] > 20  # preserve the sloping background; not zero integration


def test_sensitivity_slider_preserves_midpoint_and_increases_detection():
    from callbacks.integration_callbacks import sensitivity_threshold
    assert sensitivity_threshold(50) == .5
    assert sensitivity_threshold(100) == .001
    assert sensitivity_threshold(0) == 1
    x = np.linspace(0, 10, 1001)
    y = 100*np.exp(-((x-2)/.2)**2) + 30*np.exp(-((x-5)/.2)**2)
    service = PeakService()
    assert len(service.detect_peaks('uv', y, x, threshold=sensitivity_threshold(50))) == 1
    assert len(service.detect_peaks('uv', y, x, threshold=sensitivity_threshold(80))) == 2


def test_detection_keeps_neighbour_whose_tail_overlaps_a_manual_region():
    # Coarsely sampled chromatography: the detected tail near 4 min crosses
    # the start of an existing manual integration around the later peak.
    x = np.linspace(0, 6.5, 196)
    y = 100*np.exp(-((x-3.93333)/.09)**2) + 470*np.exp(-((x-4.6)/.05)**2)
    service = PeakService()
    manual = service.add_baseline_peak(
        file_id='uv', area=40, height=470, apex_x=4.6,
        poly_x=[4.0627, 4.6, 5.2852, 4.0627], poly_y=[0, 470, 0, 0],
        p_line=[(4.0627, 0), (5.2852, 0)], q1=(4.0627, 0), q2=(5.2852, 0),
    )
    detected = service.detect_peaks('uv', y, x, threshold=.1,
                                    integration_baseline='linear')
    assert len(detected) == 1
    assert abs(detected[0].rt - 3.93333) < .04
    assert detected[0].rt_end > manual.rt_start  # reproduce overlapping tails
    assert service.get_peaks('uv') == [manual, detected[0]]
    # Re-running replaces the automatic result, without duplicating the manual peak.
    again = service.detect_peaks('uv', y, x, threshold=.1,
                                 integration_baseline='linear')
    assert len(again) == 1 and len(service.get_peaks('uv')) == 2


def test_detection_does_not_split_an_intentionally_integrated_manual_region():
    x = np.linspace(0, 6, 601)
    y = 100*np.exp(-((x-3)/.12)**2) + 80*np.exp(-((x-3.4)/.12)**2)
    service = PeakService()
    manual = service.add_baseline_peak(
        file_id='uv', area=40, height=100, apex_x=3,
        poly_x=[2.5, 3, 4, 2.5], poly_y=[0, 100, 0, 0],
        p_line=[(2.5, 0), (4, 0)], q1=(2.5, 0), q2=(4, 0),
    )
    assert service.detect_peaks('uv', y, x, threshold=.1) == []
    assert service.get_peaks('uv') == [manual]
