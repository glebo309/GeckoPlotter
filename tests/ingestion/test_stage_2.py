import pytest
import os
from src.ingestion.stage_2_registry import FormatRegistry, FormatPreset


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class FakePreset(FormatPreset):
    name = "fake_format"
    extensions = {"csv"}
    priority = 50

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        return any("FAKE_MARKER" in line for line in head_lines)

    def parse(self, path: str) -> dict:
        return {"data": None, "column_roles": {}, "metadata": {}}


class AnotherFake(FormatPreset):
    name = "another_fake"
    extensions = {"csv"}
    priority = 10

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        return any("ANOTHER_MARKER" in line for line in head_lines)

    def parse(self, path: str) -> dict:
        return {"data": None, "column_roles": {}, "metadata": {}}


def test_registry_match_returns_none_for_unknown(tmp_path):
    f = tmp_path / "unknown.csv"
    f.write_text("a,b\n1,2\n")
    registry = FormatRegistry([FakePreset()])
    assert registry.match("csv", str(f)) is None


def test_registry_match_returns_preset_on_sniff_hit(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("FAKE_MARKER\nTime,Abs\n0,0.5\n")
    registry = FormatRegistry([FakePreset()])
    result = registry.match("csv", str(f))
    assert result is not None
    assert result.name == "fake_format"


def test_registry_respects_extension_filter(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("FAKE_MARKER\nTime,Abs\n0,0.5\n")
    registry = FormatRegistry([FakePreset()])
    assert registry.match("txt", str(f)) is None


def test_registry_higher_priority_wins(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("FAKE_MARKER\nANOTHER_MARKER\nTime,Abs\n0,0.5\n")
    registry = FormatRegistry([FakePreset(), AnotherFake()])
    result = registry.match("csv", str(f))
    assert result.name == "fake_format"


def test_registry_lists_all_presets():
    registry = FormatRegistry([FakePreset(), AnotherFake()])
    names = registry.list_formats()
    assert set(names) == {"fake_format", "another_fake"}
