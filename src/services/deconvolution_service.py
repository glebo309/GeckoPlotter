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
    best_fit: np.ndarray
    residuals: np.ndarray
    r_squared: float
    redchi: float
    components: List[DeconvComponent] = field(default_factory=list)


def serialize_result(result: DeconvResult) -> dict:
    """Convert a DeconvResult into a JSON-safe dict for a dcc.Store."""
    return {
        "x": np.asarray(result.x, dtype=float).tolist(),
        "best_fit": np.asarray(result.best_fit, dtype=float).tolist(),
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
            }
            for c in result.components
        ],
    }


def deserialize_result(payload: dict) -> DeconvResult:
    """Rebuild a DeconvResult from a serialized dict."""
    return DeconvResult(
        x=np.asarray(payload["x"], dtype=float),
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

            sigma_guess = x_range * 0.02
            params[f"{prefix}center"].set(value=center, min=x.min(), max=x.max())
            params[f"{prefix}amplitude"].set(value=height * 10, min=0)
            params[f"{prefix}sigma"].set(
                value=sigma_guess, min=x_range * 0.001, max=x_range * 0.2
            )
            params[f"{prefix}gamma"].set(
                value=sigma_guess, min=0.001, max=x_range * 0.3
            )

        composite = models[0]
        for m in models[1:]:
            composite = composite + m

        result = composite.fit(y, params, x=x, max_nfev=5000)
        comp_curves = result.eval_components(x=x)

        ss_res = float(np.sum(result.residual ** 2))
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
            best_fit=np.asarray(result.best_fit, dtype=float),
            residuals=np.asarray(result.residual, dtype=float),
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

        Each peak gets a filled polygon traced along the individual EMG curve
        with a baseline leg at ``y=0``, a ``source='deconvolved'`` tag, and a
        ``deconv_group`` tag for cross-sample matching.
        """
        x = result.x
        peaks: List[Peak] = []
        for comp in result.components:
            curve = comp.curve
            peak_h = float(curve.max())

            # Clip to the meaningful span of this component for a tight polygon.
            if peak_h > 0:
                mask = curve > peak_h * self._CURVE_FLOOR_FRAC
            else:
                mask = np.ones_like(curve, dtype=bool)
            if mask.sum() < 2:
                mask = np.ones_like(curve, dtype=bool)

            xs = x[mask]
            ys = curve[mask]
            rt_start = float(xs[0])
            rt_end = float(xs[-1])

            # Closed polygon: forward along the curve, back along a y=0 baseline.
            poly_x = np.concatenate([xs, xs[::-1]]).tolist()
            poly_y = np.concatenate([ys, np.zeros_like(ys)]).tolist()

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
                    p_line=[(rt_start, 0.0), (rt_end, 0.0)],
                    q1=(rt_start, 0.0),
                    q2=(rt_end, 0.0),
                    deconv_group=tag,
                    fit_params={
                        "sigma": comp.sigma,
                        "gamma": comp.gamma,
                        "amplitude": comp.amplitude,
                    },
                )
            )
        return peaks
