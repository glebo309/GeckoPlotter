"""Shared detector controls using scientific channel identity and existing visibility."""
from __future__ import annotations
import math


def _value(value):
    return getattr(value, 'value', value)


def channel_identity(component):
    role = _value(component.role)
    category = _value(component.source_category)
    meta = component.metadata or {}
    if role in ('ms_positive', 'ms_negative') or category == 'lcms_ms':
        polarity = {'ms_positive': 'positive', 'ms_negative': 'negative'}.get(role, meta.get('ionization_mode'))
        if polarity in ('positive', 'negative'):
            return 'ms:' + polarity, '+TIC' if polarity == 'positive' else '−TIC'
        return 'ms:unknown', 'TIC'
    if category not in ('chromatogram', 'lcms_uv') and role not in ('vwd_a', 'vwd_b'):
        return None
    wavelength = meta.get('wavelength_nm', meta.get('wavelength'))
    try:
        wavelength = float(str(wavelength).replace('nm', '').strip())
        if math.isfinite(wavelength) and wavelength > 0:
            label = f'{wavelength:.0f}'
            return 'uv:' + label, label + ' nm'
    except (TypeError, ValueError):
        pass
    detector = meta.get('detector_channel')
    if detector:
        return 'uv-channel:' + str(detector), 'UV ' + str(detector)
    if role in ('vwd_a', 'vwd_b'):
        return 'uv-channel:' + role[-1].upper(), 'UV ' + role[-1].upper()
    return None


def channel_controls(store, bundle_ids):
    groups = {}
    for bundle_id in dict.fromkeys(bundle_ids):
        bundle = store.get_bundle(bundle_id)
        if bundle is None:
            continue
        for component in bundle.component_list:
            identity = channel_identity(component)
            if identity is None:
                continue
            key, label = identity
            group = groups.setdefault(key, {'key': key, 'label': label, 'sources': [], 'visible': 0, 'enabled': 0})
            source = store.peak_owner_id(component.component_id)
            group['sources'].append(source)
            mask = getattr(store, '_hidden_sample_channels', {}).get(bundle_id, {})
            group['enabled'] += bool(mask.get(source, store.visibility_state.get(source, True)))
            group['visible'] += bool(store.visibility_state.get(source, True)
                                     and store.visibility_state.get(bundle_id, True))
    for group in groups.values():
        n = len(group['sources'])
        group['state'] = 'true' if group['enabled'] == n else 'false' if not group['enabled'] else 'mixed'
    def order(group):
        key = group['key']
        if key.startswith('uv:'):
            return (1, float(key[3:]), '')
        return (0 if key.startswith('ms:') else 2, 0, key)
    return sorted(groups.values(), key=order)


def toggle_channel(store, bundle_ids, channel_key):
    return choose_channel(store, bundle_ids, channel_key, combine=True)


def visible_component_id(store, bundle, active_file=None):
    visible = [c.component_id for c in bundle.component_list
               if store.visibility_state.get(store.peak_owner_id(c.component_id), True)]
    if active_file in visible:
        return active_file
    return visible[0] if visible else (bundle.primary.component_id if bundle.primary else None)


def group_bundle_ids(store, group_id):
    """LC-MS channel controls span runs while their plot groups remain separate."""
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
    selected = []
    for bundle in store.iter_bundles():
        entry = store.get_data_by_id(bundle.bundle_id)
        if entry and _tab_id_from_group(_get_overlay_group(entry['metadata'], entry, bundle.bundle_id, store)) == group_id:
            selected.append(bundle.bundle_id)
    if any(_value(store.get_bundle(b).bundle_type) == 'lcms' for b in selected):
        return [b.bundle_id for b in store.iter_bundles() if _value(b.bundle_type) == 'lcms']
    return selected


def set_sample_visibility(store, bundle_id, visible):
    bundle = store.get_bundle(bundle_id)
    if not bundle:
        return
    masks = getattr(store, '_hidden_sample_channels', {})
    store._hidden_sample_channels = masks
    if not visible:
        if bundle_id not in masks:
            masks[bundle_id] = {store.peak_owner_id(c.component_id): store.visibility_state.get(store.peak_owner_id(c.component_id), True)
                                for c in bundle.component_list}
        for source in masks[bundle_id]:
            store.visibility_state[source] = False
    else:
        previous = masks.pop(bundle_id, {})
        for component in bundle.component_list:
            source = store.peak_owner_id(component.component_id)
            store.visibility_state[source] = previous.get(source, True)
    store.visibility_state[bundle_id] = bool(visible)


def choose_channel(store, bundle_ids, channel_key, combine=False):
    controls = channel_controls(store, bundle_ids)
    target = next((c for c in controls if c['key'] == channel_key), None)
    if target is None:
        return False
    desired = target['state'] != 'true' if combine else True
    masks = getattr(store, '_hidden_sample_channels', {})
    for bundle_id in bundle_ids:
        bundle = store.get_bundle(bundle_id)
        if bundle is None:
            continue
        for component in bundle.component_list:
            identity = channel_identity(component)
            if identity is None or (combine and identity[0] != channel_key):
                continue
            source = store.peak_owner_id(component.component_id)
            value = desired if identity[0] == channel_key else False
            if bundle_id in masks:
                masks[bundle_id][source] = value
                store.visibility_state[source] = False
            else:
                store.visibility_state[source] = value
        if bundle_id not in masks:
            store.visibility_state[bundle_id] = any(store.visibility_state.get(store.peak_owner_id(c.component_id), True)
                                                     for c in bundle.component_list)
    return True


def channel_scope_key(store, bundle_ids, group_id):
    return 'family:lcms' if any(_value(store.get_bundle(b).bundle_type) == 'lcms'
                                for b in bundle_ids if store.get_bundle(b)) else group_id


def combine_enabled(store, bundle_ids, group_id):
    return getattr(store, '_channel_combine_modes', {}).get(channel_scope_key(store, bundle_ids, group_id), False)


def initialize_imported_channels(store, new_bundles):
    """Choose one channel in new samples, following an existing group's choice."""
    from callbacks.viz_callbacks import _get_overlay_group, _tab_id_from_group
    new_ids = {b.bundle_id for b in new_bundles}
    for bundle in new_bundles:
        if _value(bundle.bundle_type) not in ('chromatogram', 'lcms'):
            continue
        entry = store.get_data_by_id(bundle.bundle_id)
        group_id = _tab_id_from_group(_get_overlay_group(entry['metadata'], entry, bundle.bundle_id, store))
        members = group_bundle_ids(store, group_id)
        old = channel_controls(store, [b for b in members if b not in new_ids])
        available = channel_controls(store, [bundle.bundle_id])
        if not available:
            continue
        requested = [c['key'] for c in old if c['state'] != 'false']
        if not old:
            # Acquisition order supplies the default UV channel. For LC-MS,
            # prefer positive TIC when present, otherwise the available TIC.
            identities = [channel_identity(c) for c in bundle.component_list]
            keys = [identity[0] for identity in identities if identity]
            uv = next((key for key in keys if not key.startswith('ms:')), None)
            tic = 'ms:positive' if 'ms:positive' in keys else next((key for key in keys if key.startswith('ms:')), None)
            requested = ([key for key in (uv, tic) if key] if _value(bundle.bundle_type) == 'lcms'
                         else keys[:1])
        for component in bundle.component_list:
            identity = channel_identity(component)
            if identity:
                store.visibility_state[store.peak_owner_id(component.component_id)] = identity[0] in requested
        store.visibility_state[bundle.bundle_id] = any(store.visibility_state.get(store.peak_owner_id(c.component_id), True)
                                                     for c in bundle.component_list)
