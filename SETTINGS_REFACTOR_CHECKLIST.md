# GeckoPlotter V2 — Plot Settings Refactor Checklist

> **Status**: Implementation guide for context-aware plot settings panel  
> **Created**: 2026-03-22  
> **Architecture**: `active-plot-context` + `current-plot-settings` as single runtime truth

---

## Context

The analysis/publication plot is on the new settings pipeline:
- `current-plot-settings` store (app.py:111)
- `plot_settings_callbacks.py` — resolve → hydrate → edit → persist (4-callback architecture)
- `publication_callbacks.py:1008` — reads `current-plot-settings`, applies via `PlotSettingsService.apply_to_figure()`

Raw chromatogram plots are **still rendered by `plot_manager.py`** through `viz_callbacks.py:326` (`handle_view_mode_change`). The settings panel does **not** affect raw chromatograms yet. This is expected — not a bug.

### Core Rule
> The settings panel answers one question only:  
> **"What settings are valid for the plot the user is looking at right now?"**

### Short Intro For A New Chat

Use this when continuing the work in a fresh thread:

> We are simplifying GeckoPlotter V2's plot-settings architecture so the settings panel always reflects the currently visible plot. The new direction is `active-plot-context` + `current-plot-settings` as the single runtime truth. Analysis plots mostly use this already. Raw chromatogram plots still do not fully use the same styling path yet. The next goal is to make the settings UI context-aware, audit which controls apply to raw vs analysis vs specific plot types, and add raw-only layout mode for `Superposition` vs `Separate plots`.

---

## Product Model

### The intended user experience

The UI should feel like this:

1. There is one currently visible plot.
2. That plot has one current settings object.
3. The settings panel shows only the settings that make sense for that plot.
4. Editing a setting updates the currently visible plot.
5. Switching visible plot context swaps in that plot's saved settings.

If the visible plot is `Raw Data`, the user should see **Raw Plot Settings**.  
If the visible plot is `Analysis Plot`, the user should see **Analysis Plot Settings**.

### Plot families

There are really two different plot families in GeckoPlotter:

- `Raw`
  Chromatograms, UV traces, LC-MS TIC/UV traces, file-native signal views.

- `Analysis`
  Publication/data-selector plots derived from table selections.

These two families share some styling controls, but not all. The UI should stop pretending that one generic control surface fits both equally well.

---

## Files Reference

| File | Role |
|------|------|
| `app.py:210-403` | Settings panel UI (all `pt-*` controls) |
| `plot_settings_callbacks.py` | 4-callback pipeline (resolve/hydrate/edit/persist) |
| `plot_settings_service.py` | `PlotSettings` dataclass + `PlotSettingsService.apply_to_figure()` |
| `publication_callbacks.py:1008-1128` | Analysis plot renderer (reads `current-plot-settings`) |
| `components/publication_plot.py` | `create_publication_plot()` — bar/line/scatter only |
| `services/plot_manager.py` | Raw plot renderers (chromatogram, UV-Vis, LC-MS TIC, LC-MS UV) |
| `callbacks/viz_callbacks.py:317-403` | `handle_view_mode_change()` — switches between raw and analysis |
| `STATE_REGISTRY.py` | Store definitions |

---

## Detailed Control Audit

### Legend for the tables below

- `Both` = valid for raw and analysis plots
- `Analysis only` = valid only for publication/data-selector plot path
- `Raw only` = valid only for chromatogram/trace views
- `Future only` = do not expose until renderer support exists

Visibility policy:
- `Always`
- `Conditional`
- `Hide for now`

### A. Universal controls

| Control | Store key | Applies to | Visibility | Notes / Decision |
|--------|-----------|------------|------------|------------------|
| Plot title | `title` | Both | Always | Keep |
| X min / X max | `x_min`, `x_max` | Both | Conditional | Show only when auto range is off |
| Y min / Y max | `y_min`, `y_max` | Both | Conditional | Show only when auto range is off |
| Auto range | `auto_range` | Both | Always | Keep |
| X scale | `x_scale` | Both | Always | Keep |
| Y scale | `y_scale` | Both | Always | Keep |
| Font family | `font` | Both | Always | Keep |
| Base font size | `font_size` | Both | Always | Keep |
| Title font size | `title_font_size` | Both | Always | Keep |
| Tick font size | `tick_font_size` | Both | Always | Keep |
| Bold title | `bold_title` | Both | Always | Keep |
| Plot background | `bg_color` | Both | Always | Keep |
| Paper background | `paper_color` | Both | Always | Keep |
| Grid X | `show_grid_x` | Both | Always | Keep |
| Grid Y | `show_grid_y` | Both | Always | Keep |
| Tick marks | `show_tick_marks` | Both | Always | Keep |
| Tick direction | `tick_direction` | Both | Conditional | Show only when tick marks are enabled |
| Frame box | `show_frame` | Both | Always | Keep |
| Grid style | `grid_style` | Both | Conditional | Show only when grid is enabled on at least one axis |
| Show legend | `show_legend` | Both | Always | Keep, but legend semantics must be fixed |
| Legend position | `legend_pos` | Both | Conditional | Show only when legend is enabled |

