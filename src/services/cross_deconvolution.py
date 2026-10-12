"""Cross-file integration of one deconvolved component (GeckoPlotter V2).

"Integrate in All Files" on a peak that came out of a deconvolution must not
re-integrate the whole envelope in the other samples: only that component
(e.g. a small shoulder) is wanted. For each target file the source
deconvolution is replayed:

1. region    = the source region (the siblings' shared ``rt_start``/``rt_end``)
               widened by the RT tolerance, then cut at the first valley
               outside the source region so a neighbouring peak is not pulled in;
2. seeds     = the sibling RTs, each snapped to the nearest local maximum or
               curvature (shoulder) candidate within the tolerance;
3. fit       = ``DeconvolutionService.fit_peaks`` with one component per seed;
4. selection = the fitted component whose centre is closest to the clicked
               component's RT (within tolerance); only that one is stored,
               converted by ``result_to_peaks`` exactly as a manual deconvolution.

Pure computation, no Dash dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np
from scipy.signal import find_peaks, savgol_filter

from services.deconvolution_service import DeconvolutionService
from services.peak_service import Peak, PeakService

_REGION_EPS = 1e-6
_MIN_COMPONENT_AREA_FRAC = 0.002  # fitted component below this share of the total = collapsed
_MIN_R_SQUARED = 0.5
_SIGMA_LO, _SIGMA_HI = 0.4, 2.5  # allowed width change relative to the source fit
_GAMMA_LO = 0.5  # tailing rate may not drop below this fraction of the source's
_CENTER_FRAC = 0.5  # centre window as a fraction of the gap to the nearest seed


@dataclass
class CrossDeconvOutcome:
    """Result of integrating one deconvolved component across files."""

    integrated: List[Tuple[str, Peak]] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)  # (file_id, reason)


def deconv_siblings(peaks, peak: Peak) -> List[Peak]:
    """Peaks of the same deconvolution as *peak* (same file, same region), by RT."""
    if peak.source != 'deconvolved':
        return []
    sibs = [p for p in peaks
            if p.source == 'deconvolved'
            and abs(p.rt_start - peak.rt_start) < _REGION_EPS
            and abs(p.rt_end - peak.rt_end) < _REGION_EPS]
    if peak.peak_id not in {p.peak_id for p in sibs}:
        sibs.append(peak)
    return sorted(sibs, key=lambda p: p.rt)


def is_deconvolved_component(peaks, peak: Peak) -> bool:
    """True when *peak* is one of two or more components of a deconvolution."""
    return len(deconv_siblings(peaks, peak)) >= 2


def _noise(y: np.ndarray) -> float:
    d2 = np.diff(y, 2)
    if d2.size == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(d2 - np.median(d2))) / np.sqrt(6.0))


def _smooth(y: np.ndarray, points: int = 9) -> np.ndarray:
    if y.size < points:
        return y
    return np.convolve(np.pad(y, points // 2, mode='edge'),
                       np.ones(points) / points, mode='valid')


def _walk_to_valley(ys: np.ndarray, start: int, step: int, stop: int, thresh: float) -> int:
    """Walk outward from *start* to *stop* (inclusive); return the index of the
    running minimum, ending the walk once the signal climbs *thresh* above it."""
    best = start
    i = start
    while i != stop:
        i += step
        if ys[i] < ys[best]:
            best = i
        elif ys[i] - ys[best] > thresh:
            break
    return best


def target_region(x: np.ndarray, y: np.ndarray, rt_start: float, rt_end: float,
                  tol: float) -> Tuple[int, int]:
    """Index bounds (lo, hi inclusive) of the region to deconvolve in a target.

    Source region widened by *tol* on each side, but each side only as far as
    the first valley beyond the source bounds (the neighbouring peak stays out).
    """
    ys = _smooth(y)
    lo0 = int(np.searchsorted(x, rt_start))
    hi0 = int(min(np.searchsorted(x, rt_end), x.size - 1))
    lo_lim = int(np.searchsorted(x, rt_start - tol))
    hi_lim = int(min(np.searchsorted(x, rt_end + tol), x.size - 1))
    window = ys[lo_lim:hi_lim + 1]
    thresh = max(4.0 * _noise(y), 0.01 * float(np.ptp(window))) if window.size else 0.0
    lo = _walk_to_valley(ys, lo0, -1, lo_lim, thresh) if lo0 > lo_lim else lo0
    hi = _walk_to_valley(ys, hi0, +1, hi_lim, thresh) if hi0 < hi_lim else hi0
    return min(lo, lo0), max(hi, hi0)


def _candidates(svc: DeconvolutionService, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Local maxima and curvature (shoulder) positions in a region, sorted."""
    cands: List[float] = []
    noise = _noise(y)
    ys = _smooth(y)
    prom = max(5.0 * noise, 0.005 * float(np.ptp(y)))
    idx, _ = find_peaks(ys, prominence=prom)
    cands += [float(x[i]) for i in idx]
    try:
        cands += [cx for cx, _ in svc.auto_detect_centers(x, y, prominence=0.05)]
    except Exception:
        pass
    n = x.size
    if n >= 24 and float(np.ptp(np.diff(x))) <= 0.25 * float(np.median(np.diff(x))):
        dx = float(np.median(np.diff(x)))
        above = ys >= (ys.max() + ys.min()) / 2.0
        w = max(7, int(above.sum() / 2.5) | 1)
        w = min(w, n if n % 2 else n - 1)
        if w > 5:
            d2 = savgol_filter(y, w, 3, deriv=2, delta=dx)
            strongest = float(np.max(-d2))
            if strongest > 0:
                didx, _ = find_peaks(-d2, prominence=0.02 * strongest)
                margin = w // 2
                cands += [float(x[i]) for i in didx if margin <= i <= n - 1 - margin]
    return np.array(sorted(cands), dtype=float)


