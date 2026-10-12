"""Integrate in All Files on a deconvolved shoulder: only that component is
integrated in the other samples, as its own compound."""

import numpy as np
import pytest
from lmfit.models import ExponentialGaussianModel

from services.cross_deconvolution import (
    deconv_siblings, integrate_deconvolved_in_files, is_deconvolved_component,
    status_text,
)
from services.deconvolution_service import DeconvolutionService
from services.peak_service import PeakService

X = np.arange(1.9, 2.9, 0.0008)
MAIN_RT, SHOULDER_RT = 2.262, 2.232
SIGMA_MAIN, SIGMA_SHOULDER = 0.011, 0.005
GAMMA = 120.0


def _emg(amplitude, center, sigma=SIGMA_MAIN, gamma=GAMMA):
    return ExponentialGaussianModel().eval(x=X, amplitude=amplitude, center=center,
                                           sigma=sigma, gamma=gamma)


def _sample(scale, drift, seed, shoulder_area=0.6, main_area=10.0, neighbour=True):
    """Main EMG + earlier shoulder EMG (+ a later separate peak) with noise."""
    y = _emg(scale * main_area, MAIN_RT + drift) \
        + _emg(scale * shoulder_area, SHOULDER_RT + drift, SIGMA_SHOULDER)
    if neighbour:
        y = y + _emg(scale * 25.0, 2.55 + drift)
    y = y + np.random.default_rng(seed).normal(0, 0.05 * scale, X.size)
    return y


@pytest.fixture
def setup():
    svc = DeconvolutionService()
    ps = PeakService()
    signals = {
        'f1': _sample(1.0, 0.000, 1),
        'f2': _sample(2.3, 0.006, 2),
        'f3': _sample(0.6, -0.008, 3),
    }
    yr = signals['f1']
    mask = (X >= 2.15) & (X <= 2.42)
    xr, yr = X[mask], yr[mask]
    # explicit seeds: independent of the automatic shoulder detection
    centers = [(SHOULDER_RT, float(np.interp(SHOULDER_RT, xr, yr))),
               (MAIN_RT, float(np.interp(MAIN_RT, xr, yr)))]
    result = svc.fit_peaks(xr, yr, centers)
    new = svc.result_to_peaks(result, 'f1', 2.25)
    ps._peaks['f1'] = new
    shoulder = min(new, key=lambda p: p.rt)
    main = max(new, key=lambda p: p.rt)
    return svc, ps, signals, shoulder, main


def _get_xy(signals):
    return lambda fid: (X, signals[fid])


class TestSiblings:
    def test_siblings_share_region_and_sort_by_rt(self, setup):
        _, ps, _, shoulder, main = setup
        sibs = deconv_siblings(ps.get_peaks('f1'), shoulder)
        assert [p.peak_id for p in sibs] == [shoulder.peak_id, main.peak_id]
        assert is_deconvolved_component(ps.get_peaks('f1'), shoulder)

    def test_plain_peak_is_not_a_deconvolved_component(self):
        ps = PeakService()
        peak = ps.add_baseline_peak(
            file_id='f1', area=1.0, height=1.0, apex_x=2.0,
            poly_x=[1.9, 2.1], poly_y=[0, 0], p_line=[(1.9, 0), (2.1, 0)],
            q1=(1.9, 0), q2=(2.1, 0), source='manual')
        assert not is_deconvolved_component(ps.get_peaks('f1'), peak)

    def test_lone_deconvolved_peak_is_not_a_component_set(self, setup):
        _, ps, _, shoulder, main = setup
        ps.remove_peak('f1', main.peak_id)
        assert not is_deconvolved_component(ps.get_peaks('f1'), shoulder)


