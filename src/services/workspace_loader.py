"""Load instrument files into a workspace the way a drop on the app does, without Dash.

Used by the upload callback (callbacks/upload_callbacks.py) and by the agent interface (gecko_api.py), so a file opened
by an agent becomes exactly the samples, channels, methods and wavelengths the GUI shows.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

log = logging.getLogger(__name__)


@dataclass
class LoadResult:
    bundles: list = field(default_factory=list)       # new bundles, in the order they were added
    failed: List[str] = field(default_factory=list)   # file names no reader could parse
    methods: int = 0                                  # LabSolutions method files (.lcm) read


def register_method_bytes(store, raw: bytes, name: str) -> int:
    """Read the method in one .lcm/.lcd and attach it to the samples that used it. Returns the samples matched."""
    from services.shimadzu_method import MethodFormatError, read_method, register_method
    try:
        matched = register_method(store, read_method(raw, name), raw)
    except (MethodFormatError, ValueError) as exc:
        log.warning("Could not read the method in %s: %s", name, exc)
        return 0
    except Exception:
        log.exception("Could not read the method in %s", name)
        return 0
    if matched:
        log.info("Method in %s attached to %d sample(s)", name, matched)
    else:
        log.warning("%s was read but no loaded sample uses it", name)
    return matched


def auto_import_peaks(store, bundle) -> None:
    """Import the peaks of a Chromeleon Integration.txt component."""
    try:
        from callbacks.tab_callbacks import parse_integration_results
        text = bundle.get_integration_text()
        parsed = parse_integration_results(text) if text else None
        if not parsed:
            return
        time_arr, signal_arr = store.get_xy_arrays(bundle.bundle_id)
        if time_arr is None:
            return
        store.peak_service.import_instrument_peaks(file_id=bundle.bundle_id, parsed_results=parsed,
                                                   time_axis=time_arr, signal=signal_arr)
        store.peak_service.group_peaks_across_samples(file_overlay_map=store.build_file_overlay_map())
    except Exception as exc:                            # noqa: BLE001  a bad peak list never blocks the data
        log.warning("Could not auto-import peaks for '%s': %s", bundle.name, exc)


def load_files(store, files: Iterable[Tuple[str, bytes]]) -> LoadResult:
    """Parse ``(file name, bytes)`` pairs, group them into samples and add them to ``store``.

    Method files (.lcm) are attached to the loaded samples that used them instead of being plotted. Every new UV
    channel gets the wavelength remembered for its detector, every sample its LabSolutions method, and the channels
    the GUI shows first are set as on a drop.
    """
    from ingestion import ingest_file
    from services.bundling_service import assign_bundles
    from services.shimadzu_method import is_method_upload

    result = LoadResult()
    files = list(files)
    for name, raw in files:
        if is_method_upload(name):
            register_method_bytes(store, raw, name)
            result.methods += 1

    parsed = []
    for name, raw in files:
        if is_method_upload(name):
            continue
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f'_{name}')
        try:
            tmp.write(raw)
            tmp.close()
            standardized = ingest_file(tmp.name, name)
        except Exception as exc:                        # noqa: BLE001  one bad file never stops the others
            log.error("Error parsing %s: %s", name, exc)
            standardized = None
        finally:
            tmp.close()
            try:
                os.unlink(tmp.name)                     # parsers read the whole file; the bytes stay in memory
            except OSError:
                pass
        if standardized is None:
            log.warning("Pipeline could not parse %s", name)
            result.failed.append(name)
            continue
        parsed.append((name, raw, standardized))
    if not parsed:
        return result

    result.bundles = assign_bundles(parsed)
    for name, raw, _standardized in parsed:            # an .lcd carries the method it was run with
        if name.lower().endswith('.lcd'):
            register_method_bytes(store, raw, name)
    for bundle in result.bundles:
        store.add_bundle(bundle)
        if bundle.has_integration_data():
            auto_import_peaks(store, bundle)

    from services.detector_wavelengths import apply_remembered
    apply_remembered(store)                             # UV channels exported without their wavelength (VWD CSV)
    from services.shimadzu_method import apply_methods
    apply_methods(store)
    from services.channel_visibility import initialize_imported_channels
    initialize_imported_channels(store, result.bundles)
    return result
