# Session files (`.gecko`)

Engine: `src/services/session_service.py` (no Dash imports). Tests: `tests/test_session_service.py`,
`tests/test_session_real_data.py`. Status: **engine done, GUI (Save / Open buttons, autosave timer,
"restore last session?") pending** and meant to be built on the API below.

A session is a project file the user can reopen months later and keep working in: same samples, same peaks,
same calibrations, same names, same figure settings. It is also the state an AI agent can load, change and save.

## Principles

1. **Save inputs and parameters, never the figure.** The original instrument file bytes (or name + size +
   SHA-256 + path for very large sets) and every user decision are stored. Parsing, bundling and figures are
   recomputed on load by the normal ingestion pipeline. No Plotly figure JSON is ever stored, so a session
   benefits from later parser/plot fixes and stays small.
2. **Ids are preserved.** Bundles and components get uuid4 ids at ingest and everything references them
   (peaks, calibrations, `file_ui_state`, visibility, group overrides, PDA channels, analysis history, plot-tab
   state in the browser). Restore re-ingests, then re-keys the fresh objects to the *saved* ids, so nothing
   detaches (see "ID remapping").
3. **Replace, never merge.** `restore_session` empties the workspace (in place: callbacks keep their service
   objects) and rebuilds it from the file.
4. **Never crash on partial data.** Missing originals, parser differences and hash mismatches are reported in the
   `SessionReport`; everything else is restored.

## File layout

A ZIP (deflate) with extension `.gecko`:

| Entry | Content |
|-------|---------|
| `manifest.json` | `format` (`"geckoplotter-session"`), `schema_version` (int), `app` (name, version, python/numpy/pandas/scipy/plotly/dash versions), `created_at`, `saved_at` (UTC ISO), `project_name`, `counts` (bundles, components, peaks, calibrations, files, edited_tables), `samples` (bundle names), `raw_embedded`, `raw_limit_bytes`, `files` (see below), `tables`, `has_client_state`, `notes`. Human-readable (indented). |
| `state.json` | All server-side state (see "What is saved"). Compact JSON. |
| `client_state.json` | Opaque dict from the GUI layer. The engine stores it and hands it back. |
| `raw/<sha256>/<original name>` | Original instrument files, deduplicated by SHA-256. Only when embedded. |
| `edited/<component id>.csv` | Table of a component the user changed after import (see below). |
| `tables/<component id>.csv` | Table of a component that cannot be rebuilt from a file (see below). |

`manifest.files[]` entries: `name`, `size`, `sha256`, `embedded` (bool), `path` (zip path or null),
`original_path` (path the file was loaded from, or null; see "Large files").

Writing: `save_session` writes a temp file in the target folder, fsyncs and `os.replace`s it, so a crash or full
disk never damages an existing session. `.gecko` is appended when the path has no extension.

## What is saved (`state.json`)

* `bundles[]`: id, display name (renames), bundle type, **recipe**, source files, component order and per
  component: id, role, original filename, kind, `parsed_sha256` (hash of the table as parsed at import),
  `imported_at`, column roles, metadata overrides (anything that differs from the freshly parsed metadata:
  `display_name`, `sample_name`, wavelength, filled wells, source pointers), and for edited tables the dtypes.
* `group_overrides`, `visibility_state`, `collapse_state`, `file_ui_state`, `_shared_plot_settings`
  (`shared_plot_settings`), `analysis_history`, `analysis_plot_settings`, `analysis_previous` (so the first
  analysis event after a restore does not log a bogus "everything changed"), `hidden_sample_channels`,
  `channel_combine_modes`.
* `peaks`: `PeakService.serialize()` and `deserialize()`. Complete, including deconvolution fields
  (`deconv_group`, `fit_params`, colours, names, labels, grouping), manual baseline geometry
  (`poly_x/poly_y/p_line/q1/q2`, tuples restored as tuples), colour bookkeeping, the palette, and the set of
  files whose *instrument peaks were already imported*. The last one is what stops restore from importing
  instrument peaks over the saved ones; restore never calls the auto-import.
* `calibrations`: `CalibrationService.serialize()`; `integration_settings`: `IntegrationService.serialize()`.
* `lcms_eic_overlays`: only the parameters (m/z, tolerance); the EIC arrays are recomputed on restore.

### Component kinds and recipes

* **ingested** (default): rebuilt by re-ingesting the saved original file. Fresh components are matched to saved
  ones by (original filename, role, SHA-256 of the parsed table); if a parser changed, by (filename, role) in
  order, with a warning. Fresh components that were not saved (the user had removed that channel) are dropped;
  their raw bytes / PDA matrix / instrument payload move to a surviving sibling exactly as the app does when a
  channel is removed.
