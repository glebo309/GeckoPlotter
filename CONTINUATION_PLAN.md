# GeckoPlotter V2 Continuation Plan

_Updated 2026-03-22_

## Canonical Codebase

Continue development only in `GeckoPlotter_V2/`.

Archive/reference:
- `GeckoPlotter_V2 2/` and `.zip` — old backups
- `DashPlotter/` — legacy monolithic app, useful for reader/plotting/peak-integration reference
- `archive/` within V2 — old planning docs, broken callbacks, playground scripts

## Current State (March 2026)

### What works

- **Entry point**: `python app.py` starts Dash on port 8052
- **Four-panel layout**: file tree, main plot, toolbox (bottom-left), analysis tabs (bottom-right)
- **File upload and tree**: upload chromatograms, UV-Vis CSVs, LCMS CDFs; file tree renders correctly
- **Bundle detection**: Chromeleon (.txt + .cdf) and LCMS bundles auto-grouped
- **Readers**: chromatogram, generic CSV, UV-Vis CSV, LCMS CDF all functional
- **Publication plotter**: axis mapper UI, cell/column selection, per-file state save/restore, plot generation
- **Per-file state**: `context_callbacks.py` loads/saves unified state (view mode, tabs, plot settings, selections) per file via `DataManager.get_file_state()` / `save_file_state()`
- **Shared analysis state**: peak-analysis and across-samples now have separate shared selection stores, avoiding cross-tab axis leakage
- **Data table**: `pub-table` DataTable with cell selection, column selection, add row/column, transpose
- **Architectural foundation**: state registry, peak/calibration/plot-settings/integration/export/LCMS/persistence services exist and import cleanly
- **Toolbox UI**: Plot Tools, Integration, and Export panels are present in the layout with real controls

### What was just fixed (this session)

- **`pub-table` crash**: callbacks referenced `pub-table` before it existed in the layout. Fixed by adding an empty hidden DataTable with `id='pub-table'` to the initial `table-editor-container` so Dash callbacks always have a valid target.
- **Folder cleanup**: removed outdated ChatGPT session docs (SESSION_SUMMARY, TESTING_GUIDE, PROJECT_STATUS_SUMMARY), moved old planning docs to `archive/`, cleared `__pycache__`
- **Shared selection bug**: peak-analysis and across-samples no longer reuse the same axis-selection store; peak results keep `RT (min)` while across-samples defaults to `Sample`

### What is incomplete or fragile

- **`table_editor_callbacks.py`** is a no-op placeholder — table editor logic lives in `publication_callbacks.py` and `viz_callbacks.py` directly
- **Analysis mode**: "Analysis Plot" view mode shows placeholder, no real derived output
- **Toolbox wiring**: Plot Tools, Integration, and Export panels exist, but most controls are not yet connected end-to-end to the new services
- **Peak analysis / Across samples tabs**: work for Chromeleon bundles but still rely on older callback logic instead of `IntegrationService` / `PeakService`
- **Calibration tab**: placeholder only
- **Persistence split**: `ProjectPersistence` exists, but runtime persistence is still partly owned directly by `DataManager`

## Architecture

```
app.py                          # Layout + callback registration
src/
  STATE_REGISTRY.py             # Canonical dcc.Store registry, domains, owners
  callbacks/
    upload_callbacks.py         # File upload + clear
    viz_callbacks.py            # File selection → plot + table + metadata
    file_tree_callbacks.py      # File tree rendering
    publication_callbacks.py    # Pub plotter: selections, highlighting, plot
    context_callbacks.py        # Per-file UI state load/save
    tab_callbacks.py            # Analysis tab content (peak, across-samples)
    table_editor_callbacks.py   # No-op placeholder
  components/
    axis_mapper.py              # Publication plotter UI controls
    data_table_editor.py        # DataTable factory + transpose
    publication_plot.py         # Plotly figure generation
  services/
    storage_manager.py          # DataManager: file cache, state, pub memory
    plot_manager.py             # Plot dispatch (chromatogram, UV-Vis, LCMS)
    bundle_manager.py           # Bundle detection and grouping
    peak_service.py             # Peak model, grouping, detection helpers
    calibration_service.py      # Calibration models, fitting, prediction, figures
    plot_settings_service.py    # Plot settings model + figure application
    integration_service.py      # Smoothing, baseline, integration settings
    export_service.py           # Table/figure/session export workflows
    lcms_service.py             # TIC/EIC extraction, spectrum helpers
    persistence.py              # Project/session persistence layer
    table_manager.py            # Table export/support utilities
    readers/                    # File format readers
```

