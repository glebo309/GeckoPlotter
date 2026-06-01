import numpy as np
import plotly.graph_objects as go

from services.plot_smoothing import (
    normalize_smooth_window,
    smooth_plotly_traces,
    smoothing_fair_export_record,
)


def test_smoothing_window_clamps_to_short_trace():
    assert normalize_smooth_window(51, 10) == 9
    assert normalize_smooth_window(4, 10) == 3
    assert normalize_smooth_window(2, 10) == 0


def test_smooth_plotly_traces_updates_line_trace_only():
    noisy = [0, 0, 10, 0, 0, 0, 10, 0, 0]
    fig = go.Figure([
        go.Scatter(x=list(range(len(noisy))), y=noisy, mode="lines", name="line"),
        go.Bar(x=[1, 2, 3], y=[5, 1, 5], name="bar"),
    ])

    original_line = np.asarray(fig.data[0].y, dtype=float)
    original_bar = tuple(fig.data[1].y)
    smooth_plotly_traces(fig.data, 51)

    assert not np.allclose(np.asarray(fig.data[0].y, dtype=float), original_line)
    assert tuple(fig.data[1].y) == original_bar


def test_smoothing_fair_export_record_is_explicit_and_clamped():
    record = smoothing_fair_export_record(151, n_points=10)

    assert record["processing_step"] == "display_smoothing"
    assert record["applied"] is True
    assert record["algorithm"] == "Savitzky-Golay filter"
    assert record["implementation"] == "scipy.signal.savgol_filter"
    assert record["parameters"]["requested_window_points"] == 151
    assert record["parameters"]["effective_window_points"] == 9
    assert record["parameters"]["polynomial_order"] == 3
    assert "source data remains unchanged" in record["scope"]
