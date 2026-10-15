"""Wavelengths of UV detector channels whose files do not record them.

Agilent's ``.dx_VWD1A.CSV`` / ``VWD1B.CSV`` exports are two bare columns: the wavelength (280 nm, 250 nm ...) is only in
the ``.cdf`` export and the method. The user enters it once per detector channel (VWD1A, VWD1B); it is applied to that
channel in every loaded run and remembered on this computer (``detector_wavelengths.json`` in the GeckoPlotter folder,
``$GECKO_SETTINGS_DIR`` to move it) for the runs loaded later. A wavelength a file does record is never changed.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Optional


def _path() -> Path:
    folder = os.environ.get('GECKO_SETTINGS_DIR') or str(Path.home() / 'Documents' / 'GeckoPlotter')
    return Path(folder) / 'detector_wavelengths.json'


def remembered() -> dict:
    try:
        data = json.loads(_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float)) and v > 0} \
        if isinstance(data, dict) else {}


def _remember(detector: str, nm: float) -> None:
    data = remembered()
    data[detector] = nm
    try:
        _path().parent.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(data, indent=1, sort_keys=True), encoding='utf-8')
    except OSError:
        pass                                    # still applied to the loaded runs, just not remembered


def _recorded(meta: dict) -> Optional[float]:
    value = meta.get('wavelength_nm', meta.get('wavelength'))
    try:
        value = float(str(value).replace('nm', '').strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def needs_wavelength(meta: Optional[dict]) -> Optional[str]:
    """The detector name (e.g. ``VWD1A``) of a UV channel whose wavelength the file did not give, else None."""
    meta = meta or {}
    if not meta.get('is_uv_data') or not meta.get('detector_name'):
        return None
    if meta.get('wavelength_source') == 'entered' or _recorded(meta) is None:
        return str(meta['detector_name'])
    return None


def _components(store):
    for bundle in list(store._bundles.values()):
        yield from bundle.component_list


def _apply(component, nm: float) -> None:
    meta = component.metadata
    meta['wavelength'] = meta['wavelength_nm'] = nm
    meta['wavelength_source'] = 'entered'


def set_wavelength(store, detector: str, nm: float) -> int:
    """Give every loaded channel of ``detector`` without a recorded wavelength this one; remember it. Returns count."""
    nm = float(nm)
    changed = 0
    for component in _components(store):
        if isinstance(component.metadata, dict) and needs_wavelength(component.metadata) == detector:
            _apply(component, nm)
            changed += 1
    _remember(detector, nm)
    return changed


def apply_remembered(store) -> int:
    """Newly loaded channels get the wavelength entered for their detector before. Returns how many."""
    known = remembered()
    changed = 0
    for component in _components(store):
        meta = component.metadata if isinstance(component.metadata, dict) else {}
        detector = needs_wavelength(meta)
        if detector in known and meta.get('wavelength_source') != 'entered':
            _apply(component, known[detector])
            changed += 1
    return changed
