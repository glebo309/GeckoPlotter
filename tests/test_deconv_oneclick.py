"""Tests for the redesigned one-click deconvolution callbacks."""

import numpy as np
import pytest
from lmfit.models import ExponentialGaussianModel

from services.peak_service import PeakService, Peak
from services.deconvolution_service import (
    DeconvolutionService, serialize_result, deserialize_result,
)


def _emg(x, amplitude, center, sigma, gamma):
    return ExponentialGaussianModel().eval(
        x=x, amplitude=amplitude, center=center, sigma=sigma, gamma=gamma)


@pytest.fixture
def overlapping_signal():
    """Signal with two overlapping peaks between x=4 and x=9."""
    x = np.linspace(0, 20, 2000)
    y = _emg(x, 1000, 5.5, 0.3, 0.5) + _emg(x, 700, 6.8, 0.25, 0.3)
    return x, y


class TestOneClickDeconvolute:
    """Test the core logic: given a selected peak, detect + fit in one shot."""

    def test_detect_and_fit_within_peak_region(self, overlapping_signal):
        x_full, y_full = overlapping_signal
        svc = DeconvolutionService()

        # Simulate a peak region from rt_start=4.0 to rt_end=9.0
        mask = (x_full >= 4.0) & (x_full <= 9.0)
        x_region = x_full[mask]
        y_region = y_full[mask]

        centers = svc.auto_detect_centers(x_region, y_region, prominence=0.05)
        assert len(centers) >= 2

        result = svc.fit_peaks(x_region, y_region, centers)
        assert result is not None
        assert result.r_squared > 0.95
        assert len(result.components) >= 2

    def test_single_peak_region_returns_fewer_than_2(self, overlapping_signal):
        """A region with only one peak should fail detection gracefully."""
        x_full, y_full = overlapping_signal
        svc = DeconvolutionService()

        # Narrow region around just one peak
        mask = (x_full >= 5.0) & (x_full <= 6.0)
        x_region = x_full[mask]
        y_region = y_full[mask]

        centers = svc.auto_detect_centers(x_region, y_region, prominence=0.05)
        assert len(centers) < 2

    def test_accept_replaces_original_peak(self, overlapping_signal):
        """Accept should remove the original peak and add sub-peaks."""
        x_full, y_full = overlapping_signal
        svc = DeconvolutionService()
        peak_svc = PeakService()

        original = peak_svc.add_baseline_peak(
            file_id="f1", area=999.0, height=99.0, apex_x=6.0,
            poly_x=[4.0, 6.0, 9.0, 4.0], poly_y=[0.0, 99.0, 0.0, 0.0],
            p_line=[(4.0, 0.0), (9.0, 0.0)], q1=(4.0, 0.0), q2=(9.0, 0.0),
        )
        assert len(peak_svc.get_peaks("f1")) == 1

        mask = (x_full >= 4.0) & (x_full <= 9.0)
        x_region, y_region = x_full[mask], y_full[mask]
        centers = svc.auto_detect_centers(x_region, y_region, prominence=0.05)
        result = svc.fit_peaks(x_region, y_region, centers)
        region_rt = float(np.mean([c.center for c in result.components]))
        new_peaks = svc.result_to_peaks(result, "f1", region_rt)

        peak_svc.remove_peak("f1", original.peak_id)
        for p in new_peaks:
            peak_svc.add_baseline_peak(
                file_id="f1", area=p.area, height=p.height, apex_x=p.rt,
                poly_x=p.poly_x, poly_y=p.poly_y, p_line=p.p_line,
                q1=p.q1, q2=p.q2, source='deconvolved',
                deconv_group=p.deconv_group, fit_params=p.fit_params,
            )

        peaks = peak_svc.get_peaks("f1")
        assert len(peaks) >= 2
        assert all(p.source == 'deconvolved' for p in peaks)
        assert not any(p.peak_id == original.peak_id for p in peaks)

    def test_marker_refit_updates_result(self, overlapping_signal):
        """Adding/removing a marker and re-fitting produces a new result."""
        x_full, y_full = overlapping_signal
        svc = DeconvolutionService()

        mask = (x_full >= 4.0) & (x_full <= 9.0)
        x_region, y_region = x_full[mask], y_full[mask]

        centers_2 = svc.auto_detect_centers(x_region, y_region, prominence=0.05)
        result_2 = svc.fit_peaks(x_region, y_region, centers_2)

        centers_3 = list(centers_2) + [(7.5, float(y_region[np.argmin(np.abs(x_region - 7.5))]))]
        result_3 = svc.fit_peaks(x_region, y_region, centers_3)

        assert len(result_3.components) == len(centers_3)
        # With a third center the fit may still be near-perfect on synthetic
        # data, so compare component counts rather than R² which can both be 1.0
        assert len(result_3.components) != len(result_2.components)
