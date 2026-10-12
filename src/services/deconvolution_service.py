"""Peak deconvolution service for GeckoPlotter V2.

Resolves co-eluting / overlapping peaks by fitting a composite Exponentially
Modified Gaussian (EMG) model with lmfit. Pure computation — no Dash
dependency. Logic is ported from the validated sandbox at
``../deconvolution_sandbox/app.py``.

Typical flow:
    centers = svc.auto_detect_centers(x, y)        # or user-placed markers
    result  = svc.fit_peaks(x, y, centers)         # composite EMG fit
    peaks   = svc.result_to_peaks(result, fid, rt) # standard Peak objects
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from lmfit.models import ExponentialGaussianModel
from lmfit import Model
from scipy.optimize import brentq, nnls
from scipy.special import erfcx
from scipy.signal import find_peaks, savgol_filter, savgol_coeffs
from scipy.integrate import trapezoid

from services.peak_service import Peak, OKABE_ITO_PALETTE


def _emg_mode_offset(sigma, gamma):
    target = np.sqrt(2 / np.pi) / (sigma * gamma)
    z = brentq(lambda value: erfcx(value) - target, -26., max(10., sigma * gamma))
    return gamma * sigma ** 2 - np.sqrt(2) * sigma * z


def _apex_emg(x, amplitude, center, sigma, gamma):
    # This model's center control denotes the actual apex, not the Gaussian
    # center hidden inside an exponentially modified Gaussian.
    return ExponentialGaussianModel().eval(x=x, amplitude=amplitude,
        center=center - _emg_mode_offset(sigma, gamma), sigma=sigma, gamma=gamma)


@dataclass
class DeconvComponent:
    """One fitted EMG component within a composite deconvolution."""

    index: int
    center: float
    amplitude: float
    sigma: float
    gamma: float
    area: float
    curve: np.ndarray  # y-values of the individual fitted curve over x


@dataclass
class DeconvResult:
    """Full result of a composite EMG fit over a region."""

    x: np.ndarray
    baseline: np.ndarray
    best_fit: np.ndarray
    residuals: np.ndarray
    r_squared: float
    redchi: float
    components: List[DeconvComponent] = field(default_factory=list)


def serialize_result(result: DeconvResult) -> dict:
    """Convert a DeconvResult into a JSON-safe dict for a dcc.Store."""
    render_x = DeconvolutionService._render_x(result.x)
    render_baseline, render_components, stack_bottoms, stack_tops = (
        DeconvolutionService._render_component_stacks(result, render_x)
    )
    return {
        "x": np.asarray(result.x, dtype=float).tolist(),
        "baseline": np.asarray(result.baseline, dtype=float).tolist(),
        "render_x": render_x.tolist(),
        "render_baseline": render_baseline.tolist(),
        "best_fit": np.asarray(result.best_fit, dtype=float).tolist(),
        "render_best_fit": (np.sum(render_components, axis=0) + render_baseline).tolist(),
        "residuals": np.asarray(result.residuals, dtype=float).tolist(),
        "r_squared": float(result.r_squared),
        "redchi": float(result.redchi),
        "components": [
            {
                "index": c.index,
                "center": c.center,
                "amplitude": c.amplitude,
                "sigma": c.sigma,
                "gamma": c.gamma,
                "area": c.area,
                "curve": np.asarray(c.curve, dtype=float).tolist(),
                "render_curve": render_curve.tolist(),
                "render_stack_bottom": stack_bottom.tolist(),
                "render_stack_top": stack_top.tolist(),
            }
            for c, render_curve, stack_bottom, stack_top in zip(
                result.components, render_components, stack_bottoms, stack_tops
            )
        ],
    }


def deserialize_result(payload: dict) -> DeconvResult:
    """Rebuild a DeconvResult from a serialized dict."""
    return DeconvResult(
        x=np.asarray(payload["x"], dtype=float),
        baseline=np.asarray(
            payload.get("baseline", np.zeros(len(payload["x"]))), dtype=float
        ),
        best_fit=np.asarray(payload["best_fit"], dtype=float),
        residuals=np.asarray(payload["residuals"], dtype=float),
        r_squared=float(payload["r_squared"]),
        redchi=float(payload["redchi"]),
        components=[
            DeconvComponent(
                index=c["index"],
                center=c["center"],
                amplitude=c["amplitude"],
                sigma=c["sigma"],
                gamma=c["gamma"],
                area=c["area"],
                curve=np.asarray(c["curve"], dtype=float),
            )
            for c in payload["components"]
        ],
    )


class DeconvolutionService:
    """EMG peak deconvolution. Stateless — safe to instantiate per call."""

    # Fraction of a component's peak height below which it is clipped out of
    # the rendered polygon (keeps the filled shape tight around the peak).
    _CURVE_FLOOR_FRAC = 1e-3
    _RENDER_POINTS = 800

    @staticmethod
    def _render_x(x: np.ndarray) -> np.ndarray:
        """Dense x-grid for smooth component fills without changing the fit."""
        x = np.asarray(x, dtype=float)
        if x.size < 2:
            return x
        return np.linspace(float(x[0]), float(x[-1]), max(x.size, DeconvolutionService._RENDER_POINTS))

    @staticmethod
    def _interp_baseline(
        source_x: np.ndarray, source_baseline: np.ndarray, target_x: np.ndarray
    ) -> np.ndarray:
        """Interpolate a fitted region baseline onto another x-grid."""
        source_x = np.asarray(source_x, dtype=float)
        source_baseline = np.asarray(source_baseline, dtype=float)
        target_x = np.asarray(target_x, dtype=float)
        if source_x.size < 2 or source_baseline.size != source_x.size:
            return np.zeros_like(target_x)
        return np.interp(target_x, source_x, source_baseline)

    @staticmethod
    def _estimate_local_baseline(y: np.ndarray) -> np.ndarray:
        """Estimate a flat local signal floor from the selected region itself."""
        y = np.asarray(y, dtype=float)
        if y.size == 0:
            return y
        edge_n = max(3, min(y.size // 10, 25))
        edge_vals = np.concatenate([y[:edge_n], y[-edge_n:]])
        finite = edge_vals[np.isfinite(edge_vals)]
        floor = float(np.nanpercentile(finite, 20)) if finite.size else 0.0
        floor = max(0.0, floor)
        return np.full_like(y, floor, dtype=float)

    @staticmethod
    def _eval_component(comp: DeconvComponent, x: np.ndarray) -> np.ndarray:
        """Evaluate one fitted EMG component on an arbitrary x-grid."""
        model = ExponentialGaussianModel()
        curve = model.eval(
            x=x,
            amplitude=comp.amplitude,
            center=comp.center,
            sigma=comp.sigma,
            gamma=comp.gamma,
        )
        return np.maximum(np.asarray(curve, dtype=float), 0.0)

    @staticmethod
    def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
        """Smooth 0→1 transition between two x positions."""
        if edge0 == edge1:
            return (x >= edge1).astype(float)
        lo, hi = sorted((edge0, edge1))
        t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
        y = t * t * (3.0 - 2.0 * t)
        return y if edge0 < edge1 else 1.0 - y

    @staticmethod
    def _render_component_stacks(
        result: DeconvResult, x: np.ndarray
    ) -> Tuple[np.ndarray, List[np.ndarray], List[np.ndarray], List[np.ndarray]]:
        """Build hybrid component bands for visual peak fills.

        The overlap-facing side follows the fitted component. The outside,
        clean side follows the measured chromatogram so it sits neatly under
        the visible curve without redistributing area between peaks.
        """
        baseline = DeconvolutionService._interp_baseline(
            result.x, result.baseline, x
        )
        signal = np.interp(x, result.x, result.best_fit + result.residuals)
        components = [
            DeconvolutionService._eval_component(comp, x) for comp in result.components
        ]
        if not components:
            return baseline, [], [], []

        bottoms: List[np.ndarray] = []
        tops: List[np.ndarray] = []
        centers = [comp.center for comp in result.components]
        for i, curve in enumerate(components):
            component_top = curve + baseline
            measured_top = np.maximum(signal, baseline)
            clean_weight = np.zeros_like(x)

            if len(components) == 1:
                clean_weight = np.ones_like(x)
            elif i == 0:
                next_mid = (centers[i] + centers[i + 1]) / 2.0
                clean_weight = 1.0 - DeconvolutionService._smoothstep(
                    centers[i], next_mid, x
                )
            elif i == len(components) - 1:
                prev_mid = (centers[i - 1] + centers[i]) / 2.0
                clean_weight = DeconvolutionService._smoothstep(
                    prev_mid, centers[i], x
                )

            top = clean_weight * measured_top + (1.0 - clean_weight) * component_top
            bottom = baseline.copy()
            bottoms.append(bottom)
            tops.append(top)
        return baseline, components, bottoms, tops

    # ------------------------------------------------------------------
    # Auto-detection
    # ------------------------------------------------------------------

    # Shoulder detection / model-selection tuning (see ``auto_detect_centers``).
    _MAX_SHOULDERS = 3
    _MIN_POINTS_ACROSS_PEAK = 8      # FWHM in samples needed to look for shoulders
    _APEX_NOISE_SIGMAS = 8.0         # apex prominence floor in noise sigmas
    _D2_NOISE_SIGMAS = 6.0           # d2 prominence must exceed this many noise sigmas
    _D2_MIN_REL_PROMINENCE = 0.02    # ... and this fraction of the strongest apex curvature
    _MIN_AREA_FRACTION = 0.005       # accepted shoulder must carry >= 0.5 % of total area
    _MIN_SEPARATION_FWHM = 0.5       # apex separation relative to mean FWHM of the pair
    _MIN_RSS_REDUCTION = 0.25        # extra component must cut residual SS by >= 25 %
    _BIC_MARGIN = 0.0                # required BIC improvement (strong evidence)
    _MODEL_FLOOR_FRACTION = 0.005    # model-error floor, fraction of peak height
    _MIN_WIDTH_RATIO = 0.3           # shoulder FWHM relative to each neighbour's ...
    _MAX_WIDTH_RATIO = 2.5           # ... (much broader = tail/drift, not a peak)
    _SHOULDER_TAU_FWHM_INV = 0.5     # shoulder gamma >= this / FWHM (tail tau <= 2 FWHM)
    _TAIL_SIDE_BIC_MARGIN = 10.0     # downstream (tail-side) candidates need strong evidence ...
    _TAIL_SIDE_MAX_WIDTH_RATIO = 2.0 # ... and must not be much broader than the main peak
    _EVIDENCE_WINDOW = (0.75, 0.35)  # window around candidate (x - a*FWHM, x + b*FWHM)
    _INDEPENDENT_PER_SIGMA = 5.0     # independent samples per Gaussian sigma (smooth data)
    _SHOULDER_PROMINENCE_SCALE = 0.25  # shoulder height >= this * prominence * signal range
    _EDGE_MARGIN_FWHM = 0.6          # shoulders must sit this many FWHM inside the region
    _VALIDATION_POINTS = 240         # decimation target for the validation fits

    def _apex_indices(self, x: np.ndarray, y: np.ndarray, prominence: float) -> np.ndarray:
        # ``prominence`` is a fraction of the signal range; never go below a few
        # noise sigmas, or a noise-only region would "contain" dozens of peaks.
        prom_abs = max(float(np.ptp(y)) * prominence, self._APEX_NOISE_SIGMAS * self._robust_noise(y))
        distance = max(1, len(x) // 50)
        indices, _ = find_peaks(y, prominence=prom_abs, distance=distance)
        return indices

    @staticmethod
    def _robust_noise(y: np.ndarray) -> float:
        """Noise sigma from the MAD of the second difference (signal curvature
        is sparse, so the median ignores it)."""
        d2 = np.diff(y, 2)
        if d2.size == 0:
            return 0.0
        return float(1.4826 * np.median(np.abs(d2 - np.median(d2))) / np.sqrt(6.0))

    @staticmethod
    def _curve_apex_and_fwhm(x: np.ndarray, curve: np.ndarray) -> Tuple[float, float]:
        """Apex x and full width at half maximum of a fitted component curve."""
        i = int(np.argmax(curve))
        peak = float(curve[i])
        if peak <= 0:
            return float(x[i]), 0.0
        above = np.where(curve >= peak / 2.0)[0]
        lo, hi = int(above[0]), int(above[-1])
        fwhm = float(x[hi] - x[lo]) + float(np.median(np.diff(x)))
        return float(x[i]), fwhm

    def _shoulder_candidates(self, x, y, apex_idx, floor, trace=None):
        """Prominent local minima of d2 that do not coincide with a detected apex
        (a weak shoulder dents the curvature without making it negative).

        Returns (candidate x positions strongest first, fwhm_x, noise_y, height).
        """
        n = x.size
        dx = float(np.median(np.diff(x)))
        yb = y - floor
        height = float(yb[apex_idx].max()) if len(apex_idx) else float(yb.max())
        if height <= 0 or dx <= 0:
            return [], 0.0, 0.0, height
        main = int(apex_idx[np.argmax(yb[apex_idx])]) if len(apex_idx) else int(np.argmax(yb))
        above = yb >= height / 2.0
        lo = main
        while lo > 0 and above[lo - 1]:
            lo -= 1
        hi = main
        while hi < n - 1 and above[hi + 1]:
            hi += 1
        fwhm_pts = hi - lo + 1
        if fwhm_pts < self._MIN_POINTS_ACROSS_PEAK or n < 3 * self._MIN_POINTS_ACROSS_PEAK:
            return [], fwhm_pts * dx, 0.0, height

        # Window from the number of points across the peak (~FWHM / 2.5).
        w = int(round(fwhm_pts / 2.5)) | 1
        w = max(w, 7)
        if w > n:
            w = n if n % 2 == 1 else n - 1
        polyorder = 3 if w > 5 else 2
        d2 = savgol_filter(y, w, polyorder, deriv=2, delta=dx)

        noise_y = self._robust_noise(y)
        coeffs = savgol_coeffs(w, polyorder, deriv=2, delta=dx)
        noise_d2 = noise_y * float(np.linalg.norm(coeffs))
        strongest = float(np.max(-d2))
        if strongest <= 0:
            return [], fwhm_pts * dx, noise_y, height
        thr = max(self._D2_NOISE_SIGMAS * noise_d2, self._D2_MIN_REL_PROMINENCE * strongest)
        idx, props = find_peaks(-d2, prominence=thr)

        # Savitzky-Golay edges are unreliable and a bump cut by the region edge
        # cannot be told from baseline drift: keep shoulders off the borders.
        margin = int(max(w, round(self._EDGE_MARGIN_FWHM * fwhm_pts)))
        exclusion = 0.4 * fwhm_pts * dx
        cands = []
        for i, prom in zip(idx, props["prominences"]):
            ok = margin <= i <= n - 1 - margin
            if ok and len(apex_idx):
                ok = bool(np.all(np.abs(x[apex_idx] - x[i]) >= exclusion))
            if trace is not None:
                trace.append(dict(x=float(x[i]), prom=float(prom), rel=float(prom / strongest), ok=ok))
            if ok:
                cands.append((float(prom), float(x[i])))
        cands.sort(reverse=True)
        return [c[1] for c in cands[: self._MAX_SHOULDERS + 1]], fwhm_pts * dx, noise_y, height

    def _bic(self, rss: float, n_eff: float, k: int, rss_floor: float) -> float:
        return n_eff * np.log(max(rss, rss_floor) / max(rss_floor, 1e-300)) + 4.0 * k * np.log(max(n_eff, 2.0))

    def auto_detect_centers(
        self, x: np.ndarray, y: np.ndarray, prominence: float = 0.05,
        trace: Optional[list] = None,
    ) -> List[Tuple[float, float]]:
        """Detect approximate component centers, including unresolved shoulders.

        1. Apexes: ``scipy.signal.find_peaks`` on the signal (``prominence`` is
           a fraction of the signal range, as before).
        2. Shoulder candidates: a Savitzky-Golay second derivative (window from
           the number of points across the peak); prominent minima of d2 that
           are not at a detected apex and clear a noise-scaled threshold (MAD
           of the second difference) are candidate hidden components.
        3. Validation: candidates are added one at a time (strongest first) to
           the composite EMG fit and kept only if they lower a BIC computed from
           the residuals (with a noise/model-error floor), cut the residual by
           a minimum fraction, carry a minimum fraction of the total area, stay
           inside the region, be about as wide as their neighbour and sit a
           minimum distance from it relative to the peak width. Candidates on
           the tail side of the main peak need stronger evidence, so a clean
           asymmetric (tailing) peak stays one component. ``prominence`` also
           scales the minimum height of an accepted shoulder.

        Returns
        -------
        list of (x, y)
            Component positions sorted by x: apexes at their maximum, shoulders
            at the curvature minimum with the signal height there.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size < 3:
            return []

        apex_idx = self._apex_indices(x, y, prominence)
        apexes = [(float(x[i]), float(y[i])) for i in apex_idx]
        if len(apex_idx) == 0 or x.size < 24:
            return apexes
        # Savitzky-Golay derivatives assume even sampling.
        apex_u = apex_idx
        xu, yu = x, y
        if np.ptp(np.diff(x)) > 0.25 * np.median(np.diff(x)):
            xu = np.linspace(x[0], x[-1], x.size)
            yu = np.interp(xu, x, y)
            apex_u = np.unique(np.clip(np.searchsorted(xu, x[apex_idx]), 0, xu.size - 1))
        min_height = self._SHOULDER_PROMINENCE_SCALE * prominence * float(np.ptp(y))
        try:
            return self._add_validated_shoulders(xu, yu, apex_u, apexes, trace, min_height)
        except Exception:
            return apexes  # shoulder search is best effort; never lose the apexes

    def _add_validated_shoulders(self, x, y, apex_idx, apexes, trace=None, min_height=0.0):
        floor = float(self._estimate_local_baseline(y)[0])
        cands, fwhm_x, noise_y, height = self._shoulder_candidates(x, y, apex_idx, floor, trace)
        if not cands:
            return apexes

        n = x.size
        dx = float(np.median(np.diff(x)))
        # Points per resolution element -> effective number of independent samples.
        pts_per_sigma = max(fwhm_x / 2.355 / dx, 1.0)
        rss_floor = n * max(noise_y, self._MODEL_FLOOR_FRACTION * height) ** 2

        # Decimate for the validation fits only (speed); the final fit in the
        # caller uses the full data.
        step = max(1, int(np.ceil(n / self._VALIDATION_POINTS)))
        xs, ys = x[::step], y[::step]
        x_lo, x_hi = float(x[0]), float(x[-1])

        def fit(centers, trial_x=None):
            bounds = [(c - 0.5 * fwhm_x, c + 0.5 * fwhm_x) for c, _ in centers]
            # a trial shoulder must be a peak-like bump, not an endless tail
            g_min = [self._SHOULDER_TAU_FWHM_INV / fwhm_x if (trial_x is not None and c == trial_x) else None
                     for c, _ in centers]
            sig0 = fwhm_x / 2.355
            s_b = [(0.15 * sig0, 1.5 * sig0) if (trial_x is not None and c == trial_x) else None
                   for c, _ in centers]
            return self.fit_peaks(xs, ys, centers, center_bounds=bounds, max_nfev=500,
                                  gamma_min=g_min, sigma_bounds=s_b, apex_mode=True)

        current = list(apexes)
        base = fit(current)
        if base is None:
            return apexes
        rss = float(np.sum(base.residuals ** 2)) * step
        added = 0
        for cx in cands:
            if added >= self._MAX_SHOULDERS:
                break
            trial = sorted(current + [(cx, float(np.interp(cx, x, y)))])
            tf = fit(trial, cx)
            if tf is None:
                continue
            trss = float(np.sum(tf.residuals ** 2)) * step
            total_area = sum(c.area for c in tf.components)
            shapes = [self._curve_apex_and_fwhm(xs, c.curve) for c in tf.components]
            areas = [c.area / total_area if total_area > 0 else 0.0 for c in tf.components]
            # the component that took over the candidate: nearest fitted apex
            j = int(np.argmin([abs(a[0] - cx) for a in shapes]))
            new_apex, new_fwhm = shapes[j]
            others = [shapes[q] for q in range(len(shapes)) if q != j]
            sep_ok = all(abs(a - new_apex) >= self._MIN_SEPARATION_FWHM * 0.5 * (fw + new_fwhm)
                         for a, fw in others)
            # an unresolved *peak* is about as wide as its neighbours; a very
            # broad or very narrow component is baseline drift / tailing / a spike
            # A peak's own tail is the usual source of false shoulders: anything
            # downstream of the tallest component is held to a stricter standard.
            tallest = int(np.argmax([float(c.curve.max()) for c in tf.components]))
            tail_side = j != tallest and new_apex > shapes[tallest][0]
            max_ratio = self._TAIL_SIDE_MAX_WIDTH_RATIO if tail_side else self._MAX_WIDTH_RATIO
            margin = self._TAIL_SIDE_BIC_MARGIN if tail_side else self._BIC_MARGIN
            ratio_ok = all(self._MIN_WIDTH_RATIO <= new_fwhm / max(fw, 1e-12) <= max_ratio
                           for _, fw in others)
            # a component still at full height where the region is cut is truncated
            curve = tf.components[j].curve
            edge = max(float(curve[0]), float(curve[-1]))
            truncated = edge > 0.5 * float(curve.max())
            # Evidence is judged around the candidate: a small shoulder must not
            # be drowned by the (unrelated) misfit of the main peak's own shape.
            win = (xs >= cx - self._EVIDENCE_WINDOW[0] * fwhm_x) & (xs <= cx + self._EVIDENCE_WINDOW[1] * fwhm_x)
            n_win = int(win.sum())
            rss_old = float(np.sum(base.residuals[win] ** 2))
            rss_new = float(np.sum(tf.residuals[win] ** 2))
            n_eff_w = max(n_win * step / pts_per_sigma * self._INDEPENDENT_PER_SIGMA, 8.0)
            floor_w = n_win * step * max(noise_y, self._MODEL_FLOOR_FRACTION * height) ** 2
            dbic = (self._bic(rss_new, n_eff_w, len(trial), floor_w)
                    - self._bic(rss_old, n_eff_w, len(current), floor_w))
            reduction = 1.0 - rss_new / rss_old if rss_old > 0 else 0.0
            ok = (dbic < -margin and reduction >= self._MIN_RSS_REDUCTION
                  and areas[j] >= self._MIN_AREA_FRACTION and sep_ok and ratio_ok
                  and not truncated and new_fwhm >= 3 * dx * step
                  and float(curve.max()) >= min_height)
            if trace is not None:
                trace.append(dict(cand=round(cx, 4), dbic=round(float(dbic), 1), red=round(float(reduction), 3),
                                  areas=[round(a, 3) for a in areas], apexes=[round(a[0], 4) for a in shapes],
                                  fwhms=[round(a[1], 4) for a in shapes], j=j, sep_ok=sep_ok,
                                  ratio_ok=ratio_ok, trunc=truncated, accepted=bool(ok)))
            if ok:
                current, base, rss = trial, tf, trss
                added += 1
        return sorted(current)

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def _seed_schedule(
        self, x: np.ndarray, centers: List[Tuple[float, float]], multi_start: bool
    ) -> List[Tuple[float, float]]:
        """(sigma, gamma) starting guesses; the first one is the legacy default."""
        x_range = float(x.max() - x.min())
        dx = float(np.median(np.diff(x))) if x.size > 1 else x_range
        span = max(x_range, dx, 1e-12)
        legacy = (x_range * 0.04, 2.0 / span)
        if not multi_start or len(centers) < 2:
            return [legacy]
        # Overlapping components are narrower than the legacy guess: scale the
        # width seed with the closest pair of centers so the optimiser starts
        # in the right basin instead of sharing one broad Gaussian.
        xs = np.sort([float(c[0]) for c in centers])
        gap = float(np.min(np.diff(xs)))
        sig = float(np.clip(0.35 * gap, max(dx * 1.5, x_range * 0.002), x_range * 0.1))
        return [legacy, (sig, 2.0 / span), (sig, 30.0 / span), (0.6 * sig, 60.0 / span)]

    def _fit_once(self, x, y_fit, baseline_arr, centers, fixed_apices, sigma_seed, gamma_seed,
                  center_bounds=None, max_nfev=5000, gamma_min=None, sigma_bounds=None, apex_mode=False):
        """One lmfit composite fit from a single starting guess."""
        x_range = float(x.max() - x.min())
        models = []
        params = None
        dx = float(np.median(np.diff(x))) if x.size > 1 else x_range
        for i, (center, height) in enumerate(centers):
            prefix = f"p{i}_"
            m = Model(_apex_emg, prefix=prefix) if (apex_mode or i in fixed_apices) else ExponentialGaussianModel(prefix=prefix)
            if params is None:
                params = m.make_params()
            else:
                params.update(m.make_params())
            models.append(m)

            height_guess = max(
                float(np.interp(center, x, y_fit)),
                float(height) - float(np.interp(center, x, baseline_arr)),
                1e-9,
            )
            c_lo, c_hi = float(x.min()), float(x.max())
            if center_bounds is not None and center_bounds[i] is not None:
                c_lo, c_hi = max(c_lo, center_bounds[i][0]), min(c_hi, center_bounds[i][1])
                center = float(np.clip(center, c_lo, c_hi))
            params[f"{prefix}center"].set(value=center, min=c_lo, max=c_hi)
            if i in fixed_apices:
                params[f"{prefix}center"].set(value=fixed_apices[i], vary=False)
            params[f"{prefix}amplitude"].set(
                value=height_guess * sigma_seed * np.sqrt(2 * np.pi),
                min=0,
            )
            s_lo, s_hi = max(dx * 0.5, x_range * 0.0005), x_range * 0.2
            if sigma_bounds is not None and sigma_bounds[i] is not None:
                s_lo, s_hi = max(s_lo, sigma_bounds[i][0]), min(s_hi, sigma_bounds[i][1])
                s_hi = max(s_hi, s_lo * 1.0001)
            params[f"{prefix}sigma"].set(
                value=float(np.clip(sigma_seed, s_lo, s_hi)),
                min=s_lo,
                max=s_hi,
            )
            # lmfit's EMG gamma has inverse-x units. Narrow peak regions need
            # larger gamma values, not smaller ones, or the fit degenerates
            # into an almost flat, never-ending tail.
            g_max = 100.0 / max(x_range, dx, 1e-12)
            g_min = 0.001
            if gamma_min is not None and gamma_min[i] is not None:
                g_min = min(float(gamma_min[i]), 0.5 * g_max)
            params[f"{prefix}gamma"].set(
                value=float(np.clip(gamma_seed, g_min, g_max)),
                min=g_min,
                max=g_max,
            )

        self._seed_amplitudes(x, y_fit, centers, params, sigma_seed, gamma_seed, fixed_apices, apex_mode)

        composite = models[0]
        for m in models[1:]:
            composite = composite + m
        return composite.fit(y_fit, params, x=x, max_nfev=max_nfev)

    @staticmethod
    def _seed_amplitudes(x, y_fit, centers, params, sigma, gamma, fixed_apices, apex_mode=False) -> None:
        """Start amplitudes from a non-negative linear solve at the seeded shapes.

        Seeding every component with the full local signal height makes the
        initial sum overshoot badly when components overlap; the linear solve
        shares the signal between them instead. Best effort only.
        """
        if len(centers) < 2:
            return
        try:
            cols = []
            for i, (center, _h) in enumerate(centers):
                if i in fixed_apices or apex_mode:
                    col = _apex_emg(x, 1.0, fixed_apices.get(i, center), sigma, gamma)
                else:
                    col = ExponentialGaussianModel().eval(
                        x=x, amplitude=1.0, center=center, sigma=sigma, gamma=gamma)
                cols.append(np.nan_to_num(np.asarray(col, dtype=float)))
            coef, _ = nnls(np.column_stack(cols), np.asarray(y_fit, dtype=float))
            for i, c in enumerate(coef):
                if np.isfinite(c) and c > 0:
                    params[f"p{i}_amplitude"].set(value=float(c))
        except Exception:
            return

    def fit_peaks(
        self,
        x: np.ndarray,
        y: np.ndarray,
        centers: List[Tuple[float, float]],
        fixed_apices: Optional[Dict[int, float]] = None,
        multi_start: bool = True,
        center_bounds: Optional[List[Optional[Tuple[float, float]]]] = None,
        max_nfev: int = 5000,
        gamma_min: Optional[List[Optional[float]]] = None,
        sigma_bounds: Optional[List[Optional[Tuple[float, float]]]] = None,
        apex_mode: bool = False,
    ) -> Optional[DeconvResult]:
        """Fit a composite EMG model, one component per center.

        Parameters
        ----------
        x, y : np.ndarray
            Region data.
        centers : list of (center_x, height)
            Initial peak positions (and approximate heights) to seed the fit.
        fixed_apices : dict, optional
            Component indices mapped to user-dragged apex positions. Their
            actual EMG maxima stay fixed while width, tailing and area refit.
        multi_start : bool
            With two or more components, try a few width/tailing seeds and keep
            the lowest-residual fit (avoids one broad component absorbing a
            shoulder). The legacy single seed is always among them.
        center_bounds : list of (lo, hi) or None, optional
            Per-component limits for the fitted (Gaussian) center; used by the
            shoulder validation so a trial component cannot wander off its seed.
        max_nfev : int
            Function-evaluation cap per lmfit run.
        gamma_min : list of float or None, optional
            Per-component lower bound on the EMG tailing rate (caps the tail
            time constant); ``None`` entries keep the default.

        Returns
        -------
        DeconvResult or None
            ``None`` when no centers are supplied.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if not centers:
            return None
        baseline_arr = self._estimate_local_baseline(y)
        y_fit = np.maximum(y - baseline_arr, 0.0)
        fixed_apices = fixed_apices or {}

        result = None
        best_rss = np.inf
        for sigma_seed, gamma_seed in self._seed_schedule(x, centers, multi_start):
            try:
                trial = self._fit_once(
                    x, y_fit, baseline_arr, centers, fixed_apices, sigma_seed, gamma_seed,
                    center_bounds, max_nfev, gamma_min, sigma_bounds, apex_mode
                )
            except Exception:
                if result is None and (sigma_seed, gamma_seed) == self._seed_schedule(x, centers, multi_start)[0]:
                    raise
                continue
            rss = float(np.sum((np.asarray(trial.best_fit, dtype=float) - y_fit) ** 2))
            if np.isfinite(rss) and rss < best_rss:
                result, best_rss = trial, rss
        if result is None:
            return None
        comp_curves = result.eval_components(x=x)

        best_fit = np.asarray(result.best_fit, dtype=float) + baseline_arr
        residuals = y - best_fit
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        components: List[DeconvComponent] = []
        for i in range(len(centers)):
            prefix = f"p{i}_"
            curve = np.asarray(comp_curves[prefix], dtype=float)
            components.append(
                DeconvComponent(
                    index=i,
                    center=float(result.params[f"{prefix}center"].value) - (
                        _emg_mode_offset(result.params[f"{prefix}sigma"].value,
                                         result.params[f"{prefix}gamma"].value)
                        if (apex_mode or i in fixed_apices) else 0.),
                    amplitude=float(result.params[f"{prefix}amplitude"].value),
                    sigma=float(result.params[f"{prefix}sigma"].value),
                    gamma=float(result.params[f"{prefix}gamma"].value),
                    area=float(trapezoid(curve, x)),
                    curve=curve,
                )
            )

        return DeconvResult(
            x=x,
            baseline=baseline_arr,
            best_fit=best_fit,
            residuals=residuals,
            r_squared=float(r_squared),
            redchi=float(result.redchi),
            components=components,
        )

    # ------------------------------------------------------------------
    # Conversion to standard Peak objects
    # ------------------------------------------------------------------

    def result_to_peaks(
        self, result: DeconvResult, file_id: str, region_rt: float
    ) -> List[Peak]:
        """Convert each fitted component into a standard Peak object.

        Each peak gets a filled polygon traced along the individual fitted EMG
        curve over the selected peak region, matching the sandbox's
        fill-to-zero rendering.
        """
        x = self._render_x(result.x)
        baseline, _, stack_bottoms, stack_tops = self._render_component_stacks(result, x)
        peaks: List[Peak] = []
        for comp, stack_bottom, stack_top in zip(result.components, stack_bottoms, stack_tops):
            curve = self._eval_component(comp, x)
            peak_h = float(curve.max())

            rt_start = float(x[0])
            rt_end = float(x[-1])

            # Closed polygon: forward along this component's stacked top,
            # then back along its stacked bottom. Together the components tile
            # the measured area under the chromatogram curve.
            poly_x = np.concatenate([x, x[::-1]]).tolist()
            poly_y = np.concatenate([stack_top, stack_bottom[::-1]]).tolist()

            tag = f"deconv_{region_rt:.1f}_c{comp.index}"
            color = OKABE_ITO_PALETTE[comp.index % len(OKABE_ITO_PALETTE)]

            peaks.append(
                Peak(
                    peak_id=str(uuid.uuid4()),
                    file_id=file_id,
                    name=f"Peak {comp.index + 1}",
                    rt=comp.center,
                    rt_start=rt_start,
                    rt_end=rt_end,
                    area=comp.area,
                    height=peak_h,
                    width=rt_end - rt_start,
                    color=color,
                    source="deconvolved",
                    poly_x=poly_x,
                    poly_y=poly_y,
                    p_line=[(rt_start, float(baseline[0])), (rt_end, float(baseline[-1]))],
                    q1=(rt_start, float(baseline[0])),
                    q2=(rt_end, float(baseline[-1])),
                    deconv_group=tag,
                    fit_params={
                        "center": comp.center,
                        "baseline": [(rt_start, float(baseline[0])), (rt_end, float(baseline[-1]))],
                        "sigma": comp.sigma,
                        "gamma": comp.gamma,
                        "amplitude": comp.amplitude,
                    },
                )
            )
        return peaks
