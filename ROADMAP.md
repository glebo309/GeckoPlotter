# GeckoPlotter V2 — Roadmap

_Reviewed 2026-10-12_

This is the single source of truth for what's done, what's next, and what's planned.
Start every new session by reading this file.


## Current review (2026-10-12)

The May/June notes below are historical. The current UI and source are ahead of several old unchecked items.

### Delivered since the previous review

- [x] Working calibration editor, fitted curve, JSON save/load, peak matching, and calculated concentrations in Peaks and Compare samples.
- [x] Interactive deconvolution preview with component removal, adjustable apex markers, accept/cancel, keyboard shortcuts, and retained zoom.
- [x] Individual accepted component shapes and synchronized table/plot peak removal.
- [x] Data / Integration / Figure / Export inspector organization; smoothing belongs to Data.
- [x] Consistent integration tools and a compact peak-area toolbar button.
- [x] Axis-specific reset and stable X range while selecting/deselecting peaks.
- [x] Text-edit toolbar mode for dataset names, titles, axis labels, and legend names. Dataset names synchronize with the file browser.

- [x] LabSolutions method files (.lcm/.lcd): gradient, flow, oven, devices read and attached to samples (by the export's method file name or the run's own timestamps), saved with projects, written into the FAIR package as a journal-style methods paragraph plus the original file. Overlay dropdown in the Metadata tab: LC gradient (as programmed or shifted by the 715 uL dwell volume) and every pressure/temperature status trace. Group defaults (routine column, dwell volume) in `src/services/lab_defaults.json`.

### Still open or deferred

- [ ] Read the raw signal inside an .lcd so it can be opened without the text export. Container and most of the frame codec decoded (docs/LCD_FORMAT_NOTES.md); finishing needs one .lcd plus the text export of the same injection as ground truth.
- [ ] Show more of the method: autosampler program, PDA lamp/slit/response, the integration parameters LabSolutions applied, the method audit trail.
- [ ] Compare GeckoPlotter integration with LabSolutions' own peak tables (already in the export).
- [x] Recipes: save integration settings, named compound windows and calibrations, apply them to a new batch (docs/RECIPES.md). Not yet: shoulder splits, figure settings, recipes inside a project file.

- [x] Session save/restore **engine** (`.gecko` project files: originals + parameters, ids preserved, schema versions + migrations, large-file relocation, autosave helpers). See docs/SESSION_FORMAT.md, `src/services/session_service.py`.
- [x] Session **GUI**: Save / Open icon buttons (top left), autosave with a restore banner, unsaved-changes guard, FAIR packages reopen as projects (2026-10-13).
- [ ] Named figure styles: Prism Classic, Nature, ACS, Angewandte, Presentation, Dark. Existing paper/slide size presets do not fulfill this style-preset request.
- [ ] Advanced calibration: weighted regression, internal-standard normalization, LOD/LOQ. Force-through-zero is already implemented.
- [ ] Clarify the historical "HMS analysis" item. The old roadmap never defines the acronym and no current implementation was found. Do not treat it as a scoped feature until identified.
- [x] Draggable legends with edge snapping, persisted coordinates, context font-size control and shared file-browser/peak visibility.
- [ ] Drag other figure labels with snap alignment.
- [x] Research ZIP export: original uploads, untouched parsed CSV, edited data, exact current-figure source values, SVG/PDF/PNG/TIFF/HTML, peak/calibration data, timestamped processing history, linked metadata, checksums, README and HTML report.
- [ ] Extend research packages to a multi-figure registry, molecule attachments and direct Zenodo draft submission. The current package is a local draft with repository details to complete, not an automatic compliance certification. See docs/RESEARCH_EXPORT.md.
- [ ] Optional UV/MS detector-delay correction, including visual TIC alignment to UV. Glenn explicitly deferred this until later.
- [ ] Verify lab deployment/update automation on the actual host. Local work does not establish deployment status; see docs/DEPLOYMENT_PLAN.md.

### Decisions that supersede older proposals

- Keep Fit diagnostics removed; do not reintroduce the old diagnostics table/residual section as unfinished work.
- Refresh starts a clean workspace. Explicit session saving (`.gecko`) is separate; the engine exists, the GUI is pending.
- Pan, zoom-to-region, reset view, and undo/redo toolbar buttons were suggested on October 12; they are proposals, not committed new features. Existing gestures/shortcuts remain available.

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
- **Plot settings**: palette, layout mode (overlay/stacked), axis labels, styling, subplot spacing slider
- **Shared axis labels**: centered Y annotation across subplots, X label on bottom only
- **Legend toggle**: show/hide applies to all subplot legends
- **Color system**: Okabe-Ito palette, stable per-file color cycling, cross-sample group persistence
- **Data table editor**: cell/column selection, transpose, add row/column
- **Data selector / axis mapper**: select cells for X/Y/Y2 axes, "Create Plot" button for custom tabs
- **Peak Analysis / Across Samples tabs**: independent tabs, don't override chromatogram
- **File drag-and-drop reorder**: within groups, visual feedback with drop indicator
- **File group sort**: ascending/descending toggle per group
- **Auto-grouping**: files grouped by `(source_category, x_axis)` into tabs
- **Keyboard shortcuts**: Delete/Backspace/X to remove selected peak
- **Export**: PNG/SVG/TIFF with configurable DPI, presentation slide preset
- **Publication preview**: snapshot-based (send any plot to its own Publication tab)
- **Persistence opt-in**: no stale file_state.json on reload (GECKO_ENABLE_SESSION_PERSISTENCE=1)
- **LC-MS**: scan cursor constrained to MS Viewer tab, EIC controls below plots
- **Crameri palettes**: Batlow, Hawaii, Roma scientific color maps
- **DMC UI**: all form controls modernized to Dash Mantine Components
- **Tests**: 142 pass, 1 skipped

