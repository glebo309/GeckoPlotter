# GeckoPlotter V2 — Roadmap

_Updated 2026-05-30_

This is the single source of truth for what's done, what's next, and what's planned.
Start every new session by reading this file.

## Current State

### What Works (as of 2026-05-30)
- **Ingestion pipeline**: format-agnostic, preset-based detection, StandardizedResult output
- **Multi-tab plot workspace**: each data type auto-creates its own tab on upload
- **Unified context**: tab = group = full context (file selector, bottom panel, zoom all follow)
- **Bidirectional sync**: clicking file → switches tab; switching tab → restores last file
- **Per-tab memory**: file selection, bottom panel, zoom state all persist per tab
- **File selector grouping**: files grouped by data type with active group highlighting
- **Upload auto-switch**: newly uploaded file auto-selects and its tab activates
- **Chromeleon bundles**: auto-detected, auxiliary files hidden, bundle acts as unit
- **Chromeleon peak adoption**: imported peaks auto-converted to editable GeckoPlotter peaks on upload
- **Peak integration**: manual peak picking, peak overlay on any X/Y data (format-agnostic)
- **Peak deconvolution**: EMG fitting via lmfit, right-click to deconvolve
- **Right-click context menu**: on peaks (delete, rename, cross-file integrate, deconvolve)
- **Plot settings**: palette, layout mode (overlay/stacked), axis labels, styling
- **Color system**: Okabe-Ito palette, stable per-file color cycling, cross-sample group persistence
- **Data table editor**: cell/column selection, transpose, add row/column
- **Data selector / axis mapper**: select cells for X/Y/Y2 axes, "Create Plot" button for custom tabs
- **Peak Analysis / Across Samples tabs**: independent tabs, don't override chromatogram
- **File drag-and-drop reorder**: within groups, visual feedback with drop indicator
- **File group sort**: ascending/descending toggle per group
- **Auto-grouping**: files grouped by `(source_category, x_axis)` into tabs
- **Keyboard shortcuts**: Delete/Backspace/X to remove selected peak
- **Export**: basic figure export (PNG/SVG)
- **DMC UI**: all form controls modernized to Dash Mantine Components
- **Tests**: 70 pass, 1 skipped

### Key Architecture
- `StandardizedResult` normalizes all formats (column roles + plot hints + source category)
- `master_render` is sole owner of `main-plot` figure
- `sync_plot_tabs` creates tabs from overlay groups `(source_category, x_axis)`
- Stage 3 heuristic always returns GENERIC; only presets assign specific categories
- Per-file UI state saved/restored via `context_callbacks.py`
- `active-file` store always contains a real file UUID, never a bundle ID
- Bundle resolution happens at click time only

---

## Active Sprint: Quick Wins (2026-05-30) ✓

All items completed — see Completed section below.

---

## Backlog

### Calibration UI
- CalibrationService already exists (`services/calibration_service.py`) with data model
- Previous Streamlit version had working calibration (linear, polynomial, cubic)
- Rebuild with: multi-point table, weighted regression (1/x, 1/x²), force-through-origin, residual plot
- Add LOD/LOQ calculation (ICH Q2: LOD = 3.3·Sy/slope, LOQ = 10·Sy/slope)
- Add ISTD mode (divide analyte area by IS area before regression)
- Priority: **HIGH** (enables quantitative analysis, but not blocking current work)

### Legend control
- Movable legend, persistent position, no phantom entries
- Priority: **MEDIUM**

---

## Explicitly Not Planned

- System Suitability Testing (plates, tailing factor, resolution) — not needed for this use case
- Peak purity assessment — requires DAD/PDA data, not relevant
- Live Data Selector plot updates — "Create Plot" workflow is intentional and sufficient

---

## Future Phases

### Report Generation + FAIR Data Export (later)
- Jinja2 HTML template → PDF via weasyprint
- Template: sample info header, chromatogram figure, integration table, calibration plot
- Combine with FAIR Data Package (Phase 8 from CONTINUATION_PLAN.md)
- One-click Zenodo-ready ZIP with figures in paper format
- See `CONTINUATION_PLAN.md` for full FAIR spec

### Service Integration (Phase 3)
- Make DataManager own all services (Peak, Integration, Calibration, etc.)
- Replace legacy persistence with persistence service
- Route all state through registry/service boundaries

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

### Format-Agnostic Integration ✓ (2026-05-27)
- `get_xy_arrays` replaces `get_chromatogram_arrays` — uses pipeline metadata
- Bundle IDs removed from `loaded_data` — active-file is always a real UUID
- `resolve_peak_file_id` eliminated

### DMC UI Modernization ✓ (2026-05-29)
- All form controls migrated to Dash Mantine Components
- Tabs synced via bidirectional store
- Validator script for callback prop checking
- AG Grid rejected (community lacks cell selection)

### Right-Click Context Menu ✓ (2026-05-29)
- Peak context menu: delete, rename, cross-file integrate, deconvolve
- Clientside JS + DMC Menu positioning

### Peak Deconvolution ✓ (2026-05-29)
- EMG fitting via lmfit ExponentialGaussianModel
- One-click deconvolve from context menu
- Individual peak areas from composite fit

### Data Selector + Plot Context ✓ (2026-05-30)
- "Create Plot" button for custom analysis tabs
- Peak Analysis / Across Samples as independent tabs
- Messy CSV handled via data table + axis mapper
- Chromeleon peaks auto-adopted on upload

### Color System ✓ (2026-05-30)
- Okabe-Ito colorblind-friendly palette (6 colors)
- Per-file stable color cycling
- Cross-sample peak group color persistence

### Undo/Redo ✓ (2026-05-30)
- Snapshot-based undo stack on PeakService (max 50 levels)
- `save_undo()` called before every peak mutation (draw, delete, clear, deconvolve, cross-integrate)
- Ctrl+Z / Cmd+Z to undo, Ctrl+Shift+Z / Cmd+Shift+Z to redo

### Keyboard Shortcuts ✓ (2026-05-30)
- Delete/Backspace/X: remove selected peak
- Ctrl+Z / Ctrl+Shift+Z: undo/redo
- Escape: deselect peak + exit draw/edit/deconvolve mode
- Left/Right arrows: cycle through peaks by retention time
- S: toggle superposed/subplots layout

### Cross-Group Drag-and-Drop ✓ (2026-05-30)
- Drag file from one group container to another
- Orange outline highlights target group on hover
- Emits `group-move-event` → `handle_group_move` callback reassigns overlay group

### Tab Rename ✓ (2026-05-30)
- Custom tabs: contentEditable label + tab-rename-event store
- Close button on custom tabs

### File Management ✓ (2026-05-30)
- Drag-and-drop reorder within groups
- Sort toggle per group (asc/desc)
- Auto-grouping by source_category + x_axis
- Keyboard delete for peaks (Delete/Backspace/X)
