"""Fixed-window PDA wavelength screening for the Workspace and MCP interface."""
from __future__ import annotations

from copy import copy
from time import perf_counter

import numpy as np
from scipy.integrate import trapezoid
from scipy.signal import find_peaks
from scipy.stats import f as f_distribution

from services.pda_service import _arrays, add_pda_chromatogram, extract_pda_views


def _fit(concentrations, areas):
    slope, intercept = np.polyfit(concentrations, areas, 1)
    residuals = areas - (slope * concentrations + intercept)
    sse = float(residuals @ residuals)
    total = float(np.sum((areas - areas.mean()) ** 2))
    back = (areas - intercept) / slope if slope > 0 else np.full(len(areas), np.nan)
    errors = [float(100 * (b - c) / c) if c > 0 and np.isfinite(b) else None
              for c, b in zip(concentrations, back)]
    curvature = {'quadratic_coefficient': None, 'p_value': None, 'significant': False,
                 'residuals': residuals.tolist()}
    if len(areas) >= 4 and len(np.unique(concentrations)) >= 3:
        coefficients = np.polyfit(concentrations, areas, 2)
        quadratic_sse = float(np.sum((areas - np.polyval(coefficients, concentrations)) ** 2))
        improvement = max(0., sse - quadratic_sse)
        # Roundoff in a perfectly linear calibration is not significant curvature.
        p = 1.0
        if improvement > max(total * 1e-12, 1e-24):
            statistic = improvement / max(quadratic_sse / (len(areas) - 3), np.finfo(float).tiny)
            p = float(f_distribution.sf(statistic, 1, len(areas) - 3))
        curvature.update(quadratic_coefficient=float(coefficients[0]), p_value=p, significant=p < .05)
    return {'slope': float(slope), 'intercept': float(intercept),
            'r_squared': 1 - sse / total if total > 0 else None,
            'max_back_calculated_error_percent': max((abs(e) for e in errors if e is not None), default=None),
            'curvature': curvature}, back, errors


def _trace(x, y, start, end):
    """Exact fixed endpoints, signed area over a straight baseline; no crossings or valleys trim the window."""
    from gecko_api import GeckoError, _baseline_noise
    order = np.argsort(x)
    x, y = np.asarray(x)[order], np.asarray(y)[order]
    if not np.isfinite(y).all() or x[0] > start or x[-1] < end:
        raise GeckoError('A standard has nonfinite signal or does not cover the peak window.')
    inside = (x > start) & (x < end)
    if np.count_nonzero(inside) < 3:
        raise GeckoError('Need at least three measured points inside the peak window.')
    tx = np.r_[start, x[inside], end]
    ends = np.interp([start, end], x, y)
    ty = np.interp(tx, x, y)
    corrected = ty - np.interp(tx, [start, end], ends)
    return {'area': float(trapezoid(corrected, tx)), 'height': float(max(0, corrected.max())),
            'raw_height': float(ty.max()), 'noise': _baseline_noise(x, y, start, end),
            'drift': float(ends[1] - ends[0]), 'offset': float(np.mean(ends)),
            'apex': float(tx[np.argmax(corrected)])}


def _ranges(wavelengths, mask):
    """Inclusive ranges of consecutive recorded pixels (not interpolated coverage)."""
    indices = np.flatnonzero(mask)
    return [[float(wavelengths[g[0]]), float(wavelengths[g[-1]])]
            for g in np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1) if len(g)]


