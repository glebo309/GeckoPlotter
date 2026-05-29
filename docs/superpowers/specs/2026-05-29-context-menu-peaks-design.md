# Right-Click Context Menu: Peaks

Add a right-click context menu on peak polygons in the plot. First target in a multi-phase context menu rollout (plot background and file tree come later).

## Actions

Three actions when right-clicking a peak:

1. **Delete Peak** — remove the peak from PeakService, re-render overlay
2. **Rename Peak** — set peak.name/peak.label via inline input
3. **Integrate in All Files** — find and integrate the same peak across all files in the overlay group

## Menu Implementation

**Event capture**: Add `contextmenu` event listener in `manual-integration.js`. On right-click:
- Call `e.preventDefault()` to suppress Plotly/browser default menu
- Run `peakIdAtEvent()` to identify if a peak was clicked
- If peak found: publish `{peak_id, file_id, mouse_x, mouse_y}` to `context-menu-store`
- If no peak: do nothing (future: plot background menu)

**Menu rendering**: A `dmc.Menu` component in the layout, controlled by `context-menu-store`. Python callback reads the store, sets `opened=True`, positions the Menu at `(mouse_x, mouse_y)` via a wrapper div with absolute positioning. Menu items wired to individual action stores.

**Dismissal**: Click outside, Escape key, or clicking an action closes the menu (DMC Menu handles this natively via `opened` prop).

## Cross-File Peak Integration ("Integrate in All Files")

When the user selects this action on a peak:

### Algorithm

1. **Identify overlay group**: Find all files sharing the same overlay group as the source file (same `source_category` + `x_axis`)
2. **Search window**: Use source peak's RT as center, search +/- `rt_match_tolerance` (default 0.3 min, user-configurable in Integration panel)
3. **For each target file** (skip the source file, it already has the peak):
   a. Get signal data via `get_xy_arrays(file_id)`
   b. Optionally apply baseline correction via `IntegrationService.process_signal()` using that file's stored settings
   c. Within the RT window, find the most prominent local maximum (`scipy.signal.find_peaks` with prominence filtering)
   d. **Validate**: If no peak found above noise threshold, skip this file (no phantom peaks)
   e. **Find boundaries**: Use the existing slope-walking algorithm from `PeakService.detect_peaks()` to find rt_start and rt_end
   f. **Integrate**: Draw straight baseline between signal values at rt_start and rt_end, compute area via trapezoid integration, generate poly_x/poly_y
   g. **Create peak**: Call `peak_service.add_baseline_peak()` with `source='cross_integrated'`, inheriting the source peak's name/label
4. **Re-group**: Call `group_peaks_across_samples()` to update cross-sample groups
5. **Feedback**: Show brief status ("Integrated in 4/5 files" or "Peak not found in 2 files")

### RT Match Tolerance Setting

New `dmc.NumberInput` in the Integration panel:
- ID: `int-rt-tolerance`
- Default: 0.3 min
- Range: 0.05 to 1.0 min, step 0.05
- Label: "RT match tolerance (min)"
- Used by the cross-file integration algorithm

### Edge Cases

- **Peak already exists in target file at that RT**: Apply >50% overlap replacement logic (existing behavior)
- **No peak found in target file**: Skip silently, report count in status message
- **Target file has different baseline**: Use that file's own IntegrationSettings for baseline correction
- **Only one file in group**: Action is disabled/hidden in the menu

## Files to Create

- `src/callbacks/context_menu_callbacks.py` — menu action handlers (delete, rename, cross-file integrate)

## Files to Modify

- `src/assets/js/manual-integration.js` — add `contextmenu` event listener, suppress default, publish to store
- `app.py` — add `context-menu-store` (dcc.Store), `dmc.Menu` component in layout, RT tolerance NumberInput in Integration panel
- `src/services/peak_service.py` — new method `find_matching_peak(file_id, target_rt, tolerance, signal, time)` that finds and integrates a peak in a specific RT window
- `src/callbacks/peak_overlay.py` — no changes expected (peaks render normally after creation)

## Verification

1. Right-click a peak → menu appears at cursor position with three actions
2. Click away → menu closes
3. Delete Peak → peak removed, overlay updated
4. Rename Peak → input appears, type name, peak label updates in table and overlay
5. Integrate in All Files → peaks appear in other files at matching RT, status message shows count
6. Right-click where no peak exists → no menu (Plotly default also suppressed)
7. Verify existing left-click interactions (select, draw, pan) are unaffected
8. Verify cross-file integration skips files where peak is absent
9. Verify cross-file integration replaces existing overlapping peaks
