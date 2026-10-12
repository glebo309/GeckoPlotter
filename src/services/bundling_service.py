from __future__ import annotations

import os
import re
import uuid
from collections import OrderedDict
from dataclasses import replace
from typing import Any, Dict, List, NamedTuple, Tuple

try:
    from ..ingestion.types import SourceCategory, StandardizedResult
except ImportError:
    try:
        from src.ingestion.types import SourceCategory, StandardizedResult
    except ImportError:
        from ingestion.types import SourceCategory, StandardizedResult

try:
    from .data_store import Bundle, BundleType, Component, ComponentRole
except ImportError:
    from services.data_store import Bundle, BundleType, Component, ComponentRole


ParsedFile = Tuple[str, bytes, StandardizedResult]


class _ParsedFileParts(NamedTuple):
    filename: str
    raw_bytes: bytes
    standardized: StandardizedResult


CHROMELEON_MAIN_PATTERN = r"^(.+)_UV_VIS_\d+\.txt$"
CHROMELEON_AUXILIARY_PATTERNS = [
    r"^(.+)_SST\.txt$",
    r"^(.+)_Chromatogram\.txt$",
    r"^(.+)_Integration\.txt$",
    r"^(.+)_Peak Analysis\.txt$",
    r"^(.+)_Summary\.txt$",
]

def assign_bundles(parsed_files: List[ParsedFile]) -> List[Bundle]:
    groups: "OrderedDict[Tuple[BundleType, str], List[Component]]" = OrderedDict()
    fallback_index = 0

    for parsed_file in parsed_files:
        filename, raw_bytes, standardized = _unpack_parsed_file(parsed_file)
        channels = standardized.metadata.get('chromatogram_channels')
        if channels:
            # A sectioned export is one injection with independently selectable
            # signals. This capability is shared by any chromatogram adapter.
            fallback_index += 1
            name = standardized.sample_name or _display_name(filename)
            groups[(BundleType.CHROMATOGRAM, f'{name}:{fallback_index}')] = _channel_components(
                filename, raw_bytes, standardized, channels)
            continue
        bundle_type, base_name = _bundle_identity(filename, standardized)
        if base_name is None:
            fallback_index += 1
            base_name = _display_name(filename)
            group_key = (bundle_type, f"{base_name}:{fallback_index}")
        else:
            group_key = (bundle_type, base_name)

        component = _create_component(filename, raw_bytes, standardized)
        groups.setdefault(group_key, []).append(component)

    bundles: List[Bundle] = []
    for (bundle_type, group_name), components in groups.items():
        display_name = group_name.rsplit(":", 1)[0] if ":" in group_name else group_name
        bundles.append(
            Bundle(
                bundle_id=str(uuid.uuid4()),
                name=display_name,
                bundle_type=bundle_type,
                component_list=components,
            )
        )

    return bundles


def _channel_components(filename, raw_bytes, standardized, channels):
    common = {k:v for k,v in standardized.metadata.items() if k != 'chromatogram_channels'}
    components = []
    for index, channel in enumerate(channels):
        metadata = dict(common)
        if index:
            for key in ('pda', 'instrument_status', 'instrument_peaks'):
                metadata.pop(key, None)
        metadata.update(channel.get('metadata', {}))
        metadata['display_name'] = channel['name']
        metadata['sample_name'] = standardized.sample_name or _display_name(filename)
        if index:
            metadata['source_file_id'] = components[0].component_id
            if common.get('pda'):
                metadata['pda_source_id'] = components[0].component_id
        signal = replace(standardized, data=channel['data'],
                         column_roles=dict(channel['column_roles']), metadata=metadata)
        components.append(_create_component(filename, raw_bytes if index == 0 else b'', signal))
    return components


def extract_chromeleon_base_name(filename: str, metadata: Dict[str, Any] | None = None) -> str | None:
    if metadata:
        injection = metadata.get("injection")
        if injection:
            return str(injection).strip()

    clean_name = os.path.basename(filename).replace("temp_", "")
    match = re.match(CHROMELEON_MAIN_PATTERN, clean_name)
    if match:
        return match.group(1).strip()

    for pattern in CHROMELEON_AUXILIARY_PATTERNS:
        match = re.match(pattern, clean_name)
        if match:
            return match.group(1).strip()

    return None


