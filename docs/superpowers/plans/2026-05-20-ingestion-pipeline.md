# 3-Stage File Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered format-specific logic across StorageManager, PlotManager, and callbacks with a clean 3-stage pipeline that produces a `StandardizedResult` consumed by a format-agnostic plotter.

**Architecture:** Files pass through three stages: (1) extension-based type detection, (2) content-based format registry lookup against declarative presets, (3) smart heuristic fallback for unknown formats. Each stage narrows the identification. The output is a `StandardizedResult` dataclass containing clean data, column roles, metadata, and plot hints. The plotter never sees file formats -- it only reads the standardized output.

**Tech Stack:** Python 3.11+, pandas, dataclasses, Dash/Plotly, pytest

---

## File Structure

```
src/
  ingestion/
    __init__.py                    # Public API: ingest_file()
    types.py                       # StandardizedResult, ColumnRole, PlotHint, FileIdentity dataclasses
    pipeline.py                    # IngestionPipeline orchestrator (Stage 1 -> 2 -> 3)
    stage_1_detect.py              # Extension-based type detection
    stage_2_registry.py            # Content-based format registry with declarative presets
    stage_3_heuristic.py           # Smart heuristic fallback (extracted from GenericCSVReader)
    presets/
      __init__.py                  # load_all_presets()
      cary_kinetics.py             # Cary 300 spectrophotometer kinetics CSV
      chromeleon_txt.py            # Chromeleon chromatogram .txt export
      plate_reader_csv.py          # UV-Vis plate reader CSV (Wavelength + wells)
      lcms_cdf.py                  # LC-MS netCDF (TIC)
      lcms_vwd_cdf.py              # LC-MS VWD netCDF (UV channel)
  services/
    readers/                       # Existing readers stay for now; presets delegate to them
    plot_manager.py                # Refactored: routes on ColumnRole/PlotHint, not file_type strings
    storage_manager.py             # Refactored: delegates to ingestion pipeline
tests/
  ingestion/
    __init__.py
    test_types.py                  # StandardizedResult construction and validation
    test_stage_1.py                # Extension detection
    test_stage_2.py                # Format registry matching
    test_stage_3.py                # Heuristic fallback
    test_pipeline.py               # End-to-end pipeline
    test_presets.py                # Each preset against sample files
    fixtures/
      cary_kinetics.csv            # Cary 300 sample (from SeCUT_butyrate02.csv)
      chromeleon_export.txt        # Chromeleon .txt sample
      plate_reader.csv             # UV-Vis plate reader sample
      simple_xy.csv                # Minimal 2-column CSV
      european_format.csv          # Semicolon-separated, comma decimals
      headerless.csv               # No header row, pure numbers
```

---

### Task 1: StandardizedResult Dataclass

**Files:**
- Create: `src/ingestion/__init__.py`
- Create: `src/ingestion/types.py`
- Test: `tests/ingestion/__init__.py`
- Test: `tests/ingestion/test_types.py`

- [ ] **Step 1: Write failing tests for StandardizedResult**

```python
# tests/ingestion/test_types.py
import pytest
import pandas as pd
from src.ingestion.types import (
    StandardizedResult, ColumnRole, PlotHint, FileIdentity
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
    assert sr.plot_hint == PlotHint.LINE  # default
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


def test_x_columns_empty_when_no_x_role():
    df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})
    sr = StandardizedResult(
        data=df,
        column_roles={"col1": ColumnRole.Y, "col2": ColumnRole.Y},
        identity=FileIdentity("f.csv", "csv", "generic", 3),
    )
    assert sr.x_columns == []
    assert sr.y_columns == ["col1", "col2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingestion'`

- [ ] **Step 3: Implement the dataclasses**

```python
# src/ingestion/__init__.py
from .types import StandardizedResult, ColumnRole, PlotHint, FileIdentity
from .pipeline import ingest_file

__all__ = [
    "StandardizedResult",
    "ColumnRole",
    "PlotHint",
    "FileIdentity",
    "ingest_file",
]
```

```python
# src/ingestion/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import pandas as pd


class ColumnRole(str, Enum):
    X = "x"
    Y = "y"
    LABEL = "label"
    IGNORE = "ignore"
    UNKNOWN = "unknown"


class PlotHint(str, Enum):
    LINE = "line"
    SCATTER = "scatter"
    BAR = "bar"
    HEATMAP = "heatmap"
    MULTI_Y = "multi_y"


@dataclass
class FileIdentity:
    original_name: str
    extension: str
    detected_format: str
    detection_stage: int


@dataclass
class StandardizedResult:
    data: pd.DataFrame
    column_roles: Dict[str, ColumnRole]
    identity: FileIdentity
    plot_hint: PlotHint = PlotHint.LINE
    sample_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def x_columns(self) -> List[str]:
        return [c for c, r in self.column_roles.items() if r == ColumnRole.X]

    @property
    def y_columns(self) -> List[str]:
        return [c for c, r in self.column_roles.items() if r == ColumnRole.Y]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_types.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/__init__.py src/ingestion/types.py tests/ingestion/__init__.py tests/ingestion/test_types.py
git commit -m "feat: add StandardizedResult dataclass and type enums for ingestion pipeline"
```

---

### Task 2: Stage 1 -- Extension-Based Type Detection

**Files:**
- Create: `src/ingestion/stage_1_detect.py`
- Test: `tests/ingestion/test_stage_1.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingestion/test_stage_1.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_1.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement Stage 1**

```python
# src/ingestion/stage_1_detect.py
"""Stage 1: extension-based file type detection.

Returns a normalized extension string (e.g. "csv", "txt", "cdf").
Does NOT attempt content inspection -- that is Stage 2's job.
"""

_KNOWN_EXTENSIONS = {
    "csv", "tsv", "txt", "log",
    "json", "xml",
    "cdf", "cdfx",
    "png", "jpg", "jpeg", "svg",
}


def detect_by_extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _KNOWN_EXTENSIONS:
        return ext
    return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_1.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/stage_1_detect.py tests/ingestion/test_stage_1.py
