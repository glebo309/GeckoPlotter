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

    def prune(self, tab_ids):
        keep = set(tab_ids)
        self._entries = {key: value for key, value in self._entries.items() if key in keep}
