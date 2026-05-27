# Pipeline Single-Path Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `StandardizedResult` the single data path through GeckoPlotter — no legacy reader fallbacks, no `file_type` string branching.

**Architecture:** Every file goes through the ingestion pipeline → `StandardizedResult`. All plotting, overlay grouping, table display, and view-mode decisions read from `StandardizedResult` fields (`column_roles`, `plot_hint`, `source_category`). The legacy readers survive only as parsing backends called internally by presets. All `if file_type ==` branches are replaced with StandardizedResult-driven logic.

**Tech Stack:** Python, Dash/Plotly, pandas, existing ingestion pipeline in `src/ingestion/`

**Working directory:** `/Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2/`

---

## Context

### Current dual-path problem

`StorageManager.load_file_data()` currently:
1. Calls `ingest_file()` → `StandardizedResult`
2. Maps format → legacy reader key via `_file_type_from_pipeline()`
3. Loads again via legacy reader → data + metadata
4. Falls back to `StandardizedResult` only if reader fails
5. Stores both `'standardized'` and reader-produced `'data'`/`'metadata'`

Consuming code (`plot_manager`, `viz_callbacks`, `file_tree_callbacks`) then branches on `file_type` strings 30+ times to decide how to plot, group, and display.

### Target architecture

```
File upload → ingest_file() → StandardizedResult → stored
                                    ↓
                    PlotManager reads column_roles + plot_hint
                    viz_callbacks reads source_category + x_columns
                    file_tree reads plot_hint for multi-Y children
```

No `file_type` strings in any decision logic. The `type` field on file records becomes cosmetic (icons only).

---

## Task 0: Enrich presets to match legacy reader quality

**Why this must come first:** The pipeline presets currently parse data correctly but miss metadata that the legacy readers extract. If we drop the legacy readers without closing these gaps, features break.

**Files:**
- Modify: `src/ingestion/presets/chromeleon_txt.py`
- Modify: `src/ingestion/presets/plate_reader_csv.py`
- Reference: `src/services/readers/chromatogram_reader.py` (what to port)
- Reference: `src/services/readers/uvvis_csv_reader.py` (what to port)

### Gap 1: plate_reader_csv.py — missing `filled_wells` (CRITICAL)

The `UVVISCSVReader.get_filled_wells()` filters wells where any value > 0.001 (empty plate wells). Without `filled_wells` in metadata, the file tree can't show wells as children, and well visibility toggling breaks.

The reader also extracts pre-header metadata (Date, Time, instrument info) and computes `wavelength_range`, `intensity_columns`, `filled_well_count`, `total_wells`.

- [ ] **Step 1: Add filled_wells computation and pre-header metadata to plate_reader_csv.py**

Port from `UVVISCSVReader.get_filled_wells()` (readers/uvvis_csv_reader.py:139-147) and `_parse_metadata()` (lines 66-88). Add to `parse()` before the return:

```python
# Compute filled wells (wells with actual signal)
well_cols = [c for c in df.columns if c != "Wavelength" and not c.startswith("_") and c != "row_id"]
filled_wells = []
for col in well_cols:
    values = df[col].dropna()
    if len(values) > 0 and (values.abs() > 0.001).any():
        filled_wells.append(col)

# Parse pre-header metadata
pre_header_meta = {}
for enc in ("utf-8", "latin-1", "cp1252"):
    try:
        with open(path, "r", encoding=enc) as f:
            pre_lines = [l.rstrip("\n\r") for l in f.readlines()[:header_row]]
        break
    except UnicodeDecodeError:
        continue
else:
    pre_lines = []

for line in pre_lines:
    parts = line.split(",", 1)
    if len(parts) >= 2:
        key = parts[0].strip().rstrip(":")
        val = parts[1].strip().rstrip(",").strip()
        if key and val:
            pre_header_meta[key] = val

# Wavelength range
wl_range = (df["Wavelength"].min(), df["Wavelength"].max()) if "Wavelength" in df.columns else None
```

Update the return dict's metadata:
```python
"metadata": {
    "file_type_detail": "plate_reader",
    "filled_wells": filled_wells,
    "intensity_columns": well_cols,
    "filled_well_count": len(filled_wells),
    "total_wells": len(well_cols),
    "wavelength_range": wl_range,
    **pre_header_meta,
},
```

- [ ] **Step 2: Test with an actual plate reader CSV**

Find or create a test fixture. Run the preset on it and verify `filled_wells` matches what the legacy reader produces. Check that empty wells (all values < 0.001) are excluded.

### Gap 2: chromeleon_txt.py — missing header metadata and German numbers

