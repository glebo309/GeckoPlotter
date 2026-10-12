# Plot Context Menu Generalization Plan

This note is the recipe for expanding the right-click plot editor beyond the
working X-axis proof of concept.

## Current Working Examples

The first complete examples are the shared axis context editor and the legend
context editor.

Axis workflow:

1. Right-click the X-axis or Y-axis area of the main Plotly graph.
2. A small `X-axis` or `Y-axis` editor opens near the cursor.
3. The editor shows the same state as Plot Settings:
   - `Auto range`
   - axis min
   - axis max
   - axis label
   - axis scale
   - grid lines
   - minor ticks
   - tick direction
   - tick length
4. Editing those controls updates `current-plot-settings`.
5. Plot Settings controls stay synced.
6. Clicking outside the mini-dialog closes it.
7. `Escape`, keyboard `x`, and the visible close button also close it.
8. Peak deletion still only fires when an actual peak is selected.

Legend workflow:

1. Right-click the plot legend.
2. A small `Legend` editor opens near the cursor.
3. The editor can toggle legend visibility and set legend position.
4. The editor writes to `show_legend` and `legend_pos` in
   `current-plot-settings`.
5. Plot Settings controls (`pt-show-legend`, `pt-legend-pos`) stay synced.

The important architecture decision: the context editor is not a second settings
system. It is only another surface for editing `current-plot-settings`.

## Files Changed For The Example

- `app.py`
  - Adds `axis-context-menu-store`.
  - Adds `axis-context-menu-close-store`.
  - Adds `legend-context-menu-store`.
  - Adds `legend-context-menu-close-store`.
  - Adds the fixed-position `axis-context-panel`.
  - Adds the fixed-position `legend-context-panel`.
  - Adds `selected-peak-keyboard-state`, a hidden DOM mirror of selected peak
    presence for browser shortcuts.
  - Registers `register_plot_context_menu_callbacks`.

- `src/assets/js/plot-axis-context-menu.js`
  - Detects right-clicks in the Plotly X-axis and Y-axis bands.
  - Detects right-clicks on Plotly legend DOM (`.legend`).
  - Publishes `{axis, subplot, x, y, viewport_width, viewport_height, ts}` into
    `axis-context-menu-store`.
  - Publishes legend clicks into `legend-context-menu-store`.
  - Handles outside-click, `Escape`, keyboard `x`, and close-button dismissal
    for plot context panels.

- `src/callbacks/plot_context_menu_callbacks.py`
  - Opens and positions axis and legend panels.
  - Hydrates context controls from `current-plot-settings`.
  - Writes X-axis, Y-axis, and legend edits back into
    `current-plot-settings`.
  - Clears `zoom-state` and bumps `render-trigger` when axis ranges change.
  - Mirrors context-control values back to the toolbox controls.

- `src/callbacks/viz_callbacks.py`
  - Fixes axis rendering so manual ranges are not overwritten by unconditional
    autorange after settings are applied.

- `src/assets/js/keyboard-delete.js`
  - Gates peak deletion so `x`, `Delete`, and `Backspace` only fire when a peak
    is selected.
  - Lets the axis context editor own keyboard `x` while it is open.

- `src/callbacks/baseline_callbacks.py`
  - Mirrors `selected-peak-idx` into hidden DOM text for browser-side shortcut
    checks.

- `src/assets/css/main.css`
  - Styles the context panel and close button.

## Recipe For Adding Another Context Editor

Use this sequence for every new plot right-click editor.

1. Choose the clicked target.
   Examples: `x-axis`, `y-axis`, `legend`, `title`, `trace`, `peak fill`,
   `subplot panel`, `grid/frame area`.

2. Add or extend a browser hit-test in `src/assets/js/plot-axis-context-menu.js`.
   Keep the browser event payload small:
   - `target_type`
   - `axis` or `trace_index` or `subplot`
   - cursor `x/y`
   - viewport size
   - timestamp

3. Add a Dash panel in `app.py`.
   Prefer one reusable context panel if the editors stay small. Use separate
   panels only when the control sets become very different.

4. Hydrate controls from `current-plot-settings`.
   The opened menu must reflect the current toolbox state immediately.

