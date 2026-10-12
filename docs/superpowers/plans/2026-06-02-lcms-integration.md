# LCMS Peak Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable peak detection and manual baseline (p-line) integration on LCMS TIC and EIC traces, reusing the existing HPLC integration pipeline with zero new algorithms.

**Architecture:** The HPLC integration pipeline (signal processing, peak detection, manual baseline, peak rendering, peak table) is already source-agnostic — it operates on any `(time, intensity)` array. The only real blocker is `_file_id_for_subplot_row()` which incorrectly maps LCMS subplot rows back to the bundle_id instead of the component_id. Fixing this one function unblocks manual p-line integration on all subplots. Everything else (detect peaks, peak table, peak overlays) already works.

**Tech Stack:** Dash, Plotly, scipy, numpy, existing integration_service + peak_service

---

## Context: What Already Works

These components are **already compatible** with LCMS data — no changes needed:

- `get_xy_arrays()` — extracts `(time, intensity)` from any file with `auto_x`/`auto_y` metadata; LCMS components have this set via `ColumnRole.X`/`ColumnRole.Y` from the ingestion pipeline
- `IntegrationService.process_signal()` — accepts any float arrays
- `PeakService.detect_peaks()` — works on any corrected signal
- `add_peak_traces()` / `peak_overlay.py` — renders peaks for any file_id, no source filtering
- `detect_peaks` callback — uses `active_file` directly, which is the component_id when user selects +TIC/-TIC in file tree
- Trace metadata in stacked plots — `meta={'file_id': component_id}` is set for all trace types

## The Bug

`_file_id_for_subplot_row()` in `baseline_callbacks.py:262-304` maps subplot rows back to file IDs for manual integration. After finding the correct `(name, fdata)` tuple from the flat visible-files list, it tries to return the **bundle_id** (lines 294-298). This means:

- Drawing a p-line on the -TIC subplot → peaks stored under bundle_id → `get_xy_arrays(bundle_id)` resolves to the bundle's primary file (+TIC) → peak area calculated against wrong trace
- Drawing a p-line on UV subplot → same problem, peaks stored under bundle_id, computed against +TIC data

The fix: return the **component_id** from the `fdata` record, not the parent bundle_id. For LCMS bundles with multiple subplot rows, each component must store peaks independently.

---

### Task 1: Fix `_file_id_for_subplot_row` to return component IDs

**Files:**
- Modify: `src/callbacks/baseline_callbacks.py:262-304`

- [ ] **Step 1: Read the current implementation**

The function at line 262-304 builds a flat list from `_collect_visible_files()`, indexes into it by row number, then tries to map back to a bundle_id. The bundle_id mapping was correct for HPLC Chromeleon bundles (one primary chromatogram per bundle) but wrong for LCMS bundles (multiple chromatogram components per bundle).

- [ ] **Step 2: Fix the file_id resolution logic**

Replace the bundle-id lookup (lines 290-304) with logic that returns the component_id from the fdata record, falling back to bundle_id only for single-chromatogram bundles:

```python
    def _file_id_for_subplot_row(row, active_file, plot_settings, loaded_files, plot_tabs, active_tab_id):
        """Map a subplot row number to the file_id whose data occupies that row.

        Returns the component_id for multi-component bundles (LCMS) so peaks
        are stored per-component, or the bundle_id for single-chromatogram
        bundles (Chromeleon HPLC) to match the file selector convention.
        """
        from callbacks.viz_callbacks import _collect_visible_files
        from services.plot_settings_service import DEFAULT_PLOT_SETTINGS

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        if s.get('layout_mode') != 'stacked':
            return active_file

        tab = None
        for t in (plot_tabs or []):
            if t['id'] == active_tab_id:
                tab = t
                break
        if not tab:
            return active_file

        group_key = tuple(tab.get('group_key', []))
        visible = _collect_visible_files(data_manager, active_file, loaded_files, target_group_override=group_key)
        flat = []
        for files in visible.values():
            flat.extend(files)
        if row < 1 or row > len(flat):
            return active_file
        _, fdata = flat[row - 1]

        rec_id = fdata.get('record', {}).get('id', '')

        # For LCMS bundles: each component occupies its own subplot row,
        # so return the component_id to store peaks per-component.
        bundle = data_manager.get_bundle_for_component(rec_id) if hasattr(data_manager, 'get_bundle_for_component') else None
        if bundle:
            from services.data_store import BundleType
            if bundle.bundle_type == BundleType.LCMS:
                return rec_id

        # For other bundles (Chromeleon HPLC): return bundle_id to match
        # the file selector convention (one primary chromatogram per bundle).
        for b in data_manager.bundle_manager.bundles.values():
            if b.main_file and b.main_file.get('id') == rec_id:
                return b.bundle_id
            if data_manager.loaded_data.get(b.bundle_id) is fdata:
                return b.bundle_id

        # Fallback: use the loaded_data key
        for fid, fd in data_manager.loaded_data.items():
            if fd is fdata:
                return fid
        return rec_id or active_file
```

- [ ] **Step 3: Verify import and restart**

Run: `cd /Users/glenn/_CODE/GeckoPlotter_DASH/GeckoPlotter_V2 && python3 -c "import app; print('OK')"`

- [ ] **Step 4: Test manually**

1. Load an LCMS bundle with +TIC, -TIC, and UV components
2. Switch to stacked layout mode
3. Go to Integration toolbox, enable draw mode (Shift+click)
4. Draw a p-line on the **-TIC** subplot (not the first row)
5. Verify peak appears on -TIC subplot, not +TIC
6. Draw a p-line on the **UV** subplot
7. Verify peak appears on UV subplot
8. Check peak table shows correct RT/area values

- [ ] **Step 5: Commit**