git commit -m "feat: add Stage 1 extension-based type detection"
```

---

### Task 3: Test Fixtures

**Files:**
- Create: `tests/ingestion/fixtures/cary_kinetics.csv`
- Create: `tests/ingestion/fixtures/chromeleon_export.txt`
- Create: `tests/ingestion/fixtures/plate_reader.csv`
- Create: `tests/ingestion/fixtures/simple_xy.csv`
- Create: `tests/ingestion/fixtures/european_format.csv`
- Create: `tests/ingestion/fixtures/headerless.csv`

- [ ] **Step 1: Create Cary 300 kinetics fixture**

Copy the structure from `SeCUT_butyrate02.csv`. Trim to 5 data rows for a minimal fixture.

```csv
Sample 1,,
Time (min),Abs,
0.0000,0.5432,
0.0500,0.5441,
0.1000,0.5450,
0.1500,0.5461,
0.2000,0.5470,

Collection Time             2024/06/15 13:14:25 GMT+02:00
Instrument Cary 300
Current Wavelength (nm) 400.00
```

- [ ] **Step 2: Create Chromeleon .txt fixture**

```
Raw Data:
Time (min)	Value (mAU)
0.0000	-0.125
0.0083	-0.089
0.0167	0.012
0.0250	0.045
0.0333	0.067
```

- [ ] **Step 3: Create plate reader CSV fixture**

```csv
Plate:,Plate1,,,
Read Mode:,Absorbance,,
Wavelength,A1,A2,A3
200,0.1234,0.2345,0.3456
220,0.1345,0.2456,0.3567
240,0.1456,0.2567,0.3678
260,0.1567,0.2678,0.3789
```

- [ ] **Step 4: Create simple XY, European, and headerless fixtures**

```csv
x,y
0,0.0
1,1.1
2,4.0
3,9.1
4,16.0
```

```csv
Zeit;Absorption;Temperatur
0,00;0,5432;25,0
0,05;0,5441;25,1
0,10;0,5450;25,1
0,15;0,5461;25,2
```

```csv
0.0,0.5432
0.05,0.5441
0.10,0.5450
0.15,0.5461
0.20,0.5470
```

- [ ] **Step 5: Verify fixtures are readable**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -c "import os; [print(f) for f in os.listdir('tests/ingestion/fixtures')]"`
Expected: All 6 fixture files listed

- [ ] **Step 6: Commit**

```bash
git add tests/ingestion/fixtures/
git commit -m "feat: add test fixtures for ingestion pipeline"
```

---

### Task 4: Format Preset Base Class and Preset Registry

**Files:**
- Create: `src/ingestion/presets/__init__.py`
- Create: `src/ingestion/stage_2_registry.py`
- Test: `tests/ingestion/test_stage_2.py`

- [ ] **Step 1: Write failing tests for the registry**

```python
# tests/ingestion/test_stage_2.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_2.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement FormatPreset base class and FormatRegistry**

```python
# src/ingestion/stage_2_registry.py
"""Stage 2: content-based format registry.

Each FormatPreset declares which extensions it handles and a sniff()
method that inspects the first N bytes/lines of a file.  The registry
tries presets in priority order (highest first) and returns the first
match, or None if nothing matches (falling through to Stage 3).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from .types import ColumnRole


class FormatPreset(ABC):
    name: str = ""
    extensions: set[str] = set()
    priority: int = 0

    @staticmethod
    @abstractmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        """Return True if the file matches this format.

        Args:
            path: full path to the temp file
            head_bytes: first 4096 bytes of the file
            head_lines: first 50 lines of the file (decoded)
        """

    @abstractmethod
    def parse(self, path: str) -> dict:
        """Parse the file and return a dict with keys:
            data: pd.DataFrame
            column_roles: Dict[str, ColumnRole]
            plot_hint: PlotHint (optional, default LINE)
            sample_name: str (optional)
            metadata: Dict[str, Any] (optional)
        """


_HEAD_BYTES = 4096
_HEAD_LINES = 50


def _read_head(path: str) -> tuple[bytes, list[str]]:
    with open(path, "rb") as f:
        head_bytes = f.read(_HEAD_BYTES)
    lines: list[str] = []
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            text = head_bytes.decode(enc)
            lines = text.splitlines()[:_HEAD_LINES]
            break
        except UnicodeDecodeError:
            continue
    return head_bytes, lines


class FormatRegistry:
    def __init__(self, presets: List[FormatPreset]) -> None:
        self._presets = sorted(presets, key=lambda p: -p.priority)

    def match(self, extension: str, path: str) -> Optional[FormatPreset]:
        head_bytes, head_lines = _read_head(path)
        for preset in self._presets:
            if extension not in preset.extensions:
                continue
            if preset.sniff(path, head_bytes, head_lines):
                return preset
        return None

    def list_formats(self) -> list[str]:
        return [p.name for p in self._presets]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_2.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Create empty presets __init__**

```python
# src/ingestion/presets/__init__.py
from __future__ import annotations
from typing import List
from ..stage_2_registry import FormatPreset


def load_all_presets() -> List[FormatPreset]:
    from .cary_kinetics import CaryKineticsPreset
    from .chromeleon_txt import ChromeleonTxtPreset
    from .plate_reader_csv import PlateReaderCSVPreset
    from .lcms_cdf import LCMSCDFPreset
    from .lcms_vwd_cdf import LCMSVWDCDFPreset

    return [
        CaryKineticsPreset(),
        ChromeleonTxtPreset(),
        PlateReaderCSVPreset(),
        LCMSCDFPreset(),
        LCMSVWDCDFPreset(),
    ]
```

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/stage_2_registry.py src/ingestion/presets/__init__.py tests/ingestion/test_stage_2.py
git commit -m "feat: add Stage 2 format registry with FormatPreset base class"
```

---

### Task 5: Cary Kinetics Preset

**Files:**
- Create: `src/ingestion/presets/cary_kinetics.py`
- Test: `tests/ingestion/test_presets.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingestion/test_presets.py
import pytest
import os
import pandas as pd
from src.ingestion.presets.cary_kinetics import CaryKineticsPreset
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestCaryKinetics -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement CaryKineticsPreset**

```python
# src/ingestion/presets/cary_kinetics.py
"""Cary 300/3500 spectrophotometer kinetics CSV format.

