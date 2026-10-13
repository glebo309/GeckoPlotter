"""Shoulder / overlap detection in ``DeconvolutionService.auto_detect_centers``.

A shoulder has no local maximum, so ``find_peaks`` alone never sees it. These
tests pin the curvature-based detection and, just as important, the guards that
keep a clean tailing peak, noise and flat regions from being split.
"""

import json
import time
from pathlib import Path

import numpy as np
import pytest
from lmfit.models import ExponentialGaussianModel

from services.deconvolution_service import DeconvolutionService

FIXTURE = Path(__file__).parent / "fixtures" / "deconv_ala_excerpts.json"


def _gauss(x, height, center, sigma):
    return height * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _emg_peak(x, center, sigma, gamma, height=100.0):
    y = ExponentialGaussianModel().eval(x=x, amplitude=1.0, center=center, sigma=sigma, gamma=gamma)
    return y / y.max() * height


@pytest.fixture
def x():
    return np.linspace(0.0, 2.0, 1000)


@pytest.fixture
def svc():
    return DeconvolutionService()


def _xs(centers):
    return sorted(c[0] for c in centers)


class TestShoulderDetection:
    @pytest.mark.parametrize("noise", [0.0, 0.3])
    def test_left_shoulder_becomes_second_center(self, svc, x, noise):
        rng = np.random.default_rng(1)
        y = _gauss(x, 100, 1.0, 0.04) + _gauss(x, 40, 0.88, 0.035) + rng.normal(0, noise, x.size)
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 2
        assert xs[1] == pytest.approx(1.0, abs=0.02)            # main apex
        assert xs[0] == pytest.approx(0.88, abs=0.04)           # hidden component

    @pytest.mark.parametrize("noise", [0.0, 0.3])
    def test_weak_left_shoulder_without_local_maximum(self, svc, x, noise):
        rng = np.random.default_rng(2)
        y = _gauss(x, 100, 1.0, 0.04) + _gauss(x, 25, 0.92, 0.035) + rng.normal(0, noise, x.size)
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 2
        assert xs[0] == pytest.approx(0.92, abs=0.04)

    @pytest.mark.parametrize("noise", [0.0, 0.3])
    def test_right_shoulder(self, svc, x, noise):
        rng = np.random.default_rng(3)
        y = _gauss(x, 100, 1.0, 0.04) + _gauss(x, 30, 1.09, 0.04) + rng.normal(0, noise, x.size)
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 2
        assert xs[1] == pytest.approx(1.1, abs=0.04)

    def test_shoulders_on_both_flanks(self, svc, x):
        rng = np.random.default_rng(4)
        y = (_gauss(x, 100, 1.0, 0.04) + _gauss(x, 35, 0.89, 0.035)
             + _gauss(x, 32, 1.12, 0.04) + rng.normal(0, 0.3, x.size))
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 3
        assert xs[0] == pytest.approx(0.89, abs=0.04)
        assert xs[2] == pytest.approx(1.12, abs=0.05)

    def test_shoulder_centers_are_usable_seeds(self, svc, x):
        """The (x, y) pairs feed straight into the composite fit."""
        y = _gauss(x, 100, 1.0, 0.04) + _gauss(x, 40, 0.88, 0.035)
        centers = svc.auto_detect_centers(x, y)
        result = svc.fit_peaks(x, y, centers)
        assert result is not None
        assert len(result.components) == 2
        assert result.r_squared > 0.999
        for _, height in centers:
            assert height > 0


class TestNoOverSplitting:
    @pytest.mark.parametrize("gamma", [6.0, 2.5, 1.5])
    @pytest.mark.parametrize("noise", [0.0, 0.3])
    def test_single_tailing_peak_stays_single(self, svc, x, gamma, noise):
        rng = np.random.default_rng(5)
        y = _emg_peak(x, 0.95, 0.04, gamma) + rng.normal(0, noise, x.size)
        assert len(svc.auto_detect_centers(x, y)) == 1

    @pytest.mark.parametrize("noise", [0.0, 0.3, 1.0])
    def test_single_gaussian_stays_single(self, svc, x, noise):
        rng = np.random.default_rng(6)
        y = _gauss(x, 100, 1.0, 0.04) + rng.normal(0, noise, x.size)
        assert len(svc.auto_detect_centers(x, y)) == 1

    @pytest.mark.parametrize("noise", [0.0, 0.3])
    def test_two_resolved_peaks_stay_two(self, svc, x, noise):
        rng = np.random.default_rng(7)
        y = _gauss(x, 100, 0.7, 0.04) + _gauss(x, 60, 1.3, 0.04) + rng.normal(0, noise, x.size)
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 2
        assert xs[0] == pytest.approx(0.7, abs=0.02)
        assert xs[1] == pytest.approx(1.3, abs=0.02)

    def test_touching_peaks_stay_two(self, svc, x):
        y = _gauss(x, 100, 0.9, 0.04) + _gauss(x, 70, 1.1, 0.04)
        assert len(svc.auto_detect_centers(x, y)) == 2

    def test_flat_region_has_no_centers(self, svc, x):
        assert svc.auto_detect_centers(x, np.full(x.size, 5.0)) == []

    @pytest.mark.parametrize("seed", range(5))
    def test_noise_only_has_no_centers(self, svc, x, seed):
        rng = np.random.default_rng(seed)
        assert svc.auto_detect_centers(x, rng.normal(0, 0.5, x.size)) == []

    def test_noisy_flat_baseline_with_one_peak(self, svc, x):
        rng = np.random.default_rng(8)
        y = 5.0 + _gauss(x, 60, 1.0, 0.05) + rng.normal(0, 0.8, x.size)
        assert len(svc.auto_detect_centers(x, y)) == 1

    def test_small_region_and_coarse_sampling_do_not_crash(self, svc):
        xs = np.linspace(0, 1, 15)
        assert isinstance(svc.auto_detect_centers(xs, _gauss(xs, 10, 0.5, 0.1)), list)
        assert svc.auto_detect_centers(xs[:2], xs[:2]) == []

    def test_prominence_still_controls_apex_detection(self, svc, x):
        y = _gauss(x, 100, 0.7, 0.04) + _gauss(x, 10, 1.3, 0.04)
        assert len(svc.auto_detect_centers(x, y, prominence=0.02)) == 2
        assert len(svc.auto_detect_centers(x, y, prominence=0.60)) == 1


