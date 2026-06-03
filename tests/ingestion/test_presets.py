import pytest
import os
import pandas as pd
from src.ingestion.presets.cary_kinetics import CaryKineticsPreset
from src.ingestion.presets.chromeleon_txt import ChromeleonTxtPreset
from src.ingestion.presets.plate_reader_csv import PlateReaderCSVPreset
from src.ingestion.presets.agilent_lcms_csv import AgilentLCMSCSVPreset
from src.ingestion.presets.lcms_cdf import LCMSCDFPreset
from src.ingestion.presets.lcms_vwd_cdf import LCMSVWDCDFPreset
from src.ingestion.types import ColumnRole, PlotHint, SourceCategory

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


class TestPlateReaderCSV:
    def test_sniff_matches_plate_reader(self):
        path = os.path.join(FIXTURES, "plate_reader.csv")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert PlateReaderCSVPreset.sniff(path, head_bytes, lines) is True

    def test_sniff_rejects_cary_kinetics(self):
        path = os.path.join(FIXTURES, "cary_kinetics.csv")
        with open(path, "rb") as f:
            head_bytes = f.read(4096)
        lines = head_bytes.decode("utf-8").splitlines()[:50]
        assert PlateReaderCSVPreset.sniff(path, head_bytes, lines) is False

    def test_parse_returns_wavelength_x_wells_y(self):
        path = os.path.join(FIXTURES, "plate_reader.csv")
        preset = PlateReaderCSVPreset()
        result = preset.parse(path)
        df = result["data"]
        assert "Wavelength" in df.columns
        assert result["column_roles"]["Wavelength"] == ColumnRole.X
        well_cols = [c for c, r in result["column_roles"].items() if r == ColumnRole.Y]
        assert len(well_cols) >= 2
        assert result["plot_hint"] == PlotHint.MULTI_Y


class TestLCMSCDF:
    def test_sniff_matches_cdf_file(self, tmp_path):
        f = tmp_path / "sample_MS1.cdf"
        f.write_bytes(b"\x89HDF\r\n\x1a\nsome_cdf_content")
        head_bytes = f.read_bytes()[:4096]
        lines = []
        assert LCMSCDFPreset.sniff(str(f), head_bytes, lines) is True

    def test_sniff_rejects_vwd_cdf(self, tmp_path):
        f = tmp_path / "sample_VWD1A.cdf"
        f.write_bytes(b"\x89HDF\r\n\x1a\nsome_cdf_content")
        head_bytes = f.read_bytes()[:4096]
        lines = []
        assert LCMSCDFPreset.sniff(str(f), head_bytes, lines) is False


class TestAgilentLCMSCSV:
    def test_sniff_matches_vwd_sidecar_with_temp_prefix(self, tmp_path):
        f = tmp_path / "tmp123_LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1A.CSV"
        f.write_text("0.0,1.0\n0.1,2.0\n")
        head_bytes = f.read_bytes()[:4096]
        lines = head_bytes.decode("utf-8").splitlines()
        assert AgilentLCMSCSVPreset.sniff(str(f), head_bytes, lines) is True

    def test_parse_vwd_sidecar_as_lcms_uv(self, tmp_path):
        f = tmp_path / "LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1B.CSV"
        f.write_text("0.0,1.0\n0.1,2.0\n")
        result = AgilentLCMSCSVPreset().parse(str(f))

        assert result["source_category"] == SourceCategory.LCMS_UV
        assert result["metadata"]["detector_channel"] == "B"
        assert result["metadata"]["experiment_title"] == "LCMS-2026-05-28 10-22-00+02-00-03.dx"
        assert list(result["data"].columns) == ["Time (min)", "Intensity (mAU)"]

    def test_parse_negative_tic_sidecar_as_lcms_ms(self, tmp_path):
        f = tmp_path / "LCMS-2026-05-28 10-22-00+02-00-03.dx_MS1 -TIC SCAN ESI Frag=135V Gain=1.0.CSV"
        f.write_text("0.0,10\n0.1,20\n")
        result = AgilentLCMSCSVPreset().parse(str(f))

        assert result["source_category"] == SourceCategory.LCMS_MS
        assert result["metadata"]["ionization_mode"] == "negative"
        assert result["metadata"]["is_tic_only"] is True


class TestLCMSVWDCDF:
    def test_sniff_matches_vwd_cdf(self, tmp_path):
        f = tmp_path / "sample_VWD1A.cdf"
        f.write_bytes(b"\x89HDF\r\n\x1a\nsome_vwd_content")
        head_bytes = f.read_bytes()[:4096]
        lines = []
        assert LCMSVWDCDFPreset.sniff(str(f), head_bytes, lines) is True

    def test_sniff_rejects_ms_cdf(self, tmp_path):
        f = tmp_path / "sample_MS1.cdf"
        f.write_bytes(b"\x89HDF\r\n\x1a\n")
        head_bytes = f.read_bytes()[:4096]
        lines = []
        assert LCMSVWDCDFPreset.sniff(str(f), head_bytes, lines) is False
