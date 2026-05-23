"""3-stage ingestion pipeline orchestrator.

Stage 1: detect_by_extension()  -> normalized extension string
Stage 2: FormatRegistry.match() -> FormatPreset or None
Stage 3: heuristic_parse()      -> fallback for unrecognized formats

Output: StandardizedResult or None
"""
from __future__ import annotations

import logging
from typing import Optional

from .types import StandardizedResult, FileIdentity, PlotHint, ColumnRole, SourceCategory
from .stage_1_detect import detect_by_extension
from .stage_2_registry import FormatRegistry
from .stage_3_heuristic import heuristic_parse
from .presets import load_all_presets

log = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self) -> None:
        self.registry = FormatRegistry(load_all_presets())

    def ingest(self, path: str, original_name: str) -> Optional[StandardizedResult]:
        extension = detect_by_extension(original_name)

        preset = self.registry.match(extension, path)
        if preset is not None:
            try:
                raw = preset.parse(path)
                return StandardizedResult(
                    data=raw["data"],
                    column_roles=raw["column_roles"],
                    identity=FileIdentity(
                        original_name=original_name,
                        extension=extension,
                        detected_format=preset.name,
                        detection_stage=2,
                    ),
                    plot_hint=raw.get("plot_hint", PlotHint.LINE),
                    source_category=raw.get("source_category", SourceCategory.GENERIC),
                    sample_name=raw.get("sample_name"),
                    metadata=raw.get("metadata", {}),
                )
            except Exception as e:
                log.debug(f"Stage 2 preset {preset.name} failed for {original_name}: {e}")

        raw = heuristic_parse(path, extension)
        if raw is not None:
            return StandardizedResult(
                data=raw["data"],
                column_roles=raw["column_roles"],
                identity=FileIdentity(
                    original_name=original_name,
                    extension=extension,
                    detected_format="heuristic",
                    detection_stage=3,
                ),
                plot_hint=raw.get("plot_hint", PlotHint.LINE),
                source_category=raw.get("source_category", SourceCategory.GENERIC),
                sample_name=raw.get("sample_name"),
                metadata=raw.get("metadata", {}),
            )

        return None


_default_pipeline: Optional[IngestionPipeline] = None


def ingest_file(path: str, original_name: str) -> Optional[StandardizedResult]:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = IngestionPipeline()
    return _default_pipeline.ingest(path, original_name)
