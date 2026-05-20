import pytest
import os
from src.ingestion.pipeline import IngestionPipeline, ingest_file
from src.ingestion.types import StandardizedResult, ColumnRole, PlotHint

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_cary_kinetics_goes_through_stage_2():
    path = os.path.join(FIXTURES, "cary_kinetics.csv")
    result = ingest_file(path, "cary_kinetics.csv")
    assert isinstance(result, StandardizedResult)
    assert result.identity.detected_format == "cary_kinetics"
    assert result.identity.detection_stage == 2
    assert result.x_columns == ["Time (min)"]
    assert "Abs" in result.y_columns


def test_simple_csv_goes_through_stage_3():
    path = os.path.join(FIXTURES, "simple_xy.csv")
    result = ingest_file(path, "simple_xy.csv")
    assert isinstance(result, StandardizedResult)
    assert result.identity.detection_stage == 3
    assert result.identity.detected_format == "heuristic"
    assert len(result.x_columns) == 1
    assert len(result.y_columns) >= 1


def test_chromeleon_txt_goes_through_stage_2():
    path = os.path.join(FIXTURES, "chromeleon_export.txt")
    result = ingest_file(path, "chromeleon_export.txt")
    assert isinstance(result, StandardizedResult)
    assert result.identity.detected_format == "chromeleon_txt"
    assert result.identity.detection_stage == 2


def test_european_format_parsed_correctly():
    path = os.path.join(FIXTURES, "european_format.csv")
    result = ingest_file(path, "european_format.csv")
    assert isinstance(result, StandardizedResult)
    assert result.data.iloc[0, 0] == pytest.approx(0.0, abs=0.01)


def test_pipeline_returns_none_for_unparseable(tmp_path):
    f = tmp_path / "garbage.bin"
    f.write_bytes(bytes(range(256)))
    result = ingest_file(str(f), "garbage.bin")
    assert result is None


def test_pipeline_singleton_has_all_presets():
    pipeline = IngestionPipeline()
    names = pipeline.registry.list_formats()
    assert "cary_kinetics" in names
    assert "chromeleon_txt" in names
    assert "plate_reader_csv" in names