def snap_seeds(src_rts: List[float], cands: np.ndarray, tol: float,
               x_lo: float, x_hi: float) -> List[float]:
    """Snap each source RT to a distinct candidate within *tol*.

    Closest pairs are assigned first. Components without a candidate keep their
    source RT shifted by the median shift of the others.
    """
    seeds: List[Optional[float]] = [None] * len(src_rts)
    used = set()
    pairs = sorted((abs(c - r), i, j) for i, r in enumerate(src_rts)
                   for j, c in enumerate(cands) if abs(c - r) <= tol)
    for _, i, j in pairs:
        if seeds[i] is None and j not in used:
            seeds[i] = float(cands[j])
            used.add(j)
    shifts = [s - r for s, r in zip(seeds, src_rts) if s is not None]
    shift = float(np.median(shifts)) if shifts else 0.0
    out = [s if s is not None else float(np.clip(r + shift, x_lo, x_hi))
           for s, r in zip(seeds, src_rts)]
    return out


def _fwhm(x: np.ndarray, curve: np.ndarray) -> float:
    peak = float(curve.max())
    if peak <= 0:
        return 0.0
    above = np.where(curve >= peak / 2.0)[0]
    return float(x[above[-1]] - x[above[0]])


def integrate_component_in_file(
    svc: DeconvolutionService, x: np.ndarray, y: np.ndarray, file_id: str,
    src_peak: Peak, siblings: List[Peak], tol: float,
) -> Tuple[Optional[Peak], str]:
    """Replay the source deconvolution on one target signal.

    Returns ``(peak, '')`` with an unattached ``Peak`` (source 'deconvolved',
    name/label/deconv_group inherited from *src_peak*), or ``(None, reason)``.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 24:
        return None, 'too few points'
    rt_start, rt_end = siblings[0].rt_start, siblings[0].rt_end
    lo, hi = target_region(x, y, rt_start, rt_end, tol)
    xw, yw = x[lo:hi + 1], y[lo:hi + 1]
    if xw.size < 24:
        return None, 'region too narrow'

    src_rts = [p.rt for p in siblings]
    seeds = snap_seeds(src_rts, _candidates(svc, xw, yw), tol, float(xw[0]), float(xw[-1]))
    dx = float(np.median(np.diff(xw)))
    if any(b - a < 3 * dx for a, b in zip(seeds, seeds[1:])):
        return None, 'components could not be seeded apart'

    # Fit over the source region carried along with the RT drift (same width as
    # the source fit, so baseline and tailing limits behave alike), kept inside
    # the valley-bounded window.
    shift = float(np.median([s - r for s, r in zip(seeds, src_rts)]))
    r_lo = max(float(xw[0]), rt_start + shift)
    r_hi = min(float(xw[-1]), rt_end + shift)
    r_lo = min(r_lo, min(seeds) - 3 * dx)
    r_hi = max(r_hi, max(seeds) + 3 * dx)
    sel = (xw >= r_lo) & (xw <= r_hi)
    xr, yr = xw[sel], yw[sel]
    if xr.size < 24:
        return None, 'region too narrow'
    centers = [(s, float(np.interp(s, xr, yr))) for s in seeds]

    # Component widths come from the source fit: a shoulder must stay a narrow
    # bump instead of one broad component swallowing the neighbour's tail.
    sigma_bounds = []
    for p in siblings:
        sigma = (p.fit_params or {}).get('sigma')
        sigma_bounds.append((_SIGMA_LO * sigma, _SIGMA_HI * sigma) if sigma else None)
    # Each centre may move by half the distance to its nearest neighbour only,
    # so the shoulder component cannot slide onto the main peak's flank.
    order = np.argsort(seeds)
    center_bounds: List[Optional[Tuple[float, float]]] = [None] * len(seeds)
    for pos, i in enumerate(order):
        gaps = [abs(seeds[i] - seeds[j]) for j in order[max(0, pos - 1):pos + 2] if j != i]
        half = max(_CENTER_FRAC * min(gaps), 3 * dx)
        center_bounds[i] = (seeds[i] - half, seeds[i] + half)
    gamma_min = [(_GAMMA_LO * g if g else None)
                 for g in ((p.fit_params or {}).get('gamma') for p in siblings)]
    try:
        result = svc.fit_peaks(xr, yr, centers, sigma_bounds=sigma_bounds,
                               center_bounds=center_bounds, gamma_min=gamma_min)
    except Exception:
        return None, 'fit failed'
    if result is None:
        return None, 'fit failed'
    comps = result.components
    if len(comps) != len(siblings) or result.r_squared < _MIN_R_SQUARED:
        return None, 'fit failed'

    total = sum(max(c.area, 0.0) for c in comps)
    if total <= 0 or any(c.area <= _MIN_COMPONENT_AREA_FRAC * total for c in comps):
        return None, 'component count collapsed'
    apexes = sorted(float(xr[int(np.argmax(c.curve))]) for c in comps)
    fwhms = sorted(max(_fwhm(xr, c.curve), dx) for c in comps)
    if any(b - a < 0.15 * fwhms[0] for a, b in zip(apexes, apexes[1:])):
        return None, 'component count collapsed'

    distances = [abs(c.center - src_peak.rt) for c in comps]
    k = int(np.argmin(distances))
    if distances[k] > tol:
        return None, 'no component within tolerance'

    region_rt = float(np.mean([c.center for c in comps]))
    peaks = svc.result_to_peaks(result, file_id, region_rt)
    peak = peaks[k]
    peak.name = src_peak.name
    peak.label = src_peak.label
    peak.deconv_group = src_peak.deconv_group
    return peak, ''


def integrate_deconvolved_in_files(
    peak_service: PeakService,
    src_fid: str,
    src_peak: Peak,
    targets: List[str],
    get_xy: Callable[[str], Tuple[Optional[np.ndarray], Optional[np.ndarray]]],
    tol: float,
    name_of: Callable[[str], str] = str,
    svc: Optional[DeconvolutionService] = None,
) -> CrossDeconvOutcome:
    """Integrate the clicked deconvolved component in every target file.

    A previous integration of the same component (same ``deconv_group``) in a
    target is replaced, so running the command twice does not duplicate peaks.
    Does not regroup or save undo; the caller does.
    """
    svc = svc or DeconvolutionService()
    siblings = deconv_siblings(peak_service.get_peaks(src_fid), src_peak)
    out = CrossDeconvOutcome()
    for fid in targets:
        x, y = get_xy(fid)
        if x is None or y is None:
            out.skipped.append((fid, 'no signal'))
            continue
        peak, reason = integrate_component_in_file(svc, x, y, fid, src_peak, siblings, tol)
        if peak is None:
            out.skipped.append((fid, reason))
            continue
        if src_peak.deconv_group:
            for old in list(peak_service.get_peaks(fid)):
                if old.source == 'deconvolved' and old.deconv_group == src_peak.deconv_group:
                    peak_service.remove_peak(fid, old.peak_id)
        added = peak_service.add_baseline_peak(
            file_id=fid, area=peak.area, height=peak.height, apex_x=peak.rt,
            poly_x=peak.poly_x, poly_y=peak.poly_y, p_line=peak.p_line,
            q1=peak.q1, q2=peak.q2, source='deconvolved',
            deconv_group=peak.deconv_group, fit_params=peak.fit_params)
        added.name = peak.name
        added.label = peak.label
        out.integrated.append((fid, added))
    return out


def status_text(outcome: CrossDeconvOutcome, n_targets: int,
                name_of: Callable[[str], str] = str) -> str:
    ok = len(outcome.integrated)
    text = f'Integrated {ok}/{n_targets} files'
    if outcome.skipped:
        text += '; skipped: ' + ', '.join(f'{name_of(f)} ({r})' for f, r in outcome.skipped)
    return text + '.'
