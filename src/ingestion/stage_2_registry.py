"""Stage 2: content-based format registry.

Each FormatPreset declares which extensions it handles and a sniff()
method that inspects the first N bytes/lines of a file.  The registry
tries presets in priority order (highest first) and returns the first
match, or None if nothing matches (falling through to Stage 3).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from .types import ColumnRole


class FormatPreset(ABC):
    name: str = ""
    extensions: set[str] = set()
    priority: int = 0

    @staticmethod
    @abstractmethod
    def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
        pass

    @abstractmethod
    def parse(self, path: str) -> dict:
        pass


_HEAD_BYTES = 4096
_HEAD_LINES = 50


def _read_head(path: str) -> tuple[bytes, list[str]]:
    with open(path, "rb") as f:
        head_bytes = f.read(_HEAD_BYTES)
    lines: list[str] = []
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            text = head_bytes.decode(enc)
            lines = text.splitlines()[:_HEAD_LINES]
            break
        except UnicodeDecodeError:
            continue
    return head_bytes, lines


class FormatRegistry:
    def __init__(self, presets: List[FormatPreset]) -> None:
        self._presets = sorted(presets, key=lambda p: -p.priority)

    def match(self, extension: str, path: str) -> Optional[FormatPreset]:
        head_bytes, head_lines = _read_head(path)
        for preset in self._presets:
            if extension not in preset.extensions:
                continue
            if preset.sniff(path, head_bytes, head_lines):
                return preset
        return None

    def list_formats(self) -> list[str]:
        return [p.name for p in self._presets]
