"""Test compound identity system — peaks grouped by RT get consistent colors."""
import os
import sys
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.peak_service import PeakService, OKABE_ITO_PALETTE


@pytest.fixture
def ps():
    return PeakService()


def _add_peak(ps, file_id, rt, area=100.0, height=50.0):
    """Add a minimal peak directly to PeakService internals."""
    from services.peak_service import Peak
    import uuid
    peak = Peak(
        peak_id=str(uuid.uuid4()),
        file_id=file_id,
        name=f"Peak@{rt}",
        rt=rt,
        rt_start=rt - 0.1,
        rt_end=rt + 0.1,
        area=area,
        height=height,
        width=0.2,
        color=ps._next_color(),
        source='manual',
    )
    ps._peaks.setdefault(file_id, []).append(peak)
    return peak


class TestCompoundGrouping:
    def test_same_rt_gets_same_color(self, ps):
        p1 = _add_peak(ps, 'file_a', 5.0)
        p2 = _add_peak(ps, 'file_b', 5.1)
        ps.group_peaks_across_samples(rt_window=0.2)
        assert p1.color == p2.color
        assert p1.group_id == p2.group_id

    def test_different_rt_gets_different_color(self, ps):
        p1 = _add_peak(ps, 'file_a', 2.0)
        p2 = _add_peak(ps, 'file_a', 8.0)
        ps.group_peaks_across_samples(rt_window=0.2)
        assert p1.group_id != p2.group_id
        assert p1.color != p2.color

    def test_three_compounds_three_colors(self, ps):
        peaks = []
        for rt in [2.0, 5.0, 9.0]:
            for fid in ['file_a', 'file_b']:
                peaks.append(_add_peak(ps, fid, rt + np.random.uniform(-0.05, 0.05)))
        ps.group_peaks_across_samples(rt_window=0.2)
        group_ids = {p.group_id for p in peaks}
        assert len(group_ids) == 3

    def test_regrouping_after_peak_add(self, ps):
        p1 = _add_peak(ps, 'file_a', 5.0)
        p2 = _add_peak(ps, 'file_b', 5.05)
        ps.group_peaks_across_samples()
        color_before = p1.color
        _add_peak(ps, 'file_c', 5.08)
        ps.group_peaks_across_samples()
        assert p1.color == color_before

    def test_regrouping_after_peak_remove(self, ps):
        p1 = _add_peak(ps, 'file_a', 2.0)
        p2 = _add_peak(ps, 'file_a', 5.0)
        p3 = _add_peak(ps, 'file_b', 5.1)
        ps.group_peaks_across_samples()
        assert p2.group_id == p3.group_id
        ps.remove_peak('file_a', p1.peak_id)
        ps.group_peaks_across_samples()
        assert p2.group_id == p3.group_id
        assert p2.color == p3.color

    def test_empty_peaks_no_crash(self, ps):
        result = ps.group_peaks_across_samples()
        assert result == {}

    def test_single_peak_gets_group(self, ps):
        p = _add_peak(ps, 'file_a', 3.0)
        groups = ps.group_peaks_across_samples()
        assert len(groups) == 1
        assert p.group_id is not None
        assert p.color in OKABE_ITO_PALETTE

    def test_window_parameter_respected(self, ps):
        p1 = _add_peak(ps, 'file_a', 5.0)
        p2 = _add_peak(ps, 'file_b', 5.3)
        ps.group_peaks_across_samples(rt_window=0.1)
        assert p1.group_id != p2.group_id
        ps.group_peaks_across_samples(rt_window=0.5)
        assert p1.group_id == p2.group_id
