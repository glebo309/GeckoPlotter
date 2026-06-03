"""Tests for LC-MS upload grouping helpers."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.bundling_service import extract_lcms_base_name as extract_service_base
from services.storage_manager import DataManager


def test_extract_lcms_base_name_strips_agilent_dx_component_suffix():
    name = "LCMS-2026-05-28 10-22-00+02-00-03.dx_VWD1A.CSV"
    assert DataManager.extract_lcms_base_name(name) == "LCMS-2026-05-28 10-22-00+02-00-03"
    assert extract_service_base(name) == "LCMS-2026-05-28 10-22-00+02-00-03"


def test_extract_lcms_base_name_prefers_experiment_title_metadata():
    name = "flow_ps_reaction_trp_phcho_002.cdf"
    metadata = {"experiment_title": "LCMS-2026-05-28 10-22-00+02-00-03.dx"}

    assert DataManager.extract_lcms_base_name(name, metadata=metadata) == "LCMS-2026-05-28 10-22-00+02-00-03"
    assert extract_service_base(name, metadata=metadata) == "LCMS-2026-05-28 10-22-00+02-00-03"