def extract_lcms_base_name(filename: str, metadata: Dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    candidate = metadata.get("experiment_title") or metadata.get("source_file_reference") or filename
    base = os.path.splitext(os.path.basename(str(candidate)))[0]
    if ".dx_" in base.lower():
        base = re.split(r"\.dx_", base, maxsplit=1, flags=re.IGNORECASE)[0]
    elif base.lower().endswith(".dx"):
        base = base[:-3]
    patterns = [
        r"_MS1\s*[+-]TIC.*$",
        r"_VWD1[AB]$",
        r"_MS\d*.*$",
        r"_[+-]$",
        r"_pos(itive)?$",
        r"_neg(ative)?$",
    ]
    for pattern in patterns:
        base = re.sub(pattern, "", base, flags=re.IGNORECASE)
    return base.rstrip("_- ")


def _unpack_parsed_file(parsed_file: ParsedFile) -> _ParsedFileParts:
    if hasattr(parsed_file, "filename"):
        return _ParsedFileParts(
            parsed_file.filename,
            parsed_file.raw_bytes,
            parsed_file.standardized,
        )
    return _ParsedFileParts(parsed_file[0], parsed_file[1], parsed_file[2])


def _bundle_identity(filename: str, standardized: StandardizedResult) -> Tuple[BundleType, str | None]:
    if _is_chromeleon(filename, standardized):
        return BundleType.CHROMELEON, extract_chromeleon_base_name(filename, standardized.metadata)

    if _is_lcms(filename, standardized):
        return BundleType.LCMS, extract_lcms_base_name(filename, standardized.metadata)

    return _single_file_bundle_type(standardized), None


def _create_component(filename: str, raw_bytes: bytes, standardized: StandardizedResult) -> Component:
    return Component(
        component_id=str(uuid.uuid4()),
        role=_component_role(filename, standardized),
        original_filename=filename,
        raw_bytes=raw_bytes,
        dataframe=standardized.data,
        column_roles=dict(standardized.column_roles),
        metadata=dict(standardized.metadata),
        source_category=standardized.source_category,
        plot_hint=standardized.plot_hint,
        standardized=standardized,
    )


def _component_role(filename: str, standardized: StandardizedResult) -> ComponentRole:
    clean_name = os.path.basename(filename).replace("temp_", "")

    chromeleon_roles = [
        (ComponentRole.PRIMARY, CHROMELEON_MAIN_PATTERN),
        (ComponentRole.SST, r"^(.+)_SST\.txt$"),
        (ComponentRole.PRIMARY, r"^(.+)_Chromatogram\.txt$"),
        (ComponentRole.INTEGRATION, r"^(.+)_Integration\.txt$"),
        (ComponentRole.PEAK_ANALYSIS, r"^(.+)_Peak Analysis\.txt$"),
        (ComponentRole.SUMMARY, r"^(.+)_Summary\.txt$"),
    ]
    for role, pattern in chromeleon_roles:
        if re.match(pattern, clean_name):
            return role

    # Explicit detector metadata is authoritative when an MS export was renamed.
    # UV channels keep their own role even if instrument-wide metadata has polarity.
    mode = str(standardized.metadata.get("ionization_mode", "")).lower()
    if standardized.source_category == SourceCategory.LCMS_MS and mode in ("positive", "negative"):
        return ComponentRole.MS_NEGATIVE if mode == "negative" else ComponentRole.MS_POSITIVE

    lcms_roles = [
        (ComponentRole.VWD_A, r"(_VWD_A\.(?:cdf|csv)$|_VWD1A\.(?:cdf|csv)$)"),
        (ComponentRole.VWD_B, r"(_VWD_B\.(?:cdf|csv)$|_VWD1B\.(?:cdf|csv)$)"),
        (ComponentRole.MS_NEGATIVE, r"(_neg(?:ative)?\.cdf$|_MS1\s*-TIC.*\.(?:cdf|csv)$|_-\.cdf$)"),
        (ComponentRole.MS_POSITIVE, r"(_pos(?:itive)?\.cdf$|_MS1\s*\+TIC.*\.(?:cdf|csv)$|_\+\.cdf$)"),
    ]
    for role, pattern in lcms_roles:
        if re.search(pattern, clean_name, flags=re.IGNORECASE):
            return role

    if standardized.source_category in (SourceCategory.LCMS_MS, SourceCategory.LCMS_UV):
        if standardized.source_category == SourceCategory.LCMS_UV:
            return ComponentRole.VWD_A
        mode = str(standardized.metadata.get("ionization_mode", "")).lower()
        return ComponentRole.MS_NEGATIVE if mode == "negative" else ComponentRole.MS_POSITIVE

    return ComponentRole.PRIMARY if standardized.source_category != SourceCategory.GENERIC else ComponentRole.GENERIC


def _is_chromeleon(filename: str, standardized: StandardizedResult) -> bool:
    detected_format = standardized.identity.detected_format.lower()
    return (
        standardized.source_category == SourceCategory.CHROMATOGRAM
        or "chromeleon" in detected_format
        or extract_chromeleon_base_name(filename, standardized.metadata) is not None
    )


def _is_lcms(filename: str, standardized: StandardizedResult) -> bool:
    detected_format = standardized.identity.detected_format.lower()
    extension = standardized.identity.extension.lower().lstrip(".")
    return (
        standardized.source_category in (SourceCategory.LCMS_MS, SourceCategory.LCMS_UV)
        or extension == "cdf"
        or "lcms" in detected_format
    )


def _single_file_bundle_type(standardized: StandardizedResult) -> BundleType:
    detected_format = standardized.identity.detected_format.lower()
    extension = standardized.identity.extension.lower().lstrip(".")

    if "plate" in detected_format:
        return BundleType.PLATE_READER
    if extension in {"xls", "xlsx"} or "excel" in detected_format:
        return BundleType.EXCEL
    if standardized.source_category == SourceCategory.KINETICS or "kinetics" in detected_format:
        return BundleType.KINETICS
    return BundleType.GENERIC


def _display_name(filename: str) -> str:
    base = os.path.basename(filename)
    stem, _extension = os.path.splitext(base)
    return stem or base


def paired_tic_exports(bundle):
    """Match explicit ``name.cdf`` / ``name_spectra.cdf`` export pairs.

    Matching roles, full source stems (including detector settings), and scan
    times are required. Similar-looking curves alone never hide a signal.
    Returns (chromatogram, spectral) component pairs; loaded data is untouched.
    """
    if bundle.bundle_type != BundleType.LCMS:
        return []
    import numpy as np
    pairs = []
    ms_roles = (ComponentRole.MS_POSITIVE, ComponentRole.MS_NEGATIVE)
    for spectral in bundle.component_list:
        if spectral.role not in ms_roles or not spectral.metadata.get('mass_spectral_data'):
            continue
        stem = os.path.splitext(os.path.basename(spectral.original_filename))[0]
        if not stem.lower().endswith('_spectra'):
            continue
        source_stem = stem[:-len('_spectra')].casefold()
        for trace in bundle.component_list:
            if trace.role != spectral.role or not trace.metadata.get('is_tic_only'):
                continue
            trace_stem = os.path.splitext(os.path.basename(trace.original_filename))[0].casefold()
            if trace_stem != source_stem:
                continue
            def times(component):
                columns = component.standardized.x_columns if component.standardized else []
                if component.dataframe is None or not columns:
                    return None
                try:
                    return np.asarray(component.dataframe[columns[0]], dtype=float)
                except (KeyError, ValueError, TypeError):
                    return None
            tx, sx = times(trace), times(spectral)
            if (tx is not None and sx is not None and tx.size >= 2 and tx.shape == sx.shape
                    and np.all(np.isfinite(tx)) and np.all(np.isfinite(sx))
                    and np.allclose(tx, sx, rtol=0, atol=1e-6)):
                pairs.append((trace, spectral))
    return pairs
