import pytest
import os
import pandas as pd
from src.ingestion.stage_3_heuristic import heuristic_parse
from src.ingestion.types import ColumnRole, PlotHint

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_simple_xy_csv():
    path = os.path.join(FIXTURES, "simple_xy.csv")
    result = heuristic_parse(path, "csv")
    assert isinstance(result["data"], pd.DataFrame)
    assert len(result["data"]) == 5
    assert ColumnRole.X in result["column_roles"].values()
    assert ColumnRole.Y in result["column_roles"].values()
    assert result["plot_hint"] == PlotHint.LINE


def test_european_format():
    path = os.path.join(FIXTURES, "european_format.csv")
    result = heuristic_parse(path, "csv")
    df = result["data"]
    assert pd.api.types.is_numeric_dtype(df.iloc[:, 0])
    assert pd.api.types.is_numeric_dtype(df.iloc[:, 1])


def test_headerless_csv():
    path = os.path.join(FIXTURES, "headerless.csv")
    result = heuristic_parse(path, "csv")
    df = result["data"]
    assert len(df) == 5
    assert len(df.columns) == 2
    x_cols = [c for c, r in result["column_roles"].items() if r == ColumnRole.X]
    assert len(x_cols) == 1


def test_returns_none_for_binary(tmp_path):
    f = tmp_path / "garbage.bin"
    f.write_bytes(bytes(range(256)))
    result = heuristic_parse(str(f), "unknown")
    assert result is None


def test_plot_hint_line_for_many_points():
    path = os.path.join(FIXTURES, "simple_xy.csv")
    result = heuristic_parse(path, "csv")
    assert result["plot_hint"] == PlotHint.LINE


def test_sample_name_extracted_when_present():
    path = os.path.join(FIXTURES, "cary_kinetics.csv")
    result = heuristic_parse(path, "csv")
    assert result["sample_name"] == "Sample 1"
