from services.dataset_names import display_name, trace_display_name
# =============================================================================
# File: callbacks/viz_callbacks.py
# =============================================================================
"""
Visualization callbacks for GeckoPlotter V2.
"""

import logging
import os
import sys
from typing import Dict, Any, Optional
import dash
from dash import Input, Output, State, html, dash_table, Patch
from dash_iconify import DashIconify
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from services.plot_manager import PlotManager
from services.data_store import DataStore as DataManager, BundleType
from services.plot_smoothing import smooth_plotly_traces
from services import table_store
from services.metadata_display import group_metadata, measurement_summary
from components.data_table_editor import create_data_table_editor
from components.publication_plot import create_publication_plot
from callbacks.peak_overlay import overlay_peaks_on_figure, patch_figure_with_peaks, rgba, FILL_COLORS, cleanup_peak_traces, add_peak_traces
from callbacks.baseline_callbacks import get_xy_arrays
from src.ingestion.types import PlotHint, SourceCategory

log = logging.getLogger('geckoplotter.viz')
if not log.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)


def prepare_table_data(file_data, file_id=None, visible_wells=None):
    """Prepare data for the table editor using StandardizedResult column info."""
    if file_data is None or file_data.get('data') is None:
        return None

    sr = file_data.get('standardized')
    data = file_data['data']

    if visible_wells is not None and sr is not None and sr.x_columns:
        x_col = sr.x_columns[0]
        cols = [x_col] + [w for w in visible_wells if w in data.columns]
        table_data = data[cols].copy().dropna()
    elif file_id and '|' in file_id and sr is not None and sr.x_columns:
        x_col = sr.x_columns[0]
        _, item_name = file_id.split('|', 1)
        if x_col in data.columns and item_name in data.columns:
            table_data = data[[x_col, item_name]].copy().dropna()
        else:
            table_data = data.copy()
    else:
        table_data = data.copy()

    if '_row_id' not in table_data.columns:
        table_data.insert(0, '_row_id', range(len(table_data)))

    return table_data



# _rgba, _add_deselect_catcher, _overlay_peaks_on_figure, _peak_overlay_patch,
# and FILL_COLORS have been extracted to callbacks/peak_overlay.py


def _has_meaningful_raw_plot(file_data):
    """Return True if the file has a good raw plot (don't auto-switch to analysis)."""
    sr = file_data.get('standardized')
    if sr is None:
        return False
    return bool(sr.x_columns and sr.y_columns)


def _get_source_category(metadata, fdata):
    """Return the source category from StandardizedResult."""
    sr = fdata.get('standardized')
    if sr is not None:
        return sr.source_category.value
    return 'generic'


def _get_x_axis_name(metadata, fdata):
    """Return the X-axis column name from StandardizedResult."""
    sr = fdata.get('standardized')
    if sr is not None and sr.x_columns:
        return sr.x_columns[0]
    if metadata.get('auto_x'):
        return metadata['auto_x']
    data = fdata.get('data')
    if data is not None and hasattr(data, 'columns') and len(data.columns) > 0:
        return data.columns[0]
    return 'unknown'


def _get_x_domain_signature(metadata, fdata):
    """Return a coarse numeric X-domain signature for overlay compatibility."""
    x_axis = _get_x_axis_name(metadata, fdata)
    data = fdata.get('data')
    if data is None or not hasattr(data, 'columns') or x_axis not in data.columns:
        return 'domain:unknown'
    try:
        x = pd.to_numeric(data[x_axis], errors='coerce').dropna()
    except Exception:
        return 'domain:unknown'
    if x.size < 2:
        return 'domain:unknown'

    lo = float(x.min())
    hi = float(x.max())
    if not np.isfinite(lo) or not np.isfinite(hi):
        return 'domain:unknown'
    span = abs(hi - lo)
    decimals = 4 if span < 1 else 2 if span < 100 else 0
    return f"{round(lo, decimals)}:{round(hi, decimals)}"


def _get_overlay_group(metadata, fdata, file_id=None, dm=None, ignore_override=False):
    """Return composite key (source_category, x_axis, x_domain) for overlay grouping.

    Files overlay when they share both the same source type AND the same
    X-axis name/domain.  This prevents e.g. unrelated CSVs with a generic
    "Time" or "X" column from being placed on the same plot.

    If the file has a group override (from cross-group drag-drop), use that.
    The file tree drags whole bundles, so a bundle's override also applies to
    its components (chromatogram/LC-MS signals are plotted per component).
    *ignore_override* returns the natural group instead.
    Components of one LCMS run share its bundle-specific group. Equal time
    ranges in different runs never imply an automatic comparison.
    """
    overrides = getattr(dm, 'group_overrides', None) if dm and not ignore_override else None
    if file_id and overrides:
        override = overrides.get(file_id)
        if not override and hasattr(dm, 'get_bundle_for_component'):
            owner = dm.get_bundle_for_component(file_id)
            override = overrides.get(owner.bundle_id) if owner else None
        if override:
            return override

    if file_id and dm and hasattr(dm, 'get_bundle_for_component'):
        bundle = dm.get_bundle_for_component(file_id)
        if bundle is None and hasattr(dm, 'get_bundle'):
            bundle = dm.get_bundle(file_id)
        if bundle and getattr(bundle.bundle_type, 'value', bundle.bundle_type) == 'lcms':
            primary = bundle.primary
            entry = dm.get_data_by_id(primary.component_id) if primary else None
            entry = entry or fdata
            meta = entry.get('metadata', {})
            return ('lcms_ms', _get_x_axis_name(meta, entry),
                    _get_x_domain_signature(meta, entry), bundle.bundle_id)
        if bundle and len(bundle.component_list) > 1:
            primary = bundle.primary
            if primary and primary.component_id != file_id:
                p_entry = dm.get_data_by_id(primary.component_id)
                if p_entry:
                    p_meta = p_entry.get('metadata', {})
                    return (_get_source_category(p_meta, p_entry),
                            _get_x_axis_name(p_meta, p_entry),
                            _get_x_domain_signature(p_meta, p_entry))

    return (_get_source_category(metadata, fdata),
            _get_x_axis_name(metadata, fdata),
            _get_x_domain_signature(metadata, fdata))


def _get_active_file_group(dm, active_file_id):
    """Return the group key for the active file."""
    if not active_file_id:
        return None
    fdata = dm.get_data_by_id(active_file_id)
    if not fdata:
        # Check bundles
        bundle = dm.get_bundle_by_id(active_file_id)
        if bundle and bundle.main_file:
            fdata = dm.get_data_by_id(bundle.main_file.get('id'))
    if not fdata:
        return None
    metadata = fdata.get('metadata', {})
    return _get_overlay_group(metadata, fdata, file_id=active_file_id, dm=dm)



def _axis_range_from_relayout(relayout_data, axis_name='xaxis'):
    """Extract a user-controlled axis range from Plotly relayoutData."""
    if not relayout_data:
        return None

    stored_axis = relayout_data.get(axis_name)
    if isinstance(stored_axis, dict):
        stored_range = stored_axis.get('range')
        if isinstance(stored_range, (list, tuple)) and len(stored_range) == 2:
            return list(stored_range)

    direct = relayout_data.get(f'{axis_name}.range')
    if isinstance(direct, (list, tuple)) and len(direct) == 2:
        return list(direct)

    start = relayout_data.get(f'{axis_name}.range[0]')
    end = relayout_data.get(f'{axis_name}.range[1]')
    if start is not None and end is not None:
        return [start, end]

    return None


def _apply_zoom_state(fig, zoom_state):
    """Re-apply stored user zoom ranges to a freshly built figure."""
    if not zoom_state:
        return

    layout_update = {}
    for axis in fig.layout:
        if axis.startswith(('xaxis', 'yaxis')):
            axis_range = _axis_range_from_relayout(zoom_state, axis)
            if axis_range:
                layout_update[axis] = dict(range=axis_range, autorange=False)
    if layout_update:
        fig.update_layout(**layout_update)


def _apply_preserved_view(dm, figure, previous_file_id, next_file_id, relayout_data):
    """Carry the current viewport across file switches within the same group.

    Files in the same overlay group (same source category + X axis) share
    comparable axis scales, so preserving zoom makes sense. Switching to
    a different group (e.g. spectrum → kinetics) resets to autorange.
    """
    previous_group = _get_active_file_group(dm, previous_file_id)
    next_group = _get_active_file_group(dm, next_file_id)
    if previous_group != next_group or not previous_group:
        return figure

    import plotly.graph_objects as go
    fig = go.Figure(figure) if isinstance(figure, dict) else figure
    fig.update_layout(uirevision='main-plot')

    x_range = _axis_range_from_relayout(relayout_data, 'xaxis')
    y_range = _axis_range_from_relayout(relayout_data, 'yaxis')
    if not x_range and not y_range:
        return fig

    layout_update = {}
    if x_range:
        layout_update['xaxis'] = dict(range=x_range, autorange=False)
    if y_range:
        layout_update['yaxis'] = dict(range=y_range, autorange=False)
    fig.update_layout(**layout_update)
    return fig


def _find_file_id(dm, fdata):
    """Find the loaded_data key that corresponds to an fdata dict."""
    for fid, fd in dm.loaded_data.items():
        if fd is fdata:
            return fid
    rec = fdata.get('record', {})
    return rec.get('id')


