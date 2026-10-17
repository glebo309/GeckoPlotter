"""Live mode: after an agent call, the screen shows what the agent worked on (services/live_agent).

``focus`` picks the sample and channel of the call, switches that channel on when the plot does not show it (as the
channel switch in the toolbar does) and names the view to open: the MS scan at the agent's retention time, the peak's
mass spectrum, or the PDA view. The page applies it (callbacks/live_callbacks.py, assets/js/agent-live.js).
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# Calls the screen follows; the reads of the whole workspace leave the view alone ('open' zooms to the peaks).
FOLLOWED = {'open', 'detect_peaks', 'integrate', 'rename_peak', 'remove_peak', 'calibrate', 'add_uv_channel', 'uv_spectrum',
            'add_eic_channel', 'eic', 'mass_spectrum', 'figure', 'list_calibrations', 'deconvolve', 'compare_wavelengths'}


def _params(workspace, method, args, kwargs) -> dict:
    try:
        bound = inspect.signature(getattr(workspace, method)).bind(*(args or []), **(kwargs or {}))
    except TypeError:
        return {}
    bound.apply_defaults()
    return dict(bound.arguments)


def _first_hit(result) -> Optional[dict]:
    """The first sample the call changed (integrate, detect, EIC ... return one entry per sample)."""
    if isinstance(result, list):
        return next((r for r in result if isinstance(r, dict) and r.get('sample') and not r.get('error')), None)
    return None


def _ms_component(bundle, negative: bool):
    from services.data_store import ComponentRole
    role = ComponentRole.MS_NEGATIVE if negative else ComponentRole.MS_POSITIVE
    return next((c for c in bundle.component_list if c.role == role), None)


def _show(store, bundle, component) -> None:
    """Switch the sample and this channel on, as the eye and the toolbar's channel switch would."""
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
    from services.channel_visibility import (channel_identity, choose_channel, group_bundle_ids,
                                             set_sample_visibility)
    if store.visibility_state.get(bundle.bundle_id, True) is False:
        set_sample_visibility(store, bundle.bundle_id, True)
    identity = channel_identity(component)
    uv = bool(identity and str(identity[0]).startswith(('uv:', 'eic:')))
    if store.visibility_state.get(store.peak_owner_id(component.component_id), True) and not uv:
        return                                          # shown already: the user's choice of channels stays
    entry = store.get_data_by_id(bundle.bundle_id)
    if identity is None or not entry:
        from services.channel_visibility import show_channel
        show_channel(store, component.component_id)
        return
    if uv:
        _only_uv(store, identity[0], 'eic:' if str(identity[0]).startswith('eic:') else 'uv:')
        return
    group = _tab_id_from_group(_get_overlay_group(entry['metadata'], entry, bundle.bundle_id, store))
    choose_channel(store, group_bundle_ids(store, group), identity[0])


def _only_uv(store, key, kind='uv:') -> None:
    """One UV wavelength (or one extracted ion: kind 'eic:') on screen when the agent is done: in every sample that
    has it, this channel is shown and its other channels of that kind hidden; the others stay as they are. A sample hidden with its eye stays hidden
    (its channel mask changes, as the toolbar's switch does)."""
    from services.channel_visibility import channel_identity
    masks = getattr(store, '_hidden_sample_channels', {}) or {}
    for bundle in store.iter_bundles():
        uv = [(c, channel_identity(c)[0]) for c in bundle.component_list
              if channel_identity(c) and str(channel_identity(c)[0]).startswith(kind)]
        if not any(k == key for _c, k in uv):
            continue
        for component, k in uv:
            source = store.peak_owner_id(component.component_id)
            if bundle.bundle_id in masks:
                masks[bundle.bundle_id][source] = k == key
                store.visibility_state[source] = False
            else:
                store.visibility_state[source] = k == key


def _scan(store, component_id, rt) -> Optional[int]:
    from callbacks.lcms_callbacks import _resolve_lcms_spectral_entry
    lcms = store.lcms_service
    resolved = _resolve_lcms_spectral_entry(store, component_id, lcms)
    if not resolved or not lcms.has_spectral_data(resolved[1]):
        return None
    try:
        return int(lcms.get_scan_index_at_time(resolved[1], float(rt)))
    except (ValueError, IndexError):
        return None