* **pda_extracted**: a wavelength chromatogram the user extracted from a PDA matrix. Recreated with
  `pda_service.add_pda_chromatogram` from the saved wavelength and then given its saved id.
* **frame** (bundle recipe `"frame"`): a bundle that cannot be re-ingested (made by the app itself, e.g. an
  extracted mass spectrum, or without any original file). Stored as table + roles + category + identity +
  light metadata; large array metadata is not stored (listed in `manifest.notes`).
* **Edited tables**: a component whose current table differs from its parsed import (hash of the current CSV vs
  `imported_csv`, the same comparison the research package uses) is stored in `edited/<id>.csv` and applied after
  re-ingest (dtypes restored; a warning if the table does not reproduce bit for bit). The *unmodified* parsed
  import is kept as `imported_csv` after restore, so provenance and "is this edited?" stay correct.

## ID remapping

`DataStore.rekey_bundle(bundle_id, new_bundle_id=None, component_ids=None)` re-keys a loaded bundle and updates
`_bundles` (order kept), `_component_index`, `_file_index` (hence `loaded_data`), `visibility_state`,
`collapse_state`, `file_ui_state` (incl. inner `file_id`), `group_overrides`, `lcms_eic_overlays`,
hidden-channel masks, peaks (`PeakService.rekey_files`) and the `pda_source_id` / `source_file_id` pointers inside
component metadata. Keys of the form `"<id>|<well>"` follow their id. It validates before changing anything and
raises `KeyError` / `ValueError` on unknown bundles or id clashes.

Restore ingests, calls `add_bundle` (which records the fresh `imported_csv`), then re-keys to the saved ids. Final
ids therefore equal saved ids and the saved state and the browser's `client_state` stay valid unchanged. If a
re-key ever fails (id clash) the engine keeps the new id, warns, records the pair in `SessionReport.id_map`
and rewrites the saved state *and* `client_state` with `remap_ids(obj, mapping)` (dict keys, string values and,
for ids of 8+ characters, substrings, so `tab-lcms_ms_..._<id>` and `id:<id>:name` follow). `remap_ids` is public
for GUI/agent use.

## Large files and relocation

* Default: originals are embedded (deflate level 4, deduplicated by SHA-256).
* If the unique originals total more than `raw_limit_bytes` (default 400 000 000) or `embed_raw=False`, nothing
  is embedded; the manifest keeps name, size, SHA-256 and the original path (`original_path`, from the
  `source_paths` argument of `build_session`/`save_session`; the browser upload path only knows bytes, so the
  GUI/agent should pass paths when it has them). The reason is logged in `manifest.notes`.
* On restore a missing external file is searched at: the stored path; each `search_dirs` folder and one level of
  its sub-folders; the session file's own folder (and its sub-folders); finally `relocate(file_entry) -> path|None`
  (`file_entry` = the manifest dict: name, size, sha256, original_path). Candidates with a matching SHA-256
  win. The tree is never walked recursively.
* SHA-256 is **always verified** (embedded and external). A mismatch is a warning ("changed or damaged") and the
  data is used anyway.
* Still missing: listed in `report.missing_files` (name, size, sha256, original_path, searched, bundles). The
  samples that depended on it are not restored, their ids are in `report.missing_ids`, and saved state that
  belongs only to them (peaks, visibility, file UI state) is dropped. Everything else is restored.

## Schema versions and migrations

* `SCHEMA_VERSION = 1`, stored as integer `schema_version` in the manifest (and `state.json`).
* **Policy:** any change to the meaning or layout of manifest/state bumps the integer and ships a migration. Adding
  an optional field that old readers can ignore and that has a safe default does not require a bump.
* `MIGRATIONS = {from_version: fn}`. `fn(session)` receives `{'manifest', 'state', 'client_state'}` (decoded
  dicts) and upgrades it by exactly one version; `migrate_session` applies the steps in order and stamps the new
  version. A missing step raises `SessionFormatError`. Migrations must not need the original files.
