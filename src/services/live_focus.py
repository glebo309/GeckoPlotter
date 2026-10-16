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

# Calls that are about one place in the data; 'open' and the reads of the whole workspace leave the view alone.
FOLLOWED = {'detect_peaks', 'integrate', 'rename_peak', 'remove_peak', 'calibrate', 'add_uv_channel', 'uv_spectrum',
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
    uv = bool(identity and str(identity[0]).startswith('uv:'))
    if store.visibility_state.get(store.peak_owner_id(component.component_id), True) and not uv:
        return                                          # shown already: the user's choice of channels stays
    # A UV channel is shown alone: one wavelength in the plot when the agent is done, not two half-ticked ones.
    entry = store.get_data_by_id(bundle.bundle_id)
    if identity is None or not entry:
        from services.channel_visibility import show_channel
        show_channel(store, component.component_id)
        return
    group = _tab_id_from_group(_get_overlay_group(entry['metadata'], entry, bundle.bundle_id, store))
    choose_channel(store, group_bundle_ids(store, group), identity[0])


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
    if method == 'compare_wavelengths':
        chosen = result.get('recommendation')
        if not chosen:
            return None
        bundle = workspace._sample(chosen['sample'])
        component = workspace._channel(bundle, chosen['channel'])
        _show(store, bundle, component)
        # The PDA view ends on the chosen wavelength after sweeping through the range during the screen.
        screened = (result.get('screen') or {}).get('range_nm')
        return {'active': component.component_id, 'side': 'pda', 'wavelength': chosen.get('wavelength_nm'),
                'sweep_nm': screened}
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
    return view


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
