"""Tests for the EMG peak deconvolution service.

The service ports validated fitting logic from deconvolution_sandbox and
exposes it as a Dash-free computation layer.
"""

import numpy as np
import pytest
from lmfit.models import ExponentialGaussianModel

import json

from services.deconvolution_service import (
    DeconvolutionService,
    DeconvComponent,
    DeconvResult,
    serialize_result,
    deserialize_result,
)


def _emg(x, amplitude, center, sigma, gamma):
    return ExponentialGaussianModel().eval(
        x=x, amplitude=amplitude, center=center, sigma=sigma, gamma=gamma
    )


@pytest.mark.parametrize('gamma', [40, 60])
def test_bounded_tailing_and_linear_baseline_recover_components(gamma):
    x = np.linspace(.6, 1.6, 801)
    baseline = 5 + 30 * (x - x[0])
    y = baseline + _emg(x, 2, .92, .025, gamma) + _emg(x, 10, 1, .04, 40)
    svc = DeconvolutionService()
    result = svc.fit_peaks(x, y, [(.94, 30), (1.02, 100)],
                           baseline=baseline, tail_reference=1)
    assert [c.area for c in result.components] == pytest.approx([2, 10], rel=.03)
    assert result.components[0].gamma >= result.components[1].gamma
    assert result.r_squared > .99999
    assert result.baseline == pytest.approx(baseline)
    peaks = svc.result_to_peaks(result, 'sample', 1)
    assert peaks[0].p_line == [(x[0], baseline[0]), (x[-1], baseline[-1])]
    assert peaks[0].fit_params['baseline'] == peaks[0].p_line


def test_count_seeding_finds_leading_shoulder_on_a_rising_baseline():
    x = np.linspace(2.15, 2.4, 601)
    baseline = 5 + 60 * (x - x[0])
    y = baseline + _emg(x, .4, 2.229, .004, 100) + _emg(x, 12, 2.257, .009, 90)
    svc = DeconvolutionService()
    seeds = svc.seed_centers(x, y - baseline, 2)
    assert len(seeds) == 2
    assert seeds[0][0] == pytest.approx(2.234, abs=.008)
    assert seeds[1][0] == pytest.approx(2.264, abs=.008)


def test_linear_baseline_is_fitted_with_the_peaks():
    x = np.linspace(.6, 1.6, 801)
    baseline = 5 + 30 * (x - x[0])
    y = baseline + _emg(x, 2, .92, .025, 60) + _emg(x, 10, 1, .04, 40)
    svc = DeconvolutionService()
    result = svc.fit_peaks(x, y, [(.94, 30), (1.02, 100)],
                           baseline=baseline + 3, fit_baseline=True, tail_reference=1)
    assert result.baseline == pytest.approx(baseline, abs=.01)
    assert [c.area for c in result.components] == pytest.approx([2, 10], rel=.03)
    assert result.best_fit + result.residuals == pytest.approx(y)


@pytest.fixture
def two_peak_chromatogram():
    """Two clearly resolved EMG peaks on a clean baseline."""
    x = np.linspace(0, 20, 2000)
    truth = [
        dict(amplitude=1000, center=6.0, sigma=0.3, gamma=0.4),
        dict(amplitude=700, center=10.0, sigma=0.35, gamma=0.3),
    ]
    y = np.zeros_like(x)
    for p in truth:
        y += _emg(x, **p)
    return x, y, truth


@pytest.fixture
def overlapping_chromatogram():
    """Three partially overlapping EMG peaks (co-elution)."""
    x = np.linspace(0, 20, 2000)
    truth = [
        dict(amplitude=1000, center=5.5, sigma=0.3, gamma=0.5),
        dict(amplitude=700, center=6.8, sigma=0.25, gamma=0.3),
        dict(amplitude=500, center=7.8, sigma=0.2, gamma=0.6),
    ]
    y = np.zeros_like(x)
    for p in truth:
        y += _emg(x, **p)
    return x, y, truth


