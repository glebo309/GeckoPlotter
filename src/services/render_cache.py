"""Reuse rendered figures until their data or controls change."""
import json
from copy import deepcopy


class RenderCache:
    def __init__(self):
        self._entries = {}

    @staticmethod
    def _key(inputs):
        return json.dumps(inputs, sort_keys=True, default=str)

    def matches(self, tab_id, inputs):
        """Check validity without copying a potentially large Plotly figure."""
        entry = self._entries.get(tab_id)
        return bool(entry and entry[0] == self._key(inputs))

    def get(self, tab_id, inputs):
        entry = self._entries.get(tab_id)
        if entry and entry[0] == self._key(inputs):
            return deepcopy(entry[1])
        return None

    def put(self, tab_id, inputs, figure):
        self._entries[tab_id] = (self._key(inputs), deepcopy(figure))

    def visibility_update(self, tab_id, inputs, revision, delivered):
        """Retain overlay signals, peaks and labels and send only changed visibility flags.

        Unrecognized overlays and newly shown channels still use the full composer.
        Retained peak labels move to the tallest remaining visible sample. A cold client gets the complete figure.
        """
        from dash import Patch
        entry = self._entries.get(tab_id)
        if not entry:
            return None
        previous, figure = json.loads(entry[0]), entry[1]
        old_visibility = previous.pop('visibility', {})
        current = dict(inputs)
        visibility = current.pop('visibility', {})
        if self._key(previous) != self._key(current):
            return None
        if not figure.data:
            return None
        from services.peak_display import peak_id_for_trace
        geometry = (figure.layout.meta or {}).get('gecko_peak_geometry', {})
        owners, labels, represented = [], set(), set()
        for trace in figure.data:
            if trace.type not in ('scatter', 'scattergl'):
                return None
            if isinstance(trace.meta, dict) and trace.meta.get('file_id'):
                fid = trace.meta['file_id']
                owners.append((fid, None, False))
                represented.add(fid)
            else:
                pid = peak_id_for_trace(trace)
                spec = geometry.get(pid, {})
                if not spec.get('file_id') or 'label_group' not in spec:
                    return None
                is_label = trace.mode == 'text' or trace.name == 'label-room'
                owners.append((spec['file_id'], pid, is_label))
                if is_label:
                    labels.add(pid)
        decorations = []
        for kind, prefix in (('shapes', 'baseline:'), ('annotations', 'peak-label:')):
            for index, item in enumerate(getattr(figure.layout, kind) or ()):
                name = item.name or ''
                pid = name.removeprefix(prefix)
                if not name.startswith(prefix) or pid not in geometry:
                    return None
                decorations.append((kind, index, item, pid))
                if kind == 'annotations':
                    labels.add(pid)
        if any(old_visibility.get(fid, True) is False and visibility.get(fid, True)
               and fid not in represented for fid in inputs.get('signals', [])):
            return None
        tallest = {}
        if 'hide-labels' not in (inputs.get('display') or []):
            for _fid, pid, _label in owners:
                spec = geometry.get(pid)
                if not spec or visibility.get(spec['file_id'], True) is False:
                    continue
                group = spec['label_group']
                candidate = (spec['label_top'], pid)
                if group not in tallest or candidate[0] > tallest[group][0]:
                    tallest[group] = candidate
        chosen = {pid for _, pid in tallest.values()}
        if not chosen.issubset(labels):
            return None  # Older figures may not retain the next sample's label.
        old_revision = (figure.layout.meta or {}).get('gecko_render_revision')
        patch = Patch()
        for index, (fid, pid, label) in enumerate(owners):
            shown = visibility.get(fid, True) is not False and (not label or pid in chosen)
            if (figure.data[index].visible is not False) != shown:
                figure.data[index].visible = shown
                patch['data'][index]['visible'] = shown
        for kind, index, item, pid in decorations:
            shown = visibility.get(geometry[pid]['file_id'], True) is not False
            if kind == 'annotations':
                shown = shown and pid in chosen
            if (item.visible is not False) != shown:
                item.visible = shown
                patch['layout'][kind][index]['visible'] = shown
        # Peak geometry already lives in the browser. Do not send it back in
        # every visibility response or revalidate all its coordinates here.
        for key in ('gecko_render_revision', 'gecko_visibility_revision'):
            figure.layout.meta[key] = revision
            patch['layout']['meta'][key] = revision
        self._entries[tab_id] = (self._key(inputs), figure)
        seen = (delivered or {}).get('layout', {}).get('meta') or {}
        if seen.get('gecko_render_revision') == old_revision:
            return patch
        return deepcopy(figure)

    def prune(self, tab_ids):
        keep = set(tab_ids)
        self._entries = {key: value for key, value in self._entries.items() if key in keep}
