"""Filter detector polarity without mutating visibility or loaded measurements."""


def entry_polarity(entry):
    metadata = entry.get('metadata') or {}
    role = metadata.get('component_role') or (entry.get('record') or {}).get('type', '')
    if role in ('vwd_a', 'vwd_b', 'lcms_uv'):
        return None
    mode = str(metadata.get('ionization_mode', '')).lower()
    if mode in ('positive', 'negative'):
        return mode
    return {'ms_positive': 'positive', 'ms_negative': 'negative'}.get(role)


def filter_ms_polarity(groups, mode):
    if mode not in ('positive', 'negative'):
        return groups
    result = {}
    for key, entries in groups.items():
        filtered = [(name, entry) for name, entry in entries
                    if entry_polarity(entry) in (None, mode)]
        if filtered:
            result[key] = filtered
    return result


def polarity_options(groups):
    available = {entry_polarity(entry) for entries in groups.values() for _, entry in entries} - {None}
    if not available:
        return []
    return [{'label': label, 'value': value,
             'disabled': len(available) < 2 if value == 'both' else value not in available}
            for label, value in [('+', 'positive'), ('−', 'negative'), ('Both', 'both')]]
