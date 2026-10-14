"""Draw fewer points without losing a single peak.

A 10 min Shimadzu run has ~28,000 points per channel; a screen shows at most ~1,000 columns of pixels. Sending and
drawing all of them is what makes a slow computer feel slow. ``decimate_minmax`` keeps, for every bin of neighbouring
points, the lowest and the highest one (in time order), so peak tops, baseline noise extremes and spikes are exactly
where they were; only points in between disappear. It is for DRAWING only: integration, tables and exports of data use
the full arrays.

Settings: GECKO_DECIMATE=0 turns it off; GECKO_DECIMATE_ABOVE (default 6000 points) and GECKO_DECIMATE_TO (default
3000 points kept) change the thresholds. 3000 points is still ~5 per pixel across a 624 px wide journal figure.
"""
from __future__ import annotations

import os

import numpy as np

ENABLED = os.environ.get('GECKO_DECIMATE', '1') != '0'
ABOVE = int(os.environ.get('GECKO_DECIMATE_ABOVE', '6000'))
TARGET = int(os.environ.get('GECKO_DECIMATE_TO', '3000'))


def decimate_minmax(x, y, target: int = TARGET):
    """``(x, y)`` reduced to about ``target`` points, as numpy arrays, keeping each bin's minimum and maximum.

    Returned unchanged (as arrays) when there is nothing to gain, when x is not increasing, or when y is not numeric.
    """
    x = np.asarray(x)
    y = np.asarray(y)
    n = len(y)
    if n != len(x) or n <= max(target, 4):
        return x, y
    try:
        yf = y.astype(np.float64, copy=False)
        if x.dtype.kind in 'fiu' and not np.all(np.diff(x.astype(np.float64)) >= 0):
            return x, y                                        # not a time axis: leave it alone
    except (TypeError, ValueError):
        return x, y
    bins = max(2, target // 2)
    width = n // bins
    used = width * bins
    body = yf[:used].reshape(bins, width)
    low = np.where(np.isnan(body), np.inf, body).argmin(axis=1) + np.arange(bins) * width
    high = np.where(np.isnan(body), -np.inf, body).argmax(axis=1) + np.arange(bins) * width
    keep = np.unique(np.concatenate([low, high, [0, n - 1], np.arange(used, n, max(1, (n - used) // 4 or 1))]))
    return x[keep], y[keep]


def for_display(x, y):
    """``decimate_minmax`` when switched on and the trace is long enough, else the inputs unchanged."""
    if not ENABLED or len(y) <= ABOVE:
        return x, y
    return decimate_minmax(x, y)