### B. Analysis-only controls

| Control | Store key | Applies to | Visibility | Notes / Decision |
|--------|-----------|------------|------------|------------------|
| Plot type | `plot_type` | Analysis only | Always in analysis mode | Keep. Supported now: `bar`, `line`, `scatter` |
| X label | `x_label` | Analysis only | Always in analysis mode | Keep |
| Y1 label | `y1_label` | Analysis only | Always in analysis mode | Keep |
| Y2 label | `y2_label` | Analysis only | Conditional | Show when Y2 is enabled |
| Y1 stats | `y1_stats` | Analysis only | Conditional | Only meaningful for grouped/replicate analysis tables |
| Show raw points | `show_raw_points` | Analysis only | Conditional | Show only when stats / replicates exist |
| Y2 enable | `y2_enable` | Analysis only | Conditional | Show when second axis is available |
| Y1 series count | derived | Analysis only | Conditional | Only if multi-series analysis is still a supported concept in current UI |

### C. Plot-type-specific controls inside analysis mode

| Control | Store key | Bar | Line | Scatter | Notes / Decision |
|--------|-----------|-----|------|---------|------------------|
| Bar gap | `bar_gap` | Show | Hide | Hide | Keep |
| Group gap | `bar_group_gap` | Show | Hide | Hide | Keep |
| Line width | `line_width` | Hide | Show | Usually hide | Keep but conditional |
| Line style | `line_style` | Hide | Show | Hide | Keep but conditional |
| Marker size | `marker_size` | Hide | Optional | Show | Keep but conditional |
| Marker symbol | `marker_symbol` | Hide | Optional | Show | Keep but conditional |
| Trace opacity | `trace_opacity` | Show | Show | Show | Keep |

Note:
- For `line`, decide whether the design is always `lines+markers` or optionally `lines only`.
- If markers are not always shown for `line`, then `marker_size` and `marker_symbol` should also be conditional there.

### D. Raw-only controls

| Control | Store key | Applies to | Visibility | Notes / Decision |
|--------|-----------|------------|------------|------------------|
| Layout mode | `layout_mode` | Raw only | Conditional | Show when 2 or more traces are visible |
| Line width | `line_width` | Raw only | Always in raw mode | Very important for chromatograms |
| Trace opacity | `trace_opacity` | Raw only | Always in raw mode | Useful for overlays |
| Palette / trace color mode | `palette` or future split | Raw only | Always in raw mode | Keep palette for now; per-trace color later |
| Baseline visibility | future | Raw only | Conditional | Add later when raw overlays are wired |
| Peak fill visibility | future | Raw only | Conditional | Add later |
| Peak fill opacity | `peak_opacity` | Raw only | Conditional | Later, when overlays are visible |
| Legend labels mode | future | Raw only | Conditional | Filename / injection / custom later |

### E. Controls to hide for now

| Control / concept | Why |
|------------------|-----|
| Boxplot controls | The renderer does not support boxplots yet |
| Violin / swarm controls | Not implemented |
| Per-series manual color picker | Palette exists, but explicit per-trace color UI is not built yet |
| Raw marker symbol / marker size | Raw plots are line/signal views, not marker-driven currently |
| Analysis subplots / facet controls | Not yet implemented |

---

## Phase 1: Context-Aware Panel Header & Visibility

### 1.1 — Settings header shows current plot family

**What**: The panel header (`app.py:216`) should dynamically show:
- **"Raw Plot Settings"** when `view-mode` = `raw`
- **"Analysis Plot Settings"** when `view-mode` = `analysis`

**Where to change**:
- `app.py` — replace static `html.Div('Plot Type', ...)` header with a dynamic `html.Div(id='settings-panel-header')`
- Add a clientside or server callback that reads `view-mode` and updates the header text

**Complexity**: Small

---

### 1.2 — Hide analysis-only controls in raw mode

**What**: When `view-mode` = `raw`, the following controls should be **hidden**:

