"""Drawing fewer points: every peak survives, the data itself is never reduced."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location(
    'decimation_under_test', Path(__file__).resolve().parents[1] / 'src' / 'services' / 'decimation.py')
dec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dec)


def _run(n=28000, seed=0):
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 10, n)
    y = rng.normal(0, .3, n) + 80 * np.exp(-((x - 4.2) / .03) ** 2) + 30 * np.exp(-((x - 6.1) / .05) ** 2)
    return x, y


def test_a_long_trace_is_reduced_but_keeps_its_extremes_and_order():
    x, y = _run()
    y[12345] = 500.0                                           # a one-point spike must not disappear
    y[777] = np.nan
    xd, yd = dec.for_display(x, y)
    assert len(xd) == len(yd) < 3100
    assert np.nanmax(yd) == 500.0 and np.nanmin(yd) == np.nanmin(y)
    assert xd[0] == x[0] and xd[-1] == x[-1] and np.all(np.diff(xd) >= 0)
    assert set(xd) <= set(x)                                   # only original points, nothing interpolated


def test_short_or_non_time_traces_are_left_alone():
    x, y = _run(5000)
    assert len(dec.for_display(x, y)[0]) == 5000
    x, y = _run()
    assert len(dec.decimate_minmax(x[::-1], y)[0]) == len(x)    # x not increasing: not a time axis


def test_pandas_input_is_accepted():
    x, y = _run()
    xd, yd = dec.for_display(pd.Series(x), pd.Series(y))
    assert len(xd) < 3100 and np.nanmax(yd) == np.nanmax(y)


def test_a_wide_peak_fill_is_drawn_with_fewer_points_and_keeps_its_top_and_baseline():
    x, y = _run()
    xs, ys = x[10000:15000], y[10000:15000]
    base = np.linspace(ys[0], ys[-1], len(xs))
    px, py = np.r_[xs, xs[::-1]].tolist(), np.r_[ys, base[::-1]].tolist()
    dx, dy = dec.polygon_for_display(px, py)
    assert len(dx) == len(dy) < 1000 and len(dx) % 2 == 0
    half = len(dx) // 2
    assert dx[:half] == dx[half:][::-1]                          # the baseline runs back over the same times
    assert max(dy) == max(py) and dx[0] == px[0] and dx[half - 1] == px[len(px) // 2 - 1]
    assert set(dx) <= set(px)
    short = (px[:400], py[:400])
    assert dec.polygon_for_display(*short) == short               # narrow peaks are left alone
