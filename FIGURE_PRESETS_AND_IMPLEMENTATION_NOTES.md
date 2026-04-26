# Figure Presets And Implementation Notes

_Created 2026-03-22_

## Purpose

This note captures three things in one place:

1. The current visible implementation progress in GeckoPlotter V2
2. The architecture issues that still need to stay front-of-mind
3. A practical preset/reference guide for journal figures, presentations, reports, and posters

This is meant to be a working design reference for future GeckoPlotter presets.

---

## Current Snapshot

### Observed recent changes

- `plot_settings_service.py`
  - `coloraxis` matching bug fixed by narrowing axis-key matching to actual `xaxis` / `yaxis` keys
  - plot settings model expanded substantially
- `app.py`
  - toolbox tab renamed from `Publication Plotter` to `Data Selector`
  - toolbox tab renamed from `Plot Tools` to `Plot Settings`
  - plot type moved into Plot Settings as `pt-plot-type`
  - Calibration tab is now visible
  - Integration / Export / Calibration callback registration is present
- `src/services/`
  - `peak_service.py`, `calibration_service.py`, `plot_settings_service.py`, `integration_service.py`, `export_service.py`, `lcms_service.py`, and `persistence.py` exist
- `src/callbacks/`
  - `integration_callbacks.py` exists and is registered
  - `export_callbacks.py` exists and is registered
  - calibration callbacks are registered from `app.py`
- UI stabilization patch
  - tab switching and view-mode switching were moved away from brittle click-time clientside DOM mutation toward plain Dash store updates plus store-driven UI sync
  - resize handler was rewritten to be bounded-resize only, with duplicate-init protection and without hidden collapse-on-drag behavior

### Plot settings model now includes

- plot type
- axis range + axis scale
- theme + palette + plot/paper background colors
- line style + marker symbol + opacity
- bar gap + bar group gap
- font family + body/title/tick font sizes + bold title
- legend visibility + position
- tick marks + tick direction + frame + grid style

### Calibration UI currently includes

- create model
- fit type
- analyte name + units
- peak group selection
- force-through-origin
- standards entry
- fit model
- predict concentrations
- calibration graph + R² area

---

## Architecture Watchlist

These are still the most important risks to keep in mind while development continues.

### P1 - Persistence is still split

`storage_manager.py` still contains the old filename-keyed `_persistent_state` flow while also instantiating `ProjectPersistence` against the same `file_state.json`.

Why this matters:

- two different schemas are writing to the same file
- restore behavior can become inconsistent
- future session/project persistence becomes hard to trust

Recommended direction:

- remove the old `_persistent_state` path
- keep only `ProjectPersistence` as the canonical disk layer

### P1 - Session export/import is not yet round-trippable

The current session export/import path is not aligned with the new service APIs.

Why this matters:

- `PeakService.get_all_peaks()` returns `Peak` dataclass objects, not JSON-safe dicts
- `export_service.py` still expects `set_all_peaks` / `set_all_calibrations`, but the services expose `serialize()` / `deserialize()`

Recommended direction:

- export with `peak_service.serialize()`
- import with `peak_service.deserialize(...)`
- export with `calibration_service.serialize()`
- import with `calibration_service.deserialize(...)`

### P2 - Integration currently bypasses the intended state pipeline

`integration_callbacks.py` writes directly to `main-plot.figure` and clears peaks by mutating `peak_service._peaks`.

Why this matters:

- it works as a local visual shortcut, but not as durable architecture
- peak-analysis, across-samples, export, and calibration need shared canonical state

Recommended direction:

- move integration results into canonical state
- let downstream tabs/exports consume those results
- stop mutating private service internals directly

### P2 - PlotSettingsService exists, but is not yet the sole rendering authority

The new plot settings model is good, but the publication plot path still uses older ad-hoc config assembly.

Recommended direction:

- make `PlotSettingsService` the one place that applies plot styling
- keep size presets and style presets separate, then combine them intentionally

---

## UI Wiring Notes

These are useful to remember while debugging the “buttons don’t work” phase.

### Tabs

There are currently two tab-management stories in the codebase:

- inline clientside callbacks in `app.py`
- extra tab helper functions in `src/assets/js/tab-handler.js`

Even if both are not actively conflicting at runtime, this is still a maintenance smell.

Recommended direction:

- pick one source of truth for tab switching
- preferably keep the `dcc.Store` values canonical and keep DOM updates minimal

### Resizing

`src/assets/js/resize-handler.js` says “simple free-form resize”, but the implementation also includes collapse behavior when panels cross 5% / 95%.

That means resize currently does more than the comment suggests:

- hides panels entirely
- changes display modes during drag
- attaches raw document-level listeners

Recommended direction:

- decide whether GeckoPlotter wants simple resize or VS Code-style collapse
- if collapse is not required, remove it
- add a guard so resize listeners cannot be attached more than once

---

## Official Nature Figure Requirements

The points below come from official Nature / Springer Nature sources.

### Hard requirements or strong guidance

- Standard widths:
  - single column: `89 mm`
  - column-and-a-half: `120-136 mm`
  - double column: `183 mm`