**State flow**:
- `active-file` → `context_callbacks.load_file_ui_state()` → broadcasts active per-file state into `file-ui-state`, `view-mode`, `active-tab`, `toolbox-tab`, `plot-settings`, `dev-settings`
- shared analysis tabs route through tab-specific shared stores (`peak-shared-selections`, `cross-shared-selections`) plus `shared-plot-settings`
- runtime scientific services should be owned centrally and injected into callbacks through `DataManager` rather than recreated ad hoc

## Completed Phases

### Phase 0 — Cleanup and Stabilization ✓
- Single canonical codebase identified
- Backup artifacts moved to `archive/`
- App starts cleanly, imports pass
- README and plan docs cleaned up

### Phase 1 — Unified Per-File State ✓
- `DataManager` has `build_default_file_state()`, `get_file_state()`, `save_file_state()`
- `file-ui-state` dcc.Store exists
- `context_callbacks.py` loads/saves state on file switch
- Publication selections persist per file
- Shared analysis tabs now keep separate selection stores

## Next Phases

### Phase 2 — Stabilize Publication Plotter

The pub plotter is the most complex and most used feature. Before adding new features, ensure it works reliably.

Tasks:
- Verify the full workflow: upload CSV → select file → click selector button → select cells/columns → see highlights → generate plot
- Fix any remaining callback timing issues (the `pub-table` fix should have resolved the main one)
- Remove excessive debug print statements once workflow is confirmed stable
- Consider whether `table_editor_callbacks.py` should be removed or given a real purpose

### Phase 3 — Service Integration

Goal: connect the new architecture foundation to the running app.

Tasks:
- Make `DataManager` the owner/container for `PeakService`, `IntegrationService`, `CalibrationService`, `PlotSettingsService`, `ExportService`, `LCMSService`, and `ProjectPersistence`
- Replace direct legacy persistence flow in `storage_manager.py` with the persistence service
- Route shared and per-file callback state through the registry/service boundaries consistently
- Remove duplicated logic where callbacks currently reimplement behavior that now belongs in services

### Phase 4 — Analysis Mode and Scientific Pipeline

Goal: make the "Analysis Plot" view mode and analysis tabs produce real output using the new services.

Tasks:
- Wire Data Overview tab to show the table editor for the active file's data
- Replace old peak-analysis / across-samples table-building paths with `IntegrationService` + `PeakService`
- Implement analysis mode: processed/derived plots (e.g., corrected signal, baseline, peak comparison, calibration curves)
- Port useful logic from `archive/playgrounds/table_playground.py` only if it still adds value after the service migration

### Phase 5 — Toolbox Activation

Goal: connect the existing toolbox panels to the new services and state model.

Tasks:
- Plot Tools: apply labels, style, legend, themes, axis ranges, layout options through `PlotSettingsService`
- Integration: wire smoothing, baseline, detection, clear/detect actions through `IntegrationService`
- Export: connect figure/data/session export controls through `ExportService` and `ProjectPersistence`

All should read/write the correct state domain: per-file for file-specific work, shared for shared analysis tabs.

### Phase 6 — Calibration and Advanced Analysis

Goal: rebuild the richer scientific workflow on top of the stabilized architecture.

Tasks:
- Unhide and implement the calibration tab using `CalibrationService`
- Add sample-level peak property editing and richer across-sample comparison
- Integrate LC-MS-specific advanced tools using `LCMSService`

### Phase 7 — Regression Pass

Validate end-to-end workflows:
- Upload → select → inspect metadata → adjust settings → switch files → confirm state restores
- Chromatogram bundles, UV-Vis CSVs, LCMS datasets
- Publication plot generation and export
- Peak detection, across-sample comparison, calibration, and session persistence