The `ChromatogramReader` extracts all key-value pairs from the header section (channel, data vault, injection, wavelength, processing method, etc.) and handles German decimal format (comma as decimal separator, e.g. `1.234,56` → `1234.56`).

- [ ] **Step 3: Add header metadata extraction and German number support to chromeleon_txt.py**

Port from `ChromatogramReader._extract_metadata_from_header()` (readers/chromatogram_reader.py:34-64) and `_convert_german_number()` (line 26-29).

In `parse()`, before parsing the data, extract metadata from header lines (everything before "Raw Data:"):

```python
import re

# Extract header metadata
header_lines = lines[:data_start]
header_meta = {}
for line in header_lines:
    line = line.strip()
    if not line or line.startswith("---"):
        continue
    if "\t" in line:
        parts = line.split("\t")
        for i in range(0, len(parts) - 1, 2):
            if i + 1 < len(parts):
                key = parts[i].strip().rstrip(":")
                val = parts[i + 1].strip()
                if key and val:
                    clean_key = key.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").lower()
                    header_meta[clean_key] = val
    elif ":" in line and not line.startswith("chrom://"):
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if key and val:
            clean_key = key.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "").lower()
            header_meta[clean_key] = val

# Extract wavelength
wl_match = re.search(r"WVL:\s*(\d{3})\s*nm", "\n".join(header_lines))
if wl_match:
    header_meta["wavelength_nm"] = wl_match.group(1)
```

Add German number conversion before `pd.read_csv`:
```python
# Handle German decimal format (comma as decimal separator)
def _convert_german(text):
    text = re.sub(r"\d{1,3}(?:\.\d{3})*,\d+", lambda m: m.group().replace(".", "").replace(",", "."), text)
    return re.sub(r"(\d+),(\d+)", r"\1.\2", text)

data_text = _convert_german(data_text)
```

Update the return metadata:
```python
"metadata": {
    "file_type_detail": "chromeleon_chromatogram",
    "data_points": len(df),
    "time_range": f"{df[cols[0]].min():.2f} - {df[cols[0]].max():.2f} min" if cols else None,
    "value_range": f"{df[cols[1]].min():.1f} - {df[cols[1]].max():.1f} mAU" if len(cols) > 1 else None,
    **header_meta,
},
```

- [ ] **Step 4: Test with an actual Chromeleon .txt file**

Verify metadata extraction matches legacy reader output. Verify German number format converts correctly.

- [ ] **Step 5: Run existing pipeline tests**

```bash
python -m pytest tests/ingestion/ -v
```

- [ ] **Step 6: Commit**

```bash
git add src/ingestion/presets/chromeleon_txt.py src/ingestion/presets/plate_reader_csv.py
git commit -m "feat: enrich chromeleon and plate_reader presets with full metadata extraction"
```

---

## Task 1: Add `source_category` to StandardizedResult

**Files:**
- Modify: `src/ingestion/types.py`
- Test: `tests/ingestion/test_types.py`

The `source_category` tells consuming code how to group files for overlay and what UI behaviour to apply, without checking format strings.

- [ ] **Step 1: Add SourceCategory enum and field**

```python
# In src/ingestion/types.py, add after PlotHint:

class SourceCategory(str, Enum):
    CHROMATOGRAM = "chromatogram"
    SPECTRUM = "spectrum"
    LCMS_MS = "lcms_ms"
    LCMS_UV = "lcms_uv"
    KINETICS = "kinetics"
    GENERIC = "generic"
```

Add to `StandardizedResult`:
```python
@dataclass
class StandardizedResult:
    data: pd.DataFrame
    column_roles: Dict[str, ColumnRole]
    identity: FileIdentity
    plot_hint: PlotHint = PlotHint.LINE
    source_category: SourceCategory = SourceCategory.GENERIC    # NEW
    sample_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # ... existing properties unchanged
```

- [ ] **Step 2: Write test**

