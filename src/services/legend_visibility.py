"""Keep source and peak visibility together in retained publication figures."""
from services.peak_display import peak_id_for_trace


def apply_file_visibility(figure, visibility):
    geometry = (figure.layout.meta or {}).get('gecko_peak_geometry', {})
    hidden = {pid for pid, spec in geometry.items() if visibility.get(spec.get('file_id'), True) is False}
    figure.data = tuple(trace for trace in figure.data
        if not (isinstance(trace.meta, dict) and visibility.get(trace.meta.get('file_id'), True) is False)
        and peak_id_for_trace(trace) not in hidden)
    figure.layout.shapes = tuple(s for s in figure.layout.shapes or ()
        if (s.name or '').removeprefix('baseline:') not in hidden)
    return figure