### Phase 8 — FAIR Data Package Integration

**Strategic Goal**: Transform GeckoPlotter from a plotting tool into a **plot-to-publication data package pipeline** that automatically generates FAIR-compliant, Zenodo-ready datasets.

**Why this matters**:
- Research data management (RDM) compliance is mandatory for NCCR Catalysis, SNSF-funded projects, and most modern publications
- Current workflow: researchers plot data → manually assemble datasets later → often lose provenance/context → struggle with FAIR requirements
- GeckoPlotter already captures the critical provenance chain (which files → which processing → which figures) but currently discards it at export
- By embedding FAIR compliance into the plotting workflow, we eliminate the "dataset preparation as afterthought" problem
- Users get publication-quality plots AND publication-ready data packages from the same tool

**The core insight**: GeckoPlotter naturally knows:
- Which raw files were uploaded (file tree + DataManager)
- What selections/transformations were applied (per-file state)
- Which data generated which figure (publication_callbacks selections)
- File metadata (type, size, dates, format)

This is exactly what FAIR data packages require — we just need to capture and export it systematically.

**Target output**: A Zenodo-ready ZIP package containing:
```
DatasetFor_[PaperTitle]/
├── README.md                    # Auto-generated with figure-to-file mapping
├── experiment_metadata.csv      # Sample IDs, conditions, operators, dates
├── dataset_manifest.csv         # File inventory with descriptions
├── zenodo_metadata.json         # Pre-filled Zenodo upload metadata
├── figures/
│   ├── Fig1_[description].png
│   ├── Fig1_[description].svg
│   └── Fig1_source_data.csv     # Exact data behind the plot
├── raw_data/
│   └── [original uploaded files, format-converted where needed]
├── processed_data/
│   └── [selected/filtered data as CSV]
└── docs/
    └── methods_notes.md
```

**Architecture additions** (4 new modules):
```
src/
  services/
    fair_package_builder.py    # NEW — assembles ZIP, generates README/manifests
    metadata_manager.py        # NEW — project + per-file metadata store
  callbacks/
    fair_export_callbacks.py   # NEW — FAIR export UI interactions
  components/
    fair_metadata_form.py      # NEW — metadata entry form (sidebar/modal)
```

#### Phase 6a — Project-Level Metadata Store

**Goal**: Capture dataset-level metadata that persists across file switches.

**Why**: Zenodo and FAIR repositories require structured metadata (authors, license, funding, related works). Currently this context doesn't exist in GeckoPlotter — users would have to re-enter it manually during dataset preparation.

**Implementation**:
- New `MetadataManager` class in `src/services/metadata_manager.py`
- Stored via `dcc.Store` at app level (parallel to existing per-file state pattern)
- Accessible via new "Dataset Metadata" tab in toolbox or modal from Export tab

**UI Fields** (maps to Zenodo required fields + NCCR Catalysis curation policy):
- **Paper title** (string)
- **Dataset title** (string, must differ from paper title per NCCR policy)
- **Authors** (list with name + ORCID, at least one ORCID required)
- **Description** (text area, becomes Zenodo description)
- **License** (dropdown: CC-BY-4.0 default per NCCR recommendation, CC0, CC-BY-SA-4.0, MIT, etc.)
- **Funding** (NCCR Phase I checkbox [180544], Phase II checkbox [225147])
- **Related DOIs** (article DOI, other dataset DOIs)
- **Keywords** (tag input)
- **NCCR Acknowledged** (checkbox, auto-inserts acknowledgement text in README)

**Data structure**:
```python
{
    "paper_title": str,
    "dataset_title": str,
    "authors": [{"name": str, "orcid": str}, ...],
    "description": str,
    "license": str,
    "funding": {"nccr_phase_1": bool, "nccr_phase_2": bool, "grant_numbers": [str]},
    "related_dois": [str],
    "keywords": [str],
    "nccr_acknowledged": bool
}
```

**Why this design**: Separates dataset-level context from per-file context. Matches the mental model of "one paper → one dataset package → many files".