def focus(workspace, method: str, args, kwargs, result) -> Optional[dict]:
    """{'active': component id, 'side': view, 'scan' / 'peak': where} for the page, or None to leave it."""
    if method not in FOLLOWED or (isinstance(result, dict) and result.get('error')):
        return None
    try:
        return _focus(workspace, method, _params(workspace, method, args, kwargs), result)
    except Exception:                                   # noqa: BLE001  the call itself worked: never fail it here
        log.exception('Could not follow the agent call %s', method)
        return None


def _focus(workspace, method, params, result) -> Optional[dict]:
    store = workspace.store
    if method in ('calibrate', 'list_calibrations'):
        return _calibration_view(store, params, result)
    if method == 'open':
        return {'zoom': 'peaks'}                        # the page zooms to the peaks of what was opened
    if method == 'compare_wavelengths':
        chosen = result.get('recommendation')
        if not chosen:
            return None
        bundle = workspace._sample(chosen['sample'])
        component = workspace._channel(bundle, chosen['channel'])
        _show(store, bundle, component)
        # The PDA view ends on the chosen wavelength after sweeping through the range during the screen.
        screened = (result.get('screen') or {}).get('range_nm')
        apex = None
        try:
            apex = workspace._find_peak(bundle, params.get('peak'))[1].rt     # the PDA view ends on the peak's apex
        except Exception:                                   # noqa: BLE001  no such peak in that sample: leave the time
            pass
        return {'active': component.component_id, 'side': 'pda', 'wavelength': chosen.get('wavelength_nm'),
                'sweep_nm': screened, 'time': apex}
    hit = _first_hit(result)
    name = (hit or {}).get('sample') or params.get('sample')
    samples = params.get('samples')
    if not name and samples:
        name = samples if isinstance(samples, str) else samples[0]
    if not name:
        names = [b.name for b in workspace._samples(None)]
        if not names:
            return None
        name = names[0]
    bundle = workspace._sample(name)
    view: dict = {}
    if method == 'mass_spectrum':
        negative = (result.get('polarity') if isinstance(result, dict) else params.get('polarity')) == '-'
        component = _ms_component(bundle, negative) or workspace._channel(bundle, None)
        if params.get('peak'):
            owner, peak = workspace._find_peak(bundle, params['peak'])
            component = owner                               # the peak's own trace stays in view
            view.update(side='ms-peak-mass', peak=peak.peak_id, polarity='negative' if negative else 'positive')
        else:
            rt = params.get('rt')
            if rt is None and params.get('rt_start') is not None and params.get('rt_end') is not None:
                rt = (params['rt_start'] + params['rt_end']) / 2
            if rt is None and isinstance(result, dict):
                rt = result.get('rt')
            view['side'] = 'ms-scan'
            if rt is not None:
                view['scan'] = _scan(store, component.component_id, rt)
    else:
        channel = (hit or {}).get('channel') or params.get('channel')
        component = workspace._channel(bundle, channel)
        if method == 'uv_spectrum':
            view['side'] = 'pda'
        elif method in ('eic', 'add_eic_channel'):
            view['side'] = 'ms-eic'
    # The results pane follows too: the peak table after peaks change, the curve after a calibration.
    if method in ('integrate', 'detect_peaks', 'deconvolve', 'rename_peak', 'remove_peak', 'eic'):
        view['results'] = 'peak-analysis'

    _show(store, bundle, component)
    view['active'] = component.component_id
    window = _window(params, result)
    if window:
        view['zoom'] = window
    # A UV channel: an open PDA view follows it, at the agent's peak when there is one.
    nm = (component.metadata or {}).get('wavelength_nm')
    if nm and method in ('add_uv_channel', 'integrate', 'detect_peaks', 'deconvolve', 'figure'):
        time = (hit or {}).get('rt') or (hit or {}).get('apex_rt')
        parts = (hit or {}).get('components') or []
        if time is None and parts:                          # deconvolve: the first component (the one named first)
            time = parts[0].get('apex_rt') or parts[0].get('rt')
        if time is None:                                    # no peak in the answer: the channel's largest peak
            peaks = store.peak_service.get_peaks(store.peak_owner_id(component.component_id)) or []
            biggest = max(peaks, key=lambda p: getattr(p, 'area', 0) or 0, default=None)
            time = getattr(biggest, 'rt', None)
        view['pda_follow'] = {'wavelength': nm, 'time': time}
    return view


