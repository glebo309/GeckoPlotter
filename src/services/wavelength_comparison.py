"""Fixed-window PDA wavelength screening for the Workspace and MCP interface."""
from __future__ import annotations

from copy import copy

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


def _purity(ws, bundle, component, peak, payload, start, end):
    """Baseline-subtracted spectra at the reference trace's half-height flanks and apex."""
    x, y = ws._xy(component.component_id)
    order = np.argsort(x)
    x, y = x[order], y[order]
    corrected = y - np.interp(x, [start, end], np.interp([start, end], x, y))
    apex = int(np.argmin(abs(x - peak.rt)))
    left = np.flatnonzero((x > start) & (x < x[apex]))
    right = np.flatnonzero((x > x[apex]) & (x < end))
    times, _, matrix = _arrays(payload)
    if not len(left) or not len(right) or corrected[apex] <= 0:
        return {'sample': bundle.name, 'correlations': [], 'min_correlation': None}
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
    saturated = np.max(raw_spectra, axis=0) >= 1500
    finite = np.isfinite(spectra).all(axis=0) & ~saturated
    strength = np.max(abs(spectra[:, finite])) if finite.any() else 0
    keep = finite & (np.max(abs(spectra), axis=0) > max(strength * .01, 1e-9))
    correlations = []
    for a, b in [(0, 1), (1, 2), (0, 2)]:
        if keep.sum() >= 3 and min(np.std(spectra[a, keep]), np.std(spectra[b, keep])) > 1e-12:
            correlations.append(float(np.corrcoef(spectra[a, keep], spectra[b, keep])[0, 1]))
    return {'sample': bundle.name, 'times_min': [float(x[i]) for i in scans],
            'correlations': correlations, 'min_correlation': min(correlations) if correlations else None,
            'excluded_saturated_wavelengths': int(saturated.sum())}


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
    if wavelengths is None:
        maxima = ws.uv_spectrum(reference[1].name, rt, top=8)['maxima']
        maxima.sort(key=lambda m: -m['mAU'])
        # Reserve room for weaker analyte bands. The strongest UV maximum may already be saturated.
        fixed = [nm for nm in (205, 220, 254, 280, 210, 230) if low_nm <= nm <= high_nm]
        maxima = [m['nm'] for m in maxima if low_nm <= m['nm'] <= high_nm]
        original = (reference[2].metadata or {}).get('wavelength_nm')
        benchmark = [float(original)] if original is not None and low_nm <= float(original) <= high_nm else []
        wavelengths = list(dict.fromkeys(benchmark + maxima[:4] + fixed))[:8]
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
              'assessed': len(correlations) == len(purity_rows), 'standards': purity_rows,
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
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    recommendation = None
    if rows[0]['eligible']:
        best = rows[0]
        added = ws.add_uv_channel(best['requested_nm'], [b.name for b in targets])
        shown = next(r for r in added if r['sample'] == reference[1].name)
        recommendation = {'wavelength_nm': best['wavelength_nm'], 'channel': shown['channel'],
                          'sample': shown['sample'], 'eligible': True,
                          'reason': f"Lowest maximum back-calculated error among eligible wavelengths "
                                    f"({best['max_back_calculated_error_percent']:.2f}%); sensitivity breaks ties."}
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
        warnings.append('Spectral purity excludes pixels reaching 1500 mAU; their distorted spectra cannot establish coelution.')
    warnings.append('LOQ is a single-level S/N=10 estimate, not a validated quantitation limit; spectral correlation is a purity screen.')
    ws._record(f'Compared wavelengths for {peak} in {_names([r[1] for r in runs])}')
    return {'peak': peak, 'rt_start': start, 'rt_end': end,
            'baseline_rule': 'straight line between signal at fixed endpoints; signed area; no valley snapping',
            'reference_sample': reference[1].name, 'wavelengths': rows, 'recommendation': recommendation,
            'warnings': warnings + [f"{r['wavelength_nm']:g} nm: {w}" for r in rows for w in r['warnings']]}