#### Phase 6b — Per-File Experimental Metadata

**Goal**: Annotate each uploaded file with experimental context that feeds `experiment_metadata.csv`.

**Why**: FAIR reusability requires knowing what each file represents (sample ID, conditions, replicate number, etc.). Currently files are just names — no semantic metadata. This gap makes datasets hard to interpret later.

**Implementation**:
- Extends existing `DataManager.get_file_state()` / `save_file_state()` with `metadata` dict
- New "Metadata" sub-tab in bottom-right analysis panel (appears when file selected)
- All fields optional — whatever is filled gets exported

**UI Fields per file** (from FAIR_DATA_LAB_GUIDE.md standard metadata):
- **Sample ID** (string)
- **Enzyme** (string)
- **Substrate** (string)
- **Support/Material** (string)
- **Buffer/pH** (string)
- **Temperature** (string)
- **Replicate number** (integer)
- **Operator** (string)
- **Experiment date** (date picker, separate from file upload date)
- **Raw vs Processed** (radio: raw / processed / derived)
- **Figure reference** (string, e.g., "Fig 2a" — links file to figure)
- **Notes** (text area)

**Data structure** (added to per-file state):
```python
file_state["metadata"] = {
    "sample_id": str,
    "enzyme": str,
    "substrate": str,
    "support": str,
    "buffer_ph": str,
    "temperature": str,
    "replicate": int,
    "operator": str,
    "experiment_date": str,  # ISO format
    "data_type": str,  # "raw" | "processed" | "derived"
    "figure_ref": str,
    "notes": str
}
```

**Why this design**: Leverages existing per-file state infrastructure. Zero friction — fields are optional but available when needed. Directly maps to `experiment_metadata.csv` columns.

#### Phase 6c — Figure Registry and Provenance Tracking

**Goal**: Capture the mapping "Figure X was generated from File Y, columns A and B, with config Z".

**Why**: This is the killer feature for FAIR compliance. Reviewers and future researchers need to trace published figures back to source data. Currently this mapping exists only in the user's head. GeckoPlotter already has all the information (in `publication_callbacks.py` selections state) — we just need to persist it.

**Implementation**:
- New `MetadataManager.register_figure()` method
- "Save as Figure" button in publication plotter UI (next to plot generation)
- Figure registry stored at project level alongside project metadata

**Workflow**:
1. User generates publication plot (existing workflow)
2. User clicks "Save as Figure" → modal appears
3. User assigns label (e.g., "Fig1", "Fig2a") and optional description
4. System captures: source file IDs, column selections, row selections, plot config, timestamp
5. Registry entry created

**Data structure**:
```python
figure_registry = {
    "Fig1": {
        "label": "Fig1",
        "description": "Enzyme activity retention over reuse cycles",
        "source_files": [{"file_id": str, "filename": str}],
        "x_selection": {"file_id": str, "column_id": str, "row_ids": [str]},
        "y_selections": [{"file_id": str, "column_id": str, "row_ids": [str], "label": str}],
        "plot_config": {...},  # axis labels, colors, etc.
        "timestamp": str,
        "exported_as": ["Fig1.png", "Fig1.svg", "Fig1_source_data.csv"]
    }
}
```

**Why this design**: Captures full provenance without changing existing plotting workflow. The data already flows through `publication_callbacks.py` — we just add a persistence layer. Enables auto-generation of figure-to-file mapping table in README.

**Auto-generated README section example**:
```markdown
## Figure-to-File Mapping

| Figure | Description | Source Files | Data Columns |
|--------|-------------|--------------|--------------|
| Fig1   | Enzyme activity retention | hplc_reuse_cycles.csv | X: Cycle, Y: Activity (%) |
| Fig2a  | Substrate scope | substrate_screen_raw.csv | X: Substrate, Y: Conversion (%) |
```

#### Phase 6d — FAIR Package Builder and Export

**Goal**: One-click export of complete, Zenodo-ready FAIR data package.

**Why**: Manual dataset assembly is error-prone and time-consuming. Users forget files, mix up versions, write incomplete READMEs. Automating this ensures consistency and compliance.