```python
# In tests/ingestion/test_types.py, add:
def test_source_category_default():
    from src.ingestion.types import StandardizedResult, ColumnRole, FileIdentity, SourceCategory
    import pandas as pd
    sr = StandardizedResult(
        data=pd.DataFrame({"x": [1], "y": [2]}),
        column_roles={"x": ColumnRole.X, "y": ColumnRole.Y},
        identity=FileIdentity("test.csv", "csv", "heuristic", 3),
    )
    assert sr.source_category == SourceCategory.GENERIC
```

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python -m pytest tests/ingestion/test_types.py -v`

- [ ] **Step 3: Commit**

```bash
git add src/ingestion/types.py tests/ingestion/test_types.py
git commit -m "feat: add SourceCategory enum to StandardizedResult"
```

---

## Task 2: Update all presets to set `source_category`

**Files:**
- Modify: `src/ingestion/presets/chromeleon_txt.py`
- Modify: `src/ingestion/presets/plate_reader_csv.py`
- Modify: `src/ingestion/presets/cary_kinetics.py`
- Modify: `src/ingestion/presets/lcms_cdf.py`
- Modify: `src/ingestion/presets/lcms_vwd_cdf.py`
- Modify: `src/ingestion/stage_3_heuristic.py`
- Modify: `src/ingestion/pipeline.py`
- Test: `tests/ingestion/test_presets.py`

- [ ] **Step 1: Update each preset's `parse()` return dict to include `source_category`**

**chromeleon_txt.py** — add `"source_category": SourceCategory.CHROMATOGRAM` to the return dict. Add import: `from ..types import ColumnRole, PlotHint, SourceCategory`.

**plate_reader_csv.py** — add `"source_category": SourceCategory.SPECTRUM`. Add import.

**cary_kinetics.py** — add `"source_category": SourceCategory.KINETICS`. Add import.

**lcms_cdf.py** — add `"source_category": SourceCategory.LCMS_MS`. Add import.

**lcms_vwd_cdf.py** — add `"source_category": SourceCategory.LCMS_UV`. Add import.

**stage_3_heuristic.py** — the `heuristic_parse()` function should infer source_category from detected X/Y column patterns. At the bottom of `heuristic_parse()`, before the return:
```python
from .types import SourceCategory
# Infer source category from column semantics
x_sem = x_semantic  # already computed by _classify_columns
if x_sem == "time":
    cat = SourceCategory.CHROMATOGRAM
elif x_sem == "wavelength":
    cat = SourceCategory.SPECTRUM
else:
    cat = SourceCategory.GENERIC
```
Add `"source_category": cat` to the return dict.

- [ ] **Step 2: Update pipeline.py to pass source_category through**

In `IngestionPipeline.ingest()`, both the preset path and heuristic path create `StandardizedResult`. Add:
```python
source_category=raw.get("source_category", SourceCategory.GENERIC),
```
to both `StandardizedResult(...)` constructor calls.

Import `SourceCategory` at the top:
```python
from .types import StandardizedResult, FileIdentity, PlotHint, ColumnRole, SourceCategory
```

- [ ] **Step 3: Write tests**

In `tests/ingestion/test_presets.py`, add assertions on existing preset tests that `source_category` is set correctly. If there are test fixtures for each preset, add:
```python
assert result.source_category == SourceCategory.CHROMATOGRAM  # for chromeleon
assert result.source_category == SourceCategory.SPECTRUM       # for plate_reader
# etc.
```

Run: `python -m pytest tests/ingestion/ -v`

- [ ] **Step 4: Commit**

```bash
git add src/ingestion/ tests/ingestion/
git commit -m "feat: all presets and heuristic set source_category"
```

---

## Task 3: Rewrite PlotManager to be StandardizedResult-driven

**Files:**
- Modify: `src/services/plot_manager.py`
- Test: `tests/ingestion/test_plot_standardized.py`

The key change: `_add_traces_for_file()` and `get_plot_for_file()` stop branching on `file_type` strings and read from `StandardizedResult` instead.

- [ ] **Step 1: Rewrite `_add_traces_for_file()` → `_add_traces()`**

Replace the entire method (currently lines 442-501) with a format-agnostic version:

```python
def _add_traces(self, fig, name, file_data, color_offset=0):
    """Add traces from file_data to fig using StandardizedResult."""
    sr = file_data.get('standardized')
    if sr is None:
        return
    
    df = sr.data
    x_cols = sr.x_columns
    y_cols = sr.y_columns
    
    if not x_cols or not y_cols:
        return
    
    x_col = x_cols[0]
    if x_col not in df.columns:
        return
    
    x_vals = df[x_col]
    
    for j, y_col in enumerate(y_cols):
        if y_col not in df.columns:
            continue
        color = self.default_colors[(color_offset + j) % len(self.default_colors)]
        label = f"{name} — {y_col}" if len(y_cols) > 1 else name
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=pd.to_numeric(df[y_col], errors="coerce"),
            mode="lines",
            name=label,
            line=dict(color=color, width=2),
        ))
