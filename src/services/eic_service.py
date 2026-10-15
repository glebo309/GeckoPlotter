"""Extracted-ion chromatograms (EICs) as channels: the trace of one ion (m/z ± tolerance) in an LC-MS run, added to the
run like a recorded channel, so it is integrated, corrected, matched across samples, calibrated and exported like UV.

The trace is computed from the run's full-scan spectra (LCMSService.extract_eic); a saved project stores only
{source, m/z, tolerance} and extracts it again on opening (session_service), as for PDA wavelength channels.
Channel identity ``eic:+:633.8:0.5`` (polarity, m/z, tolerance), name ``EIC 633.8 ±0.5 (+)``, the same in every run.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pandas as pd


def _round(value: float) -> float:
    return round(float(value), 4)


def eic_key(mz, tolerance, polarity) -> str:
    return f"eic:{'-' if str(polarity).startswith(('-', 'n')) else '+'}:{_round(mz):g}:{_round(tolerance):g}"


def eic_label(mz, tolerance, polarity) -> str:
    sign = '−' if str(polarity).startswith(('-', 'n')) else '+'
    return f'EIC {_round(mz):g} ±{_round(tolerance):g} ({sign})'


def ms_source(store, bundle, polarity):
    """The component of ``bundle`` with full-scan spectra of that polarity, or None."""
    from .data_store import ComponentRole
    role = ComponentRole.MS_NEGATIVE if str(polarity).startswith(('-', 'n')) else ComponentRole.MS_POSITIVE
    for component in bundle.component_list:
        if component.role == role and store.lcms_service.has_spectral_data(store.get_data_by_id(component.component_id)
                                                                           or {}):
            return component
    return None


def add_eic_chromatogram(store, source_id, mz, tolerance=0.5):
    """Add the EIC of m/z ± tolerance from the spectra in ``source_id`` to its run (or reuse it); returns its id."""
    from .data_store import Component, ComponentRole, ColumnRole, SourceCategory
    from .channel_visibility import show_channel
    from .research_package import now
    from src.ingestion.types import StandardizedResult, FileIdentity

    source = store.get_data_by_id(source_id)
    bundle = store.get_bundle_for_component(source_id)
    if not source or not bundle or not store.lcms_service.has_spectral_data(source):
        raise ValueError('This run has no full-scan mass spectra to extract an ion from.')
    mz, tolerance = _round(mz), _round(tolerance)
    if tolerance <= 0:
        raise ValueError('The m/z tolerance must be greater than zero.')
    source_component = next(c for c in bundle.component_list if c.component_id == source_id)
    polarity = 'negative' if source_component.role == ComponentRole.MS_NEGATIVE else 'positive'
    key = eic_key(mz, tolerance, polarity)
    for component in bundle.component_list:
        eic = (component.metadata or {}).get('eic')
        if eic and eic_key(eic['mz'], eic['tolerance'], eic['polarity']) == key:
            show_channel(store, component.component_id)
            return component.component_id
    times, intensity = store.lcms_service.extract_eic(source, mz, tolerance)
    label = eic_label(mz, tolerance, polarity)
    metadata = {'sample_name': (source.get('metadata') or {}).get('sample_name', bundle.name),
                'display_name': label, 'eic_extracted': True, 'source_file_id': source_id,
                'eic': {'mz': mz, 'tolerance': tolerance, 'polarity': polarity},
                'ionization_mode': polarity,
                'auto_x': 'Time (min)', 'auto_y': ['Intensity'],
                'units': {'Time (min)': 'min', 'Intensity': 'counts'}}
    frame = pd.DataFrame({'Time (min)': list(times), 'Intensity': list(intensity)})
    roles = {'Time (min)': ColumnRole.X, 'Intensity': ColumnRole.Y}
    filename = source_component.original_filename
    source_result = source.get('standardized')
    identity = deepcopy(source_result.identity) if source_result else FileIdentity(
        original_name=filename, extension=Path(filename).suffix, detected_format='eic_extraction', detection_stage=0)
    standardized = StandardizedResult(frame, roles, identity, source_category=SourceCategory.LCMS_MS,
                                      sample_name=metadata['sample_name'], metadata=metadata)
    # GENERIC, not PRIMARY: the run's primary channel (its identity, grouping and default view) stays the same.
    component = Component(str(uuid4()), ComponentRole.GENERIC, filename, dataframe=frame, column_roles=roles,
                          metadata=metadata, source_category=SourceCategory.LCMS_MS, standardized=standardized)
    bundle.component_list.append(component)
    bundle.components.setdefault(component.role, component)
    store.add_bundle(bundle)
    show_channel(store, component.component_id)
    parameters = {'source_id': source_id, 'signal_id': component.component_id, 'mz': mz, 'tolerance': tolerance,
                  'polarity': polarity}
    store.analysis_history.append({'at': now(), 'trigger': ['eic-add-channel'], 'parameters': parameters,
                                   'changes': {'eic_extraction': {'before': None, 'after': parameters}}})
    return component.component_id


def add_eic_series(store, bundle_ids, mz, tolerance=0.5, polarity='+'):
    """The EIC in every given run with spectra of that polarity ('+', '-' or 'both'): {bundle_id: [component ids]}.
    Runs without spectra are left out; it is checked before anything is added."""
    polarities = ['positive', 'negative'] if str(polarity).lower() == 'both' else [polarity]
    sources = []
    for bundle_id in bundle_ids:
        bundle = store.get_bundle(bundle_id)
        for pol in polarities:
            component = ms_source(store, bundle, pol) if bundle else None
            if component is not None:
                sources.append((bundle_id, component.component_id))
    if not sources:
        raise ValueError('None of these runs has full-scan mass spectra (only exported TIC traces).')
    if float(tolerance) <= 0:
        raise ValueError('The m/z tolerance must be greater than zero.')
    added = {}
    for bundle_id, source_id in sources:
        added.setdefault(bundle_id, []).append(add_eic_chromatogram(store, source_id, mz, tolerance))
    return added
