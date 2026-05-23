from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import pandas as pd


class ColumnRole(str, Enum):
    X = "x"
    Y = "y"
    LABEL = "label"
    IGNORE = "ignore"
    UNKNOWN = "unknown"


class PlotHint(str, Enum):
    LINE = "line"
    SCATTER = "scatter"
    BAR = "bar"
    HEATMAP = "heatmap"
    MULTI_Y = "multi_y"


class SourceCategory(str, Enum):
    CHROMATOGRAM = "chromatogram"
    SPECTRUM = "spectrum"
    LCMS_MS = "lcms_ms"
    LCMS_UV = "lcms_uv"
    KINETICS = "kinetics"
    GENERIC = "generic"


@dataclass
class FileIdentity:
    original_name: str
    extension: str
    detected_format: str
    detection_stage: int


@dataclass
class StandardizedResult:
    data: pd.DataFrame
    column_roles: Dict[str, ColumnRole]
    identity: FileIdentity
    plot_hint: PlotHint = PlotHint.LINE
    source_category: SourceCategory = SourceCategory.GENERIC
    sample_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def x_columns(self) -> List[str]:
        return [c for c, r in self.column_roles.items() if r == ColumnRole.X]

    @property
    def y_columns(self) -> List[str]:
        return [c for c, r in self.column_roles.items() if r == ColumnRole.Y]
