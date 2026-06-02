# Plot Context Menus

## Working Example

The first implementation is intentionally small: right-clicking the main plot
X-axis opens an `X-axis` editor with the same axis-range controls used by Plot
Settings:

- Auto range
- X min
- X max

The panel does not own separate settings. It reads from and writes to
`current-plot-settings`, then mirrors the matching Plot Settings controls
(`pt-auto-range`, `pt-x-min`, `pt-x-max`) so both entry points stay synced.

## Workflow

1. Browser-side JS detects a right-click on a Plotly X-axis band.
2. JS publishes `{axis: "x", subplot, x, y, viewport_width, viewport_height}` to
   `axis-context-menu-store`.
3. Dash positions a small fixed panel at the cursor.
4. Dash hydrates the panel from `current-plot-settings`.
5. Editing the context panel writes back to `current-plot-settings` and mirrors
   the corresponding Plot Settings controls.
6. Existing plot render callbacks rebuild the plot from `current-plot-settings`.

## Design Principles

- **One source of truth:** context menus must not create independent plot-setting
  state. They are alternate surfaces for the same settings.
- **Small, local editors:** a context menu edits only what the user clicked
  (`X-axis` here), not the whole Plot Settings toolbox.
- **Bidirectional sync:** changing a context-menu control updates the toolbox;
  changing the toolbox updates an open context menu.
- **Progressive scope:** start with one axis and a few controls. Expand only when
  the state sync and event targeting are stable.
- **No hidden side effects:** right-clicking an axis opens an editor; it should
  not change plot values until a control is edited.
- **Keep plot interactions intact:** axis context detection should only fire in
  the axis band, leaving peak right-click and normal plot interactions alone.

## Known Difficulties

- **Plotly hit testing:** Plotly does not expose a simple "right-clicked x-axis"
  event. The browser code infers it from subplot geometry (`_fullLayout._plots`,
  axis offsets, and the cartesian drag layer).
- **Subplots:** the proof of concept stores the subplot key but edits the shared
  global X-axis settings. Per-subplot axis editing will need an explicit mapping
  from clicked subplot axis to setting keys.
- **Dash feedback loops:** the toolbox controls and context controls both write
  the same store. Callbacks must no-op when values are unchanged to avoid render
  loops.
- **Categorical axes:** `X min` / `X max` make sense for numeric axes. Categorical
  axes may need different context controls later.
- **Portal and stacking behavior:** peak menus use Mantine portals. The axis
  panel is a custom fixed panel so it can host synced form controls directly.