def _flank_noise(x, matrix, start, end):
    """Vectorised robust noise, with narrow neighbours removed from the flank trend fit."""
    width = end - start
    left = (x >= start - 2 * width) & (x < start)
    right = (x > end) & (x <= end + 2 * width)

    def mad(y):
        return np.median(abs(y - np.median(y, axis=0)), axis=0) / .67448975

    # Never difference across the gap containing the peak.
    differences = np.concatenate([np.diff(matrix[m], axis=0) for m in (left, right)])
    noise = mad(differences) / np.sqrt(2) if len(differences) else np.zeros(matrix.shape[1])
    bx, by = x[left | right], matrix[left | right]
    if len(bx) >= 6:
        half = len(bx) // 2
        x1, x2 = np.median(bx[:half]), np.median(bx[half:])
        y1, y2 = np.median(by[:half], axis=0), np.median(by[half:], axis=0)
        residual = by - (y1 + (bx[:, None] - x1) * (y2 - y1) / (x2 - x1))
        background = abs(residual - np.median(residual, axis=0)) <= 3 * mad(residual)
        count = background.sum(axis=0)
        # Centring time keeps the masked least-squares calculation well conditioned.
        tx = (bx - bx.mean())[:, None]
        denominator = np.maximum(count, 1)
        mx = (tx * background).sum(axis=0) / denominator
        my = (by * background).sum(axis=0) / denominator
        variance = (background * (tx - mx) ** 2).sum(axis=0)
        slope = (background * (tx - mx) * (by - my)).sum(axis=0) / np.maximum(variance, 1e-30)
        refit = by - (my + slope * (tx - mx))
        residual = np.where((count >= 6) & (variance > 0), refit, residual)
        noise = np.maximum(noise, mad(residual))
    return noise


def _screen(arrays, concentrations, start, end, rt):
    """Measure all common reference pixels directly; never create a channel or copy a full PDA cube."""
    from gecko_api import GeckoError
    low = max(a[1].min() for a in arrays)
    high = min(a[1].max() for a in arrays)
    wavelengths = np.unique(arrays[-1][1])
    wavelengths = wavelengths[(wavelengths >= low) & (wavelengths <= high)]
    indices = [np.argmin(abs(nm[:, None] - wavelengths), axis=0) for _, nm, _ in arrays]
    measured = np.array([a[1][i] for a, i in zip(arrays, indices)])
    matched = np.ptp(measured, axis=0) <= 1
    excluded = wavelengths[~matched].tolist()
    wavelengths = wavelengths[matched]
    if not len(wavelengths):
        raise GeckoError('The standards have no matching PDA wavelengths (within 1 nm).')
    areas, heights, raw_heights, noises, apex_spectra = [], [], [], [], []
    low_index = int(np.flatnonzero(concentrations > 0)[0])
    for run_index, ((x, _, matrix), columns) in enumerate(zip(arrays, indices)):
        order = np.argsort(x)
        x = x[order]
        if x[0] > start or x[-1] < end:
            raise GeckoError('A standard does not cover the peak window.')
        inside = (x > start) & (x < end)
        if inside.sum() < 3:
            raise GeckoError('Need at least three measured points inside the peak window.')
        columns = columns[matched]

        def interpolate(t):
            hi = int(np.clip(np.searchsorted(x, t, side='right'), 1, len(x) - 1))
            lo = hi - 1
            weight = (t - x[lo]) / (x[hi] - x[lo])
            return (1 - weight) * matrix[order[lo], columns].astype(float) + weight * matrix[order[hi], columns]

        ends = np.array([interpolate(start), interpolate(end)])
        tx = np.r_[start, x[inside], end]
        ty = np.vstack([ends[0], matrix[np.ix_(order[inside], columns)], ends[1]])
        baseline = ends[0] + ((tx - start) / (end - start))[:, None] * (ends[1] - ends[0])
        corrected = ty - baseline
        areas.append(trapezoid(corrected, tx, axis=0))
        heights.append(np.maximum(0, corrected.max(axis=0)))
        raw_heights.append(ty.max(axis=0))
        apex_spectra.append(interpolate(rt) - (ends[0] + (rt - start) / (end - start) * (ends[1] - ends[0])))
        if run_index == low_index:
            flank_window = (x >= start - 2 * (end - start)) & (x <= end + 2 * (end - start))
            noises = _flank_noise(x[flank_window], matrix[np.ix_(order[flank_window], columns)].astype(float), start, end)
    areas = np.asarray(areas)
    centered = concentrations - concentrations.mean()
    slope = (centered[:, None] * areas).sum(axis=0) / (centered @ centered)
    intercept = areas.mean(axis=0) - slope * concentrations.mean()
    residual = areas - (concentrations[:, None] * slope + intercept)
    total = ((areas - areas.mean(axis=0)) ** 2).sum(axis=0)
    positive = concentrations > 0
    with np.errstate(divide='ignore', invalid='ignore'):
        r_squared = np.where(total > 0, 1 - (residual ** 2).sum(axis=0) / total, np.nan)
        errors = abs(100 * residual[positive] / slope / concentrations[positive, None])
        max_error = np.where(slope > 0, errors.max(axis=0), np.nan)
        snr = np.where(noises > 0, heights[low_index] / noises, np.nan)
    saturated = np.maximum(heights[-1], raw_heights[-1]) >= 1500
    noisy = ~np.isfinite(snr) | (snr < 10)
    nonlinear = ~np.isfinite(max_error) | (max_error > 15) | ~np.isfinite(r_squared) | (r_squared < .99)
    return dict(wavelengths=wavelengths, areas=areas, height_high=heights[-1], raw_height_high=raw_heights[-1],
                snr=snr, slope=slope, r_squared=r_squared, max_error=max_error, apex=apex_spectra[-1],
                saturated=saturated, too_noisy=noisy, non_linear=nonlinear,
                eligible=~saturated & ~noisy & (slope > 0) & np.isfinite(max_error),
                excluded_unmatched_nm=excluded)


