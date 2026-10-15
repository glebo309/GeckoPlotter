# =============================================================================
# File: services/calibration_service.py
# =============================================================================
"""
Calibration Service for GeckoPlotter V2 — domain service for building,
fitting, and applying calibration models to chromatographic peak data.
"""

import uuid
import json
from copy import deepcopy
from dataclasses import dataclass, field, asdict
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
    source_id: str = ""
    position: Optional[float] = None


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
    response_type: str = "area"
    response_units: str = ""
    match_position: Optional[float] = None
    match_tolerance: float = 0.2
    signal_key: str = ""
    x_units: str = ""
    auto_apply: bool = True
    # Old exports contain assigned concentrations but no measured responses.
    # Keep these references distinct from measured calibration standards.
    reference_concentrations: Dict[str, float] = field(default_factory=dict)


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
        *, response_type: str = "area", response_units: str = "",
        match_position: Optional[float] = None, match_tolerance: float = 0.2,
        signal_key: str = "", x_units: str = "", auto_apply: bool = True,
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
            response_type=response_type, response_units=response_units,
            match_position=match_position, match_tolerance=match_tolerance,
            signal_key=signal_key, x_units=x_units, auto_apply=auto_apply,
        )
        self._validate_configuration(model)
        self._models[model.model_id] = model
        return model

    def remove_model(self, model_id: str) -> bool:
        """Delete a calibration; True when it existed."""
        return self._models.pop(model_id, None) is not None

    def replace_model(self, model: CalibrationModel) -> CalibrationModel:
        """Atomically commit an editor model, keeping its ID and copying data.

        Validate/refit in a temporary service before replacing the live entry;
        invalid edits cannot change an existing calibration or create a copy.
        Also accepts a newly fitted editor model whose ID is not registered yet.
        """
        if not isinstance(model, CalibrationModel) or not model.model_id:
            raise ValueError('A calibration model with an ID is required.')
        staged = CalibrationService()
        validated = staged.import_calibrations(self._model_to_dict(model))[0]
        self._models[validated.model_id] = validated
        return validated

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

    def update_standards(self, model_id: str, standards: List[CalibrationPoint]) -> None:
        """Replace measured standards and invalidate the previous fit."""
        model = self._require_model(model_id)
        if not all(isinstance(point, CalibrationPoint) for point in standards):
            raise ValueError("Standards must be CalibrationPoint measurements.")
        model.standards = deepcopy(standards)
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
        self._invalidate_fit(model)
        self._validate_configuration(model)
        included = [s for s in model.standards if s.included]

        if len(included) < 2:
            raise ValueError(
                f"At least 2 included standards required; got {len(included)}."
            )

        conc = np.array([s.concentration for s in included], dtype=np.float64)
        area = np.array([s.area for s in included], dtype=np.float64)

        if not np.all(np.isfinite(conc)) or np.any(conc < 0):
            raise ValueError("Concentrations must be finite and nonnegative.")
        if not np.all(np.isfinite(area)):
            raise ValueError("Measured responses must be finite.")
        if np.ptp(area) == 0:
            raise ValueError("Measured responses must vary across standards.")
        required = 3 if model.fit_type == "quadratic" and not model.force_zero else 2
        if np.unique(conc).size < required:
            raise ValueError(f"At least {required} distinct concentration levels required.")
        scaled = conc / max(float(np.max(conc)), 1.0)
        if model.fit_type == "quadratic":
            design = np.column_stack([scaled ** 2, scaled])
        else:
            design = scaled[:, None]
        if not model.force_zero or model.fit_type == "power":
            design = np.column_stack([design, np.ones(len(conc))])
        if np.linalg.matrix_rank(design) < design.shape[1]:
            raise ValueError("Concentration levels cannot uniquely determine this fit.")

        if model.fit_type == "linear":
            coeffs, predicted = self._fit_linear(conc, area, model.force_zero)
        elif model.fit_type == "quadratic":
            coeffs, predicted = self._fit_quadratic(conc, area, model.force_zero)
        elif model.fit_type == "power":
            coeffs, predicted = self._fit_power(conc, area)
        else:
            raise ValueError(f"Unknown fit_type: {model.fit_type!r}")

        if not np.all(np.isfinite(coeffs)) or not np.all(np.isfinite(predicted)):
            raise ValueError("The fitted model is not finite.")
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

        try:
            area = float(area)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(area):
            return None
        coeffs = np.array(model.coefficients, dtype=np.float64)

        def valid(value):
            return float(value) if np.isfinite(value) and value >= 0 else None

        if model.fit_type == "linear":
            m, b = coeffs[0], coeffs[1] if len(coeffs) > 1 else 0.0
            return valid((area - b) / m) if m != 0 else None
        if model.fit_type == "quadratic":
            a, b, c = coeffs[0], coeffs[1], coeffs[2] if len(coeffs) > 2 else 0.0
            if a == 0:
                return valid((area - c) / b) if b != 0 else None
            discriminant = b ** 2 - 4 * a * (c - area)
            tolerance = np.finfo(float).eps * max(b*b, abs(4*a*(c-area)), 1.0) * 16
            if discriminant < -tolerance:
                return None
            sqrt_d = np.sqrt(max(0.0, discriminant))
            roots = [(-b + sqrt_d)/(2*a), (-b - sqrt_d)/(2*a)]
            candidates = []
            for root in roots:
                if valid(root) is not None and not any(np.isclose(root, prior, rtol=1e-7, atol=1e-10) for prior in candidates):
                    candidates.append(float(root))
            if len(candidates) == 1:
                return candidates[0]
            levels = ([point.concentration for point in model.standards if point.included]
                      or list(model.reference_concentrations.values()))
            if levels and candidates:
                lo, hi = min(levels), max(levels)
                inside = [root for root in candidates if lo-1e-9 <= root <= hi+1e-9]
                if len(inside) == 1:
                    return inside[0]
            return None
        if model.fit_type == "power":
            a, exponent = coeffs
            if a <= 0 or exponent == 0 or area < 0 or (area == 0 and exponent < 0):
                return None
            with np.errstate(over='ignore', invalid='ignore'):
                return valid(np.power(area/a, 1.0/exponent))
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
                    f"{model.response_type.capitalize()}: %{{y:.4g}}<extra></extra>"
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
                    f"{model.response_type.capitalize()}: %{{y:.4g}}<extra></extra>"
                ),
                text=[s.sample_name for s in exc],
            ))

        # Legacy concentration references define a known fit domain, but do
        # not become observed response markers.
        levels = [s.concentration for s in inc] or list(model.reference_concentrations.values())
        if model.coefficients is not None and levels:
            conc_arr = np.array(levels)
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
            yaxis_title=f"Peak {model.response_type}" + (f" ({model.response_units})" if model.response_units else ""),
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
            y=[0.0 if abs(value) <= max(1.0, max(abs(s.area) for s in inc))*1e-12 else value
               for value in model.residuals],
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
            yaxis_title="Response error",
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
        return self.import_calibrations(data)[0].model_id

    def export_calibrations(self, model_ids=None) -> dict:
        """Return a portable, versioned object suitable for JSON download."""
        ids = list(self._models) if model_ids is None else list(model_ids)
        return {'format': 'geckoplotter-calibrations', 'version': 1,
                'models': [self.export_model(model_id) for model_id in ids]}

    def import_calibrations(self, payload) -> List[CalibrationModel]:
        """Import portable, current or Streamlit JSON atomically.

        Measured points are refitted. Coefficients-only legacy models retain
        their validated fit, without inventing observations or residuals.
        Existing live models are never overwritten by an imported ID.
        """
        if isinstance(payload, (str, bytes)):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError) as exc:
                raise ValueError('Invalid calibration JSON.') from exc
        if not isinstance(payload, dict):
            raise ValueError('Calibration file must contain an object.')
        if 'format' in payload:
            if payload.get('format') != 'geckoplotter-calibrations' or payload.get('version') != 1:
                raise ValueError('Unsupported calibration format or version.')
            records = payload.get('models')
            if not isinstance(records, list):
                raise ValueError('Calibration models must be a list.')
        elif 'calibration_models' in payload or isinstance(payload.get('standards'), dict):
            records = self._legacy_records(payload)
        elif 'analyte_name' in payload or 'model_id' in payload:
            records = [payload]
        elif 'model_type' in payload:
            records = self._legacy_records({'calibration_models': {'': payload}})
        elif payload and all(isinstance(value, dict) and 'analyte_name' in value for value in payload.values()):
            records = list(payload.values())
        else:
            raise ValueError('No calibration models found in the file.')
        if not records:
            raise ValueError('No calibration models found in the file.')

        staged = CalibrationService()
        used_ids = set(self._models)
        for record in records:
            try:
                model = self._model_from_dict(record)
                self._validate_configuration(model)
                for point in model.standards:
                    point.concentration = self._finite_number(point.concentration, 'Concentration', nonnegative=True)
                    point.area = self._finite_number(point.area, 'Measured response')
                    if point.position is not None:
                        point.position = self._finite_number(point.position, 'Standard position')
                model.reference_concentrations = {str(key): self._finite_number(value, 'Reference concentration', nonnegative=True)
                                                  for key, value in model.reference_concentrations.items()}
                if not model.model_id or model.model_id in used_ids:
                    model.model_id = str(uuid.uuid4())
                used_ids.add(model.model_id)
                staged._models[model.model_id] = model
                if model.standards:
                    staged.fit_model(model.model_id)
                elif model.coefficients is not None:
                    self._validate_coefficients(model)
                    model.residuals = None
                else:
                    self._invalidate_fit(model)
            except (KeyError, TypeError, OverflowError) as exc:
                raise ValueError(f'Invalid calibration model: {exc}') from exc
        self._models.update(staged._models)
        return list(staged._models.values())

    @staticmethod
    def _legacy_records(payload):
        """Read the Streamlit exporter: concentration references are not areas."""
        models = payload.get('calibration_models', {})
        standards = payload.get('standards', {})
        if not isinstance(models, dict) or not isinstance(standards, dict):
            raise ValueError('Legacy calibration models and standards must be objects.')
        records = []
        for group in dict.fromkeys([*models, *standards]):
            raw = models.get(group, {})
            references = standards.get(group, {})
            if not isinstance(raw, dict) or not isinstance(references, dict):
                raise ValueError('Invalid legacy calibration group.')
            fit_type = raw.get('model_type', references.get('model_type', payload.get('model_type', 'linear')))
            fit_type = 'power' if fit_type == 'power law' else fit_type
            zero = raw.get('force_zero', references.get('force_zero', payload.get('force_zero', False)))
            points = raw.get('raw_data', references.get('raw_data', []))
            if isinstance(raw.get('standards'), list):
                points = raw['standards']
            assigned = {}
            for source in (references, raw.get('standards', {})):
                if not isinstance(source, dict):
                    continue
                for key, value in source.items():
                    if key not in ('name', 'rt', 'units', 'force_zero', 'model_type') and isinstance(value, (int, float)) and not isinstance(value, bool):
                        assigned[str(key)] = value
            coefficients = None
            params = raw.get('parameters')
            if raw and not points:
                if not isinstance(params, dict):
                    raise ValueError('Legacy model has no measured points or numeric parameters.')
                if fit_type == 'linear':
                    slope = params.get('slope', params.get('m'))
                    coefficients = [slope, params.get('intercept', params.get('b', 0))]
                elif fit_type == 'quadratic':
                    coefficients = [params.get('a'), params.get('b'), params.get('c', 0)]
                elif fit_type == 'power':
                    coefficients = [params.get('a'), params.get('b')]
            records.append({
                'model_id': str(uuid.uuid4()), 'analyte_name': raw.get('name', references.get('name', f'Group {group}')),
                'group_id': str(group), 'fit_type': fit_type, 'force_zero': zero,
                'units': raw.get('units', references.get('units', payload.get('units', ''))),
                'match_position': raw.get('rt', references.get('rt')), 'x_units': 'min',
                'standards': points, 'reference_concentrations': assigned,
                'coefficients': coefficients, 'r_squared': raw.get('r_squared'),
            })
        return records

    @staticmethod
    def _finite_number(value, name, nonnegative=False):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f'{name} must be a finite number.') from exc
        if not np.isfinite(number) or (nonnegative and number < 0):
            raise ValueError(f'{name} must be finite' + (' and nonnegative.' if nonnegative else '.'))
        return number

    @classmethod
    def _validate_configuration(cls, model):
        if model.fit_type not in ('linear', 'quadratic', 'power'):
            raise ValueError(f'Unknown fit type: {model.fit_type!r}')
        if model.response_type not in ('area', 'height'):
            raise ValueError('Response must be area or height.')
        model.match_tolerance = cls._finite_number(model.match_tolerance, 'Match tolerance', nonnegative=True)
        if model.match_position is not None:
            model.match_position = cls._finite_number(model.match_position, 'Match position')

    @classmethod
    def _validate_coefficients(cls, model):
        if not isinstance(model.coefficients, (list, tuple, np.ndarray)):
            raise ValueError('Calibration coefficients must be a numeric list.')
        coefficients = list(model.coefficients)
        expected = 3 if model.fit_type == 'quadratic' else 2
        if model.force_zero and model.fit_type in ('linear', 'quadratic') and len(coefficients) == expected-1:
            coefficients.append(0.0)
        if len(coefficients) != expected:
            raise ValueError('Wrong number of calibration coefficients.')
        coefficients = [cls._finite_number(value, 'Coefficient') for value in coefficients]
        if model.force_zero and model.fit_type != 'power' and coefficients[-1] != 0:
            raise ValueError('A zero-intercept model cannot have a nonzero intercept.')
        if (model.fit_type == 'linear' and coefficients[0] == 0 or
            model.fit_type == 'quadratic' and coefficients[0] == coefficients[1] == 0 or
            model.fit_type == 'power' and (coefficients[0] <= 0 or coefficients[1] == 0)):
            raise ValueError('Calibration coefficients cannot define a constant or invalid response.')
        model.coefficients = coefficients
        if model.r_squared is not None:
            model.r_squared = cls._finite_number(model.r_squared, 'R squared')

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
        def term(value, suffix=""):
            return f" {'−' if value < 0 else '+'} {abs(value):.4g}{suffix}"
        if model.fit_type == "linear":
            if model.force_zero:
                return f"y = {c[0]:.4g} x"
            return f"y = {c[0]:.4g} x" + term(c[1])
        if model.fit_type == "quadratic":
            if model.force_zero:
                return f"y = {c[0]:.4g} x²" + term(c[1], " x")
            return f"y = {c[0]:.4g} x²" + term(c[1], " x") + term(c[2])
        if model.fit_type == "power":
            return f"y = {c[0]:.4g} · x^{c[1]:.4g}"
        return ""

    # ----- serialization helpers ---------------------------------------------

    @staticmethod
    def _model_to_dict(model: CalibrationModel) -> dict:
        return asdict(model)

    @staticmethod
    def _model_from_dict(d: dict) -> CalibrationModel:
        values = {key: deepcopy(value) for key, value in d.items()
                  if key in CalibrationModel.__dataclass_fields__ and key != 'standards'}
        values.setdefault('model_id', str(uuid.uuid4()))
        values.setdefault('analyte_name', 'Calibration')
        values.setdefault('group_id', '')
        values.setdefault('fit_type', 'linear')
        values.setdefault('force_zero', False)
        values.setdefault('units', '')
        points = d.get('standards', [])
        if not isinstance(points, list):
            raise ValueError("Measured standards must be a list.")
        values['standards'] = [CalibrationPoint(**{key: deepcopy(value) for key, value in point.items()
                                if key in CalibrationPoint.__dataclass_fields__}) for point in points]
        return CalibrationModel(**values)