```

Update all callers of `_add_traces_for_file` to use `_add_traces`.

- [ ] **Step 2: Simplify `get_plot_for_file()`**

Replace the current method (lines 615-648) — remove the legacy fallback branch entirely:

```python
def get_plot_for_file(self, file_data: Dict[str, Any]) -> go.Figure:
    """Get plot for a file. StandardizedResult is the only path."""
    try:
        sr = file_data.get('standardized')
        if sr is not None:
            return self.create_standardized_plot(sr)
        return self._create_error_plot("No standardized data available")
    except Exception as e:
        return self._create_error_plot(f"Plot error: {str(e)}")
```

- [ ] **Step 3: Delete the now-unused format-specific plot methods**

Remove these methods from PlotManager (they are no longer called):
- `create_chromatogram_plot()` (lines 19-86)
- `create_uvvis_plot()` (lines 88-182) — BUT check if `handle_file_selection()` calls it directly. If so, that call moves to Task 6.
- `create_lcms_tic_plot()` (lines ~184-280)
- `create_lcms_uv_plot()` (lines ~282-370)
- `create_generic_table_plot()` (lines ~372-398)

**IMPORTANT:** Before deleting, grep for each method name across the entire codebase. If called outside plot_manager (e.g., `viz_callbacks.py` calls `plot_manager.create_uvvis_plot()` directly in `handle_file_selection`), those calls need to be replaced with `plot_manager.get_plot_for_file(file_data)` first (Task 6).

Keep: `create_standardized_plot()`, `create_multi_file_plot()`, `create_empty_plot()`, `create_hidden_state_plot()`, `_create_error_plot()`, `_create_overlay_plot()`, `_create_stacked_plot()`.

- [ ] **Step 4: Update `create_multi_file_plot()` to use `_add_traces()`**

Both `_create_overlay_plot()` and `_create_stacked_plot()` call `_add_traces_for_file()`. Update them to call `_add_traces()`.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/ingestion/test_plot_standardized.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/services/plot_manager.py tests/ingestion/test_plot_standardized.py
git commit -m "refactor: PlotManager uses StandardizedResult exclusively, remove format-specific plot methods"
```

---

## Task 4: Simplify StorageManager.load_file_data()

**Files:**
- Modify: `src/services/storage_manager.py`

The dual-path loading (pipeline + reader + fallback) becomes: pipeline only.

- [ ] **Step 1: Rewrite `load_file_data()` (lines 401-529)**

The new flow:
1. Write temp file, call `ingest_file()`
2. If `StandardizedResult` is None → error
3. Extract data and metadata from `StandardizedResult`
4. Handle LCMS bundling (check `sr.source_category`)
5. Store entry with `standardized` field

```python
def load_file_data(self, file_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        content_bytes = _decode_content(file_record['encoded'])
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_record['name']}")
        temp_file.write(content_bytes)
        temp_file.close()
        self.temp_files.append(temp_file.name)

        sr = ingest_file(temp_file.name, file_record['name'])
        if sr is None:
            log.error(f"Pipeline could not parse {file_record['name']}")
            return None

        self.register_file_id(file_record['id'], file_record['name'])
        file_id = file_record['id']

        data = sr.data
        metadata = dict(sr.metadata)
        metadata['file_name'] = file_record['name']
        if sr.sample_name:
            metadata['sample_name'] = sr.sample_name
        if sr.x_columns:
            metadata['auto_x'] = sr.x_columns[0]
        if sr.y_columns:
            metadata['auto_y'] = sr.y_columns

        from src.ingestion.types import SourceCategory

        # LCMS bundling
        if sr.source_category in (SourceCategory.LCMS_MS, SourceCategory.LCMS_UV):
            base_name = self.extract_lcms_base_name(file_record['name'])
            self._init_lcms_bundle(base_name)
            bundle = self.lcms_bundles[base_name]
            if file_id not in bundle['files']:
                bundle['files'].append(file_id)

            entry = {
                'id': file_id,
                'record': file_record,
                'data': data,
                'metadata': metadata,
                'standardized': sr,
            }

            # Slot into bundle
            if sr.source_category == SourceCategory.LCMS_MS:
                mode = metadata.get('ionization_mode', 'unknown')
                key = 'ms_positive' if mode == 'positive' else 'ms_negative' if mode == 'negative' else None
            else:
                channel = metadata.get('detector_channel', 'Unknown')
                key = 'vwd_a' if channel == 'A' else 'vwd_b' if channel == 'B' else None

            if key:
                bundle[key] = entry

            self.loaded_data[file_id] = entry
            self._update_lcms_bundle_metadata(base_name)
            log.debug(f"Loaded {file_record['name']} as {sr.identity.detected_format} (LCMS bundle {base_name})")
            return entry

        # Standard (non-LCMS) storage
        entry = {
            'record': file_record,
            'data': data,
            'metadata': metadata,
            'standardized': sr,
        }
        self.loaded_data[file_id] = entry
        log.debug(f"Loaded {file_record['name']} as {sr.identity.detected_format}")
        return entry

    except Exception as e:
        log.error(f"Error loading {file_record['name']}: {str(e)}")
        return None
```

