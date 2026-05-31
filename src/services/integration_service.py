"""
Integration Service for GeckoPlotter V2.

Owns chromatogram signal processing and peak integration settings.
Callbacks should call this service — scientific logic does not belong in callbacks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class IntegrationSettings:
    """Per-file integration parameters."""

    file_id: str = ''

    # Signal processing
    smooth_window: int = 11          # Savitzky-Golay window length (must be odd)
    smooth_poly_order: int = 3       # Savitzky-Golay polynomial order

    # Baseline
    baseline_method: str = 'snip'    # 'snip', 'polynomial', 'none'
    baseline_iterations: int = 40    # iterative baseline iterations
    baseline_poly_order: int = 5     # polynomial baseline order

    # Peak detection
    peak_threshold: float = 0.01     # minimum peak prominence (fraction of max)
    slope_threshold: float = 0.001   # slope cutoff for boundary detection
    extension_factor: float = 1.1    # boundary extension multiplier
    min_peak_width: int = 3          # minimum peak width in points
    min_peak_distance: int = 10      # minimum distance between peaks in points


@dataclass
class ProcessedSignal:
    """Result of signal processing for a chromatogram."""

    file_id: str
    time: np.ndarray
    raw: np.ndarray
    smoothed: np.ndarray
    baseline: np.ndarray
    corrected: np.ndarray           # smoothed − baseline


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class IntegrationService:
    """Chromatogram signal processing and integration parameter management.

    This service is stateless with respect to peaks — peak storage lives in
    ``PeakService``.  This service owns:

    * signal smoothing (Savitzky-Golay)
    * baseline estimation
    * processed-signal generation
    * per-file integration settings
    """

    def __init__(self):
        self._settings: Dict[str, IntegrationSettings] = {}
        self._processed: Dict[str, ProcessedSignal] = {}

    # -- Settings management ------------------------------------------------

    def get_settings(self, file_id: str) -> IntegrationSettings:
        if file_id not in self._settings:
            self._settings[file_id] = IntegrationSettings(file_id=file_id)
        return self._settings[file_id]

    def update_settings(self, file_id: str, **kwargs) -> IntegrationSettings:
        s = self.get_settings(file_id)
        for k, v in kwargs.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s

    # -- Signal processing --------------------------------------------------

    def process_signal(
        self,
        file_id: str,
        time: np.ndarray,
        raw_signal: np.ndarray,
        settings: Optional[IntegrationSettings] = None,
    ) -> ProcessedSignal:
        """Apply smoothing + baseline → return ProcessedSignal."""
        settings = settings or self.get_settings(file_id)

        smoothed = self._smooth(raw_signal, settings.smooth_window, settings.smooth_poly_order)
        baseline = self._estimate_baseline(smoothed, settings)
        corrected = smoothed - baseline

        result = ProcessedSignal(
            file_id=file_id,
            time=np.asarray(time, dtype=float),
            raw=np.asarray(raw_signal, dtype=float),
            smoothed=smoothed,
            baseline=baseline,
            corrected=corrected,
        )
        self._processed[file_id] = result
        return result

    def get_processed_signal(self, file_id: str) -> Optional[ProcessedSignal]:
        return self._processed.get(file_id)

    def clear_processed_signal(self, file_id: str) -> None:
        self._processed.pop(file_id, None)

    # -- Smoothing ----------------------------------------------------------

    @staticmethod
    def _smooth(signal: np.ndarray, window: int, poly_order: int) -> np.ndarray:
        """Savitzky-Golay smoothing."""
        try:
            from scipy.signal import savgol_filter
        except ImportError:
            return np.asarray(signal, dtype=float)

        sig = np.asarray(signal, dtype=float)
        if len(sig) < window:
            return sig
        # Ensure odd window
        if window % 2 == 0:
            window += 1
        if poly_order >= window:
            poly_order = window - 1
        return savgol_filter(sig, window, poly_order)

    # -- Baseline estimation ------------------------------------------------

    def _estimate_baseline(self, signal: np.ndarray, settings: IntegrationSettings) -> np.ndarray:
        method = settings.baseline_method
        if method == 'none':
            return np.zeros_like(signal)
        elif method == 'polynomial':
            return self._polynomial_baseline(signal, settings.baseline_poly_order)
        else:
            return self._snip_baseline(signal, settings.baseline_iterations)

    @staticmethod
    def _snip_baseline(signal: np.ndarray, iterations: int = 40) -> np.ndarray:
        """Statistics-sensitive Non-linear Iterative Peak-clipping (SNIP)."""
        sig = np.asarray(signal, dtype=float).copy()
        n = len(sig)
        if n == 0:
            return sig

        # Work in sqrt-space for better peak suppression
        working = np.log(np.log(np.sqrt(np.maximum(sig, 1e-10) + 1) + 1) + 1)

        for p in range(1, iterations + 1):
            for i in range(p, n - p):
                avg = (working[i - p] + working[i + p]) / 2.0
                if working[i] > avg:
                    working[i] = avg

        # Invert transform
        baseline = (np.exp(np.exp(working) - 1) - 1) ** 2 - 1e-10
        return np.maximum(baseline, 0)

    @staticmethod
    def _polynomial_baseline(signal: np.ndarray, order: int = 5) -> np.ndarray:
        """Iterative polynomial baseline fitting."""
        sig = np.asarray(signal, dtype=float)
        n = len(sig)
        if n == 0:
            return sig

        x = np.arange(n, dtype=float)
        mask = np.ones(n, dtype=bool)

        for _ in range(10):  # iterations
            coeffs = np.polyfit(x[mask], sig[mask], min(order, sum(mask) - 1))
            baseline = np.polyval(coeffs, x)
            # Keep only points at or below baseline
            mask = sig <= baseline * 1.05
            if mask.sum() < order + 1:
                break

        return baseline

    # -- Serialization ------------------------------------------------------

    def serialize(self) -> dict:
        result = {}
        for fid, s in self._settings.items():
            result[fid] = {
                'smooth_window': s.smooth_window,
                'smooth_poly_order': s.smooth_poly_order,
                'baseline_method': s.baseline_method,
                'baseline_iterations': s.baseline_iterations,
                'baseline_poly_order': s.baseline_poly_order,
                'peak_threshold': s.peak_threshold,
                'slope_threshold': s.slope_threshold,
                'extension_factor': s.extension_factor,
                'min_peak_width': s.min_peak_width,
                'min_peak_distance': s.min_peak_distance,
            }
        return result

    def deserialize(self, data: dict) -> None:
        self._settings.clear()
        for fid, d in data.items():
            s = IntegrationSettings(file_id=fid)
            for k, v in d.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            self._settings[fid] = s