| Control ID | Setting Key | Why |
|-----------|------------|-----|
| `pt-plot-type` | `plot_type` | Raw has no bar/line/scatter choice |
| `pt-bar-gap` | `bar_gap` | Bar-only |
| `pt-bar-group-gap` | `bar_group_gap` | Bar-only |
| `pt-marker-symbol` | `marker_symbol` | Scatter/line-only in analysis |
| `pt-marker-size` | `marker_size` | Scatter/line-only in analysis |

Also hide from the **Data Selector** panel (pub-plotter-container):
- `plot-type`, `y1-stats`, `show-raw-points`, `y2-enable`, `y1-series-count` — all analysis-only

**Where to change**:
- Wrap each control group in a `html.Div(id='pt-<group>-wrapper')` in `app.py`
- Add a callback (or clientside callback) that toggles `style={'display': 'none'}` / `style={}` based on `view-mode`

**Complexity**: Medium — lots of wrapper Divs, but logic is simple

---

### 1.3 — Hide plot-type-specific controls within analysis mode

**What**: Within analysis mode, show/hide controls based on `plot_type`:

| Control | Show for `bar` | Show for `line` | Show for `scatter` |
|---------|:-:|:-:|:-:|
| `pt-bar-gap` | ✅ | ❌ | ❌ |
| `pt-bar-group-gap` | ✅ | ❌ | ❌ |
| `pt-line-style` | ❌ | ✅ | ❌ |
| `pt-line-width` | ❌ | ✅ | ✅ (if lines) |
| `pt-marker-size` | ❌ | ✅ | ✅ |
| `pt-marker-symbol` | ❌ | ❌ | ✅ |
| `pt-trace-opacity` | ✅ | ✅ | ✅ |

**Where to change**:
- Same wrapper approach from 1.2
- Callback reads `pt-plot-type` value + `view-mode` → sets display on wrappers

**Complexity**: Medium

---

### 1.4 — Conditional visibility for dependent controls

| Control | Visible when |
|---------|-------------|
| `pt-x-min/max`, `pt-y-min/max` | `auto_range` is OFF |
| `pt-legend-pos` | `show_legend` is ON |
| `pt-tick-dir` | `show_tick_marks` is ON |
| `pt-grid-style` | `show_grid_x` OR `show_grid_y` is ON |

**Where to change**:
- Add outputs to the existing `user_edit_settings` callback (or a dedicated visibility callback) that toggle wrapper display

**Complexity**: Small-Medium

---

## Phase 2: Raw Plot Settings Subset (Option A — Dedicated Small Panel)

### 2.1 — Define raw plot settings object

Raw chromatograms currently use **hardcoded styles** in `plot_manager.py`. The following settings should be user-controllable for raw plots:

```python
RAW_PLOT_DEFAULTS = {
    # Layout
    "layout_mode": "overlay",          # "overlay" | "stacked"
    # Axes
    "auto_range": True,
    "x_min": None, "x_max": None,
    "y_min": None, "y_max": None,
    "x_scale": "linear",
    "y_scale": "linear",
    # Appearance
    "title": "",
    "font": "Arial",
    "font_size": 12,
    "title_font_size": 14,
    "tick_font_size": 10,
    "bold_title": True,
    "bg_color": "#ffffff",
    "paper_color": "#ffffff",
    # Traces
    "line_width": 2.0,
    "trace_opacity": 1.0,
    "palette": "default",              # uses plot_manager.default_colors
    # Legend
    "show_legend": True,
    "legend_pos": "top-right",
    # Grid & Frame
    "show_grid_x": True,
    "show_grid_y": True,
    "show_tick_marks": True,
    "tick_direction": "outside",
    "show_frame": False,
    "grid_style": "solid",
}
```

**Where to add**: `plot_settings_service.py` — new `RAW_PLOT_DEFAULTS` dict alongside existing `DEFAULT_PLOT_SETTINGS`

---

### 2.2 — Add `layout_mode` to raw settings + UI

**What**: New control for raw chromatograms — overlay vs stacked subplots.

| Setting | Values | Default | Where visible |
|---------|--------|---------|--------------|
| `layout_mode` | `overlay`, `stacked` | `overlay` | Raw mode only, when ≥2 traces loaded |

User-facing labels should be:
- `Superposition`
- `Separate plots`

Internal values should stay:
- `overlay`
- `stacked`

**UI**: RadioItems control `pt-layout-mode` above traces section (raw mode only)