- [ ] **Step 2: Delete dead methods**

Remove from `DataManager`:
- `_file_type_from_pipeline()` (lines 541-561)
- `detect_file_type()` (lines 581-619)
- `_PIPELINE_TO_READER` dict (lines 534-539)

Remove the `self.readers` dict from `__init__()` (lines 181-187).

Remove reader imports at the top of file (lines 3-7):
```python
# DELETE these lines:
from services.readers.chromatogram_reader import ChromatogramReader
from services.readers.uvvis_csv_reader import UVVISCSVReader
from services.readers.generic_csv_reader import GenericCSVReader
from services.readers.lcms_cdf_reader import LCMSCDFReader
from services.readers.lcms_vwd_cdf_reader import LCMSVWDCDFReader
```

- [ ] **Step 3: Delete top-level helper functions that used file_type**

Remove or simplify:
- `guess_file_type()` (lines 44-61) — only keep if file tree icons still need it before loading
- `_build_preview()` (lines 64-71) — simplify, no file_type branching needed (just try decode as text)

```python
def _build_preview(content: bytes) -> str:
    try:
        text = content.decode("utf-8", errors="replace")
        return text[:200] + ("..." if len(text) > 200 else "")
    except Exception:
        return "Binary content"
```

- [ ] **Step 4: Update `create_file_records()` to not rely on `guess_file_type()`**

The initial file record created during upload (before `load_file_data()` runs) currently sets a `'type'` field via `guess_file_type()`. This is used by the file tree for icons. Keep a minimal version for icons only, or set type to `'pending'` and update after pipeline runs.

Decision: keep `guess_file_type()` but rename to `_guess_icon_category()` to make clear it's cosmetic:

```python
def _guess_icon_category(filename: str) -> str:
    """Rough categorization for file tree icons. Not used for data routing."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext in {"cdf", "cdfx"}:
        return "lcms"
    if ext in {"png", "jpg", "jpeg", "svg"}:
        return "image"
    return "data"
```

- [ ] **Step 5: Verify the plate reader (UV-Vis) wells metadata**

The plate_reader_csv preset currently doesn't set `filled_wells` in metadata — that was done by the UVVISCSVReader. Check if `filled_wells` is needed by file_tree_callbacks for well children.

If needed, add to `plate_reader_csv.py`'s `parse()` return:
```python
# In the metadata dict:
"filled_wells": [c for c in df.columns if c != "Wavelength" and not c.startswith("_")]
```

This is critical for the file tree to show wells as children.

- [ ] **Step 6: Commit**

```bash
git add src/services/storage_manager.py src/ingestion/presets/plate_reader_csv.py
git commit -m "refactor: StorageManager uses pipeline exclusively, remove legacy reader path"
```

---

## Task 5: Rewrite viz_callbacks helpers

**Files:**
- Modify: `src/callbacks/viz_callbacks.py`

Replace all `file_type` branching in the helper functions with StandardizedResult-driven logic.

- [ ] **Step 1: Rewrite `_get_source_category()`**

Replace the current implementation (lines 93-111) with:

```python
def _get_source_category(metadata, fdata):
    """Return the source category from StandardizedResult."""
    sr = fdata.get('standardized')
    if sr is not None:
        return sr.source_category.value
    # LCMS bundles don't have their own SR
    if fdata.get('type') == 'lcms_bundle':
        bundle_data = fdata.get('bundle_data') or {}
        if bundle_data.get('ms_positive') or bundle_data.get('ms_negative'):
            return 'lcms_ms'
        return 'lcms_uv'
    return 'generic'
```

- [ ] **Step 2: Rewrite `_get_x_axis_name()`**

Replace the current implementation (lines 114-133) with:

```python
def _get_x_axis_name(metadata, fdata):
    """Return the X-axis column name from StandardizedResult."""
    sr = fdata.get('standardized')
    if sr is not None and sr.x_columns:
        return sr.x_columns[0]
    if metadata.get('auto_x'):
        return metadata['auto_x']
    data = fdata.get('data')
    if data is not None and hasattr(data, 'columns') and len(data.columns) > 0:
        return data.columns[0]
    return 'unknown'
```

