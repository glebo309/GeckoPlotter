# Peak Deconvolution (EMG via lmfit)

Resolve co-eluting/overlapping peaks by fitting a composite Exponentially Modified Gaussian model. User marks approximate peak centers, lmfit fits the composite, and each component becomes a standard Peak object.

## Architecture

### DeconvolutionService (`src/services/deconvolution_service.py`)

Pure computation, no Dash dependency. Ported from the validated sandbox at `../deconvolution_sandbox/app.py`.

**Public methods:**

- `auto_detect_centers(x, y, prominence=0.05) -> List[Tuple[float, float]]`
  - Uses `scipy.signal.find_peaks` with relative prominence threshold
  - Returns list of (x, y) center positions

- `fit_peaks(x, y, centers: List[Tuple[float, float]]) -> DeconvResult`
  - Builds composite lmfit model: one `ExponentialGaussianModel(prefix=f"p{i}_")` per center
  - Parameter bounds: sigma in [0.1%, 20%] of x-range; gamma in [0.001, 30%] of x-range
  - Initial amplitude from peak height at center * 10
  - max_nfev=5000
  - Returns `DeconvResult` dataclass

- `result_to_peaks(result: DeconvResult, file_id, region_rt) -> List[Peak]`
  - Converts each fitted component to a standard `Peak` object
  - Generates `poly_x`/`poly_y` from the EMG curve (closed polygon with baseline at y=0)
  - Sets `source='deconvolved'`, `deconv_group=f"deconv_{region_rt:.1f}_c{i}"`
  - Computes area via `np.trapz` on the individual curve

**Data structures:**

```python
@dataclass
class DeconvComponent:
    index: int
    center: float
    amplitude: float
    sigma: float
    gamma: float
    area: float
    curve: np.ndarray  # y-values of individual fitted curve

@dataclass
class DeconvResult:
    x: np.ndarray
    best_fit: np.ndarray
    residuals: np.ndarray
    r_squared: float
    redchi: float
    components: List[DeconvComponent]
```

### Peak dataclass changes (`src/services/peak_service.py`)

Add two optional fields to the existing `Peak` dataclass:

- `deconv_group: Optional[str] = None` — tag like `"deconv_5.2_c1"` for cross-sample matching
- `fit_params: Optional[Dict] = None` — stores `{sigma, gamma, amplitude}` for display/re-fit

### Cross-sample grouping update (`peak_service.group_peaks_across_samples`)

When grouping peaks with `source='deconvolved'`, match by `deconv_group` tag instead of RT proximity. This prevents two components at RT 5.1 and 5.2 from colliding into the same group. Non-deconvolved peaks continue using the existing RT window logic.

## Interaction Flow

### Mode entry

New "Deconvolve" toggle button in the Integration panel (alongside the existing Draw toggle). Activates deconv mode, stored in `baseline-mode` store as `'deconvolve'`.

### Marker placement (auto + manual)

When deconv mode is active:

1. **Auto-detect**: Prominence slider (1-50%, default 5%) + "Detect" button in the Integration panel. Runs `auto_detect_centers()`, places vertical dashed-line markers at detected positions.
2. **Manual add**: Click plot to place a marker at the clicked x-position. Snaps to nearest local maximum within a small window.
3. **Manual remove**: Click an existing marker to remove it.
4. Markers stored in `deconv-markers` store as `[{x, y}, ...]`.
5. Markers rendered as vertical dashed lines with small circle at the peak, using Plotly shapes (not traces).

### Fitting

"Fit" button in the Integration panel. Runs `DeconvolutionService.fit_peaks()`.

**Results display** (inline in Integration panel):
- R² badge (green >0.99, orange >0.95, red otherwise)
- Per-component table: #, Center, Area, sigma, gamma

**Plot overlay** (while reviewing, before accept):
- Individual fitted curves as semi-transparent colored lines
- Composite fit as dashed black line
- Original data unchanged

### Accept / Cancel

- **Accept**: Calls `result_to_peaks()` to convert components to standard `Peak` objects. Passes each through `peak_service.add_baseline_peak()` with overlap replacement (>50% overlap removes existing peaks in the region). Clears markers and overlays, returns to Navigate mode.
- **Cancel** (or Escape): Clears markers and overlays, returns to Navigate mode. No peaks created.

### After acceptance

Deconvolved peaks behave identically to any other peak: selectable, deletable, editable (though re-drawing a baseline over them replaces them), groupable across samples, usable for calibration. The `source='deconvolved'` field distinguishes them in the UI (e.g. peak table shows "Deconv" badge).

## Files to create

- `src/services/deconvolution_service.py` — fitting engine + data structures

## Files to modify

- `src/services/peak_service.py` — add `deconv_group` and `fit_params` fields to Peak; update `group_peaks_across_samples()` to match by deconv_group
- `src/callbacks/baseline_callbacks.py` — add deconv mode handling, marker management, fit/accept/cancel callbacks
- `src/callbacks/peak_overlay.py` — render deconv preview overlays (fitted curves before accept)
- `src/assets/js/manual-integration.js` — marker click-to-place in deconv mode (distinct from baseline draw)
- `app.py` — add Deconvolve button, prominence slider, Detect/Fit/Accept/Cancel buttons, deconv-markers store, results display area in Integration panel

## Verification

1. Load a chromatogram with overlapping peaks
2. Enter Deconvolve mode, auto-detect centers, verify markers appear at correct positions
3. Add/remove markers manually by clicking
4. Fit — verify R² > 0.95, fitted curves overlay correctly
5. Accept — verify peaks appear as normal filled polygons, selectable and deletable
6. Load a second file with similar peaks, deconvolve, verify cross-sample grouping matches components correctly by deconv_group tag
7. Verify existing baseline integration still works (no regression in Draw mode)
