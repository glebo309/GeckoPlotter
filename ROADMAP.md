# GeckoPlotter V2 — Roadmap

_Updated 2026-05-27_

This is the single source of truth for what's done, what's next, and what's planned.
Start every new session by reading this file.

## Current State

### What Works (as of 2026-05-27)
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

### In-Progress (2026-05-27, separate branch — merge pending)
- **Format-agnostic integration**: `get_chromatogram_arrays` → `get_xy_arrays` using `metadata['auto_x']`/`metadata['auto_y']` from pipeline. Integration now works on any X/Y data (spectra, kinetics, generic CSV), not just chromatograms.
- **Bundle cleanup**: bundles are UI-only; `active-file` is always a real file UUID, no more synthetic `loaded_data[bundle_id]` entries. `resolve_peak_file_id` removed.

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

## Backlog — User Priorities (confirmed 2026-05-27)

### 1. Right-click context menu
- On peak: Delete peak, "Select in All Chromatograms" (auto-integrate matching peak across files)
- On plot background: zoom to region, add baseline point, export region
- On file tree: Move to group, Plot separately, rename
- Implementation: `dash-mantine-components` Menu + clientside callback intercepting `contextmenu` events, `preventDefault()`, positioned absolutely
- Priority: **HIGH** (UX multiplier — unlocks many interactions)

### 2. Peak deconvolution (EMG via lmfit)
- Resolve co-eluting/overlapping peaks using Exponentially Modified Gaussian fitting
- Library: `lmfit` (v1.3.4, installed) with `ExponentialGaussianModel`
- Algorithm: user clicks approximate peak centers → lmfit fits composite EMG model → individual peak areas calculated
- EMG is the only model needed (handles both symmetric and tailing peaks — gamma→0 = Gaussian)
- UX: "Deconvolve" mode button in toolbox (like Draw/Navigate), click to place peak markers, hit Deconvolve
- Sandbox prototype: `../deconvolution_sandbox/app.py` (port 8060) — tested, R²>0.999 on synthetic data
- Fitting engine is ~40 lines, pure numpy/lmfit, ready to drop into a `DeconvolutionService`
- Priority: **HIGH** (major differentiator, solves the #1 chromatography pain point)

### 3. Calibration UI
- CalibrationService already exists (`services/calibration_service.py`) with data model
- Previous Streamlit version had working calibration (linear, polynomial, cubic)
- Rebuild with: multi-point table, weighted regression (1/x, 1/x²), force-through-origin, residual plot
- Add LOD/LOQ calculation (ICH Q2: LOD = 3.3·Sy/slope, LOQ = 10·Sy/slope)
- Add ISTD mode (divide analyte area by IS area before regression)
- Priority: **HIGH** (enables quantitative analysis)

### 4. Undo/redo
- Track peak additions, deletions, baseline changes, deconvolution actions
- Essential for interactive analysis — exploring different integration strategies
- Priority: **HIGH**

### 5. Color system cleanup
- Colors are inconsistent and change when files are added
- Legend shows multiple entries that shouldn't be there
- Fix: stable color assignment per file/trace, not re-indexed on every render
- Priority: **HIGH** (visual quality)

### 6. Chromeleon imported peaks
- Convert imported peaks to same format as manual peaks
- User can "adopt" Chromeleon peaks → they become editable GeckoPlotter peaks
- Priority: **HIGH** (data continuity)

### 7. Keyboard shortcuts
- Backspace/Delete: delete selected peak
- Arrow keys: navigate plot (pan/zoom or cycle through peaks)
- Priority: **MEDIUM**

### 8. Subfolders / grouping for same-type data
- Problem: two sets of kinetics data (different substrates) → both go to same tab
- Need: sub-groups within a tab, or ability to split into separate tabs
- Priority: **MEDIUM**

### 9. Legend control
- Movable legend, persistent position, no phantom entries
- Priority: **MEDIUM**

### 10. Subplot file ordering
- Drag-and-drop reordering in file selector → subplot order
- Integration must work on ALL subplots
- Priority: **MEDIUM**

### 11. Tab rename
- User can rename tab labels (currently auto-generated)
- Priority: **LOW**

### 12. Drag-and-drop between groups
- Drag file from one group to another
- Priority: **LOW**

---

## Explicitly Not Planned

- System Suitability Testing (plates, tailing factor, resolution) — not needed for this use case
- Peak purity assessment — requires DAD/PDA data, not relevant

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

### Format-Agnostic Integration ✓ (2026-05-27, merge pending)
- `get_xy_arrays` replaces `get_chromatogram_arrays` — uses pipeline metadata
- Bundle IDs removed from `loaded_data` — active-file is always a real UUID
- `resolve_peak_file_id` eliminated
