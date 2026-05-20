"""Test that StorageManager uses the ingestion pipeline."""
import pytest
import base64
import os
import sys

# Add the project root to sys.path so 'services' imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_pipeline_produces_standardized_for_cary():
    from src.ingestion import ingest_file
    path = os.path.join(FIXTURES, "cary_kinetics.csv")
    result = ingest_file(path, "cary_kinetics.csv")
    assert result is not None
    assert result.identity.detected_format == "cary_kinetics"
    assert result.x_columns == ["Time (min)"]


@pytest.mark.skipif(
    not os.environ.get("GECKO_INTEGRATION_TEST"),
    reason="Requires full app dependencies (set GECKO_INTEGRATION_TEST=1)"
)
def test_load_file_data_returns_standardized_result_in_metadata():
    from src.services.storage_manager import DataManager

    dm = DataManager()

    with open(os.path.join(FIXTURES, "cary_kinetics.csv"), "rb") as f:
        content_bytes = f.read()
    encoded = base64.b64encode(content_bytes).decode("utf-8")

    record = {
        "id": "test-cary-001",
        "name": "cary_kinetics.csv",
        "type": "csv",
        "size": len(content_bytes),
        "size_display": f"{len(content_bytes)} B",
        "last_modified": 0,
        "last_modified_display": "",
        "preview": "",
        "encoded": f"data:text/csv;base64,{encoded}",
    }

    result = dm.load_file_data(record)
    assert result is not None
    assert "standardized" in result
    sr = result["standardized"]
    assert sr.identity.detected_format == "cary_kinetics"
    assert sr.x_columns == ["Time (min)"]