```bash
git add src/callbacks/baseline_callbacks.py
git commit -m "fix: return component_id for LCMS subplots in p-line integration"
```

---

### Task 2: Fix peak click selection for LCMS subplot components

**Files:**
- Modify: `src/callbacks/baseline_callbacks.py` — `select_peak_by_click()` callback

**Context:** When clicking on a peak polygon in a non-first LCMS subplot, the callback needs to resolve the correct component_id. The peak overlay traces have `meta={'file_id': component_id}` set by the plot manager, so the click data should already contain the right file_id. But the callback also updates `active-file` — verify it sets the component_id, not the bundle_id.

- [ ] **Step 1: Read `select_peak_by_click()`**

Find the callback that listens to `main-plot.clickData` and updates `selected-peak-idx`. Check if it reads `file_id` from the click trace metadata.

- [ ] **Step 2: Verify the peak click path**

The peak overlay traces (from `peak_overlay.py`) store `meta` containing `peak_id` in `customdata`. The click handler reads `customdata[0]` as peak_id and looks it up via `peak_service.get_peak_by_id()`. This should work regardless of LCMS vs HPLC — the peak_id is the lookup key, not the file_id.

If the click handler also updates `active-file`, ensure it uses the peak's `file_id` attribute (which should be the component_id after Task 1).

- [ ] **Step 3: Test manually**

1. After Task 1, draw peaks on multiple LCMS subplots
2. Click on each peak polygon — verify it highlights correctly
3. Verify the peak table updates to show the clicked peak's data
4. Verify the file tree selection follows (if applicable)

- [ ] **Step 4: Commit if changes were needed**

```bash
git add src/callbacks/baseline_callbacks.py
git commit -m "fix: peak click selection works across LCMS subplots"
```

---

### Task 3: Ensure "Detect Peaks" works per LCMS component

**Files:**
- Modify: `src/callbacks/integration_callbacks.py` (if needed)

**Context:** The "Detect Peaks" button uses `active_file` directly. When the user selects +TIC in the file tree, `active_file` is the component_id. `get_xy_arrays(component_id)` returns the TIC time/intensity arrays. Peak detection runs on those arrays and stores peaks under `component_id`. This should already work.

- [ ] **Step 1: Test detect peaks on LCMS components**

1. Select +TIC in the file tree
2. Click "Detect Peaks" in the Integration toolbox
3. Verify peaks are detected and rendered on the +TIC subplot
4. Select -TIC in the file tree
5. Click "Detect Peaks"
6. Verify peaks are detected on -TIC subplot independently
7. Select UV channel
8. Click "Detect Peaks"
9. Verify peaks on UV subplot

- [ ] **Step 2: Fix if needed**

If detect peaks doesn't work for a specific component, the issue is likely in `get_xy_arrays()` not finding the data. Check:
- Does `data_manager.get_data_by_id(component_id)` return the component data?
- Does the returned data have a DataFrame with the expected columns?
- Are `auto_x` and `auto_y` set in the metadata?

- [ ] **Step 3: Commit if changes were needed**

```bash
git add src/callbacks/integration_callbacks.py
git commit -m "feat: detect peaks works on LCMS TIC/EIC/UV components"
```

---

### Task 4: Ensure peak table shows component-specific peaks

**Files:**
- Modify: `src/callbacks/tab_callbacks.py` (if needed)

**Context:** The peak table callback reads peaks via `peak_service.peaks_to_table(active_file)`. When `active_file` is a component_id, it should return only peaks for that component. Verify this works.

- [ ] **Step 1: Test peak table with LCMS components**

1. After detecting/drawing peaks on multiple LCMS subplots
2. Select +TIC — verify table shows only +TIC peaks
3. Select -TIC — verify table shows only -TIC peaks
4. Select UV — verify table shows only UV peaks

- [ ] **Step 2: Fix if needed**

The peak service stores peaks by file_id. If `active_file` is a component_id (after Task 1 fix), `peaks_to_table(component_id)` should return only that component's peaks. If the table shows all peaks across components, the issue is in how `active_file` is resolved for the table callback.

- [ ] **Step 3: Commit if changes were needed**

```bash
git add src/callbacks/tab_callbacks.py
git commit -m "fix: peak table filters by LCMS component"
```

---

### Task 5: Handle EIC "Open as new plot" peaks

**Files:**
- No changes expected — verify only

**Context:** When an EIC is opened as a new plot (right-click → "Open as new plot"), it becomes a standalone generic bundle with its own component_id. Integration should work on it automatically since it's a regular chromatogram-shaped file.

- [ ] **Step 1: Test EIC integration after opening as new plot**

1. Extract an EIC (e.g., m/z 294)
2. Right-click → "Open as new plot"
3. The EIC appears as a new file in the file explorer
4. Select it, click "Detect Peaks" — peaks should be detected
5. Draw a manual p-line — should work
6. Verify peak table shows correct values

- [ ] **Step 2: Commit if changes were needed**

---

### Task 6: Cross-sample peak grouping for LCMS components

**Files:**
- Modify: `src/services/peak_service.py` — `group_peaks_across_samples()` (if needed)

**Context:** The cross-sample grouping uses `file_overlay_map` to determine which files are in the same overlay group. For LCMS, components like +TIC across different LCMS bundles should group together. Verify this works.

- [ ] **Step 1: Test with multiple LCMS files**

If you have multiple LCMS bundles loaded:
1. Detect peaks on +TIC of bundle A
2. Detect peaks on +TIC of bundle B
3. Check "Across Samples" tab — peaks at similar RTs should be grouped
4. Verify colors are consistent across samples

- [ ] **Step 2: Commit if changes were needed**

```bash
git add src/services/peak_service.py
git commit -m "fix: cross-sample grouping works for LCMS components"
```
