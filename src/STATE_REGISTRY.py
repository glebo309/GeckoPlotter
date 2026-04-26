"""
STATE_REGISTRY — Single source of truth for GeckoPlotter V2 state hierarchy.

GeckoPlotter V2 manages state across three domains:

1. RUNTIME DATA STATE (server-side, in DataManager)
   Parsed file data, bundles, visibility/collapse toggles.  Lives entirely
   in the DataManager singleton on the server; never serialised to dcc.Store.

2. PER-FILE UI STATE (hybrid: dcc.Store + DataManager.file_ui_state)
   Each loaded file has its own snapshot of UI settings (view mode, active
   tab, plot settings, pub selections, etc.).  The active file's state is
   broadcast to individual dcc.Stores; on file switch the stores are
   re-populated from DataManager.file_ui_state[file_id].

3. SHARED ANALYSIS STATE (dcc.Store, NOT per-file)
   Cross-file data: the master file list, shared axis selections for the
   peak-analysis / across-samples tabs, and mirrors of analysis DataTables.

A fourth pseudo-domain, UI-ONLY, covers layout-level components and
clientside-callback triggers that are NOT backed by dcc.Store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Domain enum
# ---------------------------------------------------------------------------

class StateDomain(str, Enum):
    """The three (plus one) state domains in the app."""
    RUNTIME       = "runtime"        # server-side only (DataManager attrs)
    PER_FILE      = "per_file"       # hybrid dcc.Store + DataManager
    SHARED        = "shared"         # dcc.Store, not per-file
    UI_ONLY       = "ui_only"        # layout components / clientside triggers


# ---------------------------------------------------------------------------
# Store ID constants — use these instead of raw strings
# ---------------------------------------------------------------------------

class StoreID:
    """Canonical dcc.Store id strings used throughout the app."""

    # -- Per-file UI state ---------------------------------------------------
    ACTIVE_FILE       = "active-file"
    FILE_UI_STATE     = "file-ui-state"
    ACTIVE_TAB        = "active-tab"
    VIEW_MODE         = "view-mode"
    TOOLBOX_TAB       = "toolbox-tab"
    ACTIVE_PLOT_CONTEXT   = "active-plot-context"
    CURRENT_PLOT_SETTINGS = "current-plot-settings"
    DEV_SETTINGS      = "dev-settings"
    PUB_DATA_STORE    = "pub-data-store"
    PUB_SELECTIONS    = "pub-selections"
    PUB_PLOT_FIGURE   = "pub-plot-figure"
    PUB_PLOT_TRIGGER  = "pub-plot-trigger"

    # -- Shared analysis state -----------------------------------------------
    LOADED_FILES             = "loaded-files"
    PEAK_SHARED_SELECTIONS   = "peak-shared-selections"
    CROSS_SHARED_SELECTIONS  = "cross-shared-selections"
    PEAK_TABLE_STORE         = "peak-table-store"
    CROSS_SAMPLE_TABLE_STORE = "cross-sample-table-store"

    # -- UI-only (layout components, no dcc.Store backing) -------------------
    RESIZE_STATE        = "resize-state"
    AUTO_SELECT_TRIGGER = "auto-select-trigger"
    ACTIVE_SELECTOR     = "active-selector"
    Y1_SERIES_COUNT     = "y1-series-count"
    RESIZE_INIT_TRIGGER = "resize-init-trigger"
    PLOT_EXPORT_DATA    = "plot-export-data"


# ---------------------------------------------------------------------------
# Store metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StoreEntry:
    """Metadata for a single dcc.Store (or layout-level state component)."""
    domain: StateDomain
    default: Any
    description: str
    persisted_per_file: bool = False   # True if saved in DataManager.file_ui_state


# Default selections structure (mirrors axis_mapper.get_empty_selections)
_EMPTY_SELECTIONS: Dict[str, Any] = {
    "x":  {"data": {"row_ids": [], "column_id": None}},
    "y1": {
        "series": [{"row_ids": [], "column_id": None}],
        "error":  {"row_ids": [], "column_id": None},
    },
    "y2": {
        "data":  {"row_ids": [], "column_id": None},
        "error": {"row_ids": [], "column_id": None},
    },
    "y2_enabled": False,
}


STORE_REGISTRY: Dict[str, StoreEntry] = {

    # ── Per-file UI state ──────────────────────────────────────────────
    StoreID.ACTIVE_FILE: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=None,
        description="Currently selected file ID.",
    ),
    StoreID.FILE_UI_STATE: StoreEntry(
        domain=StateDomain.PER_FILE,
        default={},
        description="Full snapshot of the active file's UI state dict.",
    ),
    StoreID.ACTIVE_TAB: StoreEntry(
        domain=StateDomain.PER_FILE,
        default="data-overview",
        description="Current content tab (data-overview | peak-analysis | across-samples | metadata | calibration).",
        persisted_per_file=True,
    ),
    StoreID.VIEW_MODE: StoreEntry(
        domain=StateDomain.PER_FILE,
        default="raw",
        description="Data view mode: 'raw' or 'processed'.",
        persisted_per_file=True,
    ),
    StoreID.TOOLBOX_TAB: StoreEntry(
        domain=StateDomain.PER_FILE,
        default="pub-plotter",
        description="Current toolbox panel (pub-plotter | plot-tools | integration | export).",
        persisted_per_file=True,
    ),
    StoreID.ACTIVE_PLOT_CONTEXT: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=None,
        description="Context key for the currently visible plot (e.g. 'file:<id>' or 'shared:peak-analysis').",
    ),
    StoreID.CURRENT_PLOT_SETTINGS: StoreEntry(
        domain=StateDomain.PER_FILE,
        default={},
        description="Single runtime source of truth for the visible plot's settings.",
        persisted_per_file=True,
    ),
    StoreID.DEV_SETTINGS: StoreEntry(
        domain=StateDomain.PER_FILE,
        default={"show": False},
        description="Developer panel state.",
        persisted_per_file=True,
    ),
    StoreID.PUB_DATA_STORE: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=None,
        description="JSON (split-orient) of the active publication table data.",
    ),
    StoreID.PUB_SELECTIONS: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=_EMPTY_SELECTIONS,
        description="Active axis selections for the publication plot.",
        persisted_per_file=True,
    ),
    StoreID.PUB_PLOT_FIGURE: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=None,
        description="Cached Plotly figure dict for the publication plot.",
    ),
    StoreID.PUB_PLOT_TRIGGER: StoreEntry(
        domain=StateDomain.PER_FILE,
        default=None,
        description="Timestamp trigger for publication plot re-render.",
    ),

    # ── Shared analysis state ──────────────────────────────────────────
    StoreID.LOADED_FILES: StoreEntry(
        domain=StateDomain.SHARED,
        default=[],
        description="List of all file records (metadata dicts).",
    ),
    StoreID.PEAK_SHARED_SELECTIONS: StoreEntry(
        domain=StateDomain.SHARED,
        default={},
        description="Axis selections for the peak-analysis tab.",
    ),
    StoreID.CROSS_SHARED_SELECTIONS: StoreEntry(
        domain=StateDomain.SHARED,
        default={},
        description="Axis selections for the across-samples tab.",
    ),
    StoreID.PEAK_TABLE_STORE: StoreEntry(
        domain=StateDomain.SHARED,
        default=None,
        description="Mirror of peak-table DataTable data (JSON split).",
    ),
    StoreID.CROSS_SAMPLE_TABLE_STORE: StoreEntry(
        domain=StateDomain.SHARED,
        default=None,
        description="Mirror of cross-sample-table DataTable data (JSON split).",
    ),

    # ── UI-only state ──────────────────────────────────────────────────
    StoreID.RESIZE_STATE: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default={"mainSplit": 30, "leftSplit": 50, "rightSplit": 60},
        description="Panel split positions (dcc.Store in layout, consumed by clientside JS).",
    ),
    StoreID.AUTO_SELECT_TRIGGER: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default=None,
        description="One-shot trigger for auto-selection after file load.",
    ),
    StoreID.ACTIVE_SELECTOR: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default=None,
        description="Which axis button the user clicked (for cell-to-axis mapping).",
    ),
    StoreID.Y1_SERIES_COUNT: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default=1,
        description="Number of Y1 series slots in the axis mapper.",
    ),
    StoreID.RESIZE_INIT_TRIGGER: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default=None,
        description="Dummy output consumed by clientside resize callbacks.",
    ),
    StoreID.PLOT_EXPORT_DATA: StoreEntry(
        domain=StateDomain.UI_ONLY,
        default=None,
        description="Serialised plot data for the export panel.",
    ),
}


# ---------------------------------------------------------------------------
# Callback ownership map
# ---------------------------------------------------------------------------
# Each store ID maps to the callback module(s) that Output() to it.
# "app" refers to clientside callbacks registered in app.py.

STATE_OWNERS: Dict[str, List[str]] = {
    # Per-file
    StoreID.ACTIVE_FILE:      ["upload_callbacks", "file_tree_callbacks", "viz_callbacks"],
    StoreID.FILE_UI_STATE:    ["context_callbacks", "publication_callbacks"],
    StoreID.ACTIVE_TAB:       ["context_callbacks"],
    StoreID.VIEW_MODE:        ["context_callbacks", "viz_callbacks", "upload_callbacks"],
    StoreID.TOOLBOX_TAB:      ["context_callbacks"],
    StoreID.ACTIVE_PLOT_CONTEXT:   ["plot_settings_callbacks"],
    StoreID.CURRENT_PLOT_SETTINGS: ["plot_settings_callbacks"],
    StoreID.DEV_SETTINGS:     ["context_callbacks"],
    StoreID.PUB_DATA_STORE:   ["upload_callbacks", "file_tree_callbacks", "viz_callbacks",
                               "publication_callbacks"],
    StoreID.PUB_SELECTIONS:   ["file_tree_callbacks", "upload_callbacks",
                               "publication_callbacks"],
    StoreID.PUB_PLOT_FIGURE:  ["publication_callbacks"],
    StoreID.PUB_PLOT_TRIGGER: ["publication_callbacks"],

    # Shared
    StoreID.LOADED_FILES:             ["upload_callbacks", "file_tree_callbacks"],
    StoreID.PEAK_SHARED_SELECTIONS:   ["publication_callbacks"],
    StoreID.CROSS_SHARED_SELECTIONS:  ["publication_callbacks"],
    StoreID.PEAK_TABLE_STORE:         ["tab_callbacks"],
    StoreID.CROSS_SAMPLE_TABLE_STORE: ["tab_callbacks"],

    # UI-only
    StoreID.RESIZE_STATE:        ["app"],
    StoreID.AUTO_SELECT_TRIGGER: [],
    StoreID.ACTIVE_SELECTOR:     ["publication_callbacks"],
    StoreID.Y1_SERIES_COUNT:     ["publication_callbacks"],
    StoreID.RESIZE_INIT_TRIGGER: ["app"],
    StoreID.PLOT_EXPORT_DATA:    ["publication_callbacks"],
}


# ---------------------------------------------------------------------------
# Runtime-only entries (DataManager attributes, NOT dcc.Stores)
# ---------------------------------------------------------------------------

RUNTIME_STATE: Dict[str, str] = {
    "DataManager.loaded_data":      "Parsed file data keyed by file_id.",
    "DataManager.bundle_manager":   "Chromeleon HPLC bundle tracking.",
    "DataManager.lcms_bundles":     "LC-MS bundle tracking.",
    "DataManager.visibility_state": "File/well visibility toggles (lazily initialised).",
    "DataManager.collapse_state":   "File tree expansion state (lazily initialised).",
    "DataManager.file_ui_state":    "Server-side per-file UI state dicts.",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_store_domain(store_id: str) -> Optional[StateDomain]:
    """Return the domain for a given store ID, or None if unregistered."""
    entry = STORE_REGISTRY.get(store_id)
    return entry.domain if entry else None


def get_store_owner(store_id: str) -> List[str]:
    """Return the list of callback modules that are allowed to write to *store_id*."""
    return STATE_OWNERS.get(store_id, [])


def get_store_default(store_id: str) -> Any:
    """Return the registered default value for a store, or None if unknown."""
    entry = STORE_REGISTRY.get(store_id)
    return entry.default if entry else None


def get_persisted_keys() -> List[str]:
    """Return store IDs whose values are persisted inside DataManager.file_ui_state."""
    return [
        sid for sid, entry in STORE_REGISTRY.items()
        if entry.persisted_per_file
    ]


def validate_output(store_id: str, caller_module: str) -> bool:
    """Check whether *caller_module* is a registered owner of *store_id*.

    Useful as a development-time assertion:

        assert validate_output('view-mode', 'context_callbacks'), \
            "context_callbacks is not a registered owner of view-mode"
    """
    owners = STATE_OWNERS.get(store_id)
    if owners is None:
        return False
    return caller_module in owners