- Maximum figure height for standard Nature figures: `170 mm`
- Text should remain between `5 pt` and `7 pt` at final size
- Use standard sans-serif fonts, preferably `Arial` or `Helvetica`
- Keep text editable; do not outline text
- Line weights should be between `0.25 pt` and `1 pt` at final size
- Axis lines and tick marks should be included
- Axes should be labelled, with units in parentheses where relevant
- Avoid rainbow scales
- Use accessible colours and avoid red/green dependence
- Prefer RGB source artwork
- Bitmap images should be at least `300 dpi`; `450 dpi` is preferred for highest online proof quality
- Vector formats are strongly preferred for graphs and line art

### Important non-rules

Nature does **not** appear to prescribe exact values for:

- tick direction inside vs outside
- boxed frame vs left/bottom axes only
- exact legend position

So those choices should be treated as **preset design decisions**, not as Nature submission rules.

---

## Nature-Inspired GeckoPlotter Presets

These are recommended defaults for GeckoPlotter. Where Nature is silent, these are reasoned design choices based on common Nature-style figure practice.

### Preset A - Nature Single Column Line Plot

Use for:

- one-panel manuscript figures
- simple chromatograms
- line/scatter plots in a paper

Suggested settings:

- size: `89 x 60 mm`
- export target: `SVG/PDF` first, `PNG 600 dpi` fallback
- `plot_type`: `line`
- `theme`: `simple_white`
- `color_palette`: `okabe_ito`
- `plot title`: blank
- `font_family`: `Arial`
- `font_size`: `6`
- `tick_font_size`: `5`
- `title_font_size`: `7`
- `bold_title`: `false`
- `show_legend`: `true` only if needed
- `legend_position`: `top-right`
- `show_grid_x`: `false`
- `show_grid_y`: `false`
- `show_tick_marks`: `true`
- `tick_direction`: `outside`
- `show_frame`: `false`
- `line_width`: start around `1.5`
- `marker_size`: `4-5`

Rationale:

- no plot title because manuscript figures usually rely on the caption
- no grid because Nature-style figures are usually cleaner without it
- open frame is the safest default for broad journal aesthetics

### Preset B - Nature Double Column Comparison Plot

Use for:

- multi-series comparison plots
- grouped bar charts
- panels that need wider legends or more x labels

Suggested settings:

- size: `183 x 120 mm`
- export target: `SVG/PDF` first, `PNG 600 dpi` fallback
- `plot_type`: `line` or `bar`
- `theme`: `simple_white`
- `color_palette`: `okabe_ito`
- `font_family`: `Arial`
- `font_size`: `6-7`
- `tick_font_size`: `5-6`
- `show_legend`: `true`
- `legend_position`: `top-right`
- `show_grid_x`: `false`
- `show_grid_y`: `false`
- `show_frame`: `false`
- `line_width`: `1.5-2.0`
- `bar_gap`: `0.15-0.20`
- `bar_group_gap`: `0.05-0.10`

### Preset C - Nature Analytical Boxed Plot

Use for:

- chromatography plots where a boxed analytical look is desired
- cases where users prefer Origin-like framing

Suggested settings:

- size: `89 x 60 mm` or `136 x 90 mm`
- `theme`: `simple_white`
- `color_palette`: `okabe_ito`
- `show_grid_x`: `false`
- `show_grid_y`: `false`
- `show_tick_marks`: `true`
- `tick_direction`: `inside`
- `show_frame`: `true`
- `legend_position`: `top-right`

Important note:

- this is **not** more “Nature compliant” than the open-frame preset
- it is simply a visually useful second preset for analytical chemistry style figures

---

## Practical Daily-Lab Export Presets

These are not journal rules. They are practical working presets for real lab usage.

### 1. PowerPoint Widescreen

Use for:

- lab meeting slides
- conference slides
- supervisor updates

Base size:

- `13.333 x 7.5 in`
- `338.67 x 190.5 mm`
- `4000 x 2250 px` at `300 dpi`

Suggested style:

- `theme`: `plotly_white` or `simple_white`
- `font_family`: `Arial`
- `font_size`: `20-24`
- `tick_font_size`: `16-18`
- `title_font_size`: `24-28`
- `line_width`: `2.5-3.0`
- `marker_size`: `8-10`
- `show_legend`: `true`
- `legend_position`: `top-right`
- `show_grid_y`: optional

Export advice:

- use `PNG` for maximum slide compatibility
- use `SVG` if the target PowerPoint workflow handles SVG cleanly

### 2. PowerPoint Standard 4:3

Use for:

- older lab templates
- projector-safe legacy decks

Base size:

- `10 x 7.5 in`
- `254 x 190.5 mm`
- `3000 x 2250 px` at `300 dpi`

Suggested style:

- same as widescreen, but slightly larger labels if the plot is dense

### 3. DIN A4 Full Page

Use for:

- internal reports
- supplementary notes
- printed protocol/report pages

Base size:

- `210 x 297 mm`
- `2480 x 3508 px` at `300 dpi`

Suggested style:

