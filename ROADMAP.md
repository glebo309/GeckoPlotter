# GeckoPlotter V2 — Roadmap

_Updated 2026-05-24_

This is the single source of truth for what's done, what's next, and what's planned.
Start every new session by reading this file.

## Current State

### What Works (as of 2026-05-24)
- **Ingestion pipeline**: format-agnostic, preset-based detection, StandardizedResult output
- **Multi-tab plot workspace**: each data type auto-creates its own tab on upload
- **Unified context**: tab = group = full context (file selector, bottom panel, zoom all follow)
- **Bidirectional sync**: clicking file → switches tab; switching tab → restores last file
- **Per-tab memory**: file selection, bottom panel, zoom state all persist per tab
- **File selector grouping**: files grouped by data type with active group highlighting
- **Upload auto-switch**: newly uploaded file auto-selects and its tab activates
- **Chromeleon bundles**: auto-detected, auxiliary files hidden, bundle acts as unit
- **Peak integration**: manual peak picking, peak overlay on chromatograms
- **Plot settings**: palette, layout mode (overlay/stacked), axis labels, styling
- **Data table editor**: cell/column selection, transpose, add row/column
- **Export**: basic figure export (PNG/SVG)
- **Tests**: 70 pass, 1 skipped

### Key Architecture
- `StandardizedResult` normalizes all formats (column roles + plot hints + source category)
- `master_render` is sole owner of `main-plot` figure
- `sync_plot_tabs` creates tabs from overlay groups `(source_category, x_axis)`
- Stage 3 heuristic always returns GENERIC; only presets assign specific categories
- Per-file UI state saved/restored via `context_callbacks.py`

---

## Active Sprint: Data Selector + Plot Context

### Design Decision (confirmed 2026-05-24)
- Data Selector updates the **current tab** (no new tab on selection)
- "New Plot Tab" button creates a fresh analysis tab for a second view
- Peak Analysis / Across Samples tabs do NOT override the raw chromatogram
  - Selections in those tabs get their own "Plot in New Tab" action

### Tasks
- [ ] Make Data Selector update current raw tab's plot live (X + Y selection → immediate render)
- [ ] Handle messy/ambiguous CSV: show data table prominently, maybe message "select axes to plot"
- [ ] Add "New Plot Tab" button (creates analysis tab with independent axis selections)
- [ ] Peak Analysis / Across Samples: "Plot in New Tab" button instead of overriding chromatogram

---

## Backlog (from user feedback 2026-05-24)

### 1. Color system cleanup
- Colors are inconsistent and change when files are added
- Legend shows multiple entries that shouldn't be there (screenshot shows duplicate traces)
- Fix: stable color assignment per file/trace, not re-indexed on every render
- Priority: **HIGH** (visual quality)

### 2. Integration on spectral/any data
- Allow peak integration on any X/Y data, not just chromatograms
- Integration tools should be format-agnostic (same as vision principle)
- Priority: **HIGH** (core feature)

### 3. Subfolders / grouping for same-type data
- Problem: two sets of kinetics data (different substrates) → both go to same "Kinetics" tab
- Need: subfolders or sub-groups within a tab, or ability to split into separate tabs
- Possible approach: drag file to "New Group" area, or right-click → "Plot Separately"
- Priority: **MEDIUM**

### 4. Keyboard shortcuts
- Backspace/Delete: delete selected peak
- Arrow keys: navigate plot (pan/zoom or cycle through peaks)
- Priority: **MEDIUM**

### 5. Right-click context menu
- On peak: Delete peak, "Select in All Chromatograms" (auto-integrate matching peak across files)
- On file: Move to group, Plot separately, etc.
- Priority: **MEDIUM**

### 6. Chromeleon imported peaks
- Currently ignored / separate from manual peaks
- Need: convert imported peaks to same format as manual peaks
- User can "adopt" Chromeleon peaks → they become editable GeckoPlotter peaks
- Should behave identically to manually integrated peaks after conversion
- Priority: **HIGH** (data continuity)

### 7. Legend control
- Movable legend (drag to reposition)
- Legend position persistent across renders and tab switches
- Clean up: no phantom entries, no duplicate traces
- Priority: **MEDIUM**

### 8. Subplot file ordering
- File order in file selector determines subplot order
- Requires: drag-and-drop reordering in file selector
- Subplot positions update from file selector order
- Integration must work on ALL subplots, not just the first/main one
- File selection in tree should NOT change which subplot is active (all visible)
- Priority: **MEDIUM**

### 9. Tab rename
- User can rename tab labels (currently auto-generated from data type)
- Priority: **LOW**

### 10. Drag-and-drop between groups
- Drag file from one group to another → creates new tab or moves to existing
- Priority: **LOW**

---

## Completed (archive reference)

### Phase 0 — Cleanup and Stabilization ✓
### Phase 1 — Unified Per-File State ✓
### Ingestion Pipeline Refactor ✓ (2026-05-20 to 2026-05-23)
- Three-stage pipeline: detect → preset → heuristic fallback
- All format-specific code replaced with StandardizedResult
- Excel support added
- Sub-table extraction for messy spreadsheets

### Multi-Tab Plot Workspace ✓ (2026-05-24)
- Dynamic tab bar with auto-creation per data type
- Bidirectional file↔tab sync
- Per-tab zoom, file, and panel memory
- File selector grouped by overlay group
- Generic CSVs auto-plot (no more "Unplotted" limbo)
- Stage 3 conservative classification (GENERIC only)
- Bundle component files excluded from tab creation
- Upload auto-switches to new file's tab

---

## Future Phases (from CONTINUATION_PLAN.md)

### FAIR Data Package Integration (Phase 8)
- Project-level metadata store (authors, license, funding, DOIs)
- Per-file experimental metadata (sample ID, enzyme, substrate, conditions)
- Figure registry and provenance tracking
- One-click Zenodo-ready ZIP export with compliance checker
- See `CONTINUATION_PLAN.md` for full spec

### Service Integration (Phase 3)
- Make DataManager own all services (Peak, Integration, Calibration, etc.)
- Replace legacy persistence with persistence service
- Route all state through registry/service boundaries

### Calibration and Advanced Analysis (Phase 6)
- Calibration tab using CalibrationService
- Sample-level peak property editing
- LC-MS advanced tools
