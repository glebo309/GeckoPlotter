"""Measured PDA slices and ordinary chromatogram extraction.

The spectral matrix stays in the server-side data store. Extracted channels
reference that source and carry their measured wavelength, without copying it.
"""
from __future__ import annotations

from uuid import uuid4
from pathlib import Path
from copy import deepcopy
import numpy as np
import pandas as pd


def resolve_pda_source(store, file_id):
    """Return the canonical component ID and PDA payload, including for siblings."""
    if not file_id:
        return None
    entry = store.get_data_by_id(file_id)
    if not entry:
        return None
    meta = entry.get('metadata') or {}
    source_id = meta.get('pda_source_id')
    if source_id and source_id != file_id:
        source = store.get_data_by_id(source_id)
        if source and isinstance((source.get('metadata') or {}).get('pda'), dict):
            return source_id, source['metadata']['pda']
    if isinstance(meta.get('pda'), dict):
        bundle = store.get_bundle(file_id)
        return (bundle.primary.component_id if bundle and bundle.primary else file_id), meta['pda']
    return None


def _arrays(pda):
    try:
        time = np.asarray(pda['time_min'], dtype=float)
        wavelength = np.asarray(pda['wavelength_nm'], dtype=float)
        intensity = np.asarray(pda['absorbance_mau'], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('The PDA matrix or its axes are missing.') from exc
    if (time.ndim != 1 or wavelength.ndim != 1 or not time.size or not wavelength.size
            or not np.isfinite(time).all() or not np.isfinite(wavelength).all()
            or intensity.shape != (len(time), len(wavelength))):
        raise ValueError('PDA dimensions do not match the measured time and wavelength axes.')
    return time, wavelength, intensity


def extract_pda_views(pda, wavelength_nm=None, time_min=None):
    """Choose nearest recorded coordinates, never invent interpolated spectra.

    Wavelengths are reported as integers; time is the exact measured value."""
    time, wavelength, intensity = _arrays(pda)
    requested_wavelength = float(round(float(wavelength_nm))) if wavelength_nm is not None else 254.
    wi = int(np.argmin(abs(wavelength - requested_wavelength)))
    if time_min is None:
        column = intensity[:, wi]
        ti = int(np.nanargmax(column)) if np.isfinite(column).any() else 0
    else:
        ti = int(np.argmin(abs(time - float(time_min))))
    return {'times': time, 'wavelengths': wavelength, 'intensity': intensity,
            'time_min': float(time[ti]),
            # Whole nanometres are the working unit; the column used is the nearest measured one.
            'wavelength_nm': float(round(wavelength[wi])), 'measured_wavelength_nm': float(wavelength[wi]),
            'time_index': ti, 'wavelength_index': wi,
            'chromatogram': intensity[:, wi], 'spectrum': intensity[ti, :]}


def _reduce_axis(values, limit, axis):
    """Reduce *axis* to at most *limit* bins, keeping the strongest sample of each bin
    so narrow peaks survive; coordinates are the bin means."""
    n = values.shape[axis]
    step = -(-n // limit)
    if step <= 1:
        return values, None
    starts = np.arange(0, n, step)
    high, low = np.maximum.reduceat(values, starts, axis=axis), np.minimum.reduceat(values, starts, axis=axis)
    return np.where(abs(high) >= abs(low), high, low), (starts, np.diff(np.append(starts, n)))


def display_matrix(times, wavelengths, intensity, max_time=700, max_wavelength=512):
    """A screen-sized copy of the PDA matrix for the heatmap.

    The browser draws a few hundred columns, so sending every one of the (often
    8000+) time points only costs transfer and redraw time. Picks and extracted
    chromatograms keep using the full-resolution matrix.
    """
    z, bins = _reduce_axis(intensity, max_time, 0)
    if bins is not None:
        starts, counts = bins
        times = np.add.reduceat(times, starts) / counts
    z, bins = _reduce_axis(z, max_wavelength, 1)
    if bins is not None:
        starts, counts = bins
        wavelengths = np.add.reduceat(wavelengths, starts) / counts
    return times, wavelengths, np.round(z, 2).astype(np.float32)


def preview_chromatograms(store, file_id, wavelength_nm, limit=1200):
    """Screen-sized chromatograms at one wavelength for every PDA sample in the selected sample's plot.

    Used while dragging the heatmap cross: each bin keeps its strongest point, so peaks survive. The exact
    full-resolution traces are drawn by the normal render when the drag ends.
    """
    series = []
    for bundle_id, (source_id, payload) in pda_series_sources(store, file_id).items():
        try:
            view = extract_pda_views(payload, wavelength_nm)
        except (ValueError, TypeError):
            continue
        y, bins = _reduce_axis(view['chromatogram'][:, None], limit, 0)
        x = view['times']
        if bins is not None:
            starts, counts = bins
            x = np.add.reduceat(x, starts) / counts
        series.append({'source_id': source_id, 'wavelength_nm': view['wavelength_nm'],
                       'x': np.round(x, 4).tolist(), 'y': np.round(y[:, 0], 3).tolist()})
    return series


def add_pda_chromatogram(store, file_id, wavelength_nm):
    """Add one independently integrable wavelength to the existing sample bundle."""
    from .data_store import Component, ComponentRole, ColumnRole, SourceCategory
    from .research_package import now
    from src.ingestion.types import StandardizedResult, FileIdentity

    resolved = resolve_pda_source(store, file_id)
    if not resolved:
        raise ValueError('Select a sample with PDA data.')
    source_id, pda = resolved
    view = extract_pda_views(pda, wavelength_nm)
    actual = view['wavelength_nm']
    bundle = store.get_bundle_for_component(source_id)
    if not bundle:
        raise ValueError('The PDA source is no longer loaded.')
    for component in bundle.component_list:
        meta = component.metadata or {}
        if meta.get('pda_source_id') == source_id and meta.get('pda_extracted') and meta.get('wavelength_nm') == actual:
            store.visibility_state[component.component_id] = True
            return component.component_id
    source = store.get_data_by_id(source_id)
    component_id = str(uuid4())
    metadata = {'sample_name': source['metadata'].get('sample_name', bundle.name),
                'display_name': f'PDA {actual:.0f} nm', 'pda_source_id': source_id,
                'source_file_id': source_id,
                'pda_extracted': True, 'wavelength_nm': actual,
                'auto_x': 'Time (min)', 'auto_y': ['Absorbance (mAU)'],
                'units': {'Time (min)': 'min', 'Absorbance (mAU)': 'mAU'}}
    frame = pd.DataFrame({'Time (min)': view['times'], 'Absorbance (mAU)': view['chromatogram']})
    roles = {'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y}
    filename = source['metadata'].get('file_name', 'PDA')
    source_result = source.get('standardized')
    identity = deepcopy(source_result.identity) if source_result else FileIdentity(
        original_name=filename, extension=Path(filename).suffix, detected_format='pda_extraction', detection_stage=0)
    standardized = StandardizedResult(frame, roles, identity, source_category=SourceCategory.CHROMATOGRAM,
        sample_name=metadata['sample_name'], metadata=metadata)
    component = Component(component_id, ComponentRole.PRIMARY, filename, dataframe=frame,
        column_roles=roles, metadata=metadata, source_category=SourceCategory.CHROMATOGRAM,
        standardized=standardized)
    bundle.component_list.append(component)
    bundle.components.setdefault(component.role, component)
    store.add_bundle(bundle)
    store.visibility_state[component_id] = True
    parameters = {'source_id': source_id, 'signal_id': component_id,
                  'wavelength_nm': actual, 'method': 'nearest measured wavelength'}
    store.analysis_history.append({'at': now(), 'trigger': ['pda-add-chromatogram'],
        'parameters': parameters, 'changes': {'pda_extraction': {'before': None, 'after': parameters}}})
    return component_id


def pda_series_sources(store, file_id):
    """PDA sources in the selected sample's exact plot group, selected first."""
    from callbacks.viz_callbacks import _get_overlay_group
    selected = store.get_bundle(file_id) or store.get_bundle_for_component(file_id)
    if not selected:
        return {}

    def group(bundle):
        entry = store.get_data_by_id(bundle.bundle_id)
        return _get_overlay_group(entry.get('metadata', {}), entry, bundle.bundle_id, store) if entry else None

    selected_group = group(selected)
    sources = {}
    bundles = [selected] + [b for b in store.iter_bundles() if b.bundle_id != selected.bundle_id]
    for bundle in bundles:
        if group(bundle) != selected_group:
            continue
        for component in bundle.component_list:
            resolved = resolve_pda_source(store, component.component_id)
            if resolved:
                sources[bundle.bundle_id] = resolved
                break
    return sources


def add_pda_series(store, file_id, wavelength_nm):
    """Extract the nearest measured wavelength for every PDA sample in this plot.

    Return {bundle_id: component_id}, with the selected sample first. Existing
    extraction IDs are reused; original data and spectral matrices stay intact.
    """
    sources = pda_series_sources(store, file_id)
    if not sources:
        raise ValueError('Select a sample with PDA data.')
    # Validate the whole operation before adding any channels.
    for _, payload in sources.values():
        extract_pda_views(payload, wavelength_nm)
    return {bundle_id: add_pda_chromatogram(store, source_id, wavelength_nm)
            for bundle_id, (source_id, _) in sources.items()}


def materialise_preview(store, preview):
    """Turn a live preview into real extracted channels for every sample it covers.

    Return {bundle_id: component_id}. Existing channels at that wavelength are reused.
    """
    owner = (preview or {}).get('owner_id')
    if not owner or (preview or {}).get('wavelength_nm') is None:
        raise ValueError('There is no previewed wavelength to keep.')
    return add_pda_series(store, owner, preview['wavelength_nm'])


def channel_for_sample(store, added, file_id):
    """The channel in *added* ({bundle_id: component_id}) belonging to the sample that owns *file_id*."""
    bundle = store.get_bundle(file_id) or store.get_bundle_for_component(file_id)
    return added.get(bundle.bundle_id) if bundle else None
