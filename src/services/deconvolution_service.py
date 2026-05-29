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
from scipy.signal import find_peaks
from scipy.integrate import trapezoid

from services.peak_service import Peak, OKABE_ITO_PALETTE


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

    def auto_detect_centers(
        self, x: np.ndarray, y: np.ndarray, prominence: float = 0.05
    ) -> List[Tuple[float, float]]:
        """Detect approximate peak centers via scipy.signal.find_peaks.

        Parameters
        ----------
        x, y : np.ndarray
            Region data (1-D, same length).
        prominence : float
            Minimum peak prominence as a fraction of the signal range.

        Returns
        -------
        list of (x, y)
            Detected apex positions.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size < 3:
            return []

        prom_abs = float(np.ptp(y)) * prominence
        distance = max(1, len(x) // 50)
        indices, _ = find_peaks(y, prominence=prom_abs, distance=distance)
        return [(float(x[i]), float(y[i])) for i in indices]

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit_peaks(
        self,
        x: np.ndarray,
        y: np.ndarray,
        centers: List[Tuple[float, float]],
    ) -> Optional[DeconvResult]:
        """Fit a composite EMG model, one component per center.

        Parameters
        ----------
        x, y : np.ndarray
            Region data.
        centers : list of (center_x, height)
            Initial peak positions (and approximate heights) to seed the fit.

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

        x_range = float(x.max() - x.min())
        models = []
        params = None

        for i, (center, height) in enumerate(centers):
            prefix = f"p{i}_"
            m = ExponentialGaussianModel(prefix=prefix)
            if params is None:
                params = m.make_params()
            else:
                params.update(m.make_params())
            models.append(m)

            dx = float(np.median(np.diff(x))) if x.size > 1 else x_range
            sigma_guess = x_range * 0.04
            gamma_guess = 2.0 / max(x_range, dx, 1e-12)
            height_guess = max(
                float(np.interp(center, x, y_fit)),
                float(height) - float(np.interp(center, x, baseline_arr)),
                1e-9,
            )
            params[f"{prefix}center"].set(value=center, min=x.min(), max=x.max())
            params[f"{prefix}amplitude"].set(
                value=height_guess * sigma_guess * np.sqrt(2 * np.pi),
                min=0,
            )
            params[f"{prefix}sigma"].set(
                value=sigma_guess,
                min=max(dx * 0.5, x_range * 0.0005),
                max=x_range * 0.2,
            )
            # lmfit's EMG gamma has inverse-x units. Narrow peak regions need
            # larger gamma values, not smaller ones, or the fit degenerates
            # into an almost flat, never-ending tail.
            params[f"{prefix}gamma"].set(
                value=gamma_guess,
                min=0.001,
                max=100.0 / max(x_range, dx, 1e-12),
            )

        composite = models[0]
        for m in models[1:]:
            composite = composite + m

        result = composite.fit(y_fit, params, x=x, max_nfev=5000)
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
                    center=float(result.params[f"{prefix}center"].value),
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
                        "sigma": comp.sigma,
                        "gamma": comp.gamma,
                        "amplitude": comp.amplitude,
                    },
                )
            )
        return peaks