def _collect_visible_files(dm, active_file_id=None, loaded_files=None, target_group_override=None, file_order=None,
                           include_hidden=False):
    """Return dict of {group_key: [(name, file_data), ...]} for visible files.

    Only returns files matching the target group so different data types
    don't get mixed. The eye icon controls visibility within the group.
    Files not present in *loaded_files* (if given) are skipped to prevent
    stale data from previous uploads leaking in.

    *target_group_override* can be a group tuple to use directly instead
    of deriving from the active file.

    *include_hidden* also returns files hidden with the eye icon; it is only used to give every trace a colour
    slot that does not change when other traces are hidden.
    """
    vis_state = getattr(dm, 'visibility_state', {})
    if include_hidden:
        vis_state = {}

    if target_group_override:
        target_group = target_group_override
    elif active_file_id:
        target_group = _get_active_file_group(dm, active_file_id)
    else:
        target_group = None

    # Build set of IDs that are actually loaded in the UI right now
    valid_ids: set | None = None
    if loaded_files:
        valid_ids = set()
        for rec in loaded_files:
            rec_id = rec.get('id')
            valid_ids.add(rec_id)
            bundle = dm.get_bundle(rec_id) if hasattr(dm, 'get_bundle') else None
            if bundle:
                valid_ids.update(c.component_id for c in bundle.component_list)
        # Also add bundle IDs that map to valid main-file IDs
        for bundle in dm.bundle_manager.bundles.values():
            main = bundle.main_file
            if main and main.get('id') in valid_ids:
                valid_ids.add(bundle.bundle_id)

    from collections import defaultdict
    groups = defaultdict(list)

    # First pass: collect all candidate files and their groups
    candidates = []
    log.debug(f"_collect_visible_files: active={active_file_id}, valid_ids={valid_ids}")
    for fid, fdata in dm.loaded_data.items():
        if valid_ids is not None and fid not in valid_ids:
            continue
        if fdata.get('standardized') is None:
            continue
        metadata = fdata.get('metadata', {})
        group = _get_overlay_group(metadata, fdata, file_id=fid, dm=dm)
        log.debug(f"{fid}: group={group}, name={fdata.get('record', {}).get('name', '?')}")
        candidates.append((fid, fdata, metadata, group))

    # If active file was deleted/invalid, fall back to the first candidate's group
    if not target_group and candidates:
        target_group = candidates[0][3]

    for fid, fdata, metadata, group in candidates:
        if target_group and group != target_group:
            continue

        sr = fdata.get('standardized')
        if sr is not None and sr.plot_hint == PlotHint.MULTI_Y and sr.x_columns:
            filled_wells = metadata.get('filled_wells', sr.y_columns)
            vis_wells = []
            for well in filled_wells:
                well_id = f"{fid}|{well}"
                if vis_state.get(well_id, True):
                    vis_wells.append(well)
            if vis_wells:
                x_col = sr.x_columns[0]
                sub_df = fdata['data'][[x_col] + [w for w in vis_wells if w in fdata['data'].columns]].copy()
                sub_data = {**fdata, 'data': sub_df}
                name = trace_display_name(fdata)
                groups[group].append((name, sub_data))
        else:
            if vis_state.get(fid, True):
                name = trace_display_name(fdata)
                groups[group].append((name, fdata))

    result = dict(groups)
    # The subplots stack in the file tree's order (upload_callbacks._sort_group_items): the tree orders samples, the
    # plot channels, so each channel is placed by the sample it belongs to.
    from services.natural_sort import natural_key

    def sample_of(fd):
        fid = (fd.get('record') or {}).get('id', '')
        for key, data in dm.loaded_data.items():
            if data is fd:
                fid = key
                break
        bundle = None
        if fid and hasattr(dm, 'get_bundle'):
            bundle = dm.get_bundle(fid) or (dm.get_bundle_for_component(fid)
                                            if hasattr(dm, 'get_bundle_for_component') else None)
        return (bundle.bundle_id, bundle.name) if bundle else (fid, '')

    for gkey, file_list in result.items():
        group_order = (file_order or {}).get(_tab_id_from_group(gkey)) or {}
        explicit = group_order.get('order')
        if explicit:
            id_map = {fid: idx for idx, fid in enumerate(explicit)}
            file_list.sort(key=lambda entry: (id_map.get(sample_of(entry[1])[0], 999999),
                                              natural_key(sample_of(entry[1])[1] or entry[0])))
        else:
            file_list.sort(key=lambda entry: natural_key(sample_of(entry[1])[1] or entry[0]),
                           reverse=group_order.get('sort_dir') == 'desc')
    return result


def _trace_color_slots(dm, group_key, loaded_files, file_order):
    """Map 'file_id|y_column' to a fixed palette slot for every trace of this plot, hidden ones included."""
    try:
        everything = _collect_visible_files(dm, None, loaded_files, target_group_override=group_key,
                                            file_order=file_order, include_hidden=True)
    except Exception:
        log.exception('colour slot calculation failed')
        return {}
    slots = {}
    for files in everything.values():
        for _name, fdata in files:
            sr = fdata.get('standardized')
            fid = _find_file_id(dm, fdata)
            if sr is None or not fid:
                continue
            columns = [c for c in sr.y_columns if c in fdata['data'].columns]
            for column in columns:
                slots[f'{fid}|{column}'] = len(slots)
    return slots


def _assign_color_slots(figure, slots):
    """Tag data traces with their fixed slot so styling uses it instead of the visible position."""
    if not slots:
        return
    for trace in figure.data:
        meta = trace.meta if isinstance(trace.meta, dict) else {}
        slot = slots.get(f"{meta.get('file_id')}|{meta.get('y_column')}")
        if slot is not None:
            trace.meta = {**meta, 'color_slot': slot}


_GROUP_LABELS = {
    'chromatogram': 'Chromatograms',
    'spectrum': 'Spectra',
    'uvvis': 'UV-Vis Spectra',
    'lcms_ms': 'LC-MS',
    'lcms_uv': 'LC-MS UV',
    'kinetics': 'Kinetics',
    'generic': 'Data',
    'table': 'Table',
}

_AUTO_PLOT_CATEGORIES = frozenset({
    'chromatogram', 'spectrum', 'lcms_ms', 'lcms_uv', 'kinetics',
})


def _tab_id_from_group(group_key):
    """Create a stable tab ID from an overlay group key tuple."""
    cat, x_axis, *rest = group_key
    slug_src = "_".join(str(part) for part in (cat, x_axis, *rest))
    slug = slug_src.replace(' ', '_').replace('(', '').replace(')', '').replace(':', '_').lower()
    return f"tab-{slug}"


def _tab_label_from_group(group_key, dm=None):
    """Create a human-readable label for a tab from its overlay group key."""
    cat, x_axis, *_rest = group_key
    if cat == 'folder' and len(group_key) >= 3:            # runs opened together from one folder (gecko_api)
        return str(group_key[2])
    if dm is not None and cat == 'lcms_ms' and len(group_key) == 4:
        bundle = dm.get_bundle(group_key[3])
        if bundle:
            return bundle.name
    base = _GROUP_LABELS.get(cat, cat.replace('_', ' ').title())
    return base


def _add_signal_processing_overlays(figure, data_manager, file_id, display_opts):
    """Add smoothed / baseline / corrected traces from stored ProcessedSignal.

    Returns the (possibly new) figure object.
    """
    import plotly.graph_objects as go

    processed = data_manager.integration_service.get_processed_signal(file_id)
    if processed is None:
        return figure

    fig = go.Figure(figure) if isinstance(figure, dict) else figure
    from services.decimation import for_display

    if 'smoothed' in display_opts:
        x_draw, y_draw = for_display(processed.time, processed.smoothed)
        fig.add_trace(go.Scatter(
            x=x_draw, y=y_draw,
            mode='lines',
            line=dict(color='rgba(0, 100, 200, 0.7)', width=1.5),
            name='Smoothed',
            showlegend=True,
            meta='signal_processing',
        ))

    if 'baseline' in display_opts:
        x_draw, y_draw = for_display(processed.time, processed.baseline)
        fig.add_trace(go.Scatter(
            x=x_draw, y=y_draw,
            mode='lines',
            line=dict(color='rgba(220, 50, 50, 0.6)', width=1.5, dash='dash'),
            name='Baseline',
            showlegend=True,
            meta='signal_processing',
        ))

    if 'corrected' in display_opts:
        x_draw, y_draw = for_display(processed.time, processed.corrected)
        fig.add_trace(go.Scatter(
            x=x_draw, y=y_draw,
            mode='lines',
            line=dict(color='rgba(50, 180, 50, 0.7)', width=1.5),
            name='Corrected',
            showlegend=True,
            meta='signal_processing',
        ))

    return fig



def _same_wavelength(identity, wavelength_nm) -> bool:
    """True when a UV channel (``('uv:263', ...)``) is the wavelength a PDA preview shows (to the nm)."""
    try:
        return bool(identity) and identity[0].startswith('uv:') and \
            round(float(identity[0][3:])) == round(float(wavelength_nm))
    except (TypeError, ValueError):
        return False


