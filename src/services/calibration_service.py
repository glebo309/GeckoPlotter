# =============================================================================
# File: services/calibration_service.py
# =============================================================================
"""
Calibration Service for GeckoPlotter V2 — domain service for building,
fitting, and applying calibration models to chromatographic peak data.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import plotly.graph_objects as go
from scipy.optimize import curve_fit


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class CalibrationPoint:
    """A single calibration standard measurement."""
    sample_name: str
    concentration: float
    area: float
    included: bool = True


@dataclass
class CalibrationModel:
    """Full calibration model for a single analyte."""
    model_id: str
    analyte_name: str
    group_id: str
    fit_type: str          # 'linear', 'quadratic', 'power'
    force_zero: bool
    units: str
    standards: List[CalibrationPoint] = field(default_factory=list)
    coefficients: Optional[List[float]] = None
    r_squared: Optional[float] = None
    residuals: Optional[List[float]] = None
    created_at: str = ""


# =============================================================================
# Calibration service
# =============================================================================

class CalibrationService:
    """Manages calibration models: creation, fitting, prediction, and export."""

    def __init__(self):
        self._models: Dict[str, CalibrationModel] = {}

    # ----- model lifecycle ---------------------------------------------------

    def create_model(
        self,
        analyte_name: str,
        group_id: str,
        fit_type: str = "linear",
        force_zero: bool = False,
        units: str = "",
    ) -> CalibrationModel:
        """Create a new, empty calibration model and register it."""
        model = CalibrationModel(
            model_id=str(uuid.uuid4()),
            analyte_name=analyte_name,
            group_id=group_id,
            fit_type=fit_type,
            force_zero=force_zero,
            units=units,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._models[model.model_id] = model
        return model

    def get_model(self, model_id: str) -> Optional[CalibrationModel]:
        """Return a model by ID, or None."""
        return self._models.get(model_id)

    def get_all_models(self) -> Dict[str, CalibrationModel]:
        """Return every registered model."""
        return dict(self._models)

    def get_model_for_group(self, group_id: str) -> Optional[CalibrationModel]:
        """Find the calibration model linked to a peak-group ID."""
        for model in self._models.values():
            if model.group_id == group_id:
                return model
        return None

    # ----- standard management -----------------------------------------------

    def add_standard(
        self, model_id: str, sample_name: str, concentration: float, area: float
    ) -> None:
        """Append a calibration point to the model."""
        model = self._require_model(model_id)
        model.standards.append(
            CalibrationPoint(
                sample_name=sample_name,
                concentration=concentration,
                area=area,
            )
        )
        # Invalidate any previous fit
        self._invalidate_fit(model)

    def remove_standard(self, model_id: str, sample_name: str) -> None:
        """Remove all standards matching *sample_name*."""
        model = self._require_model(model_id)
        model.standards = [
            s for s in model.standards if s.sample_name != sample_name
        ]
        self._invalidate_fit(model)

    def toggle_standard(self, model_id: str, sample_name: str) -> None:
        """Toggle the *included* flag on standards matching *sample_name*."""
        model = self._require_model(model_id)
        for std in model.standards:
            if std.sample_name == sample_name:
                std.included = not std.included
        self._invalidate_fit(model)

    # ----- fitting -----------------------------------------------------------

    def fit_model(self, model_id: str) -> CalibrationModel:
        """Perform regression on included standards and store coefficients."""
        model = self._require_model(model_id)
        included = [s for s in model.standards if s.included]

        if len(included) < 2:
            raise ValueError(
                f"At least 2 included standards required; got {len(included)}."
            )

        conc = np.array([s.concentration for s in included], dtype=np.float64)
        area = np.array([s.area for s in included], dtype=np.float64)

        if model.fit_type == "linear":
            coeffs, predicted = self._fit_linear(conc, area, model.force_zero)
        elif model.fit_type == "quadratic":
            coeffs, predicted = self._fit_quadratic(conc, area, model.force_zero)
        elif model.fit_type == "power":
            coeffs, predicted = self._fit_power(conc, area)
        else:
            raise ValueError(f"Unknown fit_type: {model.fit_type!r}")

        model.coefficients = coeffs.tolist()
        model.r_squared = self._calc_r_squared(area, predicted)
        model.residuals = (area - predicted).tolist()
        return model

    # ----- prediction --------------------------------------------------------

    def predict_concentration(self, model_id: str, area: float) -> Optional[float]:
        """Given a peak area, predict concentration using the fitted model.

        For linear and quadratic models the inverse is solved analytically.
        For power models the inverse is computed directly.
        Returns *None* if the model has not been fitted or if the inversion
        yields no real positive solution.
        """
        model = self._require_model(model_id)
        if model.coefficients is None:
            return None

        coeffs = np.array(model.coefficients, dtype=np.float64)

        if model.fit_type == "linear":
            # area = m*conc + b  =>  conc = (area - b) / m
            m = coeffs[0]
            b = coeffs[1] if len(coeffs) > 1 else 0.0
            if m == 0:
                return None
            return float((area - b) / m)

        if model.fit_type == "quadratic":
            # area = a*conc² + b*conc + c  =>  solve for conc
            a, b, c_coeff = coeffs[0], coeffs[1], (coeffs[2] if len(coeffs) > 2 else 0.0)
            if a == 0:
                # Degenerate — linear
                if b == 0:
                    return None
                return float((area - c_coeff) / b)
            discriminant = b ** 2 - 4 * a * (c_coeff - area)
            if discriminant < 0:
                return None
            sqrt_d = np.sqrt(discriminant)
            roots = [(-b + sqrt_d) / (2 * a), (-b - sqrt_d) / (2 * a)]
            # Prefer the positive root
            positive = [r for r in roots if r >= 0]
            if not positive:
                return None
            return float(min(positive))

        if model.fit_type == "power":
            # area = a * conc^b  =>  conc = (area / a)^(1/b)
            a_coeff, b_exp = coeffs[0], coeffs[1]
            if a_coeff <= 0 or b_exp == 0:
                return None
            ratio = area / a_coeff
            if ratio < 0:
                return None
            return float(ratio ** (1.0 / b_exp))

        return None

    def predict_area(self, model_id: str, concentration: float) -> Optional[float]:
        """Given a concentration, predict peak area using the fitted model."""
        model = self._require_model(model_id)
        if model.coefficients is None:
            return None
        return float(self._evaluate(model, concentration))

    # ----- figures -----------------------------------------------------------

    def create_calibration_figure(self, model_id: str) -> go.Figure:
        """Plotly figure: calibration curve with data points and R²."""
        model = self._require_model(model_id)
        fig = go.Figure()

        # Included points
        inc = [s for s in model.standards if s.included]
        exc = [s for s in model.standards if not s.included]

        if inc:
            fig.add_trace(go.Scatter(
                x=[s.concentration for s in inc],
                y=[s.area for s in inc],
                mode="markers",
                name="Included",
                marker=dict(color="#007acc", size=10, symbol="circle"),
                hovertemplate=(
                    "%{text}<br>"
                    "Conc: %{x:.4g}<br>"
                    "Area: %{y:.4g}<extra></extra>"
                ),
                text=[s.sample_name for s in inc],
            ))

        if exc:
            fig.add_trace(go.Scatter(
                x=[s.concentration for s in exc],
                y=[s.area for s in exc],
                mode="markers",
                name="Excluded",
                marker=dict(
                    color="grey", size=9, symbol="x",
                    line=dict(width=1, color="grey"),
                ),
                hovertemplate=(
                    "%{text} (excluded)<br>"
                    "Conc: %{x:.4g}<br>"
                    "Area: %{y:.4g}<extra></extra>"
                ),
                text=[s.sample_name for s in exc],
            ))

        # Fitted curve
        if model.coefficients is not None and inc:
            conc_arr = np.array([s.concentration for s in inc])
            x_min, x_max = conc_arr.min(), conc_arr.max()
            margin = (x_max - x_min) * 0.05 if x_max != x_min else 1.0
            x_curve = np.linspace(max(0, x_min - margin), x_max + margin, 200)
            y_curve = self._evaluate(model, x_curve)

            fig.add_trace(go.Scatter(
                x=x_curve,
                y=y_curve,
                mode="lines",
                name="Fit",
                line=dict(color="#ff6b35", width=2),
                hoverinfo="skip",
            ))

        # Annotation: R² and equation
        annotation_text = self._equation_text(model)
        if model.r_squared is not None:
            annotation_text += f"<br>R² = {model.r_squared:.6f}"

        fig.update_layout(
            title=f"Calibration — {model.analyte_name}",
            xaxis_title=f"Concentration ({model.units})" if model.units else "Concentration",
            yaxis_title="Peak Area",
            template="plotly_white",
            annotations=[
                dict(
                    xref="paper", yref="paper",
                    x=0.05, y=0.95,
                    text=annotation_text,
                    showarrow=False,
                    font=dict(size=12),
                    align="left",
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor="#ccc",
                    borderwidth=1,
                    borderpad=6,
                ),
            ],
        )
        return fig

    def create_residual_figure(self, model_id: str) -> go.Figure:
        """Plotly residual plot for the fitted model."""
        model = self._require_model(model_id)
        fig = go.Figure()

        if model.residuals is None or model.coefficients is None:
            fig.update_layout(
                title="Residuals — no fit available",
                template="plotly_white",
            )
            return fig

        inc = [s for s in model.standards if s.included]
        conc = [s.concentration for s in inc]

        fig.add_trace(go.Scatter(
            x=conc,
            y=model.residuals,
            mode="markers",
            name="Residuals",
            marker=dict(color="#007acc", size=9),
            hovertemplate=(
                "Conc: %{x:.4g}<br>"
                "Residual: %{y:.4g}<extra></extra>"
            ),
        ))

        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="grey", line_width=1)

        fig.update_layout(
            title=f"Residuals — {model.analyte_name}",
            xaxis_title=f"Concentration ({model.units})" if model.units else "Concentration",
            yaxis_title="Residual (observed − predicted)",
            template="plotly_white",
        )
        return fig

    # ----- serialization / export --------------------------------------------

    def export_model(self, model_id: str) -> dict:
        """Export a single model as a JSON-serializable dict."""
        model = self._require_model(model_id)
        return self._model_to_dict(model)

    def import_model(self, data: dict) -> str:
        """Import a model from a dict (e.g. loaded from JSON).  Returns model_id."""
        model = self._model_from_dict(data)
        self._models[model.model_id] = model
        return model.model_id

    def serialize(self) -> dict:
        """Serialize all models for persistence."""
        return {
            mid: self._model_to_dict(m) for mid, m in self._models.items()
        }

    def deserialize(self, data: dict) -> None:
        """Restore all models from a serialized dict."""
        self._models.clear()
        for _mid, mdict in data.items():
            model = self._model_from_dict(mdict)
            self._models[model.model_id] = model

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _require_model(self, model_id: str) -> CalibrationModel:
        model = self._models.get(model_id)
        if model is None:
            raise KeyError(f"No calibration model with id {model_id!r}")
        return model

    @staticmethod
    def _invalidate_fit(model: CalibrationModel) -> None:
        model.coefficients = None
        model.r_squared = None
        model.residuals = None

    # ----- fitting helpers ---------------------------------------------------

    @staticmethod
    def _fit_linear(
        conc: np.ndarray, area: np.ndarray, force_zero: bool
    ) -> tuple[np.ndarray, np.ndarray]:
        if force_zero:
            # y = m*x  =>  m = sum(x*y) / sum(x²)
            m = np.sum(conc * area) / np.sum(conc ** 2)
            coeffs = np.array([m, 0.0])
            predicted = m * conc
        else:
            coeffs = np.polyfit(conc, area, 1)  # [m, b]
            predicted = np.polyval(coeffs, conc)
        return coeffs, predicted

    @staticmethod
    def _fit_quadratic(
        conc: np.ndarray, area: np.ndarray, force_zero: bool
    ) -> tuple[np.ndarray, np.ndarray]:
        if force_zero:
            # y = a*x² + b*x  (no intercept)
            # Build design matrix [x², x] and solve least-squares
            A = np.column_stack([conc ** 2, conc])
            result, *_ = np.linalg.lstsq(A, area, rcond=None)
            coeffs = np.array([result[0], result[1], 0.0])
            predicted = A @ result
        else:
            coeffs = np.polyfit(conc, area, 2)  # [a, b, c]
            predicted = np.polyval(coeffs, conc)
        return coeffs, predicted

    @staticmethod
    def _fit_power(
        conc: np.ndarray, area: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Fit y = a * x^b using scipy curve_fit with log-space initial guesses."""
        if np.any(conc <= 0) or np.any(area <= 0):
            raise ValueError(
                "Power-law fit requires all concentrations and areas to be > 0."
            )

        # Log-space OLS for initial guesses
        log_c, log_a = np.log(conc), np.log(area)
        b0, log_a0 = np.polyfit(log_c, log_a, 1)
        a0 = np.exp(log_a0)

        def power_func(x, a, b):
            return a * np.power(x, b)

        popt, _ = curve_fit(power_func, conc, area, p0=[a0, b0], maxfev=10000)
        coeffs = np.array(popt)  # [a, b]
        predicted = power_func(conc, *popt)
        return coeffs, predicted

    @staticmethod
    def _calc_r_squared(observed: np.ndarray, predicted: np.ndarray) -> float:
        ss_res = np.sum((observed - predicted) ** 2)
        ss_tot = np.sum((observed - np.mean(observed)) ** 2)
        if ss_tot == 0:
            return 1.0
        return float(1.0 - ss_res / ss_tot)

    @staticmethod
    def _evaluate(model: CalibrationModel, x) -> np.ndarray:
        """Evaluate the fitted model at *x* (scalar or array)."""
        x = np.asarray(x, dtype=np.float64)
        coeffs = np.array(model.coefficients, dtype=np.float64)
        if model.fit_type in ("linear", "quadratic"):
            return np.polyval(coeffs, x)
        if model.fit_type == "power":
            a, b = coeffs[0], coeffs[1]
            return a * np.power(x, b)
        raise ValueError(f"Unknown fit_type: {model.fit_type!r}")

    @staticmethod
    def _equation_text(model: CalibrationModel) -> str:
        if model.coefficients is None:
            return "No fit"
        c = model.coefficients
        if model.fit_type == "linear":
            if model.force_zero:
                return f"y = {c[0]:.4g} x"
            return f"y = {c[0]:.4g} x + {c[1]:.4g}"
        if model.fit_type == "quadratic":
            if model.force_zero:
                return f"y = {c[0]:.4g} x² + {c[1]:.4g} x"
            return f"y = {c[0]:.4g} x² + {c[1]:.4g} x + {c[2]:.4g}"
        if model.fit_type == "power":
            return f"y = {c[0]:.4g} · x^{c[1]:.4g}"
        return ""

    # ----- serialization helpers ---------------------------------------------

    @staticmethod
    def _model_to_dict(model: CalibrationModel) -> dict:
        return {
            "model_id": model.model_id,
            "analyte_name": model.analyte_name,
            "group_id": model.group_id,
            "fit_type": model.fit_type,
            "force_zero": model.force_zero,
            "units": model.units,
            "standards": [
                {
                    "sample_name": s.sample_name,
                    "concentration": s.concentration,
                    "area": s.area,
                    "included": s.included,
                }
                for s in model.standards
            ],
            "coefficients": model.coefficients,
            "r_squared": model.r_squared,
            "residuals": model.residuals,
            "created_at": model.created_at,
        }

    @staticmethod
    def _model_from_dict(d: dict) -> CalibrationModel:
        return CalibrationModel(
            model_id=d["model_id"],
            analyte_name=d["analyte_name"],
            group_id=d["group_id"],
            fit_type=d["fit_type"],
            force_zero=d.get("force_zero", False),
            units=d.get("units", ""),
            standards=[
                CalibrationPoint(
                    sample_name=s["sample_name"],
                    concentration=s["concentration"],
                    area=s["area"],
                    included=s.get("included", True),
                )
                for s in d.get("standards", [])
            ],
            coefficients=d.get("coefficients"),
            r_squared=d.get("r_squared"),
            residuals=d.get("residuals"),
            created_at=d.get("created_at", ""),
        )
