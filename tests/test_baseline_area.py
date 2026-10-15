import numpy as np
import pytest

from callbacks.baseline_callbacks import _baseline_area


@pytest.mark.parametrize('signal', [
    [0.2, 0.6, 0.9, 0.5, 0.1, 0, 0, 0.001, 0],
    [0, 0.6, 0.9, 0, 0.5, 0.1, 0, 0.001, 0],
])
def test_zero_samples_do_not_discard_the_spectrum_peak(signal):
    x = np.arange(len(signal), dtype=float)
    y = np.array(signal)
    result = _baseline_area(x, y, (x[0], 0), (x[-1], 0))
    assert result is not None
    assert result['area'] == pytest.approx(np.trapezoid(y, x))
    assert result['apex_x'] == 2
    assert result['height'] == 0.9


def test_signal_entirely_on_or_below_baseline_has_no_peak():
    assert _baseline_area(np.arange(5), np.array([0, -1, 0, -1, 0]), (0, 0), (4, 0)) is None


def test_genuine_baseline_crossings_still_bound_the_peak():
    result = _baseline_area(np.arange(7), np.array([-1, -1, 1, 3, 1, -1, -1]), (0, 0), (6, 0))
    assert result['area'] == 4
    assert result['apex_x'] == 3


def test_a_curve_already_above_the_line_at_the_start_keeps_its_peak():
    """A noisy TIC: the line drawn by eye starts just under the curve; the peak must not be cut to a bump in its tail."""
    x = np.linspace(0, 1, 41)
    y = 100 + 3 * np.sin(x * 60) + 800 * np.exp(-((x - 0.3) / 0.04) ** 2)
    result = _baseline_area(x, y, (0.0, 99.0), (1.0, 99.0))
    assert result['apex_x'] == pytest.approx(0.3, abs=0.03)
    assert result['area'] > 0.8 * 800 * 0.04 * np.sqrt(np.pi)
