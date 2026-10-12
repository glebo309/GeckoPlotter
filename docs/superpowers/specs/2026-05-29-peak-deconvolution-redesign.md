# Peak Deconvolution Redesign — One-Click Flow

Replaces the multi-step deconvolution mode (toggle → place markers → detect → fit → accept) with a single-button flow that operates on an already-integrated, selected peak.

## UX Flow

1. User integrates an overlapping region normally (draws baseline → one peak)
2. User clicks the peak to select it (`selected-peak-idx`)
3. User presses **Deconvolute** button (always visible in Integration panel)
   - No peak selected → status message: "Select a peak first"
   - Peak selected → auto-detect centers within `rt_start`–`rt_end`, fit EMG composite, show preview
4. Preview: colored sub-peak curves + composite dashed line + R² badge
5. Optional: click plot to add/remove centers → auto-refit on each change
6. **Accept** → original peak replaced by sub-peaks; **Cancel** → discard, restore original

## UI Layout (Integration Panel)

Replace the current 6-control deconvolution section with:

```
[Deconvolute]                    ← always visible, btn-primary (blue)
"Select a peak first"            ← status div, updates contextually
                                   (or R² badge + component count during preview)
[Accept] [Cancel]                ← only visible during preview
```

Removed: toggle button, prominence slider, Detect button, separate Fit button.

## Callback Redesign (`deconvolution_callbacks.py`)

### Deconvolute button click

```
Input:  deconv-btn.n_clicks
State:  selected-peak-idx, active-file, file-overlay-map
Output: baseline-mode, deconv-markers, deconv-result,
        deconv-status (children), render-trigger
```

Logic:
1. If `selected-peak-idx` is None → return "Select a peak first" in status div, no_update for everything else
2. Get the selected Peak from `peak_service.get_peaks(active_file)`
3. Extract signal data within `peak.rt_start` – `peak.rt_end` from data_manager
4. Call `auto_detect_centers(x, y, prominence=0.05)`
5. If fewer than 2 centers found → show "Could not detect multiple peaks in this region"
6. Call `fit_peaks(x, y, centers)`
7. Set `baseline-mode = 'deconvolve'`, store markers and serialized result
8. Bump render-trigger so `add_deconv_overlays` renders the preview
9. Show R² badge + "{n} components detected" in status div

### Marker click (adjust centers)

```
Input:  deconv-marker-click-store
State:  deconv-markers, baseline-mode, active-file, selected-peak-idx
Output: deconv-markers, deconv-result, deconv-status, render-trigger
```

Same as current but after adding/removing a marker, immediately re-runs `fit_peaks` and updates the preview. If only 1 marker remains, show warning but allow it (single-peak refit).

### Accept

```
Input:  deconv-accept-btn.n_clicks
State:  deconv-result, active-file, selected-peak-idx, file-overlay-map
Output: baseline-mode, deconv-markers, deconv-result, deconv-status,
        peak-change-trigger, selected-peak-idx, render-trigger
```

Logic:
1. Deserialize result → `result_to_peaks(result, file_id, region_rt)`
2. Remove the original peak: `peak_service.remove_peak(file_id, original_peak_id)`
3. Add each sub-peak via `add_baseline_peak(..., source='deconvolved', deconv_group=tag)`
4. Run `group_peaks_across_samples()`
5. Reset: baseline-mode='navigate', clear markers/result/status, bump peak-change-trigger
6. Clear selected-peak-idx

### Cancel

Reset all deconv state, baseline-mode='navigate', bump render-trigger.

## What Stays Unchanged

- **`deconvolution_service.py`**: `auto_detect_centers`, `fit_peaks`, `result_to_peaks`, `serialize/deserialize_result` — all reused as-is
- **`peak_overlay.py`**: `add_deconv_overlays` for rendering preview curves and markers
- **`peak_service.py`**: `deconv_group`, `fit_params` fields on Peak; cross-sample grouping by tag; `add_baseline_peak` with deconvolved source support
- **Stores**: `deconv-markers`, `deconv-result`, `deconv-marker-click-store` kept; `baseline-mode='deconvolve'` still used during preview
- **JS marker click**: `manual-integration.js` marker placement in deconvolve mode

## What Changes

| File | Change |
|------|--------|
| `app.py` | Replace 6-control section (lines 579-616) with single button + status div + Accept/Cancel. Remove `deconv-prominence` slider and `deconv-detect-btn`. Add `deconv-status` div. Rename `deconv-toggle-btn` → `deconv-btn`. |
| `deconvolution_callbacks.py` | Rewrite: button click does detect+fit in one shot using selected peak region. Remove toggle-mode callback. Remove standalone detect callback. Marker-click callback now auto-refits. |
| Tests | Update to reflect new flow (no separate detect step, button operates on selected peak). |

## Stores (final set)

| Store | Purpose |
|-------|---------|
| `baseline-mode` | 'deconvolve' during preview, else 'navigate'/'draw'/'edit' |
| `deconv-markers` | [{x, y}, ...] current peak centers |
| `deconv-result` | serialized DeconvResult for preview |
| `deconv-marker-click-store` | browser-side click {x, ts} |
| `deconv-results-container` | existing div — repurposed for status messages and R² badge |
| `selected-peak-idx` | existing — provides the peak to deconvolve |

## Verification

1. Load chromatogram with overlapping peaks
2. Integrate the overlapping region (draw baseline → single peak)
3. Click the peak to select it
4. Press Deconvolute → preview shows sub-peaks with R² badge
5. Click to add/remove a center → preview updates automatically
6. Accept → original peak gone, sub-peaks appear as normal filled peaks
7. Cancel → original peak restored
8. Press Deconvolute with no peak selected → "Select a peak first"
9. Load second file, deconvolve same region → cross-sample grouping works
10. Verify normal baseline integration still works (regression)