- [ ] **Step 3: Rewrite `prepare_table_data()`**

Replace the current implementation (lines 30-85) with format-agnostic logic:

```python
def prepare_table_data(file_data, file_id=None, visible_wells=None):
    if file_data is None or file_data.get('data') is None:
        return None

    sr = file_data.get('standardized')
    data = file_data['data']

    # Multi-Y with well selection (e.g., plate reader)
    if visible_wells is not None and sr is not None and sr.x_columns:
        x_col = sr.x_columns[0]
        cols = [x_col] + [w for w in visible_wells if w in data.columns]
        table_data = data[cols].copy().dropna()
    elif file_id and '|' in file_id and sr is not None and sr.x_columns:
        x_col = sr.x_columns[0]
        _, item_name = file_id.split('|', 1)
        if x_col in data.columns and item_name in data.columns:
            table_data = data[[x_col, item_name]].copy().dropna()
        else:
            table_data = data.copy()
    else:
        table_data = data.copy()

    if '_row_id' not in table_data.columns:
        table_data.insert(0, '_row_id', range(len(table_data)))

    return table_data
```

- [ ] **Step 4: Update `KNOWN_RAW_TYPES` and view-mode auto-switch logic**

Replace the `KNOWN_RAW_TYPES` set (line 320-324) with a function that checks StandardizedResult:

```python
def _has_meaningful_raw_plot(file_data):
    """Return True if the file has a good raw plot (don't auto-switch to analysis)."""
    sr = file_data.get('standardized')
    if sr is None:
        return False
    return bool(sr.x_columns and sr.y_columns)
```

Then in `handle_file_selection()` around line 581, replace:
```python
# OLD:
elif file_type not in KNOWN_RAW_TYPES:
# NEW:
elif not _has_meaningful_raw_plot(file_data):
```

And in `upload_callbacks.py` line 148, make the same change.

- [ ] **Step 5: Update `_collect_visible_files()`**

The `file_type == 'uvvis_csv'` check on line 294 is for well-level visibility. Replace with:

```python
# OLD: if file_type == 'uvvis_csv':
# NEW:
from src.ingestion.types import PlotHint
sr = fdata.get('standardized')
if sr is not None and sr.plot_hint == PlotHint.MULTI_Y and sr.x_columns:
```

The well-handling logic stays the same — it's structural (multi-Y with individual visibility per Y column).

- [ ] **Step 6: Commit**

```bash
git add src/callbacks/viz_callbacks.py src/callbacks/upload_callbacks.py
git commit -m "refactor: viz_callbacks uses StandardizedResult, no file_type branching"
```

---

## Task 6: Rewrite `handle_file_selection()` plotting section

**Files:**
- Modify: `src/callbacks/viz_callbacks.py` (lines 476-606)

The big branching block in `handle_file_selection()` that decides how to create the plot based on file_type.

- [ ] **Step 1: Replace the plotting section (lines 476-540)**

Currently branches on `file_type` for uvvis_csv, lcms_cdf, lcms_bundle, etc. Replace with:

```python
# Create the plot
sr = file_data.get('standardized')
from src.ingestion.types import PlotHint, SourceCategory

visible_wells = None

if sr is not None and sr.plot_hint == PlotHint.MULTI_Y and sr.x_columns:
    # Multi-Y file (plate reader, multi-well) — respect well visibility
    filled_wells = file_data.get('metadata', {}).get('filled_wells', sr.y_columns)
    visible_wells = []
    for well in filled_wells:
        well_id = f"{file_id}|{well}"
        is_visible = True
        if hasattr(data_manager, 'visibility_state'):
            is_visible = data_manager.visibility_state.get(well_id, True)
        if is_visible:
            visible_wells.append(well)

    if visible_wells:
        # Create a filtered StandardizedResult with only visible wells
        filtered_data = sr.data[[sr.x_columns[0]] + [w for w in visible_wells if w in sr.data.columns]].copy()
        figure = plot_manager.create_standardized_plot(
            type(sr)(
                data=filtered_data,
                column_roles={c: r for c, r in sr.column_roles.items() if c in filtered_data.columns},
                identity=sr.identity,
                plot_hint=sr.plot_hint,
                source_category=sr.source_category,
                sample_name=sr.sample_name,
                metadata=sr.metadata,
            )
        )
    else:
        figure = plot_manager.create_empty_plot("All wells hidden")

elif sr is not None and sr.source_category in (SourceCategory.LCMS_MS, SourceCategory.LCMS_UV):
    # LCMS component or bundle — route to correct component
    bundle = data_manager.get_bundle_by_id(file_id)
    if not bundle and '|' in file_id:
        parent_id = file_id.split('|', 1)[0]
        bundle = data_manager.get_bundle_by_id(parent_id)

    if bundle:
        lcms_bundle = (
            data_manager.get_lcms_bundle_by_id(file_id)
            or data_manager.lcms_bundles.get(bundle.base_name if bundle else file_id)
        )
        preferred = None
        if lcms_bundle:
            preferred = lcms_bundle.get('ms_positive') or lcms_bundle.get('ms_negative') or lcms_bundle.get('vwd_a') or lcms_bundle.get('vwd_b')
        if preferred and preferred.get('standardized'):
            figure = plot_manager.create_standardized_plot(preferred['standardized'])
        else:
            figure = plot_manager.get_plot_for_file(file_data)
    else:
        figure = plot_manager.get_plot_for_file(file_data)
else:
    figure = plot_manager.get_plot_for_file(file_data)
```

