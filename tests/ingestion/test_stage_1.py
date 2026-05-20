import pytest
from src.ingestion.stage_1_detect import detect_by_extension


def test_csv_extension():
    assert detect_by_extension("data.csv") == "csv"


def test_tsv_extension():
    assert detect_by_extension("data.tsv") == "tsv"


def test_txt_extension():
    assert detect_by_extension("chromatogram.txt") == "txt"


def test_cdf_extension():
    assert detect_by_extension("sample_MS1.cdf") == "cdf"


def test_json_extension():
    assert detect_by_extension("config.json") == "json"


def test_unknown_extension():
    assert detect_by_extension("readme.md") == "unknown"


def test_no_extension():
    assert detect_by_extension("Makefile") == "unknown"


def test_case_insensitive():
    assert detect_by_extension("Data.CSV") == "csv"
    assert detect_by_extension("EXPORT.TXT") == "txt"


def test_double_extension():
    assert detect_by_extension("sample.cdf.vwd") == "unknown"


def test_image_extensions():
    assert detect_by_extension("plot.png") == "png"
    assert detect_by_extension("figure.svg") == "svg"