### Key Architecture
- `StandardizedResult` normalizes all formats (column roles + plot hints + source category)
- `master_render` is sole owner of `main-plot` figure
- `sync_plot_tabs` creates tabs from overlay groups `(source_category, x_axis)`
- Stage 3 heuristic always returns GENERIC; only presets assign specific categories
- Per-file UI state saved/restored via `context_callbacks.py`
- `active-file` store always contains a real file UUID, never a bundle ID
- Bundle resolution happens at click time only

---

## Active Sprint: Publication Preview Polish (2026-05-30)

The Publication tab is for **making the final figure** — not for data analysis.
Goal: make it feel like a pro figure-editing tool with contextual controls.

### Quick wins
- [x] **TIFF export format** — TIFF added to pub preview export (PNG→TIFF via Pillow, LZW compression, DPI metadata)
- [x] **Editable DPI** — NumberInput (72–1200) in preset bar, used by readout and all export formats
- [x] **Presentation preview** — third preset: 16:9 slide mock with title/subtitle, auto-switches container
- [x] **Shared/combined axis labels** — toggle in Plot Settings Labels section; hides per-subplot labels and adds centered paper-level X/Y annotations
- [x] **"Send to Publication" button** — in Export tab, snapshots the current plot into a new Publication tab (multi-snapshot, per-click)
- [x] **Subplot spacing slider** — adjustable vertical gap between stacked subplots (2%--25%)
- [x] **Legend toggle for all subplots** — show/hide applies to legend, legend2, legend3, etc.
- [x] **Axis labels in Plot Settings** — sole source of axis labels (Data Selector labels removed), empty = no label
- [x] **Black slider styling** — all dcc.Slider components use dark track/handle
- [x] **Automargin axes** — Plotly automargin prevents label/tick overlap
- [x] **Axis-specific zoom reset** — double-click X axis resets only X range; double-click Y resets only Y (needs custom JS handler)

### Figure style presets
- [ ] **Style preset dropdown** — "Figure Style" selector in Publication toolbox (applies Plotly template in one click)
- [ ] **Prism Classic** — white bg, Arial, no grid, bold black axes, outward ticks, Prism color cycle
- [ ] **Nature** — minimal, Helvetica, thin axes, muted palette, no box frame
- [ ] **ACS** — Arial, partial box (left+bottom axes only), serif-free, ACS color scheme
- [ ] **Angewandte** — similar to ACS, compact margins, slightly bolder lines
- [ ] **Presentation** — larger fonts (18pt+), bolder lines, high-contrast colors for projection
- [ ] **Dark** — dark background, light axes/text, for slides on dark themes

### Focus mode (Publication activation UX)
- [ ] **Publication tab hidden by default** — remove from top nav; add "Send to Publication Preview" button in Export toolbox tab
- [ ] **Focus mode on activation** — when Publication opens:
  - Collapse bottom panel (Data Overview, Peak Analysis, etc.)
  - Collapse file tree (toolbox fills left sidebar)
  - Auto-switch toolbox to Plot Settings tab
  - Clean split view: settings left, preview right
  - User can manually drag panels back at any time

### Right-click context menus on publication figure
- [ ] **Right-click on X axis** → X axis options (label text, range, scale, minor ticks, tick format)
- [ ] **Right-click on Y axis** → Y axis options (same set per Y axis)
- [ ] **Right-click on title** → title options (text, font size, position, show/hide)
- [ ] **Right-click on figure body** → general options (theme, grid, legend position, A/B comparison)

### Click-to-edit labels
- [x] **Click axis labels to edit** — click on X/Y label text on the figure → inline edit field appears
- [x] **Click title to edit** — same for figure title
- [ ] **Draggable labels** — shift+drag to reposition, with snap alignment (grid-snap like PowerPoint)

### Toolbox reorganization
- [x] **Smarter grouping** — Title + axis labels in one section; layout in another
- [ ] **Conditional visibility** — hide options that aren't relevant (e.g., no "show title" toggle if title is empty)
- [ ] **Per-axis minor ticks** — control minor ticks on X only, Y only, or both; hidden behind expandable "More" section
- [x] **Collapsible detail sections** — "More options" expand buttons for advanced controls (tick formatting, grid lines, etc.)

---

## Backlog

### Calibration UI
- CalibrationService already exists (`services/calibration_service.py`) with data model
- Previous Streamlit version had working calibration (linear, polynomial, cubic)
- Rebuild with: multi-point table, weighted regression (1/x, 1/x²), force-through-origin, residual plot
- Add LOD/LOQ calculation (ICH Q2: LOD = 3.3·Sy/slope, LOQ = 10·Sy/slope)
- Add ISTD mode (divide analyte area by IS area before regression)
- Priority: **HIGH** (enables quantitative analysis, but not blocking current work)

### HMS data analysis
- Current HMS ingestion is shaky
- Port working analysis from Streamlit version (GitHub: StreamLit repo)
- Priority: **HIGH**

### Legend control
- Movable legend, persistent position, no phantom entries
- Priority: **MEDIUM**

### Session management
- Engine done (2026-10-13): `services/session_service.py`, format in docs/SESSION_FORMAT.md. GUI pending (Save/Open, autosave, restore prompt).
- Priority: **MEDIUM**

### Polish & animations
- Smooth transitions when switching views
- Loading indicator during export (spinner/progress on Export button)
- Status line feedback for async operations
- Priority: **LOW** (nice-to-have, do after core features)

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

### Streamlit feature port
- Look at GitHub StreamLit version for analysis features (calibration, HMS)
- Port working logic, modernize code quality

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
