"""One display name for a source in the file tree and figure legends."""
import os
from copy import deepcopy


def display_name(name):
    stem, extension = os.path.splitext(name or '')
    return stem if extension.lower() in ('.csv', '.txt', '.cdf', '.xlsx', '.xls', '.tsv', '.dat') else name


def trace_display_name(source):
    """Identify both the sample and detector when channels share a figure."""
    name = display_name(source.get('record', {}).get('name', ''))
    metadata = source.get('metadata', {})
    sr = source.get('standardized')
    category = getattr(getattr(sr, 'source_category', None), 'value', None)
    sample = display_name(metadata.get('parent_bundle_name', ''))
    if sample and category in ('chromatogram', 'lcms_uv', 'lcms_ms') and name != sample:
        return f'{sample} · {name}'
    return name


def rename_style_settings(settings, renames):
    result = deepcopy(settings or {})
    def visit(value):
        if not isinstance(value, dict):
            return
        overrides = value.get('trace_overrides')
        if isinstance(overrides, dict):
            for key in list(overrides):
                for fid, (old, new) in renames.items():
                    prefix = f'id:{fid}:{old}'
                    if key == prefix or key.startswith(prefix + ' — '):
                        overrides[f'id:{fid}:{new}' + key[len(prefix):]] = overrides.pop(key)
                        break
        for child in value.values():
            visit(child)
    visit(result)
    return result


def update_named_figures(figures, store):
    result = {}
    for key, entry in (figures or {}).items():
        figure = entry.get('figure', entry)
        traces = []
        for trace in figure.get('data', []):
            meta = trace.get('meta')
            source = store.get_data_by_id(meta.get('file_id')) if isinstance(meta, dict) else None
            if source:
                name = trace_display_name(source)
                column = meta.get('y_column')
                sr = source.get('standardized')
                if column and sr and len(sr.y_columns) > 1:
                    name += ' — ' + column
                if meta.get('rename_file_id'):
                    meta = {**meta, 'rename_label': source.get('metadata', {}).get('parent_bundle_name', name)}
                trace = {**trace, 'name': name, 'meta': meta}
            traces.append(trace)
        updated = {**figure, 'data': traces}
        result[key] = {**entry, 'figure': updated} if 'figure' in entry else updated
    return result