5. Write edits back into `current-plot-settings`.
   Always deep-copy the settings dict, change only the relevant keys, and return
   `dash.no_update` when nothing changed.

6. Mirror edited values back into toolbox controls.
   This keeps the full Plot Settings panel and the right-click editor visibly in
   sync.

7. Decide whether edits must clear `zoom-state`.
   Axis ranges, axis scale, categorical/numeric mode, subplot geometry, and sync
   zoom changes usually should clear or reinterpret `zoom-state`.

8. Decide whether edits require `render-trigger`.
   If the plot renderer does not already react to the changed store value, bump
   `render-trigger`.

9. Add dismissal behavior.
   Use capture-phase `pointerdown`, `mousedown`, and `click` outside the panel.
   Also support `Escape`. Keyboard shortcuts must be ignored while the user is
   typing in an input, textarea, select, or contenteditable element.

10. Test the exact user workflow.
    Minimum checks:
    - Right-click opens the correct panel.
    - Outside click closes it.
    - The mini-panel changes the plot.
    - The toolbox reflects the same values.
    - The toolbox changes an open mini-panel.
    - Existing plot interactions still work.

## What Initially Broke And How It Was Fixed

### Fixed-position panel detection

The first outside-click implementation used `offsetParent` to decide whether the
mini-dialog was open. That fails for fixed-position elements because their
`offsetParent` can be `null` even when they are visible.

Fix: use computed styles:

```js
const style = window.getComputedStyle(panel);
const open = style.display !== 'none' && style.visibility !== 'hidden';
```

### Outside-click dismissal was too fragile

A single `mousedown` listener can lose to Plotly or other UI layers.

Fix: listen in capture phase to `pointerdown`, `mousedown`, and `click`, then use
a tiny duplicate guard so one physical click does not send three close updates.

### Axis settings changed the store but not the plot

The context editor wrote `x_min` and `x_max`, but the plot still looked
unchanged.

Two things caused that:

1. Old `zoom-state` could still be reapplied after the setting changed.
2. The render callback unconditionally set `xaxis.autorange=True` and
   `yaxis.autorange=True` whenever there was no zoom, which overwrote manual
   ranges.

Fix:

- Context axis edits clear `zoom-state`.
- Context axis edits bump `render-trigger`.
- `viz_callbacks.py` now only forces autorange when `auto_range` is true.

### Dash store values were not readable from browser JS

The keyboard-delete shortcut needed to know whether a peak was actually
selected. Reading `dcc.Store` from the DOM was unreliable because Dash does not
expose a normal DOM value for it.

Fix:

- Python mirrors `selected-peak-idx` into hidden text
  `selected-peak-keyboard-state`.
- Browser JS reads that text before firing a delete shortcut.
- Python still keeps the server-side guard as a second safety layer.

### Keyboard `x` had two meanings

`x` can be a nice close shortcut for context dialogs, but it is also the peak
delete shortcut.

Current rule:

- If the axis mini-dialog is open, `x` closes the dialog.
- If no dialog is open and a peak is selected, `x` deletes the selected peak.
- If no peak is selected, `x` does nothing.
- If the user is typing in an input, `x` is just typed text.

### Plotly axis hit testing is manual

Plotly has no direct "right-clicked this axis" event. The browser code uses
`gd._fullLayout._plots`, axis offsets, axis lengths, and SVG bounds to infer
whether the cursor is in the X-axis band.

This is acceptable for a local app, but it should remain isolated in one JS
module so future Plotly updates are easier to handle.

## Scientific Plot Elements Worth Right-Click Editing

This list includes current Plot Settings controls and additional scientific
plot controls that are useful on demand.

### X-Axis

Good first expansion after the current example.

- Auto range
- X min / X max
- Linear / log scale
- Categorical vs numeric axis
- Axis label and units
- Tick label font size
- Tick direction
- Tick length
- Tick width
- Major tick spacing
- Minor ticks on/off
- Minor tick spacing
- Grid on/off for X
- Grid line style
- Tick label rotation
- Tick number format, including scientific notation
- Reverse axis
- Show/hide axis line
- Frame/mirror behavior for this axis only

### Y1-Axis

