"""Tests for deconvolution-related changes to PeakService.

Covers the extended add_baseline_peak (deconvolved peaks tagged + never
clobbering siblings) and cross-sample grouping by deconv_group tag.
"""

from callbacks.baseline_callbacks import _find_peak_file_id
from services.peak_service import PeakService


def _add_deconv(svc, file_id, rt, tag, rt_start=None, rt_end=None):
    """Add one deconvolved component peak via the public API."""
    rt_start = rt - 0.3 if rt_start is None else rt_start
    rt_end = rt + 0.3 if rt_end is None else rt_end
    return svc.add_baseline_peak(
        file_id=file_id,
        area=100.0,
        height=50.0,
        apex_x=rt,
        poly_x=[rt_start, rt, rt_end, rt_start],
        poly_y=[0.0, 50.0, 0.0, 0.0],
        p_line=[(rt_start, 0.0), (rt_end, 0.0)],
        q1=(rt_start, 0.0),
        q2=(rt_end, 0.0),
        source="deconvolved",
        deconv_group=tag,
        fit_params={"sigma": 0.1, "gamma": 0.2, "amplitude": 500.0},
    )


def test_find_peak_file_id_finds_selected_peak_across_files():
    svc = PeakService()
    svc.add_baseline_peak(
        file_id="subplot_a", area=10, height=5, apex_x=1.0,
        poly_x=[0.9, 1.0, 1.1, 0.9], poly_y=[0, 5, 0, 0],
        p_line=[(0.9, 0), (1.1, 0)], q1=(0.9, 0), q2=(1.1, 0),
    )
    selected = svc.add_baseline_peak(
        file_id="subplot_b", area=12, height=6, apex_x=2.0,
        poly_x=[1.9, 2.0, 2.1, 1.9], poly_y=[0, 6, 0, 0],
        p_line=[(1.9, 0), (2.1, 0)], q1=(1.9, 0), q2=(2.1, 0),
    )

    assert _find_peak_file_id(svc, selected.peak_id) == "subplot_b"


class TestAddBaselinePeakDeconv:
    def test_deconvolved_peak_carries_tags(self):
        svc = PeakService()
        p = _add_deconv(svc, "f1", 5.2, "deconv_5.2_c0")
        assert p.source == "deconvolved"
        assert p.deconv_group == "deconv_5.2_c0"
        assert p.fit_params == {"sigma": 0.1, "gamma": 0.2, "amplitude": 500.0}

    def test_default_call_unchanged(self):
        """Regression: default add_baseline_peak still produces a manual peak."""
        svc = PeakService()
        p = svc.add_baseline_peak(
            file_id="f1", area=100.0, height=50.0, apex_x=5.0,
            poly_x=[4.7, 5.0, 5.3, 4.7], poly_y=[0.0, 50.0, 0.0, 0.0],
            p_line=[(4.7, 0.0), (5.3, 0.0)], q1=(4.7, 0.0), q2=(5.3, 0.0),
        )
        assert p.source == "manual"
        assert p.deconv_group is None
        assert p.fit_params is None

    def test_overlapping_deconv_siblings_do_not_replace_each_other(self):
        """Two overlapping components must both survive (no clobbering)."""
        svc = PeakService()
        _add_deconv(svc, "f1", 5.1, "deconv_5.2_c0", rt_start=4.8, rt_end=5.4)
        _add_deconv(svc, "f1", 5.3, "deconv_5.2_c1", rt_start=5.0, rt_end=5.6)
        peaks = svc.get_peaks("f1")
        assert len(peaks) == 2
        assert {p.deconv_group for p in peaks} == {"deconv_5.2_c0", "deconv_5.2_c1"}

    def test_manual_peak_still_replaces_overlap(self):
        """A manual baseline peak overlapping an existing one replaces it."""
        svc = PeakService()
        svc.add_baseline_peak(
            file_id="f1", area=100.0, height=50.0, apex_x=5.0,
            poly_x=[4.7, 5.0, 5.3, 4.7], poly_y=[0.0, 50.0, 0.0, 0.0],
            p_line=[(4.7, 0.0), (5.3, 0.0)], q1=(4.7, 0.0), q2=(5.3, 0.0),
        )
        svc.add_baseline_peak(
            file_id="f1", area=200.0, height=80.0, apex_x=5.05,
            poly_x=[4.7, 5.05, 5.3, 4.7], poly_y=[0.0, 80.0, 0.0, 0.0],
            p_line=[(4.7, 0.0), (5.3, 0.0)], q1=(4.7, 0.0), q2=(5.3, 0.0),
        )
        peaks = svc.get_peaks("f1")
        assert len(peaks) == 1
        assert peaks[0].area == 200.0


