"""Tests for LC-MS upload grouping helpers."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.bundling_service import extract_lcms_base_name as extract_service_base
from services.bundling_service import assign_bundles
from services.data_store import ComponentRole
from services.storage_manager import DataManager
from src.ingestion.presets.agilent_lcms_csv import AgilentLCMSCSVPreset
from src.ingestion.types import FileIdentity, StandardizedResult


def test_extract_lcms_base_name_strips_agilent_dx_component_suffix():
    name = "LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1A.CSV"
    assert DataManager.extract_lcms_base_name(name) == "LCMS-2026-05-28 10-22-00+02-00-03"
    assert extract_service_base(name) == "LCMS-2026-05-28 10-22-00+02-00-03"


def test_extract_lcms_base_name_prefers_experiment_title_metadata():
    name = "flow_ps_reaction_trp_phcho_002.cdf"
    metadata = {"experiment_title": "LCMS-2026-05-28 10-22-00+02-00-03.dx"}

    assert DataManager.extract_lcms_base_name(name, metadata=metadata) == "LCMS-2026-05-28 10-22-00+02-00-03"
    assert extract_service_base(name, metadata=metadata) == "LCMS-2026-05-28 10-22-00+02-00-03"


def test_agilent_vwd_csv_components_keep_channel_roles(tmp_path):
    a = tmp_path / "LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1A.CSV"
    b = tmp_path / "LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1B.CSV"
    a.write_text("0.0,1.0\n0.1,2.0\n")
    b.write_text("0.0,3.0\n0.1,4.0\n")

    preset = AgilentLCMSCSVPreset()

    def standardize(path):
        raw = preset.parse(str(path))
        return StandardizedResult(
            data=raw["data"],
            column_roles=raw["column_roles"],
            identity=FileIdentity(path.name, "csv", preset.name, 2),
            plot_hint=raw["plot_hint"],
            source_category=raw["source_category"],
            sample_name=raw.get("sample_name"),
            metadata=raw.get("metadata", {}),
        )

    bundles = assign_bundles([
        (a.name, a.read_bytes(), standardize(a)),
        (b.name, b.read_bytes(), standardize(b)),
    ])

    assert len(bundles) == 1
    assert bundles[0].get_component(ComponentRole.VWD_A) is not None
    assert bundles[0].get_component(ComponentRole.VWD_B) is not None
