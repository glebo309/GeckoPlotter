"""Sample-owned subplot letters, shared by the file tree and agent tools."""
import re


def subplot_letter(bundle):
    return (bundle.primary.metadata.get('subplot_letter', '')
            if bundle and bundle.primary else '')


def normalize_letter(letter):
    value = str(letter or '').strip().upper()
    if value and not re.fullmatch('[A-Z]', value):
        raise ValueError('Use one subplot letter, A to Z, or clear the box for the main plot.')
    return value


def set_sample_subplot(store, bundle, letter):
    value = normalize_letter(letter)
    if subplot_letter(bundle) == value:
        return False
    for component in bundle.component_list:
        component.metadata['subplot_letter'] = value
    for cache in store._render_caches:
        cache.prune([])
    return True