- `font_size`: `10-12`
- `tick_font_size`: `9-10`
- `title_font_size`: `14-16`
- `line_width`: `1.5-2.0`
- `marker_size`: `6-8`

Export advice:

- `PDF` first if the report is vector-friendly
- `PNG 300 dpi` if the figure will be placed into Word or PowerPoint

### 4. DIN A4 Half Page

Use for:

- report layouts with two figures per page
- handouts

Base size:

- `210 x 148.5 mm`
- `2480 x 1754 px` at `300 dpi`

Suggested style:

- `font_size`: `9-11`
- `tick_font_size`: `8-9`
- `line_width`: `1.5-2.0`

### 5. Poster Panel

Use for:

- a single figure panel on a scientific poster
- conference poster sub-panels

Base size:

- `250 x 150 mm`
- `2953 x 1772 px` at `300 dpi`
- `5906 x 3543 px` at `600 dpi`

Suggested style:

- `font_size`: `18-24`
- `tick_font_size`: `16-20`
- `title_font_size`: `24-30`
- `line_width`: `3-4`
- `marker_size`: `10-14`
- `show_legend`: `true`

Export advice:

- prefer `PDF` or `SVG`
- if raster is unavoidable, use `PNG` at `600 dpi`

### 6. Ultra-High-Resolution Poster / Print

Use for:

- large poster graphics
- print shop handoff where raster is unavoidable

Recommendation:

- prefer vector `PDF` / `SVG`
- if raster is required, export at `5000-8000 px` wide depending on panel size
- keep background simple and text high contrast

---

## Size Table For Future Preset Buttons

| Preset | Physical size | 300 dpi | 600 dpi | Best export |
|---|---:|---:|---:|---|
| Nature single | 89 x 60 mm | 1051 x 709 px | 2102 x 1417 px | SVG / PDF |
| Nature 1.5-column | 136 x 90 mm | 1606 x 1063 px | 3213 x 2126 px | SVG / PDF |
| Nature double | 183 x 120 mm | 2161 x 1417 px | 4323 x 2835 px | SVG / PDF |
| A4 full page | 210 x 297 mm | 2480 x 3508 px | 4961 x 7016 px | PDF |
| A4 half page | 210 x 148.5 mm | 2480 x 1754 px | 4961 x 3508 px | PDF / PNG |
| PowerPoint widescreen | 338.67 x 190.5 mm | 4000 x 2250 px | 8000 x 4500 px | PNG / SVG |
| PowerPoint standard | 254 x 190.5 mm | 3000 x 2250 px | 6000 x 4500 px | PNG / SVG |
| Poster panel | 250 x 150 mm | 2953 x 1772 px | 5906 x 3543 px | PDF / SVG / PNG |

---

## Suggested GeckoPlotter Preset Families

To keep the app flexible, it would be better to separate presets into two layers:

### Size presets

- Nature single
- Nature 1.5-column
- Nature double
- A4 full page
- A4 half page
- PPT widescreen
- PPT standard
- Poster panel

### Style presets

- Nature manuscript
- Analytical boxed
- Presentation clean
- Report clean
- Poster bold

This is better than one giant preset list because:

- users often want Nature sizing with analytical boxed styling
- or PowerPoint sizing with Nature-like colours
- it avoids exploding the number of preset combinations

---

## Concrete Future Tasks

These would be useful later and fit the current plan well.

### Preset task 1

Add a `Figure Presets` section to Plot Settings with:

- a size preset dropdown
- a style preset dropdown
- an `Apply preset` button

### Preset task 2

Add a small read-only hint below the preset selector:

- physical size
- export type recommendation
- recommended dpi

### Preset task 3

Add export shortcuts:

- `Manuscript SVG`
- `Nature PNG 600 dpi`
- `PowerPoint PNG`
- `A4 PDF`
- `Poster PDF`

### Debug task 1

Reduce tab switching to one clientside system only.

### Debug task 2

Simplify resize behavior:

- plain resize only, or
- explicit collapse buttons, but not hidden collapse-on-drag magic

### Debug task 3

Finish the persistence unification before relying on session save/load.

---

## Sources

Official sources used for this note:

- [Nature formatting guide](https://www.nature.com/nature/for-authors/formatting-guide)
- [Nature final submission guide](https://www.nature.com/nature/for-authors/final-submission)
- [Nature initial submission guide](https://www.nature.com/nature/for-authors/initial-submission)
- [Nature research figure guide: Building and exporting figure panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/)
- [Nature research figure guide: Preparing figures - our specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)
- [Nature research figure guide: Extended data formatting guidelines](https://research-figure-guide.nature.com/figures/extended-data-formatting-guidelines/)
- [Microsoft Support: Change the size of your PowerPoint slides](https://support.microsoft.com/en-us/office/change-the-size-of-your-powerpoint-slides-040a811c-be43-40b9-8d04-0de5ed79987e)

### Source interpretation note

Where this note recommends exact choices such as:

- legend position
- tick direction
- boxed vs open frame
- PowerPoint / poster styling

those are **design recommendations and inferred best practice**, not direct Nature mandates.