class TestAutoDetectCenters:
    def test_finds_both_resolved_peaks(self, two_peak_chromatogram):
        x, y, truth = two_peak_chromatogram
        svc = DeconvolutionService()
        centers = svc.auto_detect_centers(x, y, prominence=0.05)
        assert len(centers) == 2
        detected_x = sorted(c[0] for c in centers)
        # The EMG apex sits at or right of the nominal center (gamma tailing
        # pulls it downstream); allow up to ~1 min of apex shift.
        assert 6.0 <= detected_x[0] < 7.0
        assert 10.0 <= detected_x[1] < 11.0

    def test_returns_xy_tuples(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        centers = svc.auto_detect_centers(x, y)
        for c in centers:
            assert len(c) == 2
            assert isinstance(c[0], float)
            assert isinstance(c[1], float)

    def test_higher_prominence_finds_fewer_peaks(self, overlapping_chromatogram):
        x, y, _ = overlapping_chromatogram
        svc = DeconvolutionService()
        loose = svc.auto_detect_centers(x, y, prominence=0.02)
        strict = svc.auto_detect_centers(x, y, prominence=0.40)
        assert len(strict) <= len(loose)


class TestFitPeaks:
    def test_recovers_two_peak_fit(self, two_peak_chromatogram):
        x, y, truth = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        assert isinstance(result, DeconvResult)
        assert len(result.components) == 2
        assert result.r_squared > 0.99
        centers = sorted(c.center for c in result.components)
        assert abs(centers[0] - 6.0) < 0.1
        assert abs(centers[1] - 10.0) < 0.1

    def test_components_carry_curve_and_area(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        for comp in result.components:
            assert isinstance(comp, DeconvComponent)
            assert comp.curve.shape == x.shape
            assert comp.area > 0
            assert comp.sigma > 0

    def test_resolves_overlapping_peaks(self, overlapping_chromatogram):
        x, y, truth = overlapping_chromatogram
        svc = DeconvolutionService()
        centers = [(p["center"], p["amplitude"]) for p in truth]
        result = svc.fit_peaks(x, y, centers)
        assert len(result.components) == 3
        assert result.r_squared > 0.99

    def test_best_fit_and_residuals_match_x_length(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        assert result.best_fit.shape == x.shape
        assert result.residuals.shape == x.shape

    def test_empty_centers_returns_none(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        assert svc.fit_peaks(x, y, []) is None

    def test_narrow_rt_window_allows_fast_emg_tails(self):
        """Regression: gamma bounds must work in narrow chromatogram windows."""
        x = np.linspace(6.20, 6.60, 1000)
        y = (
            _emg(x, amplitude=7.0, center=6.34, sigma=0.009, gamma=40.0)
            + _emg(x, amplitude=9.0, center=6.42, sigma=0.012, gamma=45.0)
        )
        svc = DeconvolutionService()
        centers = svc.auto_detect_centers(x, y, prominence=0.05)
        result = svc.fit_peaks(x, y, centers)

        assert result is not None
        assert len(result.components) == 2
        assert result.r_squared > 0.99
        assert min(c.gamma for c in result.components) > 10.0

    def test_narrow_offset_region_fits_actual_signal_floor(self):
        """The selected p-line is only a crop; fit uses the signal's own floor."""
        x = np.linspace(6.28, 6.56, 300)
        y = (
            8.0
            + _emg(x, amplitude=3.5, center=6.36, sigma=0.018, gamma=35.0)
            + _emg(x, amplitude=7.0, center=6.45, sigma=0.012, gamma=45.0)
        )
        svc = DeconvolutionService()
        centers = svc.auto_detect_centers(x, y, prominence=0.05)
        result = svc.fit_peaks(x, y, centers)

        assert result is not None
        assert len(result.components) == 2
        assert result.r_squared > 0.99
        assert result.baseline[0] == pytest.approx(8.0, abs=0.2)


class TestResultToPeaks:
    def test_converts_components_to_peaks(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        peaks = svc.result_to_peaks(result, file_id="f1", region_rt=8.0)
        assert len(peaks) == 2
        for p in peaks:
            assert p.source == "deconvolved"
            assert p.file_id == "f1"
            assert p.area > 0
            assert p.fit_params is not None
            assert {"sigma", "gamma", "amplitude"} <= set(p.fit_params)

    def test_deconv_group_tags_are_unique_per_component(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        peaks = svc.result_to_peaks(result, file_id="f1", region_rt=8.0)
        tags = [p.deconv_group for p in peaks]
        assert len(set(tags)) == len(tags)
        for t in tags:
            assert t.startswith("deconv_8.0_c")

    def test_polygon_is_closed_with_zero_baseline(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        peaks = svc.result_to_peaks(result, file_id="f1", region_rt=8.0)
        p = peaks[0]
        assert p.poly_x is not None and p.poly_y is not None
        assert len(p.poly_x) == len(p.poly_y)
        # closed polygon: first and last x coincide
        assert p.poly_x[0] == p.poly_x[-1]
        # baseline leg sits at y=0
        assert min(p.poly_y) == pytest.approx(0.0, abs=1e-9)

    def test_accepted_polygon_matches_fit_region(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        peaks = svc.result_to_peaks(result, file_id="f1", region_rt=8.0)
        p = peaks[0]

        assert p.rt_start == pytest.approx(float(result.x[0]))
        assert p.rt_end == pytest.approx(float(result.x[-1]))
        assert len(p.poly_x) == max(result.x.size, 800) * 2

    def test_serialized_preview_contains_smooth_render_curves(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x[::20], y[::20], [(6.0, 1000.0), (10.0, 700.0)])
        payload = serialize_result(result)

        assert len(payload["render_x"]) == 800
        assert len(payload["render_best_fit"]) == 800
        for comp in payload["components"]:
            assert len(comp["render_curve"]) == 800

    def test_hybrid_fill_uses_measured_curve_on_clean_outer_sides(self):
        x = np.linspace(6.30, 6.56, 500)
        y = (
            _emg(x, amplitude=3.0, center=6.36, sigma=0.018, gamma=35.0)
            + _emg(x, amplitude=8.0, center=6.45, sigma=0.014, gamma=45.0)
        )
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.36, 80.0), (6.45, 200.0)])
        payload = serialize_result(result)
        render_x = np.asarray(payload["render_x"], dtype=float)
        first = payload["components"][0]
        second = payload["components"][1]
        first_top = np.asarray(first["render_stack_top"], dtype=float)
        second_top = np.asarray(second["render_stack_top"], dtype=float)
        measured = np.interp(render_x, result.x, result.best_fit + result.residuals)
        baseline = np.asarray(payload["render_baseline"], dtype=float)
        measured_top = np.maximum(measured, baseline)

        first_clean_side = render_x <= result.components[0].center
        second_clean_side = render_x >= result.components[1].center
        np.testing.assert_allclose(first_top[first_clean_side], measured_top[first_clean_side], rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(second_top[second_clean_side], measured_top[second_clean_side], rtol=1e-6, atol=1e-6)

    def test_hybrid_fill_keeps_fitted_curve_on_overlap_sides(self):
        x = np.linspace(6.30, 6.56, 500)
        y = (
            _emg(x, amplitude=3.0, center=6.36, sigma=0.018, gamma=35.0)
            + _emg(x, amplitude=8.0, center=6.45, sigma=0.014, gamma=45.0)
        )
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.36, 80.0), (6.45, 200.0)])
        payload = serialize_result(result)
        render_x = np.asarray(payload["render_x"], dtype=float)
        first = payload["components"][0]
        second = payload["components"][1]
        first_top = np.asarray(first["render_stack_top"], dtype=float)
        second_top = np.asarray(second["render_stack_top"], dtype=float)
        first_curve = np.asarray(first["render_curve"], dtype=float)
        second_curve = np.asarray(second["render_curve"], dtype=float)
        baseline = np.asarray(payload["render_baseline"], dtype=float)
        midpoint = (result.components[0].center + result.components[1].center) / 2.0

        first_overlap_side = render_x >= midpoint
        second_overlap_side = render_x <= midpoint
        np.testing.assert_allclose(first_top[first_overlap_side], first_curve[first_overlap_side] + baseline[first_overlap_side], rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(second_top[second_overlap_side], second_curve[second_overlap_side] + baseline[second_overlap_side], rtol=1e-6, atol=1e-6)


class TestResultSerialization:
    def test_round_trips_through_json(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])

        payload = serialize_result(result)
        # Must survive a dcc.Store (JSON) round-trip.
        payload = json.loads(json.dumps(payload))
        back = deserialize_result(payload)

        assert isinstance(back, DeconvResult)
        assert back.r_squared == pytest.approx(result.r_squared)
        assert back.redchi == pytest.approx(result.redchi)
        np.testing.assert_allclose(back.best_fit, result.best_fit)
        np.testing.assert_allclose(back.x, result.x)
        assert len(back.components) == len(result.components)
        np.testing.assert_allclose(
            back.components[0].curve, result.components[0].curve
        )
        assert back.components[0].center == pytest.approx(
            result.components[0].center
        )

    def test_deserialized_result_converts_to_peaks(self, two_peak_chromatogram):
        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        back = deserialize_result(json.loads(json.dumps(serialize_result(result))))
        peaks = svc.result_to_peaks(back, file_id="f1", region_rt=8.0)
        assert len(peaks) == 2
        assert all(p.source == "deconvolved" for p in peaks)


class TestPreviewOverlay:
    def test_markers_and_curves_render_to_figure(self, two_peak_chromatogram):
        import plotly.graph_objects as go
        from callbacks.peak_overlay import add_deconv_overlays

        x, y, _ = two_peak_chromatogram
        svc = DeconvolutionService()
        result = svc.fit_peaks(x, y, [(6.0, 1000.0), (10.0, 700.0)])
        payload = serialize_result(result)
        markers = [{"x": 6.0, "y": 900.0}, {"x": 10.0, "y": 600.0}]

        fig = go.Figure()
        add_deconv_overlays(fig, markers, payload, x, y)

        overlay_traces = [t for t in fig.data if t.meta == "deconv_overlay"]
        # 2 marker dots + 2 component curves + 1 composite = 5 traces.
        assert len(overlay_traces) == 5
        # 2 vertical marker lines as layout shapes.
        assert len(fig.layout.shapes) == 2


class TestAcceptPipelineEndToEnd:
    """Mirrors the spec's verification: deconvolve two samples, then confirm
    components match across samples by deconv_group tag (not RT)."""

    def _accept(self, peak_svc, svc, x, y, centers, file_id):
        """Replicate the accept-callback pipeline at the service level."""
        result = svc.fit_peaks(x, y, centers)
        region_rt = float(np.mean([c.center for c in result.components]))
        new_peaks = svc.result_to_peaks(result, file_id, region_rt)
        lo = min(p.rt_start for p in new_peaks)
        hi = max(p.rt_end for p in new_peaks)
        peak_svc.clear_region(file_id, lo, hi)
        for p in new_peaks:
            peak_svc.add_baseline_peak(
                file_id=file_id, area=p.area, height=p.height, apex_x=p.rt,
                poly_x=p.poly_x, poly_y=p.poly_y, p_line=p.p_line,
                q1=p.q1, q2=p.q2, source="deconvolved",
                deconv_group=p.deconv_group, fit_params=p.fit_params,
            )
        return new_peaks

    def test_two_samples_group_by_tag(self, overlapping_chromatogram):
        from services.peak_service import PeakService

        x, y, truth = overlapping_chromatogram
        centers = [(p["center"], p["amplitude"]) for p in truth]
        svc = DeconvolutionService()
        peak_svc = PeakService()

        self._accept(peak_svc, svc, x, y, centers, "fileA")
        self._accept(peak_svc, svc, x, y, centers, "fileB")

        # Each file gets 3 deconvolved components.
        assert len(peak_svc.get_peaks("fileA")) == 3
        assert len(peak_svc.get_peaks("fileB")) == 3

        peak_svc.group_peaks_across_samples()

        # Components with the same tag (one per file) share a group; the three
        # tags map to three distinct groups despite overlapping RTs.
        all_peaks = peak_svc.get_peaks("fileA") + peak_svc.get_peaks("fileB")
        by_tag = {}
        for p in all_peaks:
            by_tag.setdefault(p.deconv_group, set()).add(p.group_id)
        assert len(by_tag) == 3
        for tag, gids in by_tag.items():
            assert len(gids) == 1  # both files' same-tag peaks grouped together
        all_gids = {next(iter(g)) for g in by_tag.values()}
        assert len(all_gids) == 3  # three separate compound groups

    def test_accept_replaces_overlapping_existing_peak(self, overlapping_chromatogram):
        from services.peak_service import PeakService

        x, y, truth = overlapping_chromatogram
        svc = DeconvolutionService()
        peak_svc = PeakService()
        # A single fused manual peak spanning the whole co-eluting region.
        peak_svc.add_baseline_peak(
            file_id="f1", area=999.0, height=99.0, apex_x=6.5,
            poly_x=[5.0, 6.5, 8.5, 5.0], poly_y=[0.0, 99.0, 0.0, 0.0],
            p_line=[(5.0, 0.0), (8.5, 0.0)], q1=(5.0, 0.0), q2=(8.5, 0.0),
        )
        centers = [(p["center"], p["amplitude"]) for p in truth]
        self._accept(peak_svc, svc, x, y, centers, "f1")

        peaks = peak_svc.get_peaks("f1")
        # Fused manual peak replaced by 3 deconvolved components.
        assert len(peaks) == 3
        assert all(p.source == "deconvolved" for p in peaks)