Structure:
  Row 0: sample name (single field)
  Row 1: "Time (min),Abs," (headers with possible trailing comma)
  Rows 2-N: numeric data with trailing commas
  Footer: instrument metadata (Collection Time, Instrument, Wavelength, etc.)
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict, Any

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


_FOOTER_MARKERS = re.compile(
    r"^(Collection Time|Instrument|Current Wavelength|Kinetics Version|"
    r"Operator Name|Method Name|Date/Time stamp|Saved as|End Method)",
    re.IGNORECASE,
)


class CaryKineticsPreset(FormatPreset):
    name = "cary_kinetics"
    extensions = {"csv"}
    priority = 80

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        if len(head_lines) < 3:
            return False
        fields_row0 = [f.strip() for f in head_lines[0].split(",") if f.strip()]
        if len(fields_row0) != 1:
            return False
        row1 = head_lines[1].lower()
        if "time" in row1 and ("abs" in row1 or "value" in row1):
            return True
        return False

    def parse(self, path: str) -> dict:
        lines = _read_lines(path)

        sample_name = lines[0].split(",")[0].strip()
        header_row = 1

        data_end = len(lines)
        for i in range(header_row + 1, len(lines)):
            line = lines[i].strip()
            if not line or _FOOTER_MARKERS.match(line):
                data_end = i
                break

        data_text = "\n".join(lines[header_row:data_end])
        df = pd.read_csv(StringIO(data_text))
        df.columns = [str(c).strip().rstrip(",") for c in df.columns]
        drop = [c for c in df.columns if c.startswith("Unnamed") or c == ""]
        if drop:
            df.drop(columns=drop, inplace=True)
        df.dropna(axis=1, how="all", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        cols = list(df.columns)
        column_roles: Dict[str, ColumnRole] = {}
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        metadata = _parse_footer(lines, data_end)

        return {
            "data": df,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "sample_name": sample_name,
            "metadata": metadata,
        }


def _read_lines(path: str) -> list[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [line.rstrip("\n\r") for line in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def _parse_footer(lines: list[str], start: int) -> dict:
    meta: Dict[str, Any] = {"instrument": {}}
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        for sep in [":", "  "]:
            if sep in line:
                parts = line.split(sep, 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""
                if key and val:
                    meta["instrument"][key] = val
                break
    inst = meta["instrument"].get("Instrument", "")
    if inst:
        meta["instrument_name"] = inst
    wl = meta["instrument"].get("Current Wavelength (nm)", "")
    if wl:
        meta["wavelength"] = wl
    return meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestCaryKinetics -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/presets/cary_kinetics.py tests/ingestion/test_presets.py
git commit -m "feat: add Cary kinetics preset for Stage 2 format registry"
```

---

### Task 6: Chromeleon TXT Preset

**Files:**
- Create: `src/ingestion/presets/chromeleon_txt.py`
- Modify: `tests/ingestion/test_presets.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/ingestion/test_presets.py`:

```python
from src.ingestion.presets.chromeleon_txt import ChromeleonTxtPreset


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestChromeleonTxt -v`
Expected: FAIL

- [ ] **Step 3: Implement ChromeleonTxtPreset**

```python
# src/ingestion/presets/chromeleon_txt.py
"""Chromeleon chromatogram .txt export format.

Structure:
  Possible header lines before data
  "Raw Data:" marker line
  "Time (min)\\tValue (mAU)" header
  Tab-separated numeric data
"""
from __future__ import annotations
import pandas as pd
from io import StringIO
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


class ChromeleonTxtPreset(FormatPreset):
    name = "chromeleon_txt"
    extensions = {"txt"}
    priority = 80

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        for line in head_lines:
            stripped = line.strip()
            if stripped == "Raw Data:":
                return True
            lower = stripped.lower()
            if "time (min)" in lower and ("value (mau)" in lower or "step (s)" in lower):
                return True
        return False

    def parse(self, path: str) -> dict:
        lines: list[str] = []
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                with open(path, "r", encoding=enc) as f:
                    lines = [l.rstrip("\n\r") for l in f.readlines()]
                break
            except UnicodeDecodeError:
                continue

        data_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "Raw Data:":
                data_start = i + 1
                break
            if "Time (min)" in line:
                data_start = i
                break

        data_text = "\n".join(lines[data_start:])
        df = pd.read_csv(StringIO(data_text), sep="\t")
        df.dropna(axis=1, how="all", inplace=True)
        df.dropna(axis=0, how="all", inplace=True)

        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(axis=0, how="any", inplace=True)

        cols = list(df.columns)
        column_roles: Dict[str, ColumnRole] = {}
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        return {
            "data": df,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "sample_name": None,
            "metadata": {"file_type_detail": "chromeleon_chromatogram"},
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestChromeleonTxt -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/presets/chromeleon_txt.py tests/ingestion/test_presets.py
git commit -m "feat: add Chromeleon TXT preset"
```

---

### Task 7: Plate Reader CSV Preset

**Files:**
- Create: `src/ingestion/presets/plate_reader_csv.py`
- Modify: `tests/ingestion/test_presets.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/ingestion/test_presets.py`:

```python
from src.ingestion.presets.plate_reader_csv import PlateReaderCSVPreset


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestPlateReaderCSV -v`
Expected: FAIL

- [ ] **Step 3: Implement PlateReaderCSVPreset**

This preset delegates the heavy lifting to the existing `UVVISCSVReader` (which already handles the complex plate metadata parsing), then maps its output to `ColumnRole`.

```python
# src/ingestion/presets/plate_reader_csv.py
"""UV-Vis plate reader CSV format (e.g. SpectraMax, Tecan).

Detected by presence of "Wavelength" column header in the first 50 lines.
Delegates actual parsing to the existing UVVISCSVReader.
"""
from __future__ import annotations
import re
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


class PlateReaderCSVPreset(FormatPreset):
    name = "plate_reader_csv"
    extensions = {"csv"}
    priority = 90

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        for line in head_lines:
            if re.search(r"\bWavelength\b", line):
                return True
        return False

    def parse(self, path: str) -> dict:
        from services.readers.uvvis_csv_reader import UVVISCSVReader

        reader = UVVISCSVReader()
        if not reader.load_file(path):
            raise ValueError(f"UVVISCSVReader failed to parse {path}")

        data = reader.get_data()
        metadata = reader.get_metadata()

        column_roles: Dict[str, ColumnRole] = {}
        for col in data.columns:
            if col == "Wavelength":
                column_roles[col] = ColumnRole.X
            elif col.startswith("_") or col == "row_id":
                column_roles[col] = ColumnRole.IGNORE
            else:
                column_roles[col] = ColumnRole.Y

        return {
            "data": data,
            "column_roles": column_roles,
            "plot_hint": PlotHint.MULTI_Y,
            "sample_name": metadata.get("plate_name"),
            "metadata": metadata,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestPlateReaderCSV -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/presets/plate_reader_csv.py tests/ingestion/test_presets.py
git commit -m "feat: add plate reader CSV preset (delegates to UVVISCSVReader)"
```

---

### Task 8: LC-MS CDF and VWD Presets

**Files:**
- Create: `src/ingestion/presets/lcms_cdf.py`
- Create: `src/ingestion/presets/lcms_vwd_cdf.py`
- Modify: `tests/ingestion/test_presets.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/ingestion/test_presets.py`:

```python
from src.ingestion.presets.lcms_cdf import LCMSCDFPreset
from src.ingestion.presets.lcms_vwd_cdf import LCMSVWDCDFPreset


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestLCMSCDF tests/ingestion/test_presets.py::TestLCMSVWDCDF -v`
Expected: FAIL

- [ ] **Step 3: Implement LC-MS presets**

```python
# src/ingestion/presets/lcms_cdf.py
"""LC-MS netCDF (TIC) format.

Detected by .cdf extension + filename NOT containing vwd/uvw/uv- tags.
Delegates parsing to existing LCMSCDFReader.
"""
from __future__ import annotations
import os
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


_VWD_TAGS = ("vwd", "uvw", "uv-")


class LCMSCDFPreset(FormatPreset):
    name = "lcms_cdf"
    extensions = {"cdf", "cdfx"}
    priority = 70

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        name_lower = os.path.basename(path).lower()
        return not any(tag in name_lower for tag in _VWD_TAGS)

    def parse(self, path: str) -> dict:
        from services.readers.lcms_cdf_reader import LCMSCDFReader

        reader = LCMSCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"LCMSCDFReader failed to parse {path}")

        data = reader.get_data()
        metadata = reader.get_metadata()

        column_roles: Dict[str, ColumnRole] = {}
        cols = list(data.columns)
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        return {
            "data": data,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "sample_name": metadata.get("experiment_title"),
            "metadata": metadata,
        }
```

```python
# src/ingestion/presets/lcms_vwd_cdf.py
"""LC-MS VWD (UV detector) netCDF format.

Detected by .cdf extension + filename containing vwd/uvw/uv- tags.
Delegates parsing to existing LCMSVWDCDFReader.
"""
from __future__ import annotations
import os
from typing import Dict

from ..stage_2_registry import FormatPreset
from ..types import ColumnRole, PlotHint


_VWD_TAGS = ("vwd", "uvw", "uv-")


class LCMSVWDCDFPreset(FormatPreset):
    name = "lcms_vwd_cdf"
    extensions = {"cdf", "cdfx"}
    priority = 75

    @staticmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        name_lower = os.path.basename(path).lower()
        return any(tag in name_lower for tag in _VWD_TAGS)

    def parse(self, path: str) -> dict:
        from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader

        reader = LCMSVWDCDFReader()
        if not reader.load_file(path):
            raise ValueError(f"LCMSVWDCDFReader failed to parse {path}")

        data = reader.get_data()
        metadata = reader.get_metadata()

        column_roles: Dict[str, ColumnRole] = {}
        cols = list(data.columns)
        if cols:
            column_roles[cols[0]] = ColumnRole.X
        for c in cols[1:]:
            column_roles[c] = ColumnRole.Y

        return {
            "data": data,
            "column_roles": column_roles,
            "plot_hint": PlotHint.LINE,
            "sample_name": None,
            "metadata": metadata,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_presets.py::TestLCMSCDF tests/ingestion/test_presets.py::TestLCMSVWDCDF -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/presets/lcms_cdf.py src/ingestion/presets/lcms_vwd_cdf.py tests/ingestion/test_presets.py
git commit -m "feat: add LC-MS CDF and VWD presets"
```

---

### Task 9: Stage 3 -- Smart Heuristic Fallback

**Files:**
- Create: `src/ingestion/stage_3_heuristic.py`
- Test: `tests/ingestion/test_stage_3.py`

This is the extraction of `GenericCSVReader`'s smart parsing logic into a pipeline stage that returns column roles and plot hints instead of reader-specific metadata.

- [ ] **Step 1: Write failing tests**

```python
# tests/ingestion/test_stage_3.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_3.py -v`
Expected: FAIL

- [ ] **Step 3: Implement heuristic_parse**

Extract the core logic from `GenericCSVReader` into a standalone function. The original reader stays untouched (it is still used by existing code until the migration in Task 11).

```python
# src/ingestion/stage_3_heuristic.py
"""Stage 3: smart heuristic fallback for files not matched by any preset.

Handles: delimiter detection, header row detection, footer stripping,
European number format, auto X/Y column detection.

Returns the same dict shape as FormatPreset.parse() or None if the
file cannot be parsed as tabular data.
"""
from __future__ import annotations
import re
import pandas as pd
import numpy as np
from io import StringIO
from typing import Dict, Any, List, Optional, Tuple

from .types import ColumnRole, PlotHint

_X_PATTERNS = [
    (r"\btime\b", "time"),
    (r"\bretention\b", "time"),
    (r"\brt\b", "time"),
    (r"\bmin\b", "time"),
    (r"\bwavelength\b", "wavelength"),
    (r"\bnm\b", "wavelength"),
    (r"\bconcentration\b", "concentration"),
    (r"\bsample\b", "category"),
    (r"\bindex\b", "index"),
    (r"\bcycle\b", "cycle"),
    (r"\btemp\b", "temperature"),
]

_Y_PATTERNS = [
    (r"\babs\b", "absorbance"),
    (r"\babsorbance\b", "absorbance"),
    (r"\bintensity\b", "intensity"),
    (r"\bmau\b", "intensity"),
    (r"\bsignal\b", "signal"),
    (r"\bvalue\b", "value"),
    (r"\barea\b", "area"),
    (r"\bconversion\b", "conversion"),
    (r"\byield\b", "yield"),
    (r"\bactivity\b", "activity"),
    (r"\brate\b", "rate"),
    (r"\bpeak\b", "peak"),
    (r"\bau\b", "absorbance"),
    (r"\bod\b", "absorbance"),
]

_FOOTER_MARKERS = [
    r"^Collection Time:",
    r"^Operator Name",
    r"^Kinetics Version",
    r"^Parameter List",
    r"^Instrument\s",
    r"^Method Name",
    r"^Date/Time stamp",
    r"^Saved as ",
    r"^End Method",
    r"^<.*>",
]


def heuristic_parse(path: str, extension: str) -> Optional[dict]:
    """Try to parse a file as tabular data using heuristics.

    Returns a dict with keys: data, column_roles, plot_hint, sample_name,
    metadata.  Returns None if the file cannot be parsed.
    """
    lines = _read_raw_lines(path)
    if not lines:
        return None

    delimiter = _detect_delimiter(lines)
    header_row, sample_name = _find_header_row(lines, delimiter)
    data_end = _find_data_end(lines, header_row, delimiter)
    instrument_meta = _extract_instrument_metadata(lines, data_end)

    data_lines = lines[header_row:data_end]
    if len(data_lines) < 2:
        return None

    data_text = "\n".join(data_lines)
    is_european = _detect_european_format(data_lines, delimiter)

    try:
        if is_european:
            df = pd.read_csv(StringIO(data_text), sep=delimiter, decimal=",")
        else:
            df = pd.read_csv(StringIO(data_text), sep=delimiter)
    except Exception:
        return None

    df = _clean_dataframe(df)
    df = _coerce_numerics(df)

    if df.empty:
        return None

    column_roles = _detect_column_roles(df)
    plot_hint = _choose_plot_hint(df, column_roles)

    metadata: Dict[str, Any] = {}
    if instrument_meta:
        metadata["instrument"] = instrument_meta
        inst = instrument_meta.get("Instrument", "")
        if inst:
            metadata["instrument_name"] = inst
        wl = instrument_meta.get("Current Wavelength (nm)", "") or instrument_meta.get("Current Wavelength", "")
        if wl:
            metadata["wavelength"] = wl

    return {
        "data": df,
        "column_roles": column_roles,
        "plot_hint": plot_hint,
        "sample_name": sample_name,
        "metadata": metadata,
    }


# ------------------------------------------------------------------
# Internal helpers (extracted from GenericCSVReader)
# ------------------------------------------------------------------

def _read_raw_lines(path: str) -> List[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [line.rstrip("\n\r") for line in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def _detect_delimiter(lines: List[str]) -> str:
    candidates = [",", ";", "\t"]
    best, best_score = ",", -1
    sample = lines[: min(20, len(lines))]
    for delim in candidates:
        counts = [line.count(delim) for line in sample if line.strip()]
        if not counts:
            continue
        median_count = sorted(counts)[len(counts) // 2]
        if median_count > best_score:
            best, best_score = delim, median_count
    return best


def _find_header_row(
    lines: List[str], delimiter: str
) -> Tuple[int, Optional[str]]:
    sample_name = None
    for i, line in enumerate(lines[:20]):
        fields = [f.strip().strip('"') for f in line.split(delimiter)]
        fields = [f for f in fields if f]
        if len(fields) < 2:
            if len(fields) == 1 and i == 0:
                sample_name = fields[0]
            continue
        numeric_count = sum(1 for f in fields if _looks_numeric(f))
        text_count = len(fields) - numeric_count
        if text_count >= 2 and text_count > numeric_count:
            return i, sample_name
    return 0, sample_name


def _find_data_end(lines: List[str], header_row: int, delimiter: str) -> int:
    if header_row + 1 >= len(lines):
        return len(lines)
    for i in range(header_row + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            return i
        for pattern in _FOOTER_MARKERS:
            if re.match(pattern, line, re.IGNORECASE):
                return i
        fields = [f.strip() for f in line.split(delimiter)]
        non_empty = [f for f in fields if f]
        if len(non_empty) < 2:
            if not any(_looks_numeric(f) for f in non_empty):
                return i
    return len(lines)


def _extract_instrument_metadata(lines: List[str], data_end: int) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in lines[data_end:]:
        line = line.strip()
        if not line:
            continue
        for sep in [":", "  "]:
            if sep in line:
                parts = line.split(sep, 1)
                key = parts[0].strip().strip("<>")
                val = parts[1].strip() if len(parts) > 1 else ""
                if key and val:
                    meta[key] = val
                break
    return meta


def _detect_european_format(data_lines: List[str], delimiter: str) -> bool:
    if delimiter == ",":
        return False
    for line in data_lines[1:6]:
        fields = [f.strip() for f in line.split(delimiter)]
        for f in fields:
            if f and "," in f and "." not in f:
                try:
                    float(f.replace(",", "."))
                    return True
                except ValueError:
                    pass
    return False


def _looks_numeric(s: str) -> bool:
    s = s.strip().replace(",", ".")
    try:
        float(s)
        return True
    except ValueError:
        return False


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().rstrip(",") for c in df.columns]
    cols_to_drop = [
        c for c in df.columns if c.startswith("Unnamed") or c == "" or c.isspace()
    ]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")
    return df


def _coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            cleaned = df[col].astype(str).str.strip().str.replace(",", ".", regex=False)
            converted = pd.to_numeric(cleaned, errors="coerce")
            if converted.notna().sum() > len(df) * 0.5:
                df[col] = converted
    return df


def _detect_column_roles(df: pd.DataFrame) -> Dict[str, ColumnRole]:
    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and c != "_row_id"
    ]

    def _match(col_name: str, patterns) -> Optional[str]:
        lower = col_name.lower()
        for pat, kind in patterns:
            if re.search(pat, lower):
                return kind
        return None

    x_candidates = []
    y_candidates = []
    for col in numeric_cols:
        xk = _match(col, _X_PATTERNS)
        yk = _match(col, _Y_PATTERNS)
        if xk:
            x_candidates.append(col)
        if yk:
            y_candidates.append(col)

    roles: Dict[str, ColumnRole] = {}

    if x_candidates:
        roles[x_candidates[0]] = ColumnRole.X
    elif len(numeric_cols) >= 2:
        roles[numeric_cols[0]] = ColumnRole.X

    x_col = next((c for c, r in roles.items() if r == ColumnRole.X), None)

    if y_candidates:
        for c in y_candidates[:8]:
            if c != x_col:
                roles[c] = ColumnRole.Y
    elif len(numeric_cols) >= 2:
        for c in numeric_cols[:8]:
            if c != x_col:
                roles[c] = ColumnRole.Y

    for col in df.columns:
        if col not in roles:
            if col == "_row_id":
                roles[col] = ColumnRole.IGNORE
            elif pd.api.types.is_numeric_dtype(df[col]):
                roles[col] = ColumnRole.UNKNOWN
            else:
                roles[col] = ColumnRole.LABEL

    return roles


def _choose_plot_hint(df: pd.DataFrame, roles: Dict[str, ColumnRole]) -> PlotHint:
    y_count = sum(1 for r in roles.values() if r == ColumnRole.Y)
    if y_count > 3:
        return PlotHint.MULTI_Y
    return PlotHint.LINE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_stage_3.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/stage_3_heuristic.py tests/ingestion/test_stage_3.py
git commit -m "feat: add Stage 3 smart heuristic fallback (extracted from GenericCSVReader)"
```

---

### Task 10: Pipeline Orchestrator

**Files:**
- Create: `src/ingestion/pipeline.py`
- Test: `tests/ingestion/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/ingestion/test_pipeline.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_pipeline.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the pipeline orchestrator**

```python
# src/ingestion/pipeline.py
"""3-stage ingestion pipeline orchestrator.

Stage 1: detect_by_extension()  -> normalized extension string
Stage 2: FormatRegistry.match() -> FormatPreset or None
Stage 3: heuristic_parse()      -> fallback for unrecognized formats

Output: StandardizedResult or None
"""
from __future__ import annotations
from typing import Optional

from .types import StandardizedResult, FileIdentity, PlotHint, ColumnRole
from .stage_1_detect import detect_by_extension
from .stage_2_registry import FormatRegistry
from .stage_3_heuristic import heuristic_parse
from .presets import load_all_presets


class IngestionPipeline:
    def __init__(self) -> None:
        self.registry = FormatRegistry(load_all_presets())

    def ingest(self, path: str, original_name: str) -> Optional[StandardizedResult]:
        extension = detect_by_extension(original_name)

        preset = self.registry.match(extension, path)
        if preset is not None:
            try:
                raw = preset.parse(path)
                return StandardizedResult(
                    data=raw["data"],
                    column_roles=raw["column_roles"],
                    identity=FileIdentity(
                        original_name=original_name,
                        extension=extension,
                        detected_format=preset.name,
                        detection_stage=2,
                    ),
                    plot_hint=raw.get("plot_hint", PlotHint.LINE),
                    sample_name=raw.get("sample_name"),
                    metadata=raw.get("metadata", {}),
                )
            except Exception as e:
                print(f"Stage 2 preset {preset.name} failed for {original_name}: {e}")

        raw = heuristic_parse(path, extension)
        if raw is not None:
            return StandardizedResult(
                data=raw["data"],
                column_roles=raw["column_roles"],
                identity=FileIdentity(
                    original_name=original_name,
                    extension=extension,
                    detected_format="heuristic",
                    detection_stage=3,
                ),
                plot_hint=raw.get("plot_hint", PlotHint.LINE),
                sample_name=raw.get("sample_name"),
                metadata=raw.get("metadata", {}),
            )

        return None


_default_pipeline: Optional[IngestionPipeline] = None


def ingest_file(path: str, original_name: str) -> Optional[StandardizedResult]:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = IngestionPipeline()
    return _default_pipeline.ingest(path, original_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_pipeline.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Update `src/ingestion/__init__.py` (already has `ingest_file`)**

Verify the import works:

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -c "from src.ingestion import ingest_file, StandardizedResult; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/pipeline.py tests/ingestion/test_pipeline.py
git commit -m "feat: add 3-stage ingestion pipeline orchestrator"
```

---

### Task 11: Wire Pipeline into StorageManager

**Files:**
- Modify: `src/services/storage_manager.py:397-481` (load_file_data)
- Modify: `src/services/storage_manager.py:161-196` (DataManager.__init__)

This is the integration task. `load_file_data()` calls `ingest_file()` and wraps the `StandardizedResult` into the existing dict format that the rest of the app expects. This is a bridge -- it preserves backward compatibility while the plotter migration happens in Task 12.

- [ ] **Step 1: Write failing test for the bridge**

```python
# tests/ingestion/test_integration.py
"""Test that StorageManager uses the ingestion pipeline."""
import pytest
import base64
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_integration.py -v`
Expected: FAIL (no `standardized` key in result)

- [ ] **Step 3: Add pipeline call to load_file_data**

In `src/services/storage_manager.py`, add the import at the top of the file:

```python
from src.ingestion import ingest_file
```

Then in `load_file_data()`, after line 407 (`self.temp_files.append(temp_file.name)`), add the pipeline call. The pipeline result gets stored alongside existing data for backward compatibility:

```python
    def load_file_data(self, file_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            content_bytes = _decode_content(file_record['encoded'])
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_record['name']}")
            temp_file.write(content_bytes)
            temp_file.close()
            self.temp_files.append(temp_file.name)

            # --- NEW: run through ingestion pipeline ---
            standardized = ingest_file(temp_file.name, file_record['name'])

            # --- EXISTING: detect file type (kept for backward compat) ---
            file_type = self.detect_file_type(file_record['name'], temp_file.name)
            if file_type:
                file_record['type'] = file_type

            self.register_file_id(file_record['id'], file_record['name'])

            if file_type and file_type in self.readers:
                reader = self.readers[file_type]()
                if reader.load_file(temp_file.name):
                    data = reader.get_data()
                    metadata = reader.get_metadata()
                    file_id = file_record['id']

                    # (LC-MS bundle handling stays exactly the same)
                    if file_type in {'lcms_cdf', 'lcms_vwd_cdf'}:
                        # ... existing bundle code unchanged ...

                    entry = {
                        'record': file_record,
                        'data': data,
                        'metadata': metadata,
                        'reader': reader,
                        'type': file_type,
                    }
                    if standardized is not None:
                        entry['standardized'] = standardized

                    self.loaded_data[file_id] = entry
                    return entry

            print(f"Could not load {file_record['name']} - unknown type or no reader")
            return None

        except Exception as e:
            print(f"Error loading {file_record['name']}: {str(e)}")
            return None
```

The key change: every loaded file entry now has a `standardized` key containing the `StandardizedResult`. The old `data`, `metadata`, `reader`, `type` keys all remain so nothing breaks.

- [ ] **Step 4: Run integration test to verify it passes**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_integration.py -v`
Expected: PASS

- [ ] **Step 5: Run the full app to verify nothing broke**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python app.py &`
Then upload a CSV and a Chromeleon .txt file. Verify they still plot correctly.

- [ ] **Step 6: Commit**

```bash
git add src/services/storage_manager.py tests/ingestion/test_integration.py
git commit -m "feat: wire ingestion pipeline into StorageManager (backward-compatible bridge)"
```

---

### Task 12: Refactor PlotManager to Use StandardizedResult

**Files:**
- Modify: `src/services/plot_manager.py:558-589` (get_plot_for_file)
- Modify: `src/services/plot_manager.py:219-292` (create_generic_table_plot)
- Create: `src/services/plot_manager.py` - new method `create_standardized_plot`

This is where the plotter becomes format-agnostic. A new method `create_standardized_plot()` reads only `ColumnRole` and `PlotHint` from the `StandardizedResult`. The existing `get_plot_for_file()` tries the standardized path first, falls back to legacy routing.

- [ ] **Step 1: Write failing test**

```python
# tests/ingestion/test_plot_standardized.py
import pytest
import pandas as pd
import plotly.graph_objects as go
from src.services.plot_manager import PlotManager
from src.ingestion.types import StandardizedResult, ColumnRole, PlotHint, FileIdentity


def _make_result(df, roles, hint=PlotHint.LINE, name=None):
    return StandardizedResult(
        data=df,
        column_roles=roles,
        identity=FileIdentity("test.csv", "csv", "test", 3),
        plot_hint=hint,
        sample_name=name,
    )


def test_create_standardized_plot_line():
    pm = PlotManager()
    df = pd.DataFrame({"Time": [0, 1, 2], "Abs": [0.5, 0.6, 0.7]})
    sr = _make_result(df, {"Time": ColumnRole.X, "Abs": ColumnRole.Y})
    fig = pm.create_standardized_plot(sr)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].mode == "lines"


def test_create_standardized_plot_multi_y():
    pm = PlotManager()
    df = pd.DataFrame({"WL": [200, 300], "A1": [0.1, 0.2], "A2": [0.3, 0.4]})
    sr = _make_result(
        df,
        {"WL": ColumnRole.X, "A1": ColumnRole.Y, "A2": ColumnRole.Y},
        PlotHint.MULTI_Y,
    )
    fig = pm.create_standardized_plot(sr)
    assert len(fig.data) == 2


def test_create_standardized_plot_with_sample_name():
    pm = PlotManager()
    df = pd.DataFrame({"Time": [0, 1], "Abs": [0.5, 0.6]})
    sr = _make_result(
        df,
        {"Time": ColumnRole.X, "Abs": ColumnRole.Y},
        name="Sample 1",
    )
    fig = pm.create_standardized_plot(sr)
    assert "Sample 1" in fig.layout.title.text


def test_create_standardized_plot_no_x_uses_index():
    pm = PlotManager()
    df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})
    sr = _make_result(df, {"col1": ColumnRole.Y, "col2": ColumnRole.Y})
    fig = pm.create_standardized_plot(sr)
    assert len(fig.data) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_plot_standardized.py -v`
Expected: FAIL (no `create_standardized_plot` method)

- [ ] **Step 3: Add `create_standardized_plot` to PlotManager**

Add this method to `PlotManager` (before `get_plot_for_file`):

```python
    def create_standardized_plot(self, result: 'StandardizedResult') -> go.Figure:
        """Create a plot from a StandardizedResult. Format-agnostic."""
        from src.ingestion.types import ColumnRole, PlotHint

        fig = go.Figure()
        df = result.data

        x_cols = result.x_columns
        y_cols = result.y_columns

        if x_cols:
            x_col = x_cols[0]
            x_vals = df[x_col]
            x_title = x_col
        else:
            x_vals = list(range(len(df)))
            x_title = "Index"
            x_col = None

        if not y_cols:
            return self.create_empty_plot("No Y columns identified")

        mode_map = {
            PlotHint.LINE: "lines",
            PlotHint.SCATTER: "markers",
            PlotHint.MULTI_Y: "lines",
        }
        mode = mode_map.get(result.plot_hint, "lines")

        for i, col in enumerate(y_cols[:8]):
            color = self.default_colors[i % len(self.default_colors)]
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=pd.to_numeric(df[col], errors="coerce"),
                mode=mode,
                name=col,
                line=dict(color=color, width=2),
                hovertemplate=f"{col}<br>{x_title}: %{{x}}<br>%{{y:.4f}}<extra></extra>",
            ))

        title = result.sample_name or result.identity.original_name
        wl = result.metadata.get("wavelength", "")
        if wl:
            title += f" ({wl} nm)"

        y_title = y_cols[0] if len(y_cols) == 1 else "Value"

        fig.update_layout(
            title=title,
            xaxis_title=x_title,
            yaxis_title=y_title,
            template="plotly_white",
            autosize=True,
            showlegend=len(y_cols) > 1,
            hovermode="closest",
        )
        return fig
```

- [ ] **Step 4: Update `get_plot_for_file` to try standardized path first**

Replace the beginning of `get_plot_for_file()` (line 558-564) to check for standardized result:

```python
    def get_plot_for_file(self, file_data: Dict[str, Any]) -> go.Figure:
        try:
            sr = file_data.get('standardized')
            if sr is not None:
                return self.create_standardized_plot(sr)

            # Legacy fallback (existing routing code stays exactly as-is)
            metadata = file_data.get('metadata', {})
            file_type = (metadata.get('file_type')
                         or file_data.get('type')
                         or file_data.get('record', {}).get('type', 'unknown'))
            # ... rest of existing method unchanged ...
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Run the app and verify plots**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python app.py &`
Upload: `SeCUT_butyrate02.csv`, a Chromeleon .txt, a plate reader CSV. Verify all produce correct plots.

- [ ] **Step 7: Commit**

```bash
git add src/services/plot_manager.py tests/ingestion/test_plot_standardized.py
git commit -m "feat: add format-agnostic create_standardized_plot, wire into get_plot_for_file"
```

---

### Task 13: Update Callbacks to Use StandardizedResult

**Files:**
- Modify: `src/callbacks/viz_callbacks.py:292-540` (handle_file_selection)
- Modify: `src/callbacks/upload_callbacks.py:18-159` (handle_file_upload)

The callbacks currently read `metadata.get('auto_x')` and `metadata.get('auto_y')` to populate the publication plotter selections. Update them to also check `file_data.get('standardized')` for column roles.

- [ ] **Step 1: Update upload_callbacks auto-view logic**

In `handle_file_upload()`, where the view mode is decided (around line 140), update the check:

```python
            # Decide view mode
            sr = file_data.get('standardized')
            has_auto_axes = False
            if sr is not None:
                has_auto_axes = bool(sr.x_columns and sr.y_columns)
            else:
                has_auto_axes = bool(
                    file_data.get('metadata', {}).get('auto_x')
                    and file_data.get('metadata', {}).get('auto_y')
                )

            if has_auto_axes:
                new_view_mode = 'raw'
            elif file_type in {'chromatogram', 'uvvis_csv', 'lcms_cdf', 'lcms_vwd_cdf'}:
                new_view_mode = 'raw'
            else:
                new_view_mode = 'analysis'
```

- [ ] **Step 2: Update viz_callbacks auto-selection logic**

In `handle_file_selection()`, where publication memory auto-selection happens, update to prefer standardized result:

```python
            sr = file_data.get('standardized')
            if sr is not None and sr.x_columns and sr.y_columns:
                auto_x = sr.x_columns[0]
                auto_y = sr.y_columns
            else:
                auto_x = file_data.get('metadata', {}).get('auto_x')
                auto_y = file_data.get('metadata', {}).get('auto_y', [])
```

- [ ] **Step 3: Test the full flow**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python app.py &`
Upload `SeCUT_butyrate02.csv`. Verify:
1. Plot appears immediately (raw mode, not analysis)
2. X/Y selections are auto-populated in the data selector
3. Plot shows Time vs Abs with sample name in title

- [ ] **Step 4: Commit**

```bash
git add src/callbacks/upload_callbacks.py src/callbacks/viz_callbacks.py
git commit -m "feat: update callbacks to prefer StandardizedResult for auto-selection"
```

---

### Task 14: Add Metadata Tab Support

**Files:**
- Modify: `src/callbacks/viz_callbacks.py` (metadata container rendering)

The metadata container should display `StandardizedResult.metadata` and identity info when available.

- [ ] **Step 1: Update metadata rendering**

Find the section where `metadata-container` children are built. Add a block that renders the `StandardizedResult` identity and metadata if present:

```python
            sr = file_data.get('standardized')
            if sr is not None:
                identity = sr.identity
                meta_items = [
                    html.P(f"Format: {identity.detected_format} (Stage {identity.detection_stage})"),
                    html.P(f"Columns: {', '.join(sr.x_columns)} (X) / {', '.join(sr.y_columns)} (Y)"),
                    html.P(f"Plot hint: {sr.plot_hint.value}"),
                ]
                if sr.sample_name:
                    meta_items.append(html.P(f"Sample: {sr.sample_name}"))
                for key, val in sr.metadata.items():
                    if isinstance(val, dict):
                        for k2, v2 in val.items():
                            meta_items.append(html.P(f"{k2}: {v2}"))
                    else:
                        meta_items.append(html.P(f"{key}: {val}"))
                metadata_children = html.Div(meta_items)
```

- [ ] **Step 2: Test in browser**

Upload a Cary kinetics CSV. Switch to the metadata display. Verify:
- Shows "Format: cary_kinetics (Stage 2)"
- Shows instrument metadata from footer
- Shows sample name

- [ ] **Step 3: Commit**

```bash
git add src/callbacks/viz_callbacks.py
git commit -m "feat: display StandardizedResult identity and metadata in metadata tab"
```

---

### Task 15: Run Full Test Suite and Cleanup

**Files:**
- All test files
- Remove: nothing yet (old readers stay as preset backends)

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run the app with all file types**

Upload each of these and verify correct plotting:
1. Cary kinetics CSV (`SeCUT_butyrate02.csv`)
2. Chromeleon .txt (any HPLC export)
3. UV-Vis plate reader CSV
4. LC-MS .cdf files
5. Simple 2-column CSV
6. European-format CSV (if available)

- [ ] **Step 3: Verify no format-specific code leaked into PlotManager**

Run: `grep -n "chromatogram\|uvvis\|lcms\|cary" src/services/plot_manager.py`
Expected: Only in the legacy fallback block inside `get_plot_for_file()`, not in `create_standardized_plot()`.

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "test: verify full ingestion pipeline integration"
```

---

## Future Tasks (Not in This Plan)

These are out of scope but noted for future plans:

1. **Remove legacy readers**: Once all presets are stable, delete `GenericCSVReader`, `ChromatogramReader`, `UVVISCSVReader` and their routing code from `StorageManager.detect_file_type()` and `PlotManager.get_plot_for_file()`.

2. **Add new presets**: Each new instrument format is a single file in `src/ingestion/presets/` with `sniff()` and `parse()`. No other files need to change.

3. **User-defined presets**: Allow users to create presets via the Settings tab (column mapping, delimiter, header row). Stored as JSON in `file_state.json`.

4. **Bar chart / scatter PlotHint**: Extend `create_standardized_plot()` to handle `PlotHint.BAR` and `PlotHint.SCATTER` with appropriate Plotly trace types.

5. **Bundling via pipeline**: Move Chromeleon/LCMS bundle detection from `StorageManager.get_bundled_tree_items()` into the pipeline layer using `FileIdentity.detected_format`.
