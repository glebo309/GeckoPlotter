"""Tests for cross-file peak integration (right-click 'Integrate in All Files').

Covers PeakService.find_matching_peak — locating and integrating a peak within
an RT window of a target signal — and the add_baseline_peak source/name
inheritance used when dropping the matched peak into a target file.
"""

import numpy as np

from services.peak_service import PeakService


def _gaussian(x, amp, center, width):
    return amp * np.exp(-0.5 * ((x - center) / width) ** 2)


def _chromatogram(centers_amps):
    """Build (time, signal) with Gaussian peaks at given (center, amp)."""
    x = np.linspace(0, 20, 2000)
    y = np.zeros_like(x)
    for center, amp in centers_amps:
        y += _gaussian(x, amp, center, 0.15)
    return x, y


class TestFindMatchingPeak:
    def test_finds_peak_within_window(self):
        svc = PeakService()
        x, y = _chromatogram([(10.0, 1000.0)])
        res = svc.find_matching_peak("f1", target_rt=10.0, tolerance=0.3,
                                     signal=y, time=x)
        assert res is not None
        assert abs(res["apex_x"] - 10.0) < 0.1
        assert res["area"] > 0
        assert res["height"] > 0
        assert res["rt_start"] < res["apex_x"] < res["rt_end"]

    def test_returns_none_when_no_peak_in_window(self):
        svc = PeakService()
        # Single peak at 10.0; search a flat region around 5.0.
        x, y = _chromatogram([(10.0, 1000.0)])
        res = svc.find_matching_peak("f1", target_rt=5.0, tolerance=0.3,
                                     signal=y, time=x)
        assert res is None

    def test_offset_peak_found_within_tolerance(self):
        svc = PeakService()
        # Peak at 10.12, target 10.0, tolerance 0.3 → should be found.
        x, y = _chromatogram([(10.12, 800.0)])
        res = svc.find_matching_peak("f1", target_rt=10.0, tolerance=0.3,
                                     signal=y, time=x)
        assert res is not None
        assert abs(res["apex_x"] - 10.12) < 0.1

    def test_peak_outside_tolerance_not_matched(self):
        svc = PeakService()
        # Peak at 10.8, target 10.0, tolerance 0.3 → outside window → None.
        x, y = _chromatogram([(10.8, 800.0)])
        res = svc.find_matching_peak("f1", target_rt=10.0, tolerance=0.3,
                                     signal=y, time=x)
        assert res is None

    def test_picks_most_prominent_peak_in_window(self):
        svc = PeakService()
        # Two peaks both inside a wide window; the taller one should win.
        x, y = _chromatogram([(9.85, 300.0), (10.1, 1000.0)])
        res = svc.find_matching_peak("f1", target_rt=10.0, tolerance=0.5,
                                     signal=y, time=x)
        assert res is not None
        assert abs(res["apex_x"] - 10.1) < 0.1

    def test_polygon_is_closed_and_consistent(self):
        svc = PeakService()
        x, y = _chromatogram([(10.0, 1000.0)])
        res = svc.find_matching_peak("f1", target_rt=10.0, tolerance=0.3,
                                     signal=y, time=x)
        assert len(res["poly_x"]) == len(res["poly_y"])
        assert len(res["poly_x"]) >= 4
        assert res["p_line"][0][0] == res["rt_start"]
        assert res["p_line"][1][0] == res["rt_end"]


class TestAddBaselinePeakInheritance:
    def test_source_and_name_inherited(self):
        svc = PeakService()
        x, y = _chromatogram([(10.0, 1000.0)])
        res = svc.find_matching_peak("f2", 10.0, 0.3, y, x)
        peak = svc.add_baseline_peak(
            file_id="f2",
            area=res["area"], height=res["height"], apex_x=res["apex_x"],
            poly_x=res["poly_x"], poly_y=res["poly_y"],
            p_line=res["p_line"], q1=res["q1"], q2=res["q2"],
            source="cross_integrated", name="Caffeine", label="Caffeine",
        )
        assert peak.source == "cross_integrated"
        assert peak.name == "Caffeine"
        assert peak.label == "Caffeine"

    def test_default_call_still_manual(self):
        svc = PeakService()
        peak = svc.add_baseline_peak(
            file_id="f1", area=100.0, height=50.0, apex_x=5.0,
            poly_x=[4.7, 5.0, 5.3, 4.7], poly_y=[0.0, 50.0, 0.0, 0.0],
            p_line=[(4.7, 0.0), (5.3, 0.0)], q1=(4.7, 0.0), q2=(5.3, 0.0),
        )
        assert peak.source == "manual"
        assert peak.name == "Peak 1"


class TestIntegrateAcrossFiles:
    """Service-level mirror of the 'Integrate in All Files' callback loop."""

    def _integrate(self, svc, src_peak_name, target_rt, tol, files):
        """files: {file_id: (time, signal)}. Returns matched count."""
        matched = 0
        for fid, (t, y) in files.items():
            res = svc.find_matching_peak(fid, target_rt, tol, y, t)
            if not res:
                continue
            svc.add_baseline_peak(
                file_id=fid, area=res["area"], height=res["height"],
                apex_x=res["apex_x"], poly_x=res["poly_x"], poly_y=res["poly_y"],
                p_line=res["p_line"], q1=res["q1"], q2=res["q2"],
                source="cross_integrated", name=src_peak_name, label=src_peak_name,
            )
            matched += 1
        return matched

    def test_integrates_present_and_skips_absent(self):
        svc = PeakService()
        present = _chromatogram([(10.0, 900.0)])   # fileB: peak present
        absent = _chromatogram([(3.0, 900.0)])     # fileC: nothing near RT 10
        matched = self._integrate(svc, "Caffeine", 10.0, 0.3,
                                   {"fileB": present, "fileC": absent})
        assert matched == 1
        assert len(svc.get_peaks("fileB")) == 1
        assert svc.get_peaks("fileB")[0].name == "Caffeine"
        assert svc.get_peaks("fileB")[0].source == "cross_integrated"
        assert svc.get_peaks("fileC") == []

    def test_replaces_existing_overlapping_peak_in_target(self):
        svc = PeakService()
        # fileB already has a peak across the RT-10 region.
        svc.add_baseline_peak(
            file_id="fileB", area=10.0, height=5.0, apex_x=10.0,
            poly_x=[9.5, 10.0, 10.5, 9.5], poly_y=[0.0, 5.0, 0.0, 0.0],
            p_line=[(9.5, 0.0), (10.5, 0.0)], q1=(9.5, 0.0), q2=(10.5, 0.0),
        )
        present = _chromatogram([(10.0, 900.0)])
        self._integrate(svc, "Caffeine", 10.0, 0.3, {"fileB": present})
        peaks = svc.get_peaks("fileB")
        # Overlapping peak replaced, not duplicated.
        assert len(peaks) == 1
        assert peaks[0].source == "cross_integrated"
        assert peaks[0].name == "Caffeine"
