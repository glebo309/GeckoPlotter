# Publication Preview Tab — Design Spec

## Problem

Exporting publication figures is blind — you pick a preset size, tweak Plot Settings, export, open the file, realize the font is too small or the legend overlaps, go back, adjust, re-export. This guess-and-check loop wastes time and produces inconsistent figures.

## Solution

A new **"Publication"** plot tab that renders the figure inside a mock journal paper page at exact publication dimensions. The existing Plot Settings controls update it live. The user sees exactly how the figure will look in a two-column paper before exporting.

## Workflow

1. **Analysis mode** (daily work): Full layout — file explorer, toolbox tabs, main plot, data tables. User analyzes data, integrates peaks, calibrates.
2. User switches to the **Publication** plot tab (top tab bar, alongside Raw | Custom).
3. The main plot area becomes a mock A4 paper page with the figure embedded at the selected preset size.
4. User picks **Single-column** (84 mm) or **Full-width** (174 mm) from a preset bar at the top.
5. User collapses file explorer and data table panels → clean two-panel split: **Plot Settings | Paper Preview**.
6. User adjusts Plot Settings on the left (font, line width, legend, frame, colors) — the preview updates live.
7. User clicks **Export** directly from the Publication tab. Done.

## Architecture

### No new rendering pipeline

`master_render` already handles different tab types (raw, custom). A new branch detects `active_tab == "publication"` and:

- Renders the same figure data as the raw/custom tab
- Constrains the `dcc.Graph` to the preset pixel dimensions
- Wraps it in the paper mock HTML component
- Applies Plot Settings identically to the working plot

### Data flow

```
Plot Settings controls
  → current-plot-settings (dcc.Store)
  → master_render() callback
  → detects publication tab active
  → renders figure at preset dimensions
  → embeds in PaperMock component
  → Output: main-plot area shows paper page with live figure
```

### New components

#### 1. PaperMock (Dash HTML component)

A styled `html.Div` that looks like an A4 journal page:

- White rectangle with drop shadow on `#f0f0f0` background
- Two-column layout with grey bars simulating text paragraphs
- Fake section headers ("1. Introduction", "2. Methods")
- Figure caption placeholder below the embedded graph
- The figure placement shifts based on preset:
  - **Single-column**: figure sits inside one column (~48% page width)
  - **Full-width**: figure spans both columns (100% page width)

Location: `src/components/paper_mock.py`

#### 2. Preset bar

A thin bar at the top of the Publication tab containing:

- Radio buttons: **Single-column** (84 mm) | **Full-width** (174 mm)
- Format selector: PNG | SVG | PDF
- **Export** button
- Dimension readout: "84 × 63 mm · 300 DPI"

This bar lives inside the Publication tab layout, not in the toolbox.

#### 3. Publication tab registration

The tab appears in the top plot tab bar. It is always present (not dynamically created like custom tabs). Its ID follows the existing tab convention.

### Screen scaling

Publication dimensions at 300 DPI are large:

| Preset | Real pixels | Typical screen scale |
|--------|------------|---------------------|
| Single-column (84 mm) | 992 × 744 | ~50-60% to fit viewport |
| Full-width (174 mm) | 2055 × 1541 | ~30-40% to fit viewport |

The paper mock container uses CSS `transform: scale()` to fit the page in the viewport. The embedded `dcc.Graph` renders at true publication pixels but is visually scaled down. This preserves:

- Correct aspect ratio
- Accurate relative sizing (is this label readable at print size?)
- True pixel export — the export grabs the unscaled figure

### Export from Publication tab

The Publication tab contains its own `dcc.Graph` (ID: `pub-preview-graph`) embedded inside the paper mock. A dedicated callback renders the figure into this graph when the Publication tab is active, using the same data and Plot Settings as `master_render` but constrained to preset dimensions. The export callback reads from `pub-preview-graph.figure` and exports via the existing `ExportService`. This avoids conflicting with the main plot's callback chain.

## Presets

Only two paper presets for MVP:

| Preset | Width (mm) | Width (px @300 DPI) | Typical use |
|--------|-----------|-------------------|-------------|
| Single-column | 84 | 992 | Fits in one column of a two-column paper |
| Full-width | 174 | 2055 | Spans both columns |

Height preserves the current figure's aspect ratio by default. The preset bar includes a height override input for manual control.

PowerPoint (16:9, 1920 × 1080) stays as a separate non-paper preset.

## Files to create or modify

| File | Action | Purpose |
|------|--------|---------|
| `src/components/paper_mock.py` | Create | PaperMock component + preset bar |
| `src/callbacks/viz_callbacks.py` | Modify | Add publication branch to `master_render` |
| `src/callbacks/export_callbacks.py` | Modify | Wire export button from Publication tab |
| `app.py` | Modify | Register Publication tab in plot tab bar |
| `src/services/plot_settings_service.py` | Modify | Ensure settings apply correctly at constrained dimensions |

## Future phases (not in MVP)

### Phase A: Direct manipulation

Click a label → edit text inline. Click legend → drag to reposition. Click a trace → change color/width. Uses Plotly's click events on the embedded graph.

### Phase B: Floating property panels

Click an element → a small floating panel appears with controls specific to that element (font size, bold, color, position).

### Phase C: Journal presets & templates

Predefined page layouts for specific journals (RSC, ACS, Wiley, Elsevier). Different column widths, margins, font requirements.

### Phase D: Custom template upload

Upload a PDF or Word document as the page background. The figure is overlaid at the correct position and size.

### Phase E: Batch export

Apply the same publication settings to multiple figures/files at once.