class TestClearRegion:
    def _add_manual(self, svc, fid, lo, hi):
        return svc.add_baseline_peak(
            file_id=fid, area=100.0, height=50.0, apex_x=(lo + hi) / 2,
            poly_x=[lo, (lo + hi) / 2, hi, lo], poly_y=[0.0, 50.0, 0.0, 0.0],
            p_line=[(lo, 0.0), (hi, 0.0)], q1=(lo, 0.0), q2=(hi, 0.0),
        )

    def test_removes_peak_inside_region(self):
        svc = PeakService()
        self._add_manual(svc, "f1", 5.0, 6.0)
        removed = svc.clear_region("f1", 5.2, 5.8)
        assert removed == 1
        assert svc.get_peaks("f1") == []

    def test_keeps_peak_outside_region(self):
        svc = PeakService()
        self._add_manual(svc, "f1", 1.0, 2.0)
        removed = svc.clear_region("f1", 5.0, 6.0)
        assert removed == 0
        assert len(svc.get_peaks("f1")) == 1

    def test_keeps_peak_with_minor_overlap(self):
        svc = PeakService()
        # Peak 5.0-6.0; region 5.9-7.0 overlaps only 0.1 of its 1.0 width (<50%).
        self._add_manual(svc, "f1", 5.0, 6.0)
        removed = svc.clear_region("f1", 5.9, 7.0)
        assert removed == 0
        assert len(svc.get_peaks("f1")) == 1


class TestGroupByDeconvTag:
    def test_components_match_across_samples_by_tag(self):
        svc = PeakService()
        # Same region deconvolved in two files: c0 and c1 in each.
        _add_deconv(svc, "f1", 5.1, "deconv_5.2_c0")
        _add_deconv(svc, "f1", 5.3, "deconv_5.2_c1")
        _add_deconv(svc, "f2", 5.15, "deconv_5.2_c0")
        _add_deconv(svc, "f2", 5.32, "deconv_5.2_c1")

        groups = svc.group_peaks_across_samples()

        # Two groups (c0, c1), each holding one peak from each file.
        c0 = [p for p in svc.get_peaks("f1") + svc.get_peaks("f2")
              if p.deconv_group == "deconv_5.2_c0"]
        c1 = [p for p in svc.get_peaks("f1") + svc.get_peaks("f2")
              if p.deconv_group == "deconv_5.2_c1"]
        assert len({p.group_id for p in c0}) == 1
        assert len({p.group_id for p in c1}) == 1
        # c0 and c1 must NOT collide into one group despite close RTs.
        assert c0[0].group_id != c1[0].group_id

    def test_close_components_not_merged_by_rt(self):
        """RT 5.1 and 5.2 in the same file stay in separate groups."""
        svc = PeakService()
        _add_deconv(svc, "f1", 5.1, "deconv_5.2_c0")
        _add_deconv(svc, "f1", 5.2, "deconv_5.2_c1")
        svc.group_peaks_across_samples()
        peaks = {p.deconv_group: p for p in svc.get_peaks("f1")}
        assert peaks["deconv_5.2_c0"].group_id != peaks["deconv_5.2_c1"].group_id

    def test_non_deconv_peaks_still_group_by_rt(self):
        """Regression: ordinary peaks group across files by RT proximity."""
        svc = PeakService()
        for fid in ("f1", "f2"):
            svc.add_baseline_peak(
                file_id=fid, area=100.0, height=50.0, apex_x=5.0,
                poly_x=[4.7, 5.0, 5.3, 4.7], poly_y=[0.0, 50.0, 0.0, 0.0],
                p_line=[(4.7, 0.0), (5.3, 0.0)], q1=(4.7, 0.0), q2=(5.3, 0.0),
            )
        svc.group_peaks_across_samples(rt_window=0.2)
        gids = {svc.get_peaks("f1")[0].group_id, svc.get_peaks("f2")[0].group_id}
        assert len(gids) == 1
        assert None not in gids