def _apply_pda_main_preview(figure, data_manager, preview):
    """Preview one UV channel per visible sample of this plot without changing data.

    The sample being inspected keeps its inspected channel; every other sample shows the same channel when it has
    it, else its first visible UV trace. A sample with no visible trace (hidden in the tree) gets none.
    """
    if not preview or not preview.get('owner_id'):
        return None
    from services.pda_service import resolve_pda_source, extract_pda_views, pda_series_sources
    from services.channel_visibility import channel_identity
    owner = preview['owner_id']
    source = resolve_pda_source(data_manager, owner)
    if not source or source[0] != preview.get('source_id'):
        return None
    selected_bundle = data_manager.get_bundle(owner) or data_manager.get_bundle_for_component(owner)
    if not selected_bundle:
        return None
    selected_component = next((c for c in selected_bundle.component_list if c.component_id == owner), None)
    identity = channel_identity(selected_component) if selected_component else None
    sources = pda_series_sources(data_manager, owner)

    # Which sample (bundle) does each plotted trace belong to? Traces are matched by the component they plot
    # (meta.file_id); previews already applied and peak traces are never candidates.
    owner_of_component = {}
    for bundle_id in sources:
        bundle = data_manager.get_bundle(bundle_id)
        for component in (bundle.component_list if bundle else ()):
            owner_of_component[component.component_id] = (bundle_id, component)
    candidates = {bundle_id: [] for bundle_id in sources}
    for trace in figure.data:
        meta = trace.meta if isinstance(trace.meta, dict) else {}
        if meta.get('pda_preview') or meta.get('peak_id'):
            continue
        fid = meta.get('file_id')
        found = owner_of_component.get(fid)
        if found is None:
            continue
        bundle_id, component = found
        trace_identity = channel_identity(component)
        if trace_identity and trace_identity[0].startswith('ms:'):
            continue
        resolved = resolve_pda_source(data_manager, fid)
        if not resolved or resolved[0] != sources[bundle_id][0]:
            continue
        candidates[bundle_id].append((trace, fid, trace_identity))

    replaced = []
    for bundle_id, (source_id, payload) in sources.items():
        options = candidates[bundle_id]
        target = (next((c for c in options if c[1] == owner), None)
                  or next((c for c in options if identity and c[2] == identity), None)
                  or next((c for c in options if c[2] and c[2][0].startswith('uv')), None)
                  or (options[0] if options else None))
        if target is None:
            continue
        if _same_wavelength(target[2], preview.get('wavelength_nm')):
            continue                    # the channel itself, with its peaks: a preview of it would only hide them
        try:
            view = extract_pda_views(payload, preview.get('wavelength_nm'), preview.get('time_min'))
        except (ValueError, TypeError):
            continue
        trace, fid, _ = target
        bundle = data_manager.get_bundle(bundle_id)
        from services.decimation import for_display
        trace.x, trace.y = for_display(view['times'], view['chromatogram'])     # drawing only, every peak top kept
        sample = f'{bundle.name} · ' if len(sources) > 1 else ''
        trace.name = f"{sample}PDA {view['wavelength_nm']:.0f} nm · preview"
        previous = trace.meta if isinstance(trace.meta, dict) else {}
        trace.meta = {'pda_preview': True, 'pda_source_id': source_id, 'pda_owner_id': fid,
                      **({'color_slot': previous['color_slot']} if 'color_slot' in previous else {})}
        trace.customdata = None
        trace.hovertemplate = '%{x:.4g} min<br>%{y:.5g} mAU<extra>%{fullData.name}</extra>'
        replaced.append(fid)
    return replaced[0] if len(replaced) == 1 else (replaced or None)


def _apply_pda_main_cursor(figure, cursor):
    """Remove legacy editable shapes; the source-owned DOM overlay handles time."""
    figure.layout.shapes = tuple(shape for shape in (figure.layout.shapes or ())
                                 if shape.name != 'pda-time-cursor')


def _raw_render_revision(inputs):
    """Identify the figure revision actually delivered to a browser."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _raw_render_settings(settings):
    """Fingerprint only settings that affect a raw figure's rendered content."""
    result = dict(settings)
    for key in ('pub_dpi', 'export_format'):
        result.pop(key, None)
    modes = result.get('axis_label_modes') or {}
    if modes.get('x') == 'auto':
        result.pop('x_label', None)
    if modes.get('y') == 'auto':
        result.pop('y1_label', None)
    return result


def compose_raw_figure(data_manager, plot_manager, active_tab_id, group_key, s, active_file, loaded_files,
                       file_order=None, selected_peak_id=None, baseline_mode=None, deconv_markers=None,
                       deconv_result=None, display_opts=None, pda_preview=None, pda_cursor=None, link_x=None,
                       y_scope=None, effective_zoom=None):
    """The figure of a raw plot tab: its visible signals with their peaks, overlays and the tab's plot settings ``s``.

    master_render draws every raw tab with it, and the upload draws the new tab with it before the rest of the app has
    caught up (``first_paint``), so both are the same figure. None when no signal of the tab is visible.
    """
    from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS
    layout_mode = s.get('layout_mode', 'overlay')
    visible_files = _collect_visible_files(
        data_manager, active_file, loaded_files, target_group_override=group_key,
        file_order=file_order)
    from services.ms_polarity import filter_ms_polarity, entry_polarity
    visible_files = filter_ms_polarity(visible_files, s.get('ms_polarity', 'both'))
    if not visible_files:
        return None


    subplot_spacing = s.get('subplot_spacing', 0.08)
    figure = plot_manager.create_multi_file_plot(visible_files, layout_mode, subplot_spacing=subplot_spacing)
    if hasattr(figure, 'data'):
        _assign_color_slots(figure, _trace_color_slots(data_manager, group_key, loaded_files, file_order))

    smooth_window = s.get('smooth_window', 0)
    if smooth_window >= 3:
        fig_sm = go.Figure(figure) if isinstance(figure, dict) else figure
        smooth_plotly_traces(fig_sm.data, smooth_window)
        figure = fig_sm

    preview_owner = _apply_pda_main_preview(figure, data_manager, pda_preview)

    show_peaks = 'peaks' in (['peaks'] if display_opts is None else display_opts)

    # If the user switched palette, update peak_service and re-group
    # so peak.color reflects the new palette. Compare by name (robust).
    from services.plot_settings_service import PlotSettingsService as _PSS
    from services.plot_settings_service import DEFAULT_PALETTE as _DEFAULT_PALETTE
    _pal_name = s.get('palette', _DEFAULT_PALETTE)
    _ps = data_manager.peak_service
    if getattr(_ps, '_palette_name', None) != _pal_name:
        _ps.set_palette(_pal_name, _PSS.get_color_palette(_pal_name))
        _ps.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())

    if show_peaks or deconv_result:
        fig_obj_for_peaks = go.Figure(figure) if isinstance(figure, dict) else figure
        cleanup_peak_traces(fig_obj_for_peaks)
        flat_files = [entry for files in visible_files.values() for entry in files]
        labelled = None
        if 'hide-labels' in (display_opts or []):
            labelled = set()                                  # "Hide peak names" (Integration panel)
        elif layout_mode != 'stacked':
            # Overlaid samples: the same compound (peak group) is named once, above its tallest peak.
            tallest = {}
            for _name, fdata in flat_files:
                for p in data_manager.peak_service.get_peaks(_find_file_id(data_manager, fdata) or ''):
                    top = max((v for v in (p.poly_y or []) if v is not None), default=p.height or 0)
                    key = p.group_id or p.peak_id
                    if key not in tallest or top > tallest[key][0]:
                        tallest[key] = (top, p.peak_id)
            labelled = {peak_id for _top, peak_id in tallest.values()}
        for row_idx, (_name, fdata) in enumerate(flat_files, start=1):
            fid = _find_file_id(data_manager, fdata)
            if not fid or fid in ([preview_owner] if isinstance(preview_owner, str) else (preview_owner or [])):
                continue
            peaks = data_manager.peak_service.get_peaks(fid)
            preview_peak_id = (deconv_result or {}).get('peak_id', selected_peak_id)
            deconvolving = bool(deconv_result) and any(p.peak_id == preview_peak_id for p in peaks)
            if deconvolving:
                peaks = [p for p in peaks if p.peak_id != preview_peak_id]
            if not peaks and not deconvolving:
                continue
            time_arr, signal_arr = get_xy_arrays(data_manager, fid)
            if time_arr is None:
                continue
            row = row_idx if layout_mode == 'stacked' else None
            add_peak_traces(fig_obj_for_peaks, peaks, time_arr, signal_arr, selected_peak_id, row=row, labelled=labelled)
            if deconvolving:
                from callbacks.peak_overlay import add_deconv_overlays
                add_deconv_overlays(fig_obj_for_peaks, deconv_markers, deconv_result,
                                    time_arr, signal_arr, row=row)
        figure = fig_obj_for_peaks

    # LC-MS scan cursor is rendered as a DOM overlay in app.py /
    # scan-line-constraint.js. Keep the Plotly figure free of old scan
    # traces/shapes so no stale vertical line remains in the SVG.
    if active_file:
        _af_entry = data_manager.get_data_by_id(active_file)
        if _af_entry and data_manager.lcms_service.has_spectral_data(_af_entry):
            try:
                fig_for_line = go.Figure(figure) if isinstance(figure, dict) else figure
                fig_for_line.data = tuple(
                    tr for tr in fig_for_line.data
                    if getattr(tr, 'name', None) != 'lcms-scan-line'
                )
                if fig_for_line.layout.shapes:
                    fig_for_line.update_layout(shapes=[
                        sh for sh in fig_for_line.layout.shapes
                        if getattr(sh, 'name', None) != 'lcms-scan-line'
                    ])
                figure = fig_for_line
            except Exception:
                pass

    if s.get('layout_mode') == 'stacked' and s.get('subplot_rows', 1) * s.get('subplot_cols', 1) > 1:
        from services.publication_figure import editable_publication_figure
        source = figure.to_plotly_json() if hasattr(figure, 'to_plotly_json') else figure
        figure = editable_publication_figure(source, s, {**s, 'subplot_rows':1, 'subplot_cols':1}, clean_output=False)

    try:
        fig_obj = go.Figure(figure) if isinstance(figure, dict) else figure
        settings_for_style = dict(s, y_label=s.get('y1_label', 'Y1'))
        if ((s.get('axis_label_modes') or {}).get('x') != 'custom'
                and s.get('x_label') == DEFAULT_PLOT_SETTINGS['x_label'] and len(group_key) > 1):
            settings_for_style['x_label'] = group_key[1]
        ps = PlotSettingsService.from_dict(settings_for_style)
        PlotSettingsService.apply_to_figure(fig_obj, ps)
        from services.axis_linking import apply_axis_linking
        apply_axis_linking(fig_obj, bool(link_x), y_scope == 'global')
        PlotSettingsService.share_stacked_y_label(fig_obj, ps)
        from services.signal_axis_range import apply_signal_x_bounds
        apply_signal_x_bounds(fig_obj)
        fig_obj.update_layout(uirevision=active_tab_id,
            meta={**(fig_obj.layout.meta or {}), 'gecko_tab_id': active_tab_id})
        if (effective_zoom and s.get('auto_range', True)
                and effective_zoom.get('_axis_range_revision', 0) == s.get('_axis_range_revision', 0)):
            _apply_zoom_state(fig_obj, effective_zoom)
        elif s.get('auto_range', True):
            fig_obj.update_layout(
                xaxis=dict(autorange=True),
                yaxis=dict(autorange=True),
            )
        from services.axis_inspector import apply_axis_overrides
        apply_axis_overrides(fig_obj, s.get('axis_overrides', {}))
        axis_revision = f"{active_tab_id}:range:{s.get('_axis_range_revision',0)}"
        fig_obj.update_xaxes(uirevision=axis_revision)
        fig_obj.update_yaxes(uirevision=axis_revision)
        figure = fig_obj
    except Exception:
        log.exception("Failed to apply plot settings to raw figure")

    _apply_pda_main_cursor(figure, pda_cursor)
    overlay = next((o[len('overlay:'):] for o in (display_opts or []) if str(o).startswith('overlay:')), None)
    missing = None                      # why the chosen overlay is not drawn, shown under its selector (app.py)
    if overlay and layout_mode == 'stacked':
        missing = 'stacked'
    elif overlay:
        from services.shimadzu_method import add_gradient_overlay, add_status_overlay
        overlay_entries = [e for files in visible_files.values() for e in files]
        if overlay in ('gradient', 'gradient_column'):
            from services.lab_defaults import dwell_volume_ul
            if not add_gradient_overlay(figure, data_manager, overlay_entries,
                                        dwell_volume_ul() if overlay == 'gradient_column' else None):
                missing = 'method'
        elif overlay.startswith('status:'):
            if not add_status_overlay(figure, overlay_entries, overlay[len('status:'):]):
                missing = 'status'
    if missing:
        figure.update_layout(meta={**(figure.layout.meta or {}), 'gecko_overlay_missing': missing})
    return figure


