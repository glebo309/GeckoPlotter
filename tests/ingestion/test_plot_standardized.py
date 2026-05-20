import pytest
import pandas as pd
import plotly.graph_objects as go
import sys
import os
import importlib.util

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, ROOT)

# Import PlotManager directly from file to avoid triggering src/services/__init__.py,
# which chain-imports storage_manager (bare 'services' module, breaks outside app context).
_spec = importlib.util.spec_from_file_location(
    "plot_manager",
    os.path.join(ROOT, "src", "services", "plot_manager.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PlotManager = _mod.PlotManager

from src.ingestion.types import StandardizedResult, ColumnRole, PlotHint, FileIdentity


def _make_result(df, roles, hint=PlotHint.LINE, name=None):
    return StandardizedResult(
        data=df,
        column_roles=roles,
        identity=FileIdentity("test.csv", "csv", "test", 3),
        plot_hint=hint,
        sample_name=name,
    )


def test_create_standardized_plot_line():
    pm = PlotManager()
    df = pd.DataFrame({"Time": [0, 1, 2], "Abs": [0.5, 0.6, 0.7]})
    sr = _make_result(df, {"Time": ColumnRole.X, "Abs": ColumnRole.Y})
    fig = pm.create_standardized_plot(sr)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].mode == "lines"


def test_create_standardized_plot_multi_y():
    pm = PlotManager()
    df = pd.DataFrame({"WL": [200, 300], "A1": [0.1, 0.2], "A2": [0.3, 0.4]})
    sr = _make_result(
        df,
        {"WL": ColumnRole.X, "A1": ColumnRole.Y, "A2": ColumnRole.Y},
        PlotHint.MULTI_Y,
    )
    fig = pm.create_standardized_plot(sr)
    assert len(fig.data) == 2


def test_create_standardized_plot_with_sample_name():
    pm = PlotManager()
    df = pd.DataFrame({"Time": [0, 1], "Abs": [0.5, 0.6]})
    sr = _make_result(
        df,
        {"Time": ColumnRole.X, "Abs": ColumnRole.Y},
        name="Sample 1",
    )
    fig = pm.create_standardized_plot(sr)
    assert "Sample 1" in fig.layout.title.text


def test_create_standardized_plot_no_x_uses_index():
    pm = PlotManager()
    df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})
    sr = _make_result(df, {"col1": ColumnRole.Y, "col2": ColumnRole.Y})
    fig = pm.create_standardized_plot(sr)
    assert len(fig.data) == 2