def _window(params, result):
    """The time range the call worked on, with room around it, for the plot to zoom to (None: leave the zoom)."""
    starts, ends = [], []
    for row in result if isinstance(result, list) else []:
        if isinstance(row, dict) and not row.get('error'):
            for key_a, key_b in (('rt_start', 'rt_end'), ('window_start', 'window_end')):
                if row.get(key_a) is not None and row.get(key_b) is not None:
                    starts.append(row[key_a]); ends.append(row[key_b])
    if not starts and params.get('rt_start') is not None and params.get('rt_end') is not None:
        starts, ends = [params['rt_start']], [params['rt_end']]
    if not starts:
        return None
    a, b = float(min(starts)), float(max(ends))
    pad = max(0.5 * (b - a), 0.05)                      # the page widens it to all the peaks shown
    return [round(max(0.0, a - pad), 4), round(b + pad, 4)]


def _calibration_view(store, params, result) -> dict:
    """The Calibration tab with the agent's curve selected; the sample and channel on screen stay."""
    view = {'results': 'calibration'}
    name = (result.get('calibration') if isinstance(result, dict) else None) or params.get('name') or params.get('peak')
    models = store.calibration_service.get_all_models()
    chosen = next((m for m in models.values() if m.analyte_name == name), None)
    if chosen is None and models:
        chosen = list(models.values())[-1]
    if chosen is not None:
        view['calibration'] = chosen.model_id
    return view


def peaks_range(store, active_id, window=None):
    """The time range the plot zooms to after an agent step: from the first to the last place where a shown trace of
    the active sample's tab rises clearly above its baseline (3 % of the tallest rise on the tab), a small margin
    around it, always including the agent's window; and the y range of those traces inside it. Returns
    (tab_id, {'xaxis.range': [a, b], 'yaxis.range': [lo, hi]}) or None."""
    import numpy as np
    from callbacks.viz_callbacks import _get_active_file_group, _tab_id_from_group
    from callbacks.baseline_callbacks import get_xy_arrays
    from services.channel_visibility import group_bundle_ids
    group = _get_active_file_group(store, active_id) if active_id else None
    if not group:
        return None
    tab = _tab_id_from_group(group)
    rows = []
    for bundle_id in group_bundle_ids(store, tab, span=False):
        bundle = store.get_bundle(bundle_id)
        if bundle is None or store.visibility_state.get(bundle_id, True) is False:
            continue
        for component in bundle.component_list:
            if not store.visibility_state.get(store.peak_owner_id(component.component_id), True):
                continue
            x, y = get_xy_arrays(store, component.component_id)
            if x is None or y is None or len(x) < 10:
                continue
            x, y = np.asarray(x, float), np.asarray(y, float)
            keep = np.isfinite(x) & np.isfinite(y)
            if keep.sum() >= 10:
                rows.append((x[keep], y[keep], float(np.median(y[keep]))))
    if not rows:
        return None
    tallest = max(float(y.max()) - base for _x, y, base in rows)
    if tallest <= 0:
        return None
    lo, hi = np.inf, -np.inf
    for x, y, base in rows:
        hit = x[y > base + .03 * tallest]
        if hit.size:
            lo, hi = min(lo, hit.min()), max(hi, hit.max())
    if window:
        lo, hi = min(lo, window[0]), max(hi, window[1])
    if not np.isfinite(lo) or hi <= lo:
        return None
    first = min(float(x.min()) for x, _y, _b in rows)
    last = max(float(x.max()) for x, _y, _b in rows)
    margin = max(.08 * (hi - lo), .05)
    a, b = max(first, lo - margin), min(last, hi + margin)
    inside = [y[(x >= a) & (x <= b)] for x, y, _b in rows]
    inside = [v for v in inside if v.size]
    zoom = {'xaxis.range': [round(float(a), 4), round(float(b), 4)]}
    if inside:
        ylo, yhi = min(float(v.min()) for v in inside), max(float(v.max()) for v in inside)
        pad = (yhi - ylo) * .08 or 1.0
        zoom['yaxis.range'] = [round(ylo - pad, 3), round(yhi + pad, 3)]
    return tab, zoom