def register_viz_callbacks(app: dash.Dash, data_manager: DataManager) -> None:
    """Register visualization-related callbacks."""

    plot_manager = PlotManager()
    from services.render_cache import RenderCache
    from services.workspaces import scoped

    def _new_render_cache():
        cache = RenderCache()
        if not hasattr(data_manager, '_render_caches'):
            data_manager._render_caches = []
        data_manager._render_caches.append(cache)
        return cache

    render_cache = scoped(data_manager, 'render_cache:viz', _new_render_cache)      # one per workspace

    # ------------------------------------------------------------------
    # Plot tab management
    # ------------------------------------------------------------------

    @app.callback(
        [Output('plot-tabs', 'data'),
         Output('active-plot-tab', 'data', allow_duplicate=True)],
        [Input('loaded-files', 'data')],
        [State('plot-tabs', 'data'),
         State('active-plot-tab', 'data'),
         State('active-file', 'data')],
        prevent_initial_call=True,
    )
    def sync_plot_tabs(loaded_files, existing_tabs, current_active_tab, active_file):
        """Auto-create/remove plot tabs based on loaded files.

        Each unique overlay group (source_category, x_axis) gets its own tab,
        but only for recognized scientific data types. Generic CSVs stay
        unplotted until the user explicitly creates an analysis tab.
        """
        existing_tabs = existing_tabs or []

        if not loaded_files:
            return [], None

        seen_groups = set()
        for fid, fdata in data_manager.loaded_data.items():
            sr = fdata.get('standardized')
            if sr is None:
                continue
            metadata = fdata.get('metadata', {})
            group = _get_overlay_group(metadata, fdata, file_id=fid, dm=data_manager)
            seen_groups.add(group)

        new_tabs = []
        for group in sorted(seen_groups):
            tid = _tab_id_from_group(group)
            existing = next((t for t in existing_tabs if t['id'] == tid), None)
            if existing:
                # A regrouped file may reach a tab id with a different key tuple.
                new_tabs.append({**existing, 'group_key': list(group)}
                                if existing.get('type') == 'raw' else existing)
            else:
                new_tabs.append({
                    'id': tid,
                    'label': _tab_label_from_group(group, data_manager),
                    'type': 'raw',
                    'group_key': list(group),
                })

        for t in existing_tabs:
            if t.get('type') in ('custom', 'publication'):
                new_tabs.append(t)

        new_tab_ids = {t['id'] for t in new_tabs}
        existing_ids = {t['id'] for t in existing_tabs}
        just_created = [t['id'] for t in new_tabs
                        if t['id'] not in existing_ids and t.get('type') != 'custom']

        if just_created:
            if active_file:
                file_group = _get_active_file_group(data_manager, active_file)
                if file_group and _tab_id_from_group(file_group) in just_created:
                    next_active = _tab_id_from_group(file_group)
                else:
                    next_active = just_created[0]
            else:
                next_active = just_created[0]
        elif active_file:
            file_group = _get_active_file_group(data_manager, active_file)
            if file_group and _tab_id_from_group(file_group) in new_tab_ids:
                next_active = _tab_id_from_group(file_group)
            elif current_active_tab and current_active_tab in new_tab_ids:
                next_active = current_active_tab
            else:
                next_active = new_tabs[0]['id'] if new_tabs else None
        elif current_active_tab and current_active_tab in new_tab_ids:
            next_active = current_active_tab
        else:
            next_active = new_tabs[0]['id'] if new_tabs else None

        # A name edit changes loaded-files but not the tab structure. Re-emitting
        # the same active tab can cancel its concurrent rename render in Dash.
        if new_tabs == existing_tabs:
            return dash.no_update, dash.no_update
        return new_tabs, next_active if next_active != current_active_tab else dash.no_update

    @app.callback(
        Output('plot-tab-bar', 'children'),
        [Input('plot-tabs', 'data'),
         Input('active-plot-tab', 'data')],
    )
    def render_tab_bar(tabs, active_tab_id):
        """Render the plot tab bar above the main plot."""
        from dash import html as _html
        if not tabs:
            return []
        children = []
        for tab in tabs:
            is_active = tab['id'] == active_tab_id
            is_custom = tab.get('type') == 'custom'
            is_closable = is_custom or tab.get('type') == 'publication'
            label_el = _html.Span(
                tab['label'],
                id={'type': 'plot-tab-label', 'index': tab['id']},
                contentEditable='false',
                style={'outline': 'none'},
            )
            tab_children = [label_el]
            if is_closable:
                tab_children.append(_html.Span(
                    '×',
                    id={'type': 'plot-tab-close', 'index': tab['id']},
                    n_clicks=0,
                    style={'marginLeft': '6px', 'cursor': 'pointer', 'fontWeight': 'bold',
                           'fontSize': '14px', 'opacity': '0.6'},
                ))
            children.append(_html.Button(
                tab_children,
                id={'type': 'plot-tab-btn', 'index': tab['id']},
                className='plot-tab-btn active' if is_active else 'plot-tab-btn',
                n_clicks=0,
                **{'aria-pressed': 'true' if is_active else 'false'},
            ))
        return children

    app.clientside_callback(
        dash.ClientsideFunction(namespace='plotWorkspace', function_name='switchTab'),
        Output('active-plot-tab', 'data', allow_duplicate=True),
        Input({'type': 'plot-tab-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
        State('active-plot-tab', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        [Output('active-plot-tab', 'data', allow_duplicate=True),
         Output('tab-file-memory', 'data', allow_duplicate=True)],
        Input('active-file', 'data'),
        [State('plot-tabs', 'data'),
         State('active-plot-tab', 'data'),
         State('tab-file-memory', 'data')],
        prevent_initial_call=True,
    )
    def auto_switch_tab_and_remember(active_file, tabs, current_tab, memory):
        """When a file is selected: save it as last-touched for the target tab,
        and switch to that tab if needed."""
        if not active_file or not tabs:
            return dash.no_update, dash.no_update
        file_group = _get_active_file_group(data_manager, active_file)
        if not file_group:
            return dash.no_update, dash.no_update
        target_tab = _tab_id_from_group(file_group)
        tab_exists = any(t['id'] == target_tab for t in tabs)

        new_memory = {**(memory or {}), target_tab: active_file}

        # Don't auto-switch away from the Publication tab; the user
        # is previewing the figure and just wants a different file.
        if current_tab and str(current_tab).startswith('publication'):
            return dash.no_update, new_memory

        if tab_exists and target_tab != current_tab:
            return target_tab, new_memory
        if not tab_exists:
            if current_tab:
                new_memory[current_tab] = active_file
            return dash.no_update, new_memory
        return dash.no_update, new_memory

    @app.callback(
        [Output('active-file', 'data', allow_duplicate=True),
         Output('zoom-state', 'data', allow_duplicate=True)],
        Input('active-plot-tab', 'data'),
        [State('tab-file-memory', 'data'),
         State('active-file', 'data'),
         State('tab-zoom-memory', 'data'),
         State('plot-tabs', 'data')],
        prevent_initial_call=True,
    )
    def restore_file_on_tab_switch(active_tab_id, memory, current_file, zoom_memory, tabs):
        """Keep the displayed raw figure and its data/results selection together."""
        tab = next((item for item in tabs or [] if item.get('id') == active_tab_id), None)
        if not tab or tab.get('type') != 'raw':
            return dash.no_update, dash.no_update
        restored_zoom = (zoom_memory or {}).get(active_tab_id)
        group = tuple(tab.get('group_key') or ())
        def belongs(file_id):
            return bool(file_id and data_manager.get_data_by_id(file_id)
                        and _get_active_file_group(data_manager, file_id) == group)
        remembered = (memory or {}).get(active_tab_id)
        if belongs(remembered):
            selected = remembered
        elif belongs(current_file):
            selected = current_file
        else:
            members = [file_id for file_id, data in data_manager.loaded_data.items()
                       if data.get('standardized') is not None and belongs(file_id)]
            visibility = getattr(data_manager, 'visibility_state', {})
            selected = next((file_id for file_id in members if visibility.get(file_id, True)),
                            members[0] if members else None)
        # Updating active-file also refreshes Data Overview, metadata and peak
        # results; the figure's settings remain owned by its existing tab key.
        return (selected if selected != current_file else dash.no_update), restored_zoom

    # Only shape edits reach the peak/deconvolution callbacks. Zoom, pan and autorange relayouts used to send the
    # whole figure (several MB) to the server as State just to be ignored there.
    app.clientside_callback(
        """
        function(relayoutData) {
            if (!relayoutData) return window.dash_clientside.no_update;
            var shapes = null;
            Object.keys(relayoutData).forEach(function(key) {
                if (key.indexOf('shapes[') === 0) { shapes = shapes || {}; shapes[key] = relayoutData[key]; }
            });
            if (!shapes) return window.dash_clientside.no_update;
            shapes._ts = Date.now();
            return shapes;
        }
        """,
        Output('main-shape-relayout', 'data'),
        Input('main-plot', 'relayoutData'),
        prevent_initial_call=True,
    )

    # Capture user zoom into a dedicated store so it survives figure rebuilds.
    app.clientside_callback(
        r"""
        function(relayoutData, settings, previous) {
            if (!relayoutData) return window.dash_clientside.no_update;
            var revision=(settings || {})._axis_range_revision || 0;
            var zoom=Object.assign({}, previous && previous._axis_range_revision===revision ? previous : {});
            zoom._axis_range_revision=revision;
            var found=false;
            Object.keys(relayoutData).forEach(function(key){
                if (/^[xy]axis\d*\.autorange$/.test(key) && relayoutData[key]===true) {
                    var axis=key.split('.')[0];
                    Object.keys(zoom).forEach(function(old){if(old.indexOf(axis+'.range')===0) delete zoom[old];});
                    found=true;
                }
            });
            Object.keys(relayoutData).forEach(function(key){
                if (/^[xy]axis\d*\.range(\[\d\])?$/.test(key)) {
                    var axis=key.split('.')[0];
                    if(relayoutData[axis+'.autorange']!==true){zoom[key]=relayoutData[key];found=true;}
                }
            });
            return found ? zoom : window.dash_clientside.no_update;
        }
        """,
        Output('zoom-state', 'data', allow_duplicate=True),
        Input('main-plot', 'relayoutData'),
        State('current-plot-settings', 'data'),
        State('zoom-state', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('tab-zoom-memory', 'data', allow_duplicate=True),
        Input('zoom-state', 'data'),
        State('active-plot-tab', 'data'),
        State('tab-zoom-memory', 'data'),
        prevent_initial_call=True,
    )
    def save_zoom_per_tab(zoom_state, active_tab, memory):
        """Persist zoom ranges per plot tab so they survive tab switches."""
        if not active_tab:
            return dash.no_update
        memory = memory or {}
        if memory.get(active_tab) == zoom_state:
            return dash.no_update
        return {**memory, active_tab: zoom_state}

    # -- Close custom plot tab --
    @app.callback(
        [Output('plot-tabs', 'data', allow_duplicate=True),
         Output('active-plot-tab', 'data', allow_duplicate=True),
         Output('custom-plot-figures', 'data', allow_duplicate=True)],
        Input({'type': 'plot-tab-close', 'index': dash.dependencies.ALL}, 'n_clicks'),
        [State('plot-tabs', 'data'),
         State('active-plot-tab', 'data'),
         State('custom-plot-figures', 'data')],
        prevent_initial_call=True,
    )
    def close_custom_tab(n_clicks_list, tabs, active_tab, figures):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            return dash.no_update, dash.no_update, dash.no_update
        import json as _json
        triggered = ctx.triggered[0]['prop_id']
        tab_id = _json.loads(triggered.rsplit('.', 1)[0])['index']
        new_tabs = [t for t in tabs if t['id'] != tab_id]
        new_figures = {k: v for k, v in (figures or {}).items() if k != tab_id}
        new_active = active_tab
        if active_tab == tab_id:
            new_active = new_tabs[-1]['id'] if new_tabs else None
        return new_tabs, new_active, new_figures

    # -- Rename a plot tab (kept in plot-tabs, so it is saved with the project) --
    @app.callback(
        Output('plot-tabs', 'data', allow_duplicate=True),
        Input('tab-rename-event', 'data'),
        State('plot-tabs', 'data'),
        prevent_initial_call=True,
    )
    def rename_custom_tab(event, tabs):
        if not event or not tabs:
            return dash.no_update
        tab_id = event.get('tab_id')
        new_label = event.get('new_label')
        if not tab_id or not new_label:
            return dash.no_update
        updated = []
        changed = False
        for t in tabs:
            if t['id'] == tab_id and t['label'] != new_label:
                updated.append({**t, 'label': new_label})
                changed = True
            else:
                updated.append(t)
        return updated if changed else dash.no_update

    # -- Create custom plot tab from Plot button --
    @app.callback(
        [Output('plot-tabs', 'data', allow_duplicate=True),
         Output('active-plot-tab', 'data', allow_duplicate=True),
         Output('custom-plot-figures', 'data', allow_duplicate=True),
         Output('custom-plot-counter', 'data')],
        Input('create-plot-btn', 'n_clicks'),
        [State('pub-selections', 'data'),
         State('pub-data-store', 'data'),
         State('current-plot-settings', 'data'),
         State('plot-tabs', 'data'),
         State('custom-plot-figures', 'data'),
         State('custom-plot-counter', 'data'),
         State('active-tab', 'data'),
         State('peak-group-selector', 'value')],
        prevent_initial_call=True,
    )
    def create_custom_plot_tab(n_clicks, selections, data_json, settings,
                               tabs, figures, counter, active_bottom_tab,
                               peak_group_idx):
        import plotly.graph_objects as go
        import time
        import io
        from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS

        if not n_clicks or not data_json or not selections:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        x_col = selections.get('x', {}).get('data', {}).get('column_id')
        y1_series = selections.get('y1', {}).get('series', [])
        has_y = any(sr.get('column_id') for sr in y1_series)
        if not x_col or not has_y:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        s = {**DEFAULT_PLOT_SETTINGS, **(settings or {})}
        df = table_store.frame(data_json)
        if df is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if '_row_id' not in df.columns:
            df.insert(0, '_row_id', range(len(df)))

        plot_config = {
            'type': s['plot_type'],
            'calc_stats': len(s['y1_stats']) > 0,
            'stat_type': s['y1_stats'][0] if s['y1_stats'] else 'mean_sd',
            'x_label': s['x_label'],
            'y1_label': s['y1_label'],
            'y2_label': s['y2_label'],
            'show_raw_points': s['show_raw_points'],
            'categorical_x': s.get('categorical_x', True),
        }

        fig, _ = create_publication_plot(df, None, selections, plot_config)
        settings_for_style = dict(s, y_label=s.get('y1_label', 'Y1'))
        ps = PlotSettingsService.from_dict(settings_for_style)
        PlotSettingsService.apply_to_figure(fig, ps)

        counter = (counter or 0) + 1
        y_cols = [sr['column_id'] for sr in y1_series if sr.get('column_id')]
        label = f"Plot {counter}"
        if y_cols:
            label = f"{', '.join(y_cols)} vs {x_col}"
        tab_id = f"custom-plot-{counter}"

        source_tab = active_bottom_tab or 'data-overview'
        new_tab = {'id': tab_id, 'label': label, 'type': 'custom'}
        tabs = list(tabs or [])
        tabs.append(new_tab)
        figures = dict(figures or {})
        entry = {
            'figure': fig.to_dict() if hasattr(fig, 'to_dict') else fig,
            'selections': selections,
            'data_json': table_store.as_json(data_json),     # saved with the project: the data, not a reference
            'source_tab': source_tab,
        }
        if source_tab == 'across-samples' and peak_group_idx is not None:
            entry['peak_group_idx'] = peak_group_idx
        figures[tab_id] = entry

        return tabs, tab_id, figures, counter

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('selected-peak-idx', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True)],
        [Input({'type': 'file-tree-item', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State('loaded-files', 'data'),
         State('active-file', 'data'),
         State('active-tab', 'data'),
         State('main-plot', 'relayoutData'),
         State('selected-peak-idx', 'data')],
        prevent_initial_call=True
    )
    def handle_file_selection(n_clicks_list, loaded_files, active_file, active_tab, relayout_data, selected_peak_id):
        """Handle file selection from the tree."""
        
        from components.axis_mapper import get_empty_selections
        
        # Check if any file was clicked
        ctx = dash.callback_context
        if not ctx.triggered:
            return (dash.no_update,) * 6

        # Find which file was clicked
        triggered_id = ctx.triggered[0]['prop_id']
        if 'n_clicks' not in triggered_id:
            return (dash.no_update,) * 6

        # Extract file ID from the triggered component
        import json
        try:
            # Parse the component ID from the prop_id
            # Use rsplit to handle IDs containing periods (e.g. "lys - 2.5 mM")
            component_str = triggered_id.rsplit('.', 1)[0]
            component_id = json.loads(component_str)
            file_id = component_id['index']
            
            # IMPORTANT: Check if this is a control button click
            # Control buttons have different component types
            if ('visibility-btn' in triggered_id or 
                'delete-btn' in triggered_id or 
                'expand-btn' in triggered_id or 
                'collapse-btn' in triggered_id):
                log.debug(f"🚫 Ignoring control button click: {triggered_id}")
                return (dash.no_update,) * 6
            
            # Check if this click actually happened (n_clicks > 0)
            trigger_value = ctx.triggered[0]['value']
            if not trigger_value or trigger_value == 0:
                return (dash.no_update,) * 6
                
        except Exception as e:
            log.debug(f"Error parsing callback trigger: {e}")
            return (dash.no_update,) * 6

        # Resolve bundle clicks to real file UUIDs
        bundle = data_manager.get_bundle_by_id(file_id)
        if bundle and bundle.main_file:
            file_id = bundle.main_file.get('id')
            log.debug(f"Resolved bundle click to main file: {file_id}")
        elif not data_manager.get_data_by_id(file_id) and file_id in data_manager.lcms_bundles:
            lcms = data_manager.lcms_bundles[file_id]
            comp_ids = lcms.get('files', [])
            if comp_ids:
                file_id = comp_ids[0]
                log.debug(f"Resolved LCMS bundle click to first component: {file_id}")

        # A compact sample row can outlive a legend visibility change.
        # Always select the currently visible detector channel for analysis.
        if hasattr(data_manager, 'get_bundle_for_component'):
            channel_bundle = data_manager.get_bundle_for_component(file_id)
            if channel_bundle and channel_bundle.bundle_type in (BundleType.CHROMATOGRAM, BundleType.LCMS):
                from services.channel_visibility import visible_component_id
                file_id = visible_component_id(data_manager, channel_bundle, file_id)

        log.debug(f"File clicked: {file_id} (tab={active_tab})")

        # Don't redraw if the same file is already active
        if file_id == active_file:
            return (dash.no_update,) * 6

        # Publish the selection immediately. The active-file callback below is
        # the sole table/metadata owner, avoiding two full table payloads for
        # every tree click and letting cached plots activate before table work.
        file_data = data_manager.get_data_by_id(file_id)
        if not file_data and '|' in file_id:
            file_data = data_manager.get_data_by_id(file_id.split('|', 1)[0])
        if file_data:
            initialise_file_selections(file_id, file_data)
        return dash.no_update, file_id, None, dash.no_update, dash.no_update, dash.no_update

    def initialise_file_selections(file_id, file_data, table_data=None):
        from components.axis_mapper import get_empty_selections
        if not hasattr(data_manager, 'get_publication_memory'):
            return
        if data_manager.get_publication_memory(file_id) is not None:
            return
        if table_data is None:
            table_data = prepare_table_data(file_data, file_id=file_id)
        if data_manager.get_publication_memory(file_id) is None:
            sr = file_data.get('standardized')
            if sr is not None and sr.x_columns and sr.y_columns:
                auto_x = sr.x_columns[0]
                auto_y = sr.y_columns
            else:
                auto_x = file_data.get('metadata', {}).get('auto_x')
                auto_y = file_data.get('metadata', {}).get('auto_y', [])
            if table_data is not None:
                auto_y = [column for column in (auto_y or []) if column in table_data.columns]
            if auto_x and auto_y and table_data is not None and '_row_id' in table_data.columns:
                all_row_ids = table_data['_row_id'].tolist()
                sel = get_empty_selections()
                sel['x']['data']['column_id'] = auto_x
                sel['x']['data']['row_ids'] = all_row_ids
                if auto_y:
                    sel['y1']['series'][0]['column_id'] = auto_y[0]
                    sel['y1']['series'][0]['row_ids'] = all_row_ids
                for extra_y in auto_y[1:]:
                    sel['y1']['series'].append({'column_id': extra_y, 'row_ids': all_row_ids})
                data_manager.initialise_publication_memory(file_id, sel)
                log.debug(f"📊 Auto-populated selections: X={auto_x}, Y={auto_y}")
            else:
                data_manager.initialise_publication_memory(file_id, get_empty_selections())


    @app.callback(
        [Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True)],
        Input('active-file', 'data'),
        State('active-tab', 'data'),
        prevent_initial_call=True,
    )
    def sync_table_to_active_file(active_file, active_tab):
        """Keep Data Overview table in sync whenever the active file changes.

        Own all table preparation for both tree clicks and programmatic
        active-file changes (tab switches, initial load).
        """
        if not active_file:
            return create_data_table_editor(None, table_id='pub-table'), None, html.Div()

        file_data = data_manager.get_data_by_id(active_file)
        if not file_data and '|' in active_file:
            file_data = data_manager.get_data_by_id(active_file.split('|', 1)[0])
        if not file_data:
            return create_data_table_editor(None, table_id='pub-table'), None, html.Div()

        on_shared_tab = active_tab in ('peak-analysis', 'across-samples')

        sr = file_data.get('standardized')
        visible_wells = None
        if sr is not None and getattr(sr, 'plot_hint', None) == PlotHint.MULTI_Y and sr.x_columns:
            if '|' in active_file:
                visible_wells = [active_file.split('|', 1)[1]]
            else:
                filled = file_data.get('metadata', {}).get('filled_wells', sr.y_columns)
                visible_wells = [well for well in filled
                    if getattr(data_manager, 'visibility_state', {}).get(f'{active_file}|{well}', True)]
        table_data = (prepare_table_data(file_data, file_id=active_file, visible_wells=visible_wells)
                      if visible_wells is not None else prepare_table_data(file_data, file_id=active_file))
        initialise_file_selections(active_file, file_data, table_data)
        sheet_names = file_data.get('metadata', {}).get('sheet_names')
        active_sheet = file_data.get('metadata', {}).get('active_sheet')
        source = table_store.remember(table_data)
        table_editor = create_data_table_editor(
            table_data, table_id='pub-table',
            sheet_names=sheet_names, active_sheet=active_sheet, source=source,
        )
        pub_data = dash.no_update
        if not on_shared_tab:
            pub_data = source

        bundle = data_manager.get_bundle_by_id(active_file)
        if bundle:
            metadata_table = create_bundle_data_table(bundle, file_data, data_manager)
        else:
            metadata_table = create_data_table(file_data)

        return table_editor, pub_data, metadata_table

    # ---- Sheet tab switching for multi-sheet Excel files ----
    @app.callback(
        [Output('render-trigger', 'data', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True)],
        [Input({'type': 'sheet-tab', 'index': dash.dependencies.ALL}, 'n_clicks')],
        [State('active-file', 'data'),
         State('active-sheet-name', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def handle_sheet_tab_click(n_clicks_list, active_file, current_sheet, render_counter):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            return (dash.no_update,) * 4

        triggered_id = ctx.triggered[0]['prop_id']
        import json
        try:
            component_str = triggered_id.rsplit('.', 1)[0]
            clicked_sheet = json.loads(component_str)['index']
        except Exception:
            return (dash.no_update,) * 4

        if clicked_sheet == current_sheet:
            return (dash.no_update,) * 4

        if not active_file:
            return (dash.no_update,) * 4

        file_data = data_manager.get_data_by_id(active_file)
        if not file_data:
            return (dash.no_update,) * 4

        sheets = file_data.get('sheets')
        if not sheets or clicked_sheet not in sheets:
            return (dash.no_update,) * 4

        sheet_info = sheets[clicked_sheet]
        new_df = sheet_info['data']
        new_roles = sheet_info['column_roles']
        new_cat = sheet_info.get('source_category', SourceCategory.GENERIC)
        new_hint = sheet_info.get('plot_hint', PlotHint.LINE)

        file_data['data'] = new_df
        file_data['metadata']['active_sheet'] = clicked_sheet
        sr = file_data.get('standardized')
        if sr is not None:
            from src.ingestion.types import StandardizedResult
            file_data['standardized'] = StandardizedResult(
                data=new_df,
                column_roles=new_roles,
                identity=sr.identity,
                plot_hint=new_hint,
                source_category=new_cat,
                sample_name=sr.sample_name,
                metadata=file_data['metadata'],
            )

        table_data = prepare_table_data(file_data, file_id=active_file)
        sheet_names = file_data.get('metadata', {}).get('sheet_names')
        pub_data = table_store.remember(table_data)
        table_editor = create_data_table_editor(
            table_data, table_id='pub-table',
            sheet_names=sheet_names, active_sheet=clicked_sheet, source=pub_data,
        )
        data_table = create_data_table(file_data)

        return (render_counter or 0) + 1, table_editor, pub_data, data_table

    @app.callback(
        [Output('main-plot', 'figure', allow_duplicate=True),
         Output('zoom-state', 'data', allow_duplicate=True)],
        [Input('active-plot-tab', 'data'),
         State('pub-plot-trigger', 'data'),
         Input('active-file', 'data'),
         Input('current-plot-settings', 'data'),
         Input('render-trigger', 'data'),
         Input('file-order', 'data'),
         Input('pub-table', 'sort_by'),
         Input('peak-table', 'sort_by'),
         Input('cross-sample-table', 'sort_by'),
         Input('peak-change-trigger', 'data')],
        [State('pub-zoom-sync', 'checked'),
         State('plot-y-scope', 'value'),
         State('loaded-files', 'data'),
         State('plot-tabs', 'data'),
         State('pub-plot-figure', 'data'),
         State('selected-peak-idx', 'data'),
         State('zoom-state', 'data'),
         State('tab-zoom-memory', 'data'),
         State('custom-plot-figures', 'data'),
         State('baseline-mode', 'data'),
         State('deconv-markers', 'data'),
         State('deconv-result', 'data'),
         State('int-display-opts', 'value'),
         State('rendered-plot-tabs', 'data'),
         State('main-inspector-context', 'data'),
         Input('pda-preview', 'data'), State('pda-main-cursor', 'data')],
        prevent_initial_call=True
    )
    def master_render(active_tab_id, plot_trigger, active_file, plot_settings, render_trigger,
                      file_order, pub_sort, peak_sort, cross_sort, peak_change_trigger,
                      link_x, y_scope,
                      loaded_files, plot_tabs, pub_plot_figure, selected_peak_id,
                      zoom_state, zoom_memory, custom_figures,
                      baseline_mode, deconv_markers, deconv_result, display_opts, rendered_tabs=None, current_figure=None, pda_preview=None, pda_cursor=None):
        """Single owner of main-plot. Renders the active plot tab's figure."""
        import plotly.graph_objects as go
        from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS

        no_zoom = dash.no_update

        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]['prop_id'].rsplit('.', 1)[0] if ctx.triggered else ''
        log.debug(f"master_render: trigger={trigger_id}, tab={active_tab_id}")

        if not active_tab_id or not plot_tabs:
            return plot_manager.create_empty_plot("Upload files to get started"), None

        tab = next((t for t in plot_tabs if t['id'] == active_tab_id), None)
        if not tab:
            return plot_manager.create_empty_plot("Upload files to get started"), None

        render_cache.prune(t['id'] for t in plot_tabs)

        # Publication tab has its own dedicated callback and graph
        if tab.get('type') == 'publication':
            return dash.no_update, dash.no_update

        owner = (plot_settings or {}).get('_context_key')
        if owner and not owner.endswith(':' + active_tab_id):
            return dash.no_update, no_zoom

        # -- Custom plot tab --
        if tab.get('type') == 'custom':
            entry = (custom_figures or {}).get(active_tab_id)
            if not entry:
                return plot_manager.create_empty_plot("Plot data not found"), no_zoom
            if isinstance(entry, dict) and 'selections' in entry:
                import io as _io
                s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
                sel = entry['selections']
                df = table_store.frame(entry['data_json'])
                if df is None:
                    return plot_manager.create_empty_plot("Plot data not found"), no_zoom
                if '_row_id' not in df.columns:
                    df.insert(0, '_row_id', range(len(df)))

                source_tab = entry.get('source_tab', 'data-overview')
                sort_by = None
                if source_tab == 'data-overview':
                    sort_by = pub_sort
                elif source_tab == 'peak-analysis':
                    sort_by = peak_sort
                elif source_tab == 'across-samples':
                    sort_by = cross_sort
                if sort_by:
                    for sb in reversed(sort_by):
                        col = sb.get('column_id')
                        asc = sb.get('direction', 'asc') == 'asc'
                        if col in df.columns:
                            df = df.sort_values(col, ascending=asc, ignore_index=True)

                plot_config = {
                    'type': s['plot_type'],
                    'calc_stats': len(s['y1_stats']) > 0,
                    'stat_type': s['y1_stats'][0] if s['y1_stats'] else 'mean_sd',
                    'x_label': s['x_label'],
                    'y1_label': s['y1_label'],
                    'y2_label': s['y2_label'],
                    'show_raw_points': s['show_raw_points'],
                    'categorical_x': s.get('categorical_x', True),
                }
                fig, _ = create_publication_plot(df, None, sel, plot_config)
                settings_for_style = dict(s, y_label=s.get('y1_label', 'Y1'))
                ps = PlotSettingsService.from_dict(settings_for_style)
                PlotSettingsService.apply_to_figure(fig, ps)
                fig.update_layout(uirevision=active_tab_id)
                fig.update_layout(meta={'gecko_tab_id': active_tab_id})
                return fig, no_zoom
            fig = go.Figure(entry.get('figure', entry))
            fig.update_layout(meta={'gecko_tab_id': active_tab_id})
            return fig, no_zoom

        # -- Raw tab --
        # Table-derived publication previews do not drive this plot. Other
        # shared inputs still use the delivery check below because Dash can
        # cancel a response while settings are being hydrated.

        s = {**DEFAULT_PLOT_SETTINGS, **(plot_settings or {})}
        layout_mode = s.get('layout_mode', 'overlay')

        is_tab_switch = trigger_id == 'active-plot-tab'
        restored_zoom = (zoom_memory or {}).get(active_tab_id) if is_tab_switch else None
        set_zoom = restored_zoom if is_tab_switch else no_zoom

        group_key = tuple(tab.get('group_key', []))
        active_file_group = _get_active_file_group(data_manager, active_file)
        zoom_matches_tab = not active_file_group or active_file_group == group_key
        if not zoom_matches_tab:
            # The tab, its settings and its active source arrive via separate
            # callbacks. Wait for file restoration instead of building a figure
            # without its peak overlays and immediately building it again.
            return dash.no_update, set_zoom

        render_inputs = {
            'settings': _raw_render_settings(s), 'render': render_trigger, 'peaks': peak_change_trigger,
            'order': file_order, 'selected': selected_peak_id,
            # Overlay keeps the inspected source in its rendering context for
            # overlapping selection. Separate panes retain their source identity.
            'file': active_file if layout_mode != 'stacked' else None,
            'baseline': baseline_mode, 'markers': deconv_markers,
            'deconvolution': deconv_result, 'display': display_opts,
            'visibility': data_manager.visibility_state,
            **({'methods': sorted(data_manager.instrument_methods)}
               if getattr(data_manager, 'instrument_methods', None) else {}),
            'files': [record.get('id') for record in (loaded_files or [])],
            # Adding a wavelength does not change its parent bundle's ID.
            'signals': sorted(data_manager.loaded_data),
            'pda_preview': pda_preview,
            'link_x': link_x, 'y_scope': y_scope,
        }
        render_revision = _raw_render_revision(render_inputs)
        if render_cache.matches(active_tab_id, render_inputs):
            delivered_meta = (current_figure or {}).get('layout', {}).get('meta') or {}
            if (active_tab_id in (rendered_tabs or []) and isinstance(delivered_meta, dict)
                    and delivered_meta.get('gecko_tab_id') == active_tab_id
                    and delivered_meta.get('gecko_render_revision') == render_revision):
                return dash.no_update, set_zoom
            # Computing a revision is not proof that the browser received it:
            # Dash may cancel its response when a newer callback starts. Resend
            # the cached figure until the browser's figure acknowledges it.
            return render_cache.get(active_tab_id, render_inputs), set_zoom

        if is_tab_switch:
            effective_zoom = restored_zoom
        else:
            effective_zoom = zoom_state if zoom_matches_tab else None
        figure = compose_raw_figure(
            data_manager, plot_manager, active_tab_id, group_key, s, active_file, loaded_files,
            file_order=file_order, selected_peak_id=selected_peak_id, baseline_mode=baseline_mode,
            deconv_markers=deconv_markers, deconv_result=deconv_result, display_opts=display_opts,
            pda_preview=pda_preview, pda_cursor=pda_cursor, link_x=link_x, y_scope=y_scope,
            effective_zoom=effective_zoom)
        if figure is None:
            figure = plot_manager.create_hidden_state_plot()
            figure.update_layout(meta={'gecko_tab_id': active_tab_id, 'gecko_render_revision': render_revision})
            render_cache.put(active_tab_id, render_inputs, figure)
            return figure, set_zoom
        figure.update_layout(meta={**(figure.layout.meta or {}), 'gecko_render_revision': render_revision})
        render_cache.put(active_tab_id, render_inputs, figure)
        return figure, set_zoom

    # Selection highlighting is handled centrally in app.py.
    # Keeping a second DOM-mutation callback here causes stale/high-conflicting
    # selection state where multiple file items can remain highlighted.

    @app.callback(
        Output('active-file', 'data', allow_duplicate=True),
        Input('main-plot', 'clickData'),
        [State('main-inspector-context', 'data'),
         State('active-file', 'data')],
        prevent_initial_call=True,
    )
    def subplot_click_selects_file(click_data, figure, current_active):
        if not click_data or 'points' not in click_data:
            raise dash.exceptions.PreventUpdate
        points = click_data['points']
        if not points:
            raise dash.exceptions.PreventUpdate
        curve = points[0].get('curveNumber')
        if curve is None or not figure or 'data' not in figure:
            raise dash.exceptions.PreventUpdate
        traces = figure['data']
        if curve >= len(traces):
            raise dash.exceptions.PreventUpdate
        meta = traces[curve].get('meta')
        if isinstance(meta, dict) and meta.get('file_id'):
            fid = meta['file_id']
            if fid and fid != current_active:
                return fid
        raise dash.exceptions.PreventUpdate


def create_bundle_data_table(bundle, file_data: Dict[str, Any], data_manager) -> html.Div:
    """Create a data table display for a bundle with rich metadata."""
    try:
        main_file = bundle.main_file
        aux_files = bundle.auxiliary_files
        metadata = file_data.get('metadata', {})
        
        # Bundle header
        bundle_header = html.Div([
            html.H5([DashIconify(icon='tabler:package', width=16, height=16, style={'marginRight': '6px', 'color': '#555'}), bundle.base_name],
                   style={'margin': '0 0 5px 0', 'color': '#1a1a1a', 'fontSize': '16px', 'display': 'flex', 'alignItems': 'center'}),
            html.P([
                html.Strong("Bundle Type: "), f"{bundle.bundle_type.capitalize()}",
                html.Br(),
                html.Strong("Files: "), f"{1 + len(aux_files)} files in bundle",
            ], style={'margin': '0 0 15px 0', 'fontSize': '13px', 'color': '#666'})
        ])

        # File list section
        file_list_items = []
        file_list_items.append(html.Div([
            DashIconify(icon='tabler:file-text', width=14, height=14, style={'marginRight': '5px', 'color': '#888'}),
            html.Strong(main_file.get('name', 'Unknown'), style={'color': '#333'})
        ], style={'padding': '4px 0', 'fontSize': '13px'}))
        
        for aux_file in aux_files:
            file_list_items.append(html.Div([
                DashIconify(icon='tabler:file-text', width=14, height=14, style={'marginRight': '5px', 'color': '#888'}),
                html.Span(aux_file.get('name', 'Unknown'), style={'color': '#666'})
            ], style={'padding': '4px 0', 'fontSize': '13px'}))
        
        files_section = html.Div(file_list_items, style={'marginBottom': '20px', 'paddingLeft': '10px'})

        metadata_section = build_metadata_panel(metadata)

        return html.Div([bundle_header, files_section, metadata_section], style={'padding': '5px 0'})

    except Exception as e:
        log.exception("Unable to display bundle details")
        return build_message_state(title="Unable to display bundle details", subtitle=str(e), icon="⚠️", variant="error")


def _measurement_metadata_summary(key, value):
    return measurement_summary(key, value)


_META_LABEL_STYLE = {'padding': '5px 10px', 'fontWeight': '500', 'color': '#555', 'fontSize': '13px',
                     'verticalAlign': 'top', 'width': '38%', 'borderBottom': '1px solid #f0f0f0'}
_META_VALUE_STYLE = {'padding': '5px 10px', 'color': '#333', 'fontSize': '13px', 'verticalAlign': 'top',
                     'borderBottom': '1px solid #f0f0f0', 'wordBreak': 'break-word'}


def build_metadata_panel(metadata: Optional[Dict[str, Any]]) -> html.Div:
    """Curated metadata grouped as Sample / Acquisition / Instrument / Method / Detector / Channels."""
    sections = []
    for group, rows in group_metadata(metadata):
        sections.append(html.Div([
            html.H6(group, style={'margin': '0 0 4px 0', 'color': '#333', 'fontSize': '13px', 'fontWeight': '600'}),
            html.Table(
                [html.Tr([html.Td(label, style=_META_LABEL_STYLE), html.Td(text, style=_META_VALUE_STYLE)])
                 for label, text in rows],
                style={'width': '100%', 'borderCollapse': 'collapse', 'backgroundColor': '#ffffff',
                       'border': '1px solid #e0e0e0', 'borderRadius': '4px'}),
        ], className='metadata-group', style={'marginBottom': '12px'}))
    return html.Div(sections) if sections else html.Div()


def create_data_table(file_data: Dict[str, Any]) -> html.Div:
    """Create a data table display for the selected file."""
    try:
        record = file_data.get('record', {})
        metadata = file_data.get('metadata', {})
        data = file_data.get('data')
        log.debug(f"🔍 METADATA DEBUG (single file): metadata keys: {list(metadata.keys())}")

        # File info section
        file_info = html.Div([
            html.H5([DashIconify(icon='tabler:file-text', width=16, height=16, style={'marginRight': '6px', 'color': '#888'}), record.get('name', 'Unknown')], style={'margin': '0 0 10px 0', 'color': '#333', 'display': 'flex', 'alignItems': 'center'}),
            html.P([
                html.Strong("Type: "), f"{record.get('type', 'unknown').capitalize()}",
                html.Br(),
                html.Strong("Size: "), f"{record.get('size_display', 'Unknown')}",
            ], style={'margin': '0 0 15px 0', 'fontSize': '14px', 'color': '#666'})
        ])

        # StandardizedResult identity section (pipeline info)
        sr_section = html.Div()
        sr = file_data.get('standardized')
        if sr is not None:
            identity = sr.identity
            sr_items = [
                html.P(f"Format: {identity.detected_format} (Stage {identity.detection_stage})",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
                html.P(f"Columns: {', '.join(sr.x_columns)} (X) / {', '.join(sr.y_columns)} (Y)",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
                html.P(f"Plot hint: {sr.plot_hint.value}",
                       style={'margin': '2px 0', 'fontSize': '13px'}),
            ]
            if sr.sample_name:
                sr_items.append(html.P(f"Sample: {sr.sample_name}",
                                        style={'margin': '2px 0', 'fontSize': '13px'}))
            sr_section = html.Div([
                html.H6("Pipeline Detection", style={'margin': '0 0 6px 0', 'color': '#333'}),
                html.Div(sr_items, style={'paddingLeft': '4px'})
            ], style={'marginBottom': '15px', 'padding': '8px', 'backgroundColor': '#f8f9fa',
                      'border': '1px solid #e0e0e0', 'borderRadius': '4px'})

        # Metadata section
        groups = build_metadata_panel(metadata)
        metadata_section = html.Div([
            html.H6("\U0001F4CA Metadata", style={'margin': '0 0 8px 0', 'color': '#333'}),
            groups,
        ], style={'marginBottom': '15px'}) if groups.children else html.Div()

        # Data info (no preview - that's in Data Overview tab)
        if data is not None and not data.empty:
            data_info = html.Div([
                html.P([
                    html.Strong("Data Shape: "),
                    f"{len(data)} rows × {len(data.columns)} columns"
                ], style={'margin': '0', 'fontSize': '14px', 'color': '#666'})
            ], style={'marginBottom': '10px'})
        else:
            data_info = html.Div()

        return html.Div([
            file_info,
            sr_section,
            metadata_section,
            data_info
        ], style={'width': '100%', 'boxSizing': 'border-box'})

    except Exception as e:
        return build_message_state(
            title="Error displaying file details",
            subtitle=str(e),
            icon="⚠️",
            variant="error"
        )


def build_message_state(title: str, subtitle: Optional[str] = None, icon: str = "🦎", variant: str = "default") -> html.Div:
    """Return a styled empty-state or message block."""

    classes = ['empty-state']
    if variant and variant != 'default':
        classes.append(f"empty-state--{variant}")

    children = [
        html.Span(icon, className='empty-state__icon'),
        html.H4(title, className='empty-state__title')
    ]

    if subtitle:
        children.append(html.P(subtitle, className='empty-state__subtitle'))

    return html.Div(children, className=" ".join(classes))