**Implementation**:
- New `FairPackageBuilder` class in `src/services/fair_package_builder.py`
- Activated from Export toolbox tab (currently placeholder)
- Pre-export compliance checker validates metadata completeness

**Export workflow**:
1. User clicks "Export FAIR Package" button
2. Compliance checker runs (see below)
3. If warnings exist, modal shows issues + option to proceed anyway
4. Package builder assembles ZIP:
   - Creates folder structure
   - Copies raw files → `raw_data/`
   - Exports selected/processed data as CSV → `processed_data/`
   - Exports registered figures as PNG + SVG → `figures/`
   - Exports figure source data as CSV → `figures/[FigX]_source_data.csv`
   - Generates `experiment_metadata.csv` from per-file annotations
   - Generates `dataset_manifest.csv` from file registry
   - Generates `README.md` from project metadata + figure registry
   - Generates `zenodo_metadata.json` for Zenodo upload API
5. ZIP downloaded to user's machine

**Compliance checker** (runs before export):
- ⚠️ **Missing ORCID**: At least one author must have ORCID (required by NCCR policy)
- ⚠️ **Dataset title = Paper title**: Forbidden by NCCR Zenodo curation policy
- ⚠️ **No dataset title**: Required field
- ⚠️ **No license selected**: Required for Zenodo
- ⚠️ **Figures without source data**: Registered figures must have traceable source files
- ⚠️ **Proprietary formats without open equivalents**: Flags `.xlsx` without `.csv`, etc.
- ⚠️ **Missing NCCR acknowledgement**: If NCCR funding selected but acknowledgement not checked
- ⚠️ **No README DOI placeholder**: README should reference the dataset DOI (can be reserved on Zenodo before publication)

**Auto-generated README.md structure** (follows FAIR_DATA_LAB_GUIDE.md template):
```markdown
# [Dataset Title]

**Related Publication**: [Paper Title]  
**Article DOI**: [DOI if available]  
**Dataset DOI**: [Reserved Zenodo DOI or placeholder]

## Authors
- [Name] ([ORCID])
- [Name] ([ORCID])

**Contact**: [First author email from ORCID or manual entry]

## Description
[User-provided description from project metadata]

## Folder Structure
- `README.md` — This file
- `experiment_metadata.csv` — Experimental conditions and sample metadata
- `dataset_manifest.csv` — File inventory with descriptions
- `figures/` — Publication figures and source data
- `raw_data/` — Original instrument/measurement data
- `processed_data/` — Cleaned and processed data tables
- `docs/` — Additional documentation

## Figure-to-File Mapping
[Auto-generated table from figure registry]

## File Formats
[Auto-detected from uploaded files]
- CSV: Comma-separated values (open format)
- PNG/SVG: Figure exports
- [Other formats detected]

## Raw vs Processed Data
- **Raw data** (`raw_data/`): Direct exports from instruments/experiments
- **Processed data** (`processed_data/`): Cleaned, filtered, or aggregated data used for plotting

## Abbreviations
[Extracted from per-file metadata notes if provided]

## License
[Selected license, e.g., CC-BY-4.0]

## Funding
[Auto-generated NCCR acknowledgement if applicable]:
"This dataset was created as part of NCCR Catalysis (grant number [180544/225147]), 
a National Centre of Competence in Research funded by the Swiss National Science Foundation."

## Related Works
[DOIs from project metadata]

## Software
Data visualization and package assembly: GeckoPlotter V2 (https://github.com/[repo])

---
Generated: [Timestamp]  
Dataset DOI: [Zenodo DOI]
```

**zenodo_metadata.json structure** (pre-filled for Zenodo API upload):
```json
{
  "title": "[Dataset Title]",
  "description": "[Description]",
  "creators": [{"name": "[Name]", "orcid": "[ORCID]"}],
  "license": "cc-by-4.0",
  "keywords": ["keyword1", "keyword2"],
  "grants": [{"id": "10.13039/501100001711::180544"}],
  "related_identifiers": [
    {"identifier": "[Article DOI]", "relation": "isSupplementTo", "scheme": "doi"}
  ],
  "communities": [{"identifier": "nccr-catalysis"}]
}
```

