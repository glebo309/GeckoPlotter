import pytest
import os
import pandas as pd
from src.ingestion.presets.cary_kinetics import CaryKineticsPreset
from src.ingestion.presets.chromeleon_txt import ChromeleonTxtPreset
from src.ingestion.types import ColumnRole, PlotHint

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestCaryKinetics:
    def test_sniff_matches_cary_format(self):
        path = os.path.join(FIXTURES, "cary_kinetics.csv")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert CaryKineticsPreset.sniff(path, head_bytes, lines) is True

    def test_sniff_rejects_simple_csv(self):
        path = os.path.join(FIXTURES, "simple_xy.csv")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert CaryKineticsPreset.sniff(path, head_bytes, lines) is False

    def test_parse_returns_correct_structure(self):
        path = os.path.join(FIXTURES, "cary_kinetics.csv")
        preset = CaryKineticsPreset()
        result = preset.parse(path)

        assert isinstance(result["data"], pd.DataFrame)
        assert "Time (min)" in result["data"].columns
        assert "Abs" in result["data"].columns
        assert result["column_roles"]["Time (min)"] == ColumnRole.X
        assert result["column_roles"]["Abs"] == ColumnRole.Y
        assert result["plot_hint"] == PlotHint.LINE
        assert result["sample_name"] == "Sample 1"
        assert "instrument" in result["metadata"]

    def test_parse_numeric_data(self):
        path = os.path.join(FIXTURES, "cary_kinetics.csv")
        preset = CaryKineticsPreset()
        result = preset.parse(path)
        df = result["data"]
        assert pd.api.types.is_numeric_dtype(df["Time (min)"])
        assert pd.api.types.is_numeric_dtype(df["Abs"])
        assert len(df) == 5


class TestChromeleonTxt:
    def test_sniff_matches_chromeleon(self):
        path = os.path.join(FIXTURES, "chromeleon_export.txt")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert ChromeleonTxtPreset.sniff(path, head_bytes, lines) is True

    def test_sniff_rejects_simple_csv(self):
        path = os.path.join(FIXTURES, "simple_xy.csv")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert ChromeleonTxtPreset.sniff(path, head_bytes, lines) is False

    def test_parse_returns_correct_roles(self):
        path = os.path.join(FIXTURES, "chromeleon_export.txt")
        preset = ChromeleonTxtPreset()
        result = preset.parse(path)
        df = result["data"]
        assert "Time (min)" in df.columns
        assert "Value (mAU)" in df.columns
        assert result["column_roles"]["Time (min)"] == ColumnRole.X
        assert result["column_roles"]["Value (mAU)"] == ColumnRole.Y
        assert result["plot_hint"] == PlotHint.LINE
        assert len(df) == 5
