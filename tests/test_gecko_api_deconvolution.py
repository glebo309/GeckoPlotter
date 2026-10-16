"""Agent deconvolution uses the GUI's EMG fit and editable component peaks."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from lmfit.models import ExponentialGaussianModel
from scipy.signal import find_peaks

from gecko_api import GeckoError, Workspace
from services.data_store import Bundle, BundleType, Component, ComponentRole
from services.deconvolution_service import DeconvolutionService


def _sample(ws, name, x, y):
    component = Component(name + '-uv', ComponentRole.PRIMARY, name + '.csv',
                          dataframe=pd.DataFrame({'time': x, 'signal': y}),
                          metadata={'auto_x': 'time', 'auto_y': ['signal']})
    ws.store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM, component_list=[component]))


@pytest.fixture
def shoulder():
    ws = Workspace()
    x = np.linspace(0, 2, 1001)
    model = ExponentialGaussianModel()
    left = model.eval(x=x, amplitude=2, center=.88, sigma=.025, gamma=60)
    main = model.eval(x=x, amplitude=10, center=1, sigma=.04, gamma=40)
    for name, scale in [('standard', 1), ('sample', 2)]:
        _sample(ws, name, x, 5 + scale * (left + main))
    return ws, x, left, main


@pytest.mark.parametrize('n_peaks', [None, 2])
def test_shoulder_areas_and_gui_peak_storage(shoulder, n_peaks):
    ws, x, left, main = shoulder
    ws.agent = {'client': 'test-agent'}
    rows = ws.deconvolve(.6, 1.5, n_peaks=n_peaks, names=['alanine', 'main'])
    assert len(rows) == 2
    for row, scale in zip(rows, [1, 2]):
        assert row['r_squared'] > .9999 and not row['warnings']
        assert row['residual_rmse'] < .1 and row['redchi'] >= 0
        peaks = row['components']
        assert [p['name'] for p in peaks] == ['alanine', 'main']
        assert [p['area'] for p in peaks] == pytest.approx([2 * scale, 10 * scale], rel=.03)
        assert [p['apex_rt'] for p in peaks] == pytest.approx([x[left.argmax()], x[main.argmax()]], abs=.003)
        assert sum(p['area_percent'] for p in peaks) == pytest.approx(100, abs=.02)
        assert all(p['height'] > 0 and p['source'] == 'deconvolved' for p in peaks)
        stored = ws.store.peak_service.get_peaks(row['sample'] + '-uv')
        assert len({p.deconv_group for p in stored}) == 2
        assert all(p.poly_x and p.poly_y and p.p_line and p.q1 and p.q2 and p.fit_params for p in stored)
    assert ws.store.analysis_history[-1]['agent'] == ws.agent
    assert 'Deconvolved' in ws.store.analysis_history[-1]['trigger'][0]
    assert ws.store.peak_service.undo()
    assert ws.peaks() == []
    assert ws.store.peak_service.redo()
    assert len(ws.peaks()) == 4


def test_bounded_apex_markers_recover_the_shoulder(shoulder):
    ws, x, left, main = shoulder
    row = ws.deconvolve(.6, 1.5, samples=['standard'], centers=[.895, 1.02], center_tolerance=.01)[0]
    assert [p['area'] for p in row['components']] == pytest.approx([2, 10], rel=.03)
    assert [p['apex_rt'] for p in row['components']] == pytest.approx([x[left.argmax()], x[main.argmax()]], abs=.003)


def test_unresolved_shoulder_without_a_second_maximum():
    ws = Workspace()
    x = np.linspace(0, 2, 1001)
    model = ExponentialGaussianModel()
    left = model.eval(x=x, amplitude=2, center=.92, sigma=.025, gamma=60)
    main = model.eval(x=x, amplitude=10, center=1, sigma=.04, gamma=40)
    assert len(find_peaks(left + main)[0]) == 1
    _sample(ws, 'shoulder', x, left + main)
    row = ws.deconvolve(.6, 1.5)[0]
    assert [p['area'] for p in row['components']] == pytest.approx([2, 10], rel=.03)


def test_default_count_fit_removes_baseline_and_limits_shoulder_tailing():
    ws = Workspace()
    x = np.linspace(.6, 1.6, 801)
    model = ExponentialGaussianModel()
    baseline = 5 + 30 * (x - x[0])
    y = baseline + model.eval(x=x, amplitude=2, center=.92, sigma=.025, gamma=60)
    y += model.eval(x=x, amplitude=10, center=1, sigma=.04, gamma=40)
    _sample(ws, 'sloping', x, y)
    row = ws.deconvolve(.6, 1.6, n_peaks=2)[0]
    assert [p['area'] for p in row['components']] == pytest.approx([2, 10], rel=.03)
    stored = sorted(ws.store.peak_service.get_peaks('sloping-uv'), key=lambda p: p.rt)
    assert stored[0].fit_params['gamma'] >= stored[1].fit_params['gamma']
    assert stored[0].p_line[0][1] == pytest.approx(5, abs=.01)
    assert stored[0].p_line[-1][1] == pytest.approx(35, abs=.01)
    assert row['components'][0]['fwhm'] < 2 * row['components'][1]['fwhm']


def test_requested_count_overrides_detection(shoulder, monkeypatch):
    monkeypatch.setattr(DeconvolutionService, 'auto_detect_centers', lambda self, x, y, **kw: [(1.02, 100)])
    row = shoulder[0].deconvolve(.6, 1.5, samples=['standard'], n_peaks=2)[0]
    assert [p['area'] for p in row['components']] == pytest.approx([2, 10], rel=.03)


@pytest.mark.parametrize('sample', ['0.31.mM', '0.625mM', '1.25mM', '2.5mM', '5mM', '10mM'])
def test_alanine_default_count_produces_a_leading_peak_not_a_shelf(sample):
    data = json.loads((Path(__file__).parent / 'fixtures' / 'deconv_ala_250nm.json').read_text())
    signal = data['l-alanine ' + sample]
    ws = Workspace()
    _sample(ws, 'standard', signal['x'], signal['y'])
    row = ws.deconvolve(2.15, 2.36, n_peaks=2)[0]
    left, main = row['components']
    assert 2.22 < left['apex_rt'] < 2.245
    assert .005 - 1e-9 <= left['fwhm'] < 2 * main['fwhm']
    peaks = ws.store.peak_service.get_peaks('standard-uv')
    assert peaks[0].fit_params['gamma'] >= peaks[1].fit_params['gamma']
    x = np.linspace(2.15, 2.36, 501)
    for peak in peaks:
        curve = ExponentialGaussianModel().eval(x=x, **{k: peak.fit_params[k]
                                                       for k in ['center', 'amplitude', 'sigma', 'gamma']})
        assert max(curve[0], curve[-1]) < .02 * curve.max()


def test_broad_component_shape_warning():
    ws = Workspace()
    x = np.linspace(0, 3, 1001)
    model = ExponentialGaussianModel()
    y = model.eval(x=x, amplitude=3, center=1, sigma=.2, gamma=40)
    y += model.eval(x=x, amplitude=10, center=1.5, sigma=.04, gamma=40)
    _sample(ws, 'broad', x, y)
    row = ws.deconvolve(0, 3, centers=[1, 1.5])[0]
    assert any('not peak-shaped' in w for w in row['warnings'])


def test_warns_when_apex_hits_a_marker_bound(shoulder):
    row = shoulder[0].deconvolve(.6, 1.5, samples=['standard'], centers=[.86, 1.02], center_tolerance=.005)[0]
    assert any('bound' in warning for warning in row['warnings'])


def test_failed_sample_does_not_prevent_fit_or_undo(shoulder):
    ws = shoulder[0]
    _sample(ws, 'empty', np.linspace(3, 4, 100), np.zeros(100))
    rows = ws.deconvolve(.6, 1.5, samples=['empty', 'sample'])
    assert 'error' in rows[0] and len(rows[1]['components']) == 2
    assert {p['sample'] for p in ws.peaks()} == {'sample'}
    assert ws.store.peak_service.undo() and ws.peaks() == []


def test_replaces_envelope_and_previous_fit_with_one_undo(shoulder):
    ws = shoulder[0]
    ws.integrate(.6, 1.5, snap_to_valleys=False)
    before = ws.peaks()
    ws.deconvolve(.6, 1.5, centers=[1.02, .9], names=['alanine', 'main'])
    assert len(ws.peaks()) == 4
    ws.deconvolve(.6, 1.5)
    assert len(ws.peaks()) == 4
    assert ws.store.peak_service.undo()
    assert {p['name'] for p in ws.peaks()} == {'alanine', 'main'}
    assert ws.store.peak_service.undo()
    assert ws.peaks() == before


@pytest.mark.parametrize('kwargs', [
    {'rt_start': 1.5, 'rt_end': .6}, {'rt_start': float('nan'), 'rt_end': 1.5},
    {'n_peaks': 0}, {'n_peaks': 2.5}, {'centers': [.9, .9]}, {'centers': [3]},
    {'n_peaks': 2, 'names': ['only one']}, {'n_peaks': 2, 'centers': [.9]},
    {'prominence': -1}, {'center_tolerance': 0}, {'center_tolerance': .01},
])
def test_invalid_arguments_leave_peaks_untouched(shoulder, kwargs):
    ws = shoulder[0]
    with pytest.raises(GeckoError):
        ws.deconvolve(**dict({'rt_start': .6, 'rt_end': 1.5}, **kwargs))
    assert ws.peaks() == [] and not ws.store.peak_service.can_undo


def test_single_peak_and_empty_window_are_per_sample_errors():
    ws = Workspace()
    x = np.linspace(0, 2, 1001)
    _sample(ws, 'single', x, 100 * np.exp(-.5 * ((x - 1) / .04) ** 2))
    assert 'error' in ws.deconvolve(.6, 1.5)[0]
    assert 'error' in ws.deconvolve(3, 4)[0]
    assert ws.peaks() == [] and not ws.store.peak_service.can_undo


def test_poor_fit_is_reported(shoulder, monkeypatch):
    fit = DeconvolutionService.fit_peaks

    def poor_fit(self, *args, **kwargs):
        result = fit(self, *args, **kwargs)
        result.r_squared = .8
        return result

    monkeypatch.setattr(DeconvolutionService, 'fit_peaks', poor_fit)
    row = shoulder[0].deconvolve(.6, 1.5, samples=['sample'], centers=[.9, 1.02])[0]
    assert row['r_squared'] == .8 and row['warnings']


def test_mcp_and_live_agent_deconvolution(shoulder, monkeypatch):
    pytest.importorskip('mcp')
    import gecko_mcp
    from services.live_agent import METHODS, READS, describe
    from services.live_focus import focus
    calls = []
    monkeypatch.setattr(gecko_mcp, '_run', lambda *args, **kwargs: calls.append((args, kwargs)) or [])
    assert gecko_mcp.deconvolve(.6, 1.5, samples=['sample'], n_peaks=2, names=['alanine', 'main']) == []
    assert calls == [(('deconvolve', .6, 1.5, ['sample'], None, 2, ['alanine', 'main'], None, .05, None), {'ctx': None})]
    assert 'deconvolve' in METHODS and 'deconvolve' not in READS
    assert describe('deconvolve', [.6, 1.5]) == 'deconvolving 0.6-1.5 min'
    ws = shoulder[0]
    rows = ws.deconvolve(.6, 1.5, samples=['sample'])
    assert focus(ws, 'deconvolve', [.6, 1.5], {'samples': ['sample']}, rows)['active'] == 'sample-uv'
