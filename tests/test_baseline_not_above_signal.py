"""A manual baseline end dragged above the signal drops onto it; one below the signal stays where it was drawn."""
import numpy as np

from callbacks.baseline_callbacks import _not_above_signal, _area_with_constraints


def _peak():
    t = np.linspace(2.0, 2.5, 1201)
    return t, 48.8 * np.exp(-((t - 2.264) / 0.02) ** 2)


def test_a_line_drawn_across_the_peak_top_integrates_the_whole_peak():
    t, y = _peak()
    drawn = [(2.1292, 42.07), (2.3785, 53.84)]            # the gesture from the 14 Oct autosave: area 0.001
    ends = _not_above_signal(t, y, drawn)
    assert [x for x, _ in ends] == [2.1292, 2.3785]
    assert all(abs(v - np.interp(x, t, y)) < 1e-9 for x, v in ends)
    res, _, _ = _area_with_constraints(t, y, *ends)
    assert res['height'] > 48 and res['area'] > 1.5


def test_a_line_below_the_signal_keeps_its_height():
    t, y = _peak()
    drawn = [(2.13, -1.5), (2.38, -1.5)]
    assert _not_above_signal(t, y, drawn) == drawn