* A session from a **newer** schema raises `SessionVersionError` (a `ValueError`) with a plain message ("This
  session was saved by a newer version of GeckoPlotter ... Please update GeckoPlotter to open it. The file has
  not been changed."). The current workspace is untouched. `inspect_session` does not raise for it: it returns
  `info.compatible = False` and `info.problem`.
* Files are fully validated (zip, manifest, version, JSON) **before** the workspace is reset, so a bad or too-new
  file never destroys the current work.

## API (`services.session_service`)

```python
SCHEMA_VERSION = 1
MIGRATIONS: dict[int, Callable[[dict], dict]]

build_session(store, client_state=None, *, project_name=None, embed_raw=True,
              raw_limit_bytes=400_000_000, source_paths=None) -> bytes
save_session(store, path, client_state=None, *, project_name=None, embed_raw=True,
             raw_limit_bytes=400_000_000, source_paths=None) -> Path        # atomic
inspect_session(data_or_path) -> SessionInfo                                # manifest only
restore_session(store, data_or_path, *, search_dirs=(), relocate=None) -> SessionReport
remap_ids(obj, mapping) -> obj
migrate_session(session, *, target=None, migrations=None) -> session
autosave_dir(create=True) -> Path          # $GECKO_AUTOSAVE_DIR or ~/Documents/GeckoPlotter/Autosave
latest_autosave() -> Path | None           # newest *.gecko, never creates the folder
save_autosave(store, client_state=None, *, keep=5, **build_kwargs) -> Path
class SessionFormatError(ValueError); class SessionVersionError(SessionFormatError)
```

`data_or_path` is bytes, a path, or a binary file object.

`SessionInfo`: `path, project_name, saved_at, created_at, schema_version, app_version, counts, files, samples,
raw_embedded, has_client_state, size_bytes, compatible, problem, notes`.

`SessionReport`: `ok` (nothing lost: no errors and no missing files; warnings alone keep it True), `warnings`,
`errors`, `missing_files`, `missing_ids`, `client_state` (remapped if needed), `info`, `restored` (counts of
bundles, components, peaks, calibrations, edited_tables), `id_map` (only ids that could not be kept).

Side effects on the store: `save_session` remembers `store.session_meta` (`project_name`, `created_at`,
`saved_at`, `path`) so Save-again keeps name and creation time; `restore_session` sets it from the file.
`save_autosave` does not set `path`.

### Notes for the GUI layer

* Dash stores (plot-tabs, active-plot-tab, active-file, hidden-files, file-order, zoom-state, per-tab memory,
  current-plot-settings, custom figures ...) belong in `client_state`; after `restore_session`, write
  `report.client_state` back into the stores and re-render. Ids inside stay valid.
* The workspace is wiped by `start_empty_workspace_on_reload` on every layout request. Offer "restore last
  session?" *after* that point (e.g. from a button/interval), not before.
* Show `report.warnings`, `report.errors` and, for `missing_files`, a "locate file" step that calls
  `restore_session(..., relocate=...)` or `search_dirs=[...]` again.
* Autosave with `embed_raw=False` is cheap for big sets but then needs original paths (`source_paths`);
  otherwise autosave embeds and costs one compression of the originals per save (about 0.4 s for 35 MB).

## Not saved

Undo histories (file-removal undo, peak undo/redo), render caches and EIC arrays (recomputed), temporary upload
files, the Plotly figure, Dash component state outside `client_state`, `store.project` (disabled persistence),
metadata arrays of app-made "frame" tables, the history of the *session file itself* (only the last save).
The parsed table of an app-made frame component is stored as of save time (its earlier unmodified state is not
kept).

## Using a session from an agent / MCP

```python
from services.data_store import DataStore
from services import session_service as ss

store = DataStore()
info = ss.inspect_session("project.gecko")          # cheap: names, counts, files, compatibility
report = ss.restore_session(store, "project.gecko", search_dirs=["/data/raw"])
assert report.ok, report.warnings + report.errors
# ... work through store.peak_service / calibration_service / integration_service ...
ss.save_session(store, "project.gecko", report.client_state)
```

Everything needed (ids, peaks, calibrations) is in plain services; `state.json` is plain JSON that can also be
read directly (peaks keyed by peak-owner id). Remember `restore_session` replaces the store's content. Python
`json` is used with NaN allowed (non-finite floats are written as `NaN`).

## FAIR research package

`build_research_package` could embed the session as `session/project.gecko` (originals are already in the
package, so build it with `embed_raw=False` and `source_paths` pointing at the package-relative
`raw_data/originals/...` files, and have `restore_session` accept the package folder via `search_dirs`), and
accept a session through the same `restore_session` for "re-run this analysis". The manifest's SHA-256 list is the
same hash the package manifest records, so the two can be cross-checked. Nothing in the package format needs to
change for that; it is intentionally not wired yet.