- [ ] **Step 2: Update table_data preparation call**

Replace line 543:
```python
# OLD:
table_data = prepare_table_data(file_data, file_id=file_id, visible_wells=visible_wells if file_type == 'uvvis_csv' else None)
# NEW:
table_data = prepare_table_data(file_data, file_id=file_id, visible_wells=visible_wells)
```

- [ ] **Step 3: Remove the `file_type` variable assignment**

Remove lines 477-478:
```python
# DELETE:
metadata = file_data.get('metadata', {})
file_type = metadata.get('file_type') or file_data.get('type')
```

The `metadata` variable is still needed for other uses — keep it but remove `file_type`.

- [ ] **Step 4: Update view-mode auto-switch (lines 576-597)**

Already addressed in Task 5 Step 4. Verify the `_has_meaningful_raw_plot()` function is used here instead of `file_type not in KNOWN_RAW_TYPES`.

- [ ] **Step 5: Manual test**

Start the app (`python app.py`) and test:
1. Upload a Chromeleon .txt file → plots correctly
2. Upload a plate reader .csv → wells show in tree, toggle visibility works
3. Upload LCMS .cdf files → bundle groups, component switching works
4. Upload a generic CSV → auto-detects axes, plots
5. Switch between files → no zoom reset (or at least same behaviour as before)

- [ ] **Step 6: Commit**

```bash
git add src/callbacks/viz_callbacks.py
git commit -m "refactor: handle_file_selection plots from StandardizedResult"
```

---

## Task 7: Update file_tree_callbacks

**Files:**
- Modify: `src/callbacks/file_tree_callbacks.py`

Three locations check `file_type == 'uvvis_csv'` to decide if a file has wells. Replace with structural check.

- [ ] **Step 1: Create a helper function**

Add at the top of the file:

```python
def _is_multi_well(file_data):
    """Check if file has individually-selectable Y columns (wells/channels)."""
    if file_data is None:
        return False
    sr = file_data.get('standardized')
    if sr is not None:
        from src.ingestion.types import PlotHint
        return sr.plot_hint == PlotHint.MULTI_Y
    metadata = file_data.get('metadata', {})
    return bool(metadata.get('filled_wells'))
```

- [ ] **Step 2: Replace all `file_type == 'uvvis_csv'` checks**

Line 133:
```python
# OLD: if parent_file_data and parent_file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
# NEW: if _is_multi_well(parent_file_data):
```

Line 368:
```python
# OLD: if file_data and file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
# NEW: if _is_multi_well(file_data):
```

Line 533:
```python
# OLD: if file_data and file_data.get('metadata', {}).get('file_type') == 'uvvis_csv':
# NEW: if _is_multi_well(file_data):
```

- [ ] **Step 3: Commit**

```bash
git add src/callbacks/file_tree_callbacks.py
git commit -m "refactor: file_tree uses structural check instead of file_type string"
```

---

## Task 8: Update upload_callbacks

**Files:**
- Modify: `src/callbacks/upload_callbacks.py`

- [ ] **Step 1: Update KNOWN_RAW_TYPES usage (line 148)**

Replace the `ft not in KNOWN_RAW_TYPES` check with the `_has_meaningful_raw_plot()` function from viz_callbacks:

```python
# Import at top:
from callbacks.viz_callbacks import _has_meaningful_raw_plot

# Replace lines 145-163:
if file_data and auto_active_file and auto_active_file != dash.no_update:
    if _has_meaningful_raw_plot(file_data):
        auto_view_mode = 'raw'
    else:
        auto_view_mode = 'analysis'
```

Remove the `KNOWN_RAW_TYPES` set definition (lines 17-21) if it's only used here.