Equivalent to X-axis, but should target the primary Y-axis only.

- Auto range
- Y min / Y max
- Linear / log scale
- Axis label and units
- Tick label font size
- Tick direction
- Tick length
- Major/minor ticks
- Grid on/off for Y1
- Grid line style
- Zero line on/off
- Reverse axis
- Scientific notation and exponent display
- Frame/mirror behavior for this axis only

### Y2-Axis

Important because secondary axes need separate control without cluttering the
main settings panel.

- Enable/disable Y2
- Y2 label and units
- Y2 min / max
- Y2 linear / log scale
- Y2 tick marks and minor ticks
- Y2 color or trace association
- Overlay mode vs separate axis domain
- Show/hide Y2 grid

### Title And Text

Right-click title or label text.

- Plot title
- Subtitle
- X/Y axis labels
- Font family
- Font size
- Bold/regular
- Title alignment
- Label standoff from axes
- Annotation text for publication figures

### Legend

Right-click legend or legend entries.

- Show/hide legend
- Position
- Orientation horizontal/vertical
- Legend title
- Font size
- Trace order
- Group traces by file, compound, or sample group
- Rename a trace or group
- Hide/show selected trace
- Lock/unlock trace color

### Trace / Series

Right-click an actual data trace.

- Trace color
- Line width
- Line style
- Opacity
- Marker size
- Marker shape
- Marker color
- Fill under curve
- Smoothing on/off
- Smoothing algorithm and parameters
- Normalize / raw intensity
- Baseline correction display
- Error bars for analysis traces
- Move trace to Y1/Y2
- Hide trace
- Rename trace

### Peak / Chromatogram Features

Right-click peak fill or peak boundary.

- Rename peak / compound
- Delete peak
- Deconvolute peak
- Integrate in all files
- Peak fill opacity
- Peak fill color lock by compound/retention time
- Show/hide peak label
- Show area, height, retention time, or compound name label
- Edit baseline endpoints
- Snap baseline to local valley
- Recompute area with current baseline

### Grid, Frame, And Canvas

Right-click empty plot area or frame.

- Plot background color
- Paper/background color
- Frame on/off
- Frame width
- Grid X/Y on/off
- Grid style
- Grid opacity
- Margins
- Figure width/height
- Export DPI
- Publication preset

### Subplots

Right-click a subplot panel, subplot title, or subplot axis.

- Rows / columns
- Subplot spacing
- Shared axis labels
- Sync zoom across subplots
- Per-subplot title
- Per-subplot axis label visibility
- Per-subplot Y range
- Reorder subplot
- Hide subplot
- Match Y range to another subplot

### LC-MS And Higher-Dimensional Plots

Right-click LC-MS-specific elements only when LC-MS data is active.

- Set scan line to clicked retention time
- Extract EIC from clicked m/z
- Change target m/z
- Change m/z tolerance
- Smooth spectrum display
- Normalize spectrum
- Set m/z range
- Label selected ion
- Copy selected scan metadata

## Suggested Expansion Order

1. Finish X-axis controls:
   label, scale, tick direction, tick length, minor ticks, grid X.
2. Add Y1-axis editor with equivalent controls.
3. Add Y2-axis editor, including enable/disable and association controls.
4. Add legend editor.
5. Add trace editor for color, line, marker, opacity, smoothing.
6. Add title/text editor.
7. Add subplot editor.
8. Add LC-MS-specific right-click editors.

## Settings Menu Strategy

The toolbox Plot Settings panel should remain the stable, complete control
surface for common settings. Right-click context menus should become the fast,
local editing surface for the thing the user is looking at.

Good candidates for toolbox:

- Plot type
- Main layout mode
- Common axis range and scale
- Theme and palette
- Broad trace styling
- Legend visibility
- Export dimensions

Good candidates for context menu only or context-first:

- Per-axis minor tick settings
- Per-axis tick formats
- Per-axis grid/frame behavior
- Per-subplot overrides
- Per-trace color/line/marker overrides
- Peak-specific actions
- LC-MS target ion tools

If a setting becomes important enough for repeated batch editing, mirror it into
the toolbox later. The context menu can safely lead because it edits the same
source-of-truth settings.
