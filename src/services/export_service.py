"""Export service for GeckoPlotter V2.

Handles all export workflows: table data (CSV/Excel), peak results,
calibration models, figures (PNG/SVG/HTML), and full session save/restore.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go

if TYPE_CHECKING:
    from services.data_store import DataStore as DataManager


class ExportService:
    """Centralised export/import handler for GeckoPlotter V2."""

    # ------------------------------------------------------------------
    # Table exports
    # ------------------------------------------------------------------

    @staticmethod
    def export_table_csv(df: pd.DataFrame, filename: str = "data.csv") -> bytes:
        """Export a DataFrame as CSV bytes (UTF-8 with BOM for Excel compat)."""
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        return buf.getvalue()

    @staticmethod
    def export_table_excel(df: pd.DataFrame, filename: str = "data.xlsx") -> bytes:
        """Export a DataFrame as an .xlsx workbook using *openpyxl*."""
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Peak / comparison exports
    # ------------------------------------------------------------------

    @staticmethod
    def export_peak_results(
        peaks: List[Dict[str, Any]],
        file_id: Optional[str] = None,
    ) -> bytes:
        """Export a list of peak dicts as a CSV.

        Each dict is expected to contain keys such as *name*, *retention_time*,
        *area*, *height*, *width*, *start*, *end*, etc.  Missing keys are
        filled with empty strings.
        """
        if not peaks:
            return b""

        columns = [
            "name",
            "retention_time",
            "area",
            "height",
            "width",
            "start",
            "end",
            "symmetry",
            "resolution",
        ]
        # Collect any extra keys that may be present
        all_keys = set()
        for p in peaks:
            all_keys.update(p.keys())
        extra = sorted(all_keys - set(columns))
        columns.extend(extra)

        rows = []
        for p in peaks:
            row: Dict[str, Any] = {}
            if file_id is not None:
                row["file_id"] = file_id
            for col in columns:
                row[col] = p.get(col, "")
            rows.append(row)

        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        return buf.getvalue()

    @staticmethod
    def export_comparison_table(comparison_df: pd.DataFrame) -> bytes:
        """Export a cross-sample comparison DataFrame as CSV bytes."""
        buf = io.BytesIO()
        comparison_df.to_csv(buf, index=False, encoding="utf-8-sig")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Calibration export
    # ------------------------------------------------------------------

    @staticmethod
    def export_calibration(calibration_model: dict) -> str:
        """Serialise a calibration model to a JSON string.

        The *calibration_model* dict typically holds equation type,
        coefficients, R-squared, concentration units, etc.
        """
        serialisable = {}
        for key, value in calibration_model.items():
            try:
                json.dumps(value)
                serialisable[key] = value
            except (TypeError, ValueError):
                serialisable[key] = str(value)

        return json.dumps(serialisable, indent=2)

    # ------------------------------------------------------------------
    # Figure exports
    # ------------------------------------------------------------------

    @staticmethod
    def export_figure_png(
        fig: go.Figure,
        width: int = 800,
        height: int = 500,
        scale: float = 3,
    ) -> bytes:
        """Render a Plotly figure to high-resolution PNG bytes via *kaleido*."""
        try:
            return fig.to_image(
                format="png",
                width=width,
                height=height,
                scale=scale,
            )
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                "PNG export requires the 'kaleido' package (>=1.0.0). "
                "Install it with: pip install -U kaleido"
            ) from exc

    @staticmethod
    def export_figure_svg(
        fig: go.Figure,
        width: int = 800,
        height: int = 500,
    ) -> bytes:
        """Render a Plotly figure to SVG bytes via *kaleido*."""
        try:
            return fig.to_image(
                format="svg",
                width=width,
                height=height,
            )
        except (ImportError, ValueError) as exc:
            raise RuntimeError(
                "SVG export requires the 'kaleido' package (>=1.0.0). "
                "Install it with: pip install -U kaleido"
            ) from exc

    @staticmethod
    def export_figure_html(fig: go.Figure) -> str:
        """Return a self-contained interactive HTML string of the figure."""
        return fig.to_html(full_html=True, include_plotlyjs="cdn")

    # ------------------------------------------------------------------
    # Session save / restore
    # ------------------------------------------------------------------

    @staticmethod
    def export_session(
        data_manager: "DataManager",
        peak_service: Any = None,
        calibration_service: Any = None,
    ) -> str:
        """Serialise the full session state to a JSON string.

        Captures file records (with data stored as serialisable types),
        peak results, and calibration models so the session can be
        restored later.
        """
        session: Dict[str, Any] = {
            "version": "2.0",
            "exported_at": datetime.utcnow().isoformat() + "Z",
        }

        # --- File states ---
        file_states: List[Dict[str, Any]] = []
        if hasattr(data_manager, "file_records"):
            for rec in data_manager.file_records:
                entry = {}
                for key, value in rec.items():
                    try:
                        json.dumps(value)
                        entry[key] = value
                    except (TypeError, ValueError):
                        if isinstance(value, pd.DataFrame):
                            entry[key] = value.to_dict(orient="list")
                        else:
                            entry[key] = str(value)
                file_states.append(entry)
        session["file_states"] = file_states

        # --- Peaks ---
        if peak_service is not None and hasattr(peak_service, "get_all_peaks"):
            try:
                session["peaks"] = peak_service.get_all_peaks()
            except Exception:
                session["peaks"] = []
        else:
            session["peaks"] = []

        # --- Calibrations ---
        if calibration_service is not None and hasattr(
            calibration_service, "get_all_calibrations"
        ):
            try:
                cals = calibration_service.get_all_calibrations()
                serialisable_cals = {}
                for key, cal in cals.items():
                    try:
                        json.dumps(cal)
                        serialisable_cals[key] = cal
                    except (TypeError, ValueError):
                        serialisable_cals[key] = str(cal)
                session["calibrations"] = serialisable_cals
            except Exception:
                session["calibrations"] = {}
        else:
            session["calibrations"] = {}

        return json.dumps(session, indent=2)

    @staticmethod
    def import_session(
        data: str,
        data_manager: "DataManager",
        peak_service: Any = None,
        calibration_service: Any = None,
    ) -> None:
        """Restore a session from a JSON string produced by :meth:`export_session`.

        Repopulates the *data_manager* file records and optionally restores
        peak and calibration state.
        """
        session = json.loads(data)

        # --- File states ---
        file_states = session.get("file_states", [])
        if hasattr(data_manager, "file_records"):
            data_manager.file_records = file_states

        # --- Peaks ---
        peaks = session.get("peaks", [])
        if peak_service is not None and hasattr(peak_service, "set_all_peaks"):
            try:
                peak_service.set_all_peaks(peaks)
            except Exception:
                pass

        # --- Calibrations ---
        calibrations = session.get("calibrations", {})
        if calibration_service is not None and hasattr(
            calibration_service, "set_all_calibrations"
        ):
            try:
                calibration_service.set_all_calibrations(calibrations)
            except Exception:
                pass