class TestIntegrateShoulder:
    def test_each_target_gets_only_the_shoulder(self, setup):
        svc, ps, signals, shoulder, _ = setup
        out = integrate_deconvolved_in_files(
            ps, 'f1', shoulder, ['f2', 'f3'], _get_xy(signals), tol=0.3, svc=svc)
        assert out.skipped == []
        for fid, scale, drift in (('f2', 2.3, 0.006), ('f3', 0.6, -0.008)):
            peaks = ps.get_peaks(fid)
            assert len(peaks) == 1, 'only the shoulder, not the main peak'
            p = peaks[0]
            assert p.source == 'deconvolved'
            assert p.name == shoulder.name
            assert abs(p.rt - (SHOULDER_RT + drift)) < 0.01
            true_area = scale * 0.6
            assert abs(p.area - true_area) / true_area < 0.4
            # nothing close to the main peak's area (10 * scale)
            assert p.area < 0.2 * scale * 10.0

    def test_shoulder_peaks_group_together_and_apart_from_main(self, setup):
        svc, ps, signals, shoulder, main = setup
        for clicked in (shoulder, main):
            integrate_deconvolved_in_files(
                ps, 'f1', clicked, ['f2', 'f3'], _get_xy(signals), tol=0.3, svc=svc)
        groups = ps.group_peaks_across_samples()
        assert len(groups) == 2
        by_tag = {ms[0].deconv_group: ms for ms in groups.values()}
        assert set(by_tag) == {shoulder.deconv_group, main.deconv_group}
        for tag, expected_rt in ((shoulder.deconv_group, SHOULDER_RT),
                                 (main.deconv_group, MAIN_RT)):
            members = by_tag[tag]
            assert {p.file_id for p in members} == {'f1', 'f2', 'f3'}
            assert all(abs(p.rt - expected_rt) < 0.02 for p in members)

    def test_plain_peak_next_to_integrated_shoulder_stays_separate(self, setup):
        svc, ps, signals, shoulder, _ = setup
        integrate_deconvolved_in_files(
            ps, 'f1', shoulder, ['f2', 'f3'], _get_xy(signals), tol=0.3, svc=svc)
        for fid, drift in (('f2', 0.006), ('f3', -0.008)):
            ps.add_baseline_peak(
                file_id=fid, area=10.0, height=1.0, apex_x=MAIN_RT + drift,
                poly_x=[2.2, 2.4], poly_y=[0, 0], p_line=[(2.2, 0), (2.4, 0)],
                q1=(2.2, 0), q2=(2.4, 0), source='manual')
        groups = ps.group_peaks_across_samples()
        plain = [ms for ms in groups.values() if all(p.source == 'manual' for p in ms)]
        assert len(plain) == 1 and {p.file_id for p in plain[0]} == {'f2', 'f3'}

    def test_rerun_replaces_instead_of_duplicating(self, setup):
        svc, ps, signals, shoulder, _ = setup
        for _ in range(2):
            integrate_deconvolved_in_files(
                ps, 'f1', shoulder, ['f2'], _get_xy(signals), tol=0.3, svc=svc)
        assert len(ps.get_peaks('f2')) == 1

    def test_main_component_can_be_integrated_too(self, setup):
        svc, ps, signals, _, main = setup
        out = integrate_deconvolved_in_files(
            ps, 'f1', main, ['f2'], _get_xy(signals), tol=0.3, svc=svc)
        assert out.skipped == []
        p = ps.get_peaks('f2')[0]
        assert abs(p.rt - (MAIN_RT + 0.006)) < 0.01
        assert abs(p.area - 23.0) / 23.0 < 0.15

    def test_file_without_shoulder_is_skipped_with_reason(self, setup):
        svc, ps, signals, shoulder, _ = setup
        signals['f2'] = _emg(2.3 * 10.0, MAIN_RT + 0.006)  # plain single peak
        signals['f3'] = np.zeros_like(X)
        out = integrate_deconvolved_in_files(
            ps, 'f1', shoulder, ['f2', 'f3'], _get_xy(signals), tol=0.3, svc=svc)
        skipped = dict(out.skipped)
        assert 'f3' in skipped
        for fid in ('f2', 'f3'):
            if fid in skipped:
                assert ps.get_peaks(fid) == []
        text = status_text(out, 2, name_of=lambda f: f.upper())
        assert text.startswith(f'Integrated {len(out.integrated)}/2 files')
        assert 'skipped:' in text and 'F3' in text

    def test_missing_signal_is_skipped(self, setup):
        svc, ps, signals, shoulder, _ = setup
        out = integrate_deconvolved_in_files(
            ps, 'f1', shoulder, ['f2'], lambda fid: (None, None), tol=0.3, svc=svc)
        assert out.skipped == [('f2', 'no signal')]
        assert out.integrated == []