class TestSpeed:
    def test_detection_is_fast(self, svc, x):
        rng = np.random.default_rng(9)
        y = (_gauss(x, 100, 1.0, 0.04) + _gauss(x, 35, 0.89, 0.035)
             + _gauss(x, 32, 1.12, 0.04) + rng.normal(0, 0.3, x.size))
        t0 = time.perf_counter()
        svc.auto_detect_centers(x, y)
        assert time.perf_counter() - t0 < 3.0


@pytest.fixture(scope="module")
def excerpts():
    raw = json.loads(FIXTURE.read_text())
    out = {}
    for name, s in raw.items():
        y = np.asarray(s["y"], dtype=float)
        out[name] = (s["x0"] + s["dx"] * np.arange(y.size), y)
    return out


class TestRealHplcExcerpts:
    """Excerpts of Shimadzu PDA exports (l-alanine calibration, 263 nm)."""

    def test_shoulder_2p5mM(self, svc, excerpts):
        xs = _xs(svc.auto_detect_centers(*excerpts["shoulder_2p5mM"]))
        assert len(xs) == 2
        assert xs[0] == pytest.approx(2.235, abs=0.012)
        assert xs[1] == pytest.approx(2.265, abs=0.008)

    def test_shoulder_0p625mM(self, svc, excerpts):
        xs = _xs(svc.auto_detect_centers(*excerpts["shoulder_0p625mM"]))
        assert len(xs) == 2
        assert xs[0] == pytest.approx(2.235, abs=0.012)
        assert xs[1] == pytest.approx(2.265, abs=0.008)

    def test_blank_has_no_shoulder(self, svc, excerpts):
        assert len(svc.auto_detect_centers(*excerpts["blank_peak"])) == 1

    def test_tailing_second_peak_stays_single(self, svc, excerpts):
        xs = _xs(svc.auto_detect_centers(*excerpts["single_tailing_5mM"]))
        assert len(xs) == 1
        assert xs[0] == pytest.approx(2.54, abs=0.02)

    def test_shoulder_fit_runs_end_to_end(self, svc, excerpts):
        x, y = excerpts["shoulder_2p5mM"]
        centers = svc.auto_detect_centers(x, y)
        t0 = time.perf_counter()
        result = svc.fit_peaks(x, y, centers)
        assert time.perf_counter() - t0 < 1.0
        assert len(result.components) == 2
        assert result.r_squared > 0.99


class TestBroadShoulderOnATail:
    """A low, broad plateau on the tail only shows in the curvature at a coarser scale than the main peak's."""

    def _data(self, noise):
        rng = np.random.default_rng(5)
        x = np.linspace(1.5, 2.6, 2300)
        main = _emg_peak(x, 1.78, 0.025, 25.0, height=990.0)
        return x, main, rng.normal(0, noise, x.size)

    @pytest.mark.parametrize("noise", [0.0, 0.2])
    def test_plateau_on_the_tail_is_a_second_component(self, svc, noise):
        x, main, jitter = self._data(noise)
        y = main + _gauss(x, 80.0, 2.0, 0.06) + jitter
        xs = _xs(svc.auto_detect_centers(x, y))
        assert len(xs) == 2
        assert xs[0] == pytest.approx(x[np.argmax(main)], abs=0.02) and xs[1] == pytest.approx(2.0, abs=0.06)

    @pytest.mark.parametrize("noise", [0.0, 0.2])
    def test_the_same_tailing_peak_without_the_plateau_stays_one_component(self, svc, noise):
        x, main, jitter = self._data(noise)
        assert len(svc.auto_detect_centers(x, main + jitter)) == 1