**Why this design**: Automates the entire FAIR packaging workflow. Users don't need to know Zenodo metadata schemas, NCCR curation policies, or FAIR principles — the tool enforces them. The compliance checker prevents common mistakes before submission.

#### Phase 8 Implementation Roadmap

**Dependencies**:
- Phase 6a (project metadata): Independent, can start immediately
- Phase 6b (per-file metadata): Depends on stable per-file state (Phase 1 ✓)
- Phase 6c (figure registry): Depends on stable publication plotter (Phase 2)
- Phase 6d (package builder): Depends on 6a + 6b + 6c

**Recommended sequence**:
1. **Phase 2** (stabilize pub plotter) — prerequisite for 6c
2. **Phase 3** (service integration) — ensure FAIR features plug into the real service layer
3. **Phase 4** (analysis pipeline) — can proceed in parallel with 6a + 6b once services are wired
4. **Phase 6a + 6b in parallel** — independent metadata/state additions
5. **Phase 6c** (figure registry) — after Phase 2 stable
6. **Phase 5** (toolbox activation) — Export tab becomes FAIR export home
7. **Phase 6d** (package builder) — ties everything together
8. **Phase 7** (regression) — validate end-to-end including FAIR export

**Estimated complexity**:
- 6a: ~200 lines (metadata form + store)
- 6b: ~150 lines (extends existing per-file state UI)
- 6c: ~250 lines (figure registry + "Save as Figure" UI)
- 6d: ~500 lines (package builder + README generator + compliance checker)
- Total: ~1100 lines across 4 new modules

**Testing strategy**:
- Unit tests for README generation (template rendering)
- Unit tests for compliance checker (each rule)
- Integration test: upload files → annotate → plot → register figure → export → validate ZIP structure
- Real-world test: export actual lab dataset, upload to Zenodo sandbox, verify compliance

**User documentation needs**:
- "Quick Start: Export Your First FAIR Package" guide
- Metadata field explanations (what is ORCID, why it matters)
- NCCR Catalysis-specific workflow (phase selection, acknowledgement)
- Zenodo upload instructions (reserve DOI, upload ZIP, link to publication)

#### Why This Makes GeckoPlotter Uniquely Valuable

**Current landscape**:
- Plotting tools (Origin, Prism, matplotlib): Make figures, ignore data provenance
- RDM tools (OSF, Dataverse): Store datasets, no integration with analysis workflow
- Lab notebooks (ELN): Track experiments, weak export/packaging features

**GeckoPlotter with FAIR integration**:
- **Plot + Package in one workflow**: Users don't context-switch between analysis and data management
- **Provenance by design**: Figure-to-data mapping captured automatically, not reconstructed later
- **Compliance as default**: FAIR/Zenodo requirements enforced at export, not as afterthought
- **Lab-specific**: Tailored to chemistry/biocatalysis workflows (HPLC, UV-Vis, LCMS, enzyme assays)

**Impact for your NCCR Catalysis group**:
- **Reduces Data Steward workload**: Colleagues produce compliant packages themselves
- **Increases dataset quality**: Structured metadata, complete provenance, clean file organization
- **Speeds up publication**: Dataset preparation happens during analysis, not after paper acceptance
- **Improves reproducibility**: Future researchers (or future you) can trace every figure to source data

**Potential for broader adoption**:
- Other NCCR Catalysis groups face same RDM requirements → tool is directly transferable
- SNSF-funded projects have similar FAIR mandates → applicable beyond NCCR
- Chemistry/biocatalysis community lacks good plot-to-package tools → fills real gap
- Could become reference implementation for "FAIR-by-design" analysis software

## Decisions to Keep Fixed

- Continue only in `GeckoPlotter_V2/`
- `DashPlotter/` is read-only reference
- Do not build in `GeckoPlotter_V2 2/`
- Prefer modular services/callbacks over monolithic logic
- `pub-table` must exist in the initial layout (even if hidden/empty) so callbacks never crash
