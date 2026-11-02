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
        """Retain simple overlay traces and patch their flags without shipping signal arrays.

        Peaks, auxiliary overlays and new channels still use the full composer so their
        labels, geometry and axes remain correct. A cold client gets the complete figure.
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
        if not figure.data or figure.layout.shapes or figure.layout.annotations:
            return None
        if any(trace.type not in ('scatter', 'scattergl') or not isinstance(trace.meta, dict)
               or not trace.meta.get('file_id') for trace in figure.data):
            return None
        represented = {trace.meta['file_id'] for trace in figure.data}
        if any(old_visibility.get(fid, True) is False and visibility.get(fid, True)
               and fid not in represented for fid in inputs.get('signals', [])):
            return None
        old_meta = dict(figure.layout.meta or {})
        patch = Patch()
        for index, trace in enumerate(figure.data):
            shown = visibility.get(trace.meta['file_id'], True) is not False
            trace.visible = shown
            patch['data'][index]['visible'] = shown
        meta = {**old_meta, 'gecko_render_revision': revision, 'gecko_visibility_revision': revision}
        figure.layout.meta = meta
        patch['layout']['meta'] = meta
        self._entries[tab_id] = (self._key(inputs), figure)
        seen = (delivered or {}).get('layout', {}).get('meta') or {}
        if seen.get('gecko_render_revision') == old_meta.get('gecko_render_revision'):
            return patch
        return deepcopy(figure)

    def prune(self, tab_ids):
        keep = set(tab_ids)
        self._entries = {key: value for key, value in self._entries.items() if key in keep}