**Renderer impact**:
- `plot_manager.py` — `create_uvvis_plot()`, `create_chromatogram_plot()` need a `settings` parameter
- `overlay` = current behavior (one figure, shared axes)
- `stacked` = `make_subplots(rows=N, cols=1, shared_xaxes=True)` with one trace per subplot

**Where to change**:
- `app.py` — add `pt-layout-mode` RadioItems
- `plot_manager.py` — accept optional `PlotSettings`/dict and branch on `layout_mode`
- `viz_callbacks.py:374-401` — pass raw settings to plot_manager calls
- `plot_settings_service.py` — add `layout_mode` to `PlotSettings` dataclass

**Complexity**: Medium-Large (renderer changes needed)

### 2.2b — Define the exact behavior of raw layout mode

#### `overlay` / Superposition
- all visible traces are drawn into one axes system
- one shared X axis
- one shared Y axis
- legend is important here
- palette and opacity matter a lot

Use this for:
- same-unit traces
- quick comparison
- checking retention-time alignment

#### `stacked` / Separate plots
- one subplot per visible trace
- shared X axis
- independent Y autoscaling by default
- trace label can live in subplot title or annotation
- legend can be reduced or hidden in this mode

Use this for:
- crowded overlays
- traces with very different amplitudes
- comparing shapes without overlap confusion

Recommended defaults:
- `overlay` when 1 trace or casual comparison
- `stacked` available only when 2+ traces are visible

Recommended future sub-settings for stacked mode:
- `shared_y_axis` (default `False`)
- `subplot_spacing`
- `show_trace_labels`
- `sync_zoom_x` (default `True`)

---

### 2.3 — Wire raw settings through viz_callbacks

**What**: `handle_view_mode_change()` (viz_callbacks.py:326) currently calls `plot_manager.create_uvvis_plot()` etc. with no settings. After 2.1, it should:

1. Read `current-plot-settings` (State)
2. Pass to plot_manager render functions
3. PlotManager applies font/grid/legend/color settings to the raw figure

**Where to change**:
- `viz_callbacks.py:317` — add `State('current-plot-settings', 'data')` to callback
- `plot_manager.py` — each `create_*_plot` method gets optional `settings: dict = None`
- Apply subset of settings (font, grid, frame, legend, bg, line_width, palette) to raw figures

**Complexity**: Medium

---

## Phase 3: Legend Semantics Fix

### 3.1 — Fix legend eligibility in publication_plot.py

**Current problem**: In `publication_plot.py:284/292/301`, `showlegend` is set to `len(y1_aligned) > 1 or include_y2`. Single-series plots get `showlegend=False` on the trace, so the legend toggle feels broken.

**Fix**: Always set `showlegend=True` on every data trace. Let `PlotSettingsService.apply_to_figure()` control legend **visibility** via `fig.update_layout(legend=dict(visible=...))`.

**Rule**:
- Every meaningful data series → `showlegend=True` on trace + real `name`
- Helper traces (fills, baselines, jittered raw points) → `showlegend=False`
- Global on/off → `PlotSettingsService` handles via `settings.show_legend`

**Where to change**:
- `publication_plot.py:284, 292, 301` — change to `showlegend=True`
- `publication_plot.py:241` — keep `showlegend=False` for raw jitter points (correct)
- Verify `PlotSettingsService.apply_to_figure()` line 344 already handles global toggle (it does)

**Complexity**: Small

---

### 3.2 — Give traces stable meaningful names

**Current**: Traces are named `"Series 1"`, `"Series 2"`, `"Y1"`, `"Y2"`.

**Better**: Use the actual column name from selections:
```python
series_name = series.get('column_id', f'Series {idx+1}')
```

**Where to change**:
- `publication_plot.py:267, 279, 289, 297` — use `column_id` for trace names
- Consider truncating long column names

**Complexity**: Small

---

## Phase 4: Control Surface Cleanup

### 4.1 — Remove/defer unsupported controls

These settings exist in the UI or dataclass but have **no renderer support yet**:

| Setting | Status | Action |
|---------|--------|--------|
| Boxplot support | Not in `publication_plot.py` | **Don't add** `pt-plot-type` option yet |
| Per-series manual colors | Not implemented | **Don't add** UI yet; palette-only is fine |
| `separate_subplots` in `PlotSettings` dataclass | Exists (line 196) but unused for analysis | Keep in dataclass; wire for raw only via `layout_mode` |
| `show_baseline`, `show_peaks`, `peak_opacity` in `PlotSettings` | Exist (lines 191-193) but only applied to fills | Keep in dataclass; consider wiring to raw integration overlays later |

**Complexity**: Small (mostly deletions/comments)

---

