"""
Persistence Layer for GeckoPlotter V2.

Three distinct persistence tiers:

1. **Ephemeral UI state** — lives only in dcc.Store / browser memory.
   Lost on page refresh.  Examples: active-selector.

2. **Project/session state** — survives page refresh, saved to a local
   JSON file.  Contains per-file UI settings, peak data, calibration
   models, integration settings.  This is the "reopen where I left off"
   tier.

3. **Exported scientific results** — deliberately exported by the user
   as CSV, Excel, JSON, PNG, SVG, or session bundle.  These are the
   deliverables.

This module provides the project/session persistence layer (tier 2).
Tier 1 is handled by Dash stores.  Tier 3 is handled by ExportService.
"""

from __future__ import annotations

import json
import os
import copy
import logging
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger('geckoplotter.persistence')


class ProjectPersistence:
    """Manages project-level persistence to a JSON file.

    Holds:
    - per-file UI state (view mode, tab, plot settings, selections)
    - peak data (via PeakService.serialize)
    - calibration models (via CalibrationService.serialize)
    - integration settings (via IntegrationService.serialize)
    - shared analysis state (peak-shared-selections, cross-shared-selections,
      shared-plot-settings)
    """

    def __init__(self, state_file: str):
        self._state_file = state_file
        self._enabled = os.environ.get("GECKO_ENABLE_SESSION_PERSISTENCE") == "1"
        self._data: Dict[str, Any] = {}
        self._load()

    # -- File I/O -----------------------------------------------------------

    def _load(self) -> None:
        if not self._enabled:
            self._data = {}
            return
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, 'r') as f:
                    self._data = json.load(f)
                log.debug(f"Loaded project state from {self._state_file}")
            except (json.JSONDecodeError, IOError) as e:
                log.warning(f"Failed to load project state: {e}")
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        """Write current state to disk."""
        if not self._enabled:
            return
        try:
            tmp = self._state_file + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(self._data, f, indent=2, default=str)
            os.replace(tmp, self._state_file)
        except IOError as e:
            log.error(f"Failed to save project state: {e}")

    # -- Section accessors --------------------------------------------------

    def get_section(self, section: str) -> Dict[str, Any]:
        return copy.deepcopy(self._data.get(section, {}))

    def set_section(self, section: str, data: Dict[str, Any], auto_save: bool = True) -> None:
        self._data[section] = copy.deepcopy(data)
        if auto_save:
            self.save()

    # -- Convenience accessors for common sections --------------------------

    @property
    def file_states(self) -> Dict[str, Any]:
        return self.get_section('file_states')

    @file_states.setter
    def file_states(self, value: Dict[str, Any]):
        self.set_section('file_states', value)

    def get_file_state(self, file_id: str) -> Dict[str, Any]:
        return self.file_states.get(file_id, {})

    def set_file_state(self, file_id: str, state: Dict[str, Any]) -> None:
        all_states = self._data.setdefault('file_states', {})
        all_states[file_id] = copy.deepcopy(state)
        self.save()

    @property
    def peaks(self) -> Dict[str, Any]:
        return self.get_section('peaks')

    @peaks.setter
    def peaks(self, value: Dict[str, Any]):
        self.set_section('peaks', value)

    @property
    def calibrations(self) -> Dict[str, Any]:
        return self.get_section('calibrations')

    @calibrations.setter
    def calibrations(self, value: Dict[str, Any]):
        self.set_section('calibrations', value)

    @property
    def integration_settings(self) -> Dict[str, Any]:
        return self.get_section('integration_settings')

    @integration_settings.setter
    def integration_settings(self, value: Dict[str, Any]):
        self.set_section('integration_settings', value)

    @property
    def shared_state(self) -> Dict[str, Any]:
        return self.get_section('shared_state')

    @shared_state.setter
    def shared_state(self, value: Dict[str, Any]):
        self.set_section('shared_state', value)

    # -- Project metadata ---------------------------------------------------

    @property
    def metadata(self) -> Dict[str, Any]:
        return self.get_section('project_metadata')

    def update_metadata(self, **kwargs) -> None:
        meta = self._data.setdefault('project_metadata', {})
        meta.update(kwargs)
        meta['last_saved'] = datetime.now().isoformat()
        self.save()

    # -- Full project export/import -----------------------------------------

    def export_project(self) -> str:
        """Export entire project state as JSON string."""
        export = copy.deepcopy(self._data)
        export.setdefault('project_metadata', {})['exported_at'] = datetime.now().isoformat()
        return json.dumps(export, indent=2, default=str)

    def import_project(self, json_str: str) -> None:
        """Replace current state with imported project data."""
        data = json.loads(json_str)
        self._data = data
        self.save()
        log.info("Imported project state")

    # -- Cleanup ------------------------------------------------------------

    def clear(self) -> None:
        """Reset all persisted state."""
        self._data = {}
        if not self._enabled:
            try:
                if os.path.exists(self._state_file):
                    os.remove(self._state_file)
            except OSError:
                pass
            return
        self.save()

    def remove_file(self, file_id: str) -> None:
        """Remove all state associated with a file."""
        for section in ['file_states', 'peaks', 'integration_settings']:
            if section in self._data and file_id in self._data[section]:
                del self._data[section][file_id]
        self.save()