- [ ] **Step 2: Update icon mapping**

The `TYPE_ICONS` dict (lines 380-397) maps `file_type` strings to icons. After the refactor, `item.get('type')` from file records will still have the rough category from `_guess_icon_category()`. Update the dict:

```python
TYPE_ICONS = {
    'data': '📊',
    'lcms': '🧪',
    'image': '🖼️',
    'pending': '⏳',
}
```

Or keep the old mapping as a cosmetic layer — it doesn't affect data routing, just icons. The existing dict is fine if `guess_file_type()` still sets the initial type on file records.

**Decision:** Keep the existing icon dict and `guess_file_type()` for now — it's cosmetic and doesn't violate the architecture. The important thing is that no **data routing** uses these strings.

- [ ] **Step 3: Commit**

```bash
git add src/callbacks/upload_callbacks.py
git commit -m "refactor: upload_callbacks uses StandardizedResult for view-mode detection"
```

---

## Task 9: Clean up dead code and archive

**Files:**
- Modify: `src/services/storage_manager.py` (remove dead methods)
- Modify: `src/callbacks/viz_callbacks.py` (remove KNOWN_RAW_TYPES, dead file_type refs)

- [ ] **Step 1: Final grep for `file_type` branching**

```bash
grep -rn "file_type\|\.get('type')\|get_type\|KNOWN_RAW" src/callbacks/ src/services/ --include="*.py" | grep -v "icon\|TYPE_ICON\|__pycache__\|file_type_detail\|#.*file_type"
```

Every remaining hit should be either:
- Cosmetic (icons)
- In a `log.debug()` statement
- In metadata display
- Already addressed

Fix any remaining branching logic found.

- [ ] **Step 2: Remove `KNOWN_RAW_TYPES` from viz_callbacks**

If it's still defined, delete it — replaced by `_has_meaningful_raw_plot()`.

- [ ] **Step 3: Remove `'type'` from loaded_data entries**

In `load_file_data()` (after Task 4), the entry dict should NOT have a top-level `'type'` key. Check that no code reads `fdata.get('type')` for routing purposes. Remaining reads should get `sr.source_category` or `sr.identity.detected_format` instead.

Grep and fix:
```bash
grep -rn "fdata.get('type')\|file_data.get('type')" src/ --include="*.py"
```

- [ ] **Step 4: Remove `'reader'` from loaded_data entries**

No code should reference `file_data.get('reader')` anymore. Grep and verify:
```bash
grep -rn "\.get('reader')\|'reader'" src/ --include="*.py"
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 6: Start the app and do a full manual test**

```bash
cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python app.py
```

Test each file type:
1. Chromeleon .txt → plots, metadata displays, peaks work
2. Plate reader .csv → wells in tree, visibility toggles, well deletion
3. Cary kinetics .csv → plots with sample name
4. LCMS .cdf → bundle grouping, component switching
5. Generic CSV → auto-detects axes, plots or switches to analysis mode
6. File switching → overlay works, peak display works
7. Publication plot → data selector works with new table_data format

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "cleanup: remove all legacy file_type routing, pipeline is sole data path"
```

---

## Summary of what gets deleted

| What | Where | Why safe to remove |
|------|-------|-------------------|
| `_file_type_from_pipeline()` | storage_manager.py:541-561 | Pipeline detection feeds source_category directly |
| `detect_file_type()` | storage_manager.py:581-619 | Pipeline's stage 1-3 replaces this |
| `_PIPELINE_TO_READER` dict | storage_manager.py:534-539 | No legacy reader mapping needed |
| `self.readers` dict | storage_manager.py:181-187 | Readers called by presets, not by StorageManager |
| Reader imports | storage_manager.py:3-7 | Same as above |
| `KNOWN_RAW_TYPES` | viz_callbacks.py:320-324 | Replaced by `_has_meaningful_raw_plot()` |
| Format-specific plot methods | plot_manager.py | Replaced by `create_standardized_plot()` |
| `_add_traces_for_file()` | plot_manager.py:442-501 | Replaced by `_add_traces()` |
| All `file_type` branching | viz_callbacks, plot_manager | Replaced by StandardizedResult fields |

## What stays

| What | Why |
|------|-----|
| Legacy readers (`src/services/readers/`) | Called internally by LCMS presets |
| `guess_file_type()` (renamed) | File tree icons before loading |
| LCMS bundle system | Multi-file grouping is structural, not format-dependent |
| `filled_wells` metadata | Structural (which Y columns are active), now set by preset |
| `'type'` on file_record | Cosmetic for initial tree display |