def _screen_candidates(screen, original):
    """Bound detailed work to eight diverse candidates drawn from the measured curves."""
    nm, eligible = screen['wavelengths'], screen['eligible']
    error = np.where(eligible, screen['max_error'], np.inf)
    best = [int(i) for i in np.argsort(error) if np.isfinite(error[i])]
    benchmark = [int(np.argmin(abs(nm - float(original))))] if original is not None and nm[0] <= float(original) <= nm[-1] else []

    def maxima(values, mask):
        values = np.where(mask & np.isfinite(values), values, -np.inf)
        peaks, _ = find_peaks(np.r_[-np.inf, values, -np.inf])
        return sorted((int(i - 1) for i in peaks if np.isfinite(values[i - 1])), key=lambda i: -values[i])

    absorbance = maxima(screen['apex'], screen['apex'] > max(0, np.nanmax(screen['apex']) * .01))
    snr = maxima(screen['snr'], eligible)
    plateau = eligible & ~screen['non_linear'] & (error <= (error[best[0]] + 1 if best else 1))
    groups = np.split(np.flatnonzero(plateau), np.flatnonzero(np.diff(np.flatnonzero(plateau)) > 1) + 1)
    plateaus = [int(g[len(g) // 2]) for g in sorted(groups, key=len, reverse=True) if len(g)]
    # Boundaries of usable unsaturated bands, not the noise-only tail of the detector.
    groups = np.split(np.flatnonzero(eligible), np.flatnonzero(np.diff(np.flatnonzero(eligible)) > 1) + 1)
    edges = [int(i) for g in sorted(groups, key=len, reverse=True) if len(g) for i in (g[0], g[-1])]
    queues = [('best_linearity', best[:1]), ('original_channel', benchmark), ('absorbance_maximum', absorbance),
              ('snr_maximum', snr), ('linearity_plateau', plateaus), ('unsaturated_range_end', edges)]
    selected = {}
    # Round robin reserves room for each kind of evidence; deduplicate in physical nm.
    while any(q for _, q in queues) and len(selected) < 8:
        for reason, queue in queues:
            while queue:
                i = queue.pop(0)
                if i in selected:
                    if reason not in selected[i]:
                        selected[i].append(reason)
                    continue
                selected[i] = [reason]
                break
            if len(selected) == 8:
                break
    if not selected:
        selected[0] = ['detector_range_end']
    return {float(nm[i]): reasons for i, reasons in selected.items()}


def _screen_summary(screen, runs, candidates, elapsed):
    nm = screen['wavelengths']
    chosen = {int(np.argmin(abs(nm - wavelength))): reasons for wavelength, reasons in candidates.items()}
    ticks = np.arange(np.ceil(nm[0] / 10) * 10, nm[-1] + 1e-9, 10)
    indices = {0, len(nm) - 1, *chosen, *(int(np.argmin(abs(nm - tick))) for tick in ticks)}

    def number(value):
        return float(value) if np.isfinite(value) else None

    points = []
    for i in sorted(indices):
        points.append(dict(wavelength_nm=float(nm[i]), areas=[number(v) for v in screen['areas'][:, i]],
                           height_high_mau=number(screen['height_high'][i]),
                           raw_height_high_mau=number(screen['raw_height_high'][i]), snr_low=number(screen['snr'][i]),
                           r_squared=number(screen['r_squared'][i]),
                           max_back_calculated_error_percent=number(screen['max_error'][i]),
                           candidate_reasons=chosen.get(i, [])))
    return {'range_nm': [float(nm[0]), float(nm[-1])], 'wavelength_count': len(nm),
            'sampling': 'every matching recorded wavelength of the highest standard; nearest pixels within 1 nm',
            'standards': [{'sample': r[1].name, 'concentration': r[0]} for r in runs],
            'points': points, 'ranges_nm': {key: _ranges(nm, screen[key])
                for key in ('saturated', 'too_noisy', 'non_linear')},
            'thresholds': {'saturation_mau': 1500, 'snr_min': 10, 'r_squared_min': .99, 'max_error_percent': 15},
            'noise_method': 'robust first differences within flanks and outlier-detrended flanks',
            'excluded_unmatched_nm': screen['excluded_unmatched_nm'], 'elapsed_seconds': elapsed}


def _purity(ws, bundle, component, peak, payload, start, end):
    """Baseline-subtracted spectra at the reference trace's half-height flanks and apex."""
    x, y = ws._xy(component.component_id)
    order = np.argsort(x)
    x, y = x[order], y[order]
    corrected = y - np.interp(x, [start, end], np.interp([start, end], x, y))
    apex = int(np.argmin(abs(x - peak.rt)))
    left = np.flatnonzero((x > start) & (x < x[apex]))
    right = np.flatnonzero((x > x[apex]) & (x < end))
    times, wavelengths, matrix = _arrays(payload)
    if not len(left) or not len(right) or corrected[apex] <= 0:
        return {'sample': bundle.name, 'correlations': [], 'min_correlation': None,
                'wavelength_ranges_nm': [], 'wavelength_count': 0}
    half = corrected[apex] / 2
    scans = [left[np.argmin(abs(corrected[left] - half))], apex,
             right[np.argmin(abs(corrected[right] - half))]]
    lo, hi = [int(np.argmin(abs(times - t))) for t in (start, end)]
    spectra, raw_spectra = [], []
    for scan in scans:
        ti = int(np.argmin(abs(times - x[scan])))
        raw_spectra.append(matrix[ti])
        weight = (times[ti] - times[lo]) / (times[hi] - times[lo]) if hi != lo else 0
        spectra.append(matrix[ti].astype(float) - ((1 - weight) * matrix[lo] + weight * matrix[hi]))
    spectra = np.asarray(spectra)
    saturated = np.max([*raw_spectra, matrix[lo], matrix[hi]], axis=0) >= 1000
    finite = np.isfinite(spectra).all(axis=0) & ~saturated
    # Where the analyte clearly absorbs: 5 % of its strongest unsaturated absorbance and at least 3 mAU, so a band
    # far weaker than a saturated maximum (PEA near 257 nm against ~2000 mAU at 200 nm) still counts.
    strength = np.max(spectra[1, finite]) if finite.any() else 0
    keep = finite & (spectra[1] > max(strength * .05, 3.0))
    correlations = []
    for a, b in [(0, 1), (1, 2), (0, 2)]:
        if keep.sum() >= 3 and min(np.std(spectra[a, keep]), np.std(spectra[b, keep])) > 1e-12:
            correlations.append(float(np.corrcoef(spectra[a, keep], spectra[b, keep])[0, 1]))
    return {'sample': bundle.name, 'times_min': [float(x[i]) for i in scans],
            'correlations': correlations, 'min_correlation': min(correlations) if correlations else None,
            'excluded_saturated_wavelengths': int(saturated.sum()),
            'wavelength_ranges_nm': _ranges(wavelengths[np.argsort(wavelengths)], keep[np.argsort(wavelengths)]),
            'wavelength_count': int(keep.sum()), 'apex_absorbance_fraction': .05, 'minimum_mau': 3.0, 'saturation_limit_mau': 1000}


def _neighbours(x, y, start, end, rt, height, noise):
    width = end - start
    found, properties = find_peaks(y, prominence=max(5 * noise, .01 * height, 1e-9))
    in_window = [i for i in found if start <= x[i] <= end]
    analyte = min(in_window, key=lambda i: abs(x[i] - rt)) if in_window else None
    return [{'rt': float(x[i]), 'height_mau': float(prominence),
             'relative_height': float(prominence / height) if height > 0 else None}
            for i, prominence in zip(found, properties['prominences'])
            if abs(x[i] - rt) <= 2 * width and i != analyte]


def compare_wavelengths(ws, peak, standards, wavelengths, samples, rt_tolerance):
    from gecko_api import GeckoError, Workspace, _names
    if not standards or len(standards) < 2:
        raise GeckoError('Need at least two standards with the named peak.')
    if not np.isfinite(rt_tolerance) or rt_tolerance < 0:
        raise GeckoError('rt_tolerance must be finite and nonnegative.')
    runs = []
    for name, concentration in standards.items():
        try:
            concentration = float(concentration)
        except (TypeError, ValueError):
            raise GeckoError('Standard concentrations must be finite and nonnegative.') from None
        if not np.isfinite(concentration) or concentration < 0:
            raise GeckoError('Standard concentrations must be finite and nonnegative.')
        bundle = ws._sample(name)
        component, named = ws._find_peak(bundle, peak)
        source, payload = ws._pda_source(bundle)
        runs.append((concentration, bundle, component, named, source, payload))
    runs.sort(key=lambda r: r[0])
    concentrations = np.array([r[0] for r in runs])
    if len(np.unique(concentrations)) < 2 or concentrations[-1] <= 0:
        raise GeckoError('Need at least two distinct concentrations, including a positive standard.')
    if len({r[1].bundle_id for r in runs}) != len(runs):
        raise GeckoError('Each standard must resolve to a different sample.')
    reference = runs[-1]
    start, end, rt = map(float, (reference[3].rt_start, reference[3].rt_end, reference[3].rt))
    if not np.isfinite([start, end, rt]).all() or end <= start:
        raise GeckoError('The named peak has an invalid integration window.')
    for _, bundle, _, named, _, _ in runs:
        if abs(named.rt - rt) > rt_tolerance or not start < named.rt < end:
            raise GeckoError(f'{bundle.name}: named peak is outside the shared window or RT tolerance.')
    arrays = [_arrays(r[5]) for r in runs]
    low_nm = max(float(a[1].min()) for a in arrays)
    high_nm = min(float(a[1].max()) for a in arrays)
    if low_nm > high_nm:
        raise GeckoError('The standards have no common PDA wavelength range.')
    warnings = []
    screen_started = perf_counter()
    screen = _screen(arrays, concentrations, start, end, rt)
    selection = _screen_candidates(screen, (reference[2].metadata or {}).get('wavelength_nm'))
    screen_elapsed = perf_counter() - screen_started
    if wavelengths is None:
        wavelengths = list(selection)
    else:
        selection = {}  # The caller controls the detailed shortlist; the full screen is still returned.
    try:
        requested = [float(nm) for nm in wavelengths]
    except (TypeError, ValueError):
        raise GeckoError('wavelengths must be a list of finite numbers.') from None
    if not requested or not np.isfinite(requested).all() or any(not low_nm <= nm <= high_nm for nm in requested):
        raise GeckoError(f'Wavelengths must lie in the common PDA range {low_nm:g}-{high_nm:g} nm.')
    candidates, seen = [], set()
    for nm in requested:
        views = [extract_pda_views(r[5], nm) for r in runs]
        actual = tuple(v['measured_wavelength_nm'] for v in views)
        if max(actual) - min(actual) > 1:
            raise GeckoError(f'{nm:g} nm maps to different detector wavelengths across standards (over 1 nm).')
        if actual not in seen:
            candidates.append((nm, views[-1]['wavelength_nm']))
            selection.setdefault(actual[-1], ['requested'])
            seen.add(actual)
    if len(candidates) > 8:
        raise GeckoError('Compare at most eight distinct wavelengths at a time.')
    targets = [r[1] for r in runs]
    for bundle in ws._samples(samples) if samples is not None else []:
        if bundle.bundle_id not in {b.bundle_id for b in targets}:
            ws._pda_source(bundle)  # Fail before any real channels change.
            targets.append(bundle)
    purity_rows = [_purity(ws, r[1], r[2], r[3], r[5], start, end) for r in runs if r[0] > 0]
    correlations = [r['min_correlation'] for r in purity_rows if r['min_correlation'] is not None]
    purity = {'min_correlation': min(correlations) if correlations else None,
              'impure': any(c < .99 for c in correlations),
              'assessed': all(len(r['correlations']) == 3 for r in purity_rows), 'standards': purity_rows,
              'excluded_saturated_wavelengths': max((r.get('excluded_saturated_wavelengths', 0)
                                                    for r in purity_rows), default=0),
              'threshold': .99}
    # Share immutable signal arrays, but isolate bundle containers, metadata, visibility and history.
    scratch = Workspace()
    for _, bundle, _, _, _, _ in runs:
        cloned = copy(bundle)
        cloned.component_list = [copy(c) for c in bundle.component_list]
        for component in cloned.component_list:
            component.metadata = dict(component.metadata or {})
        cloned.components = {}
        for component in cloned.component_list:
            cloned.components.setdefault(component.role, component)
        scratch.store.add_bundle(cloned)
    low_index = int(np.flatnonzero(concentrations > 0)[0])
    rows = []
    for requested_nm, actual_nm in candidates:
        measurements, neighbours = [], []
        for concentration, bundle, _, named, source, payload in runs:
            component_id = add_pda_chromatogram(scratch.store, source, requested_nm)
            x, y = scratch._xy(component_id)
            measured = _trace(x, y, start, end)
            view = extract_pda_views(payload, requested_nm)
            nearby = _neighbours(x, y, start, end, named.rt, measured['height'], measured['noise'])
            neighbours.extend(dict(n, sample=bundle.name) for n in nearby)
            measurements.append(dict(measured, sample=bundle.name, concentration=concentration,
                                     measured_nm=view['measured_wavelength_nm'], rt_start=start, rt_end=end))
        fit, back, errors = _fit(concentrations, np.array([m['area'] for m in measurements]))
        for m, b, error in zip(measurements, back, errors):
            m.update(back_calculated=float(b) if np.isfinite(b) else None, error_percent=error)
        low, high = measurements[low_index], measurements[-1]
        snr = low['height'] / low['noise'] if low['noise'] > 0 else None
        saturated = max(high['height'], high['raw_height']) >= 1500
        gradient = actual_nm < 220 and any(abs(m['drift']) > max(3 * m['noise'], .1 * m['height']) or
                                          abs(m['offset']) > max(3 * m['noise'], .1 * m['height']) for m in measurements)
        reasons, notes = [], []
        if saturated:
            reasons.append('Highest standard reaches 1500 mAU: possible detector saturation/non-linearity.')
        elif max(high['height'], high['raw_height']) >= 1000:
            notes.append('Highest standard exceeds 1000 mAU; check detector linearity.')
        if snr is None or snr < 10:
            reasons.append('Lowest positive standard has S/N < 10 or unmeasurable baseline noise.')
        if fit['slope'] <= 0 or fit['max_back_calculated_error_percent'] is None:
            reasons.append('No positive calibration response.')
        if fit['curvature']['significant']:
            notes.append('Significant quadratic curvature (nested F test, p < 0.05).')
        if fit['max_back_calculated_error_percent'] is not None and fit['max_back_calculated_error_percent'] > 15:
            notes.append('At least one standard back-calculates more than 15% off.')
        if gradient:
            notes.append('Low wavelength shows elevated baseline/drift: possible gradient or solvent absorbance.')
        rows.append(dict(fit, wavelength_nm=actual_nm, requested_nm=requested_nm, area_low=low['area'],
                         area_high=high['area'], height_high_mau=high['height'], raw_height_high_mau=high['raw_height'],
                         saturated=saturated, snr_low=snr,
                         loq_estimate=low['concentration'] * 10 / snr if snr and snr > 0 else None,
                         baseline={'drift_mau': max(abs(m['drift']) for m in measurements),
                                   'noise_mau': low['noise'], 'gradient_or_solvent': gradient,
                                   'noise_method': 'robust first differences and detrended flanks outside the peak'},
                         purity=purity, selectivity={'neighbours': neighbours,
                            'max_relative_height': max((n['relative_height'] for n in neighbours
                                                       if n['relative_height'] is not None), default=0.)},
                         standards=measurements, eligible=not reasons, warnings=reasons + notes))
    rows.sort(key=lambda r: (not r['eligible'], round(r['max_back_calculated_error_percent'], 6)
                             if r['max_back_calculated_error_percent'] is not None else float('inf'), -r['slope']))
    # Linearity within 3 percentage points of the best is a tie (a few % is integration noise): then the better
    # S/N at the lowest standard wins.
    eligible = [r for r in rows if r['eligible'] and r['max_back_calculated_error_percent'] is not None]
    if eligible:
        limit = eligible[0]['max_back_calculated_error_percent'] + 3
        tied = [r for r in eligible if r['max_back_calculated_error_percent'] <= limit]
        tied.sort(key=lambda r: -(r['snr_low'] or 0))
        rows = tied + [r for r in rows if r not in tied]
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    recommendation = None
    if rows[0]['eligible']:
        best = rows[0]
        added = ws.add_uv_channel(best['requested_nm'], [b.name for b in targets])
        shown = next(r for r in added if r['sample'] == reference[1].name)
        recommendation = {'wavelength_nm': best['wavelength_nm'], 'channel': shown['channel'],
                          'sample': shown['sample'], 'eligible': True,
                          'reason': f"Best S/N ({best['snr_low']:.0f} at the lowest standard) among the most linear "
                                    f"wavelengths (max back-calculated error {best['max_back_calculated_error_percent']:.1f}%, "
                                    f"within 3 points of the best)."}
    else:
        warnings.append('No wavelength passes the saturation and S/N screening; inspect the ranked results.')
    # Purity is the peak's, not a wavelength's: it does not choose between them, it qualifies the whole calibration.
    if purity['impure']:
        warnings.append(f"The analyte spectrum changes across the peak (lowest correlation {purity['min_correlation']:.3f}, "
                        'below 0.99): possible co-elution; check the PDA spectra of the peak before trusting any '
                        'wavelength.')
    elif not purity['assessed']:
        warnings.append('Spectral purity could not be assessed in every standard.')
    if len(runs) < 4:
        warnings.append('Fewer than four standards: quadratic significance cannot be assessed; two-point linearity is uninformative.')
    if concentrations[0] == 0:
        warnings.append('Blank included in the fit; percentage error is undefined at zero. S/N and LOQ use the lowest positive standard.')
    if purity['excluded_saturated_wavelengths']:
        warnings.append('Spectral purity uses clear apex absorbance (>10% of its maximum) and excludes pixels reaching '
                        '1000 mAU in any spectrum used, including baseline endpoints; see its wavelength_ranges_nm.')
    warnings.append('LOQ is a single-level S/N=10 estimate, not a validated quantitation limit; spectral correlation is a purity screen.')
    ws._record(f'Compared wavelengths for {peak} in {_names([r[1] for r in runs])}')
    return {'peak': peak, 'rt_start': start, 'rt_end': end,
            'baseline_rule': 'straight line between signal at fixed endpoints; signed area; no valley snapping',
            'reference_sample': reference[1].name, 'wavelengths': rows, 'recommendation': recommendation,
            'purity': purity, 'screen': _screen_summary(screen, runs, selection, screen_elapsed),
            'warnings': warnings + [f"{r['wavelength_nm']:g} nm: {w}" for r in rows for w in r['warnings']]}