### 4.2 — Sync `PlotSettings` dataclass field names with store keys

Current mismatches between `DEFAULT_PLOT_SETTINGS` dict keys and `PlotSettings` field names:

| Store key | Dataclass field | Fix |
|-----------|----------------|-----|
| `palette` | `color_palette` | Rename one to match |
| `font` | `font_family` | Rename one to match |
| `legend_pos` | `legend_position` | Rename one to match |
| `y_label` → `y1_label` | `y_label` | Clarify naming |

The translation currently happens manually in `publication_callbacks.py:1089-1114`. Should be automatic via `PlotSettingsService.from_dict()`.

**Fix**: Either rename `PlotSettings` fields to match store keys, or add an alias map in `from_dict()`.

**Complexity**: Small-Medium

### 4.3 — Make the panel actually context-aware instead of globally generic

The panel should have two top-level modes:

#### Raw mode sections
- Layout
- Axes
- Appearance
- Trace Style
- Legend
- Overlays

#### Analysis mode sections
- Plot Type
- Data Labels
- Axes
- Trace Style
- Legend
- Stats / Raw Points

Implementation recommendation:
- keep one `current-plot-settings` runtime object
- but do not keep one giant permanently visible form
- instead, hide/show sections by plot family and plot type

This is the key product fix that makes the UI feel sane even before every rendering feature is fully complete.

### 4.4 — Fix legend semantics, not just legend styling

The problem with legends is partly structural, not just cosmetic.

Correct target behavior:
- every meaningful data trace gets a stable `name`
- every meaningful data trace is legend-eligible
- helper traces stay out of legend
- `show_legend` only controls global visibility and position

So the work is:
- fix `publication_plot.py` trace `showlegend` behavior
- make raw plot renderers consistently expose trace names
- only then will `show_legend` and `legend_pos` feel trustworthy

---

## Phase 5: Future Enhancements (Don't Build Yet)

These are noted for completeness — only implement when the foundation is stable.

### Raw chromatogram specific (after Phase 2)
- [ ] Trace color mode (auto palette / single / by-trace)
- [ ] Single trace color picker
- [ ] Baseline visibility toggle (wired to integration)
- [ ] Peak fill visibility + opacity
- [ ] Line smoothing display toggle
- [ ] Legend label mode (filename / injection / custom)

### Analysis plot specific
- [ ] Error bar thickness
- [ ] Bar outline width + color
- [ ] Marker outline width + color
- [ ] Connect-points toggle (scatter → scatter+lines)
- [ ] Jitter amount for raw replicate points
- [ ] Per-series color picker

### Universal
- [ ] Preset selector (Nature, Presentation, Poster, Clean Default)
- [ ] Export-aware sizing (auto-set dimensions for target)
- [ ] Context-aware panel copy (`Raw Plot Settings` vs `Analysis Plot Settings`)

### Future plot types
- [ ] Boxplot in `publication_plot.py`
- [ ] Violin/swarm
- [ ] Faceted layout for analysis (`analysis_layout_mode: single | faceted`)

---

## Implementation Order (Recommended)

```
Phase 1.1  →  Settings header context-aware           [30 min]
Phase 1.2  →  Hide analysis-only in raw mode           [1 hr]
Phase 1.3  →  Plot-type-specific visibility             [1 hr]
Phase 1.4  →  Conditional dependent controls            [30 min]
Phase 3.1  →  Legend eligibility fix                    [20 min]
Phase 3.2  →  Stable trace names                       [15 min]
Phase 4.2  →  Sync field names                         [30 min]
Phase 4.3  →  Split panel by plot family               [1 hr]
Phase 4.4  →  Fix legend semantics end-to-end          [45 min]
Phase 2.1  →  Define raw plot defaults                  [20 min]
Phase 2.2  →  layout_mode setting + UI                  [1.5 hr]
Phase 2.3  →  Wire raw settings through viz_callbacks   [1 hr]
Phase 4.1  →  Remove/defer unsupported                  [15 min]
```

**Total estimated**: ~9 hours of focused work, split across sessions.

---

## Quick Wins (Can Do Right Now)

1. **Phase 3.1** — One-line fix in `publication_plot.py` to always set `showlegend=True` on data traces
2. **Phase 3.2** — Use `column_id` for trace names
3. **Phase 1.4** — Conditional visibility for `legend_pos` / `tick_direction` / `grid_style`
4. **Phase 2.2** — Add `Superposition` vs `Separate plots` UI stub even before full raw renderer wiring

These three changes alone will make the settings panel feel much more responsive without any architectural changes.
