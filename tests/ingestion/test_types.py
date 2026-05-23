import pytest
import pandas as pd
from src.ingestion.types import (
    StandardizedResult, ColumnRole, PlotHint, FileIdentity, SourceCategory
)


def test_column_role_values():
    assert ColumnRole.X == "x"
    assert ColumnRole.Y == "y"
    assert ColumnRole.LABEL == "label"
    assert ColumnRole.IGNORE == "ignore"
    assert ColumnRole.UNKNOWN == "unknown"


def test_plot_hint_values():
    assert PlotHint.LINE == "line"
    assert PlotHint.SCATTER == "scatter"
    assert PlotHint.BAR == "bar"
    assert PlotHint.HEATMAP == "heatmap"
    assert PlotHint.MULTI_Y == "multi_y"


def test_file_identity_fields():
    fi = FileIdentity(
        original_name="SeCUT_butyrate02.csv",
        extension="csv",
        detected_format="cary_kinetics",
        detection_stage=2,
    )
    assert fi.original_name == "SeCUT_butyrate02.csv"
    assert fi.extension == "csv"
    assert fi.detected_format == "cary_kinetics"
    assert fi.detection_stage == 2


def test_standardized_result_minimal():
    df = pd.DataFrame({"Time (min)": [0.0, 0.1], "Abs": [0.5, 0.6]})
    sr = StandardizedResult(
        data=df,
        column_roles={"Time (min)": ColumnRole.X, "Abs": ColumnRole.Y},
        identity=FileIdentity(
            original_name="test.csv",
            extension="csv",
            detected_format="generic",
            detection_stage=3,
        ),
    )
    assert len(sr.data) == 2
    assert sr.x_columns == ["Time (min)"]
    assert sr.y_columns == ["Abs"]
    assert sr.plot_hint == PlotHint.LINE
    assert sr.metadata == {}
    assert sr.sample_name is None


def test_standardized_result_with_metadata():
    df = pd.DataFrame({"Wavelength": [200, 300], "A1": [0.1, 0.2], "A2": [0.3, 0.4]})
    sr = StandardizedResult(
        data=df,
        column_roles={
            "Wavelength": ColumnRole.X,
            "A1": ColumnRole.Y,
            "A2": ColumnRole.Y,
        },
        identity=FileIdentity(
            original_name="plate.csv",
            extension="csv",
            detected_format="plate_reader_csv",
            detection_stage=2,
        ),
        plot_hint=PlotHint.MULTI_Y,
        sample_name="Plate 1",
        metadata={"instrument": "SpectraMax", "wavelength_range": "200-800"},
    )
    assert sr.x_columns == ["Wavelength"]
    assert set(sr.y_columns) == {"A1", "A2"}
    assert sr.plot_hint == PlotHint.MULTI_Y
    assert sr.sample_name == "Plate 1"


def test_source_category_default():
    sr = StandardizedResult(
        data=pd.DataFrame({"x": [1], "y": [2]}),
        column_roles={"x": ColumnRole.X, "y": ColumnRole.Y},
        identity=FileIdentity("test.csv", "csv", "heuristic", 3),
    )
    assert sr.source_category == SourceCategory.GENERIC


def test_source_category_values():
    assert SourceCategory.CHROMATOGRAM == "chromatogram"
    assert SourceCategory.SPECTRUM == "spectrum"
    assert SourceCategory.LCMS_MS == "lcms_ms"
    assert SourceCategory.LCMS_UV == "lcms_uv"
    assert SourceCategory.KINETICS == "kinetics"
    assert SourceCategory.GENERIC == "generic"


def test_x_columns_empty_when_no_x_role():
    df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})
    sr = StandardizedResult(
        data=df,
        column_roles={"col1": ColumnRole.Y, "col2": ColumnRole.Y},
        identity=FileIdentity("f.csv", "csv", "generic", 3),
    )
    assert sr.x_columns == []
    assert sr.y_columns == ["col1", "col2"]
