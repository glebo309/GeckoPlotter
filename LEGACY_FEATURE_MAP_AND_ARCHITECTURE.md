# Legacy Feature Map And Dash Architecture Guide

This document has two goals:

1. Capture the rich feature set that existed in the old Streamlit app and point to the exact places in the legacy code where those features live.
2. Explain what architecture the new Dash app needs so those features can be rebuilt cleanly without repeating the Streamlit-era state and synchronization problems.

The intent is not to port the old app blindly. The intent is to preserve the good functionality while using a much better state architecture in Dash.

## Scope

The useful legacy reference is mainly under:

- `../OLD_STREAMLIT_APP/app.py`
- `../OLD_STREAMLIT_APP/models/`
- `../OLD_STREAMLIT_APP/ui/`
- `../OLD_STREAMLIT_APP/utils/`
- `../OLD_STREAMLIT_APP/lcms/`

The `../OLD_STREAMLIT_APP/pdb/` area appears to be a separate product branch and should not drive GeckoPlotter V2 planning.

## Why The Streamlit App Hit Limits

The old Streamlit version was strong on functionality, but weak on architecture.

Key problems visible in the old code:

- Heavy dependence on `st.session_state` as one global mutable bucket for everything.
- UI state, domain state, plot state, and persistence state were mixed together.
- Many workflows depended on reruns, manual `st.rerun()`, hidden buttons, query params, and UI hacks.
- Cross-panel coordination was implicit rather than modeled as one explicit state graph.
- Shared workflows and per-file workflows were not clearly separated.
- Plot interactions, peak editing, calibration, and export all depended on the same mutable session blob.

You can see this style in:

- `../OLD_STREAMLIT_APP/app.py:142-238`
- `../OLD_STREAMLIT_APP/ui/sidebar.py:36-320`
- `../OLD_STREAMLIT_APP/ui/plot.py:117-260`
- `../OLD_STREAMLIT_APP/ui/plot_settings.py:12-208`

This is exactly why the Dash rewrite should prioritize state architecture first.

## Legacy Feature Atlas

### 1. Upload And File Routing

What it did:

- Accepted `.txt`, `.csv`, and `.cdf` uploads.
- Routed files by extension and processing path.
- Created chromatogram entries in runtime state.
- Activated the newest upload as the current sample.

Where to find it:

- `../OLD_STREAMLIT_APP/app.py:25-130`
- `../OLD_STREAMLIT_APP/ui/sidebar.py:124-155`
- `../OLD_STREAMLIT_APP/utils/data_processing.py:132-178`

Notes:

- The old implementation was extension-driven and fairly ad hoc.
- V2 already improves this area with dedicated readers and `DataManager`.

### 2. Sample Management

What it did:

- Listed loaded samples in the sidebar.
- Let the user toggle sample visibility.
- Let the user recolor a sample.
- Let the user rename or delete a sample.
- Maintained one active chromatogram.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/sidebar.py:166-223`

Why it matters:

- This is still an important user workflow.
- In V2 this belongs in the file tree / file management layer, but with explicit file state rather than direct UI mutation.

### 3. Signal Processing

What it did:

- Applied Savitzky-Golay smoothing.
- Calculated an iterative polynomial baseline.
- Produced raw, smoothed, baseline, and corrected signals.

Where to find it:

- `../OLD_STREAMLIT_APP/utils/data_processing.py:8-130`
- `../OLD_STREAMLIT_APP/app.py:199-224`

Why it matters:

- This is core scientific logic, not just UI.
- It should become a real service layer in Dash, not a callback-local computation pattern.

### 4. Peak Detection And Manual Peak Picking

What it did:

- Added peaks by retention time.
- Used a thresholded local search around the user-selected time.
- Estimated left/right boundaries from slope behavior.
- Extended the boundaries with a configurable factor.
- Calculated area and width at half height.
- Assigned colors intelligently, including group-consistent colors across samples.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/sidebar.py:254-320`
- `../OLD_STREAMLIT_APP/utils/peak_detection.py:12-260`
- `../OLD_STREAMLIT_APP/utils/peak_detection.py:263-364`

Important legacy behaviors worth preserving:

- Per-sample peak threshold control.
- Automatic duplicate detection.
- Width at half height.
- Group-aware peak coloring across samples.

### 5. Chromatogram Plotting And Plot Interaction

What it did:

- Rendered one combined chromatogram plot or separate subplots.
- Supported raw/smoothed display logic.
- Displayed baselines and filled peak areas.
- Added peak markers and editable titles.
- Tracked legend position and zoom state.
- Rebuilt the figure for export.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/plot.py:64-115`
- `../OLD_STREAMLIT_APP/ui/plot.py:117-260`
- `../OLD_STREAMLIT_APP/ui/plot.py:1137-1207`

Why it matters:

- The old app had much richer plot behavior than the current placeholder Plot Tools panel in Dash.

### 6. Plot Settings And Axis Controls

What it did:

- Managed manual axis min/max.
- Captured zoom and pan events.
- Reset to full data range.
- Controlled line thickness, separate plots, legend, grids, size, color theme, and scientific theme.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/plot_settings.py:12-99`
- `../OLD_STREAMLIT_APP/ui/plot_settings.py:102-208`
- `../OLD_STREAMLIT_APP/ui/plot_settings.py:240-260`
- `../OLD_STREAMLIT_APP/ui/plot_settings.py:266-552`

This is one of the biggest feature gaps in V2 right now.

### 7. Sample Results View

What it did:

- Showed peak results for the active sample.
- Reported peak name, midpoint, area, area %, width, and width at half height.
- Added concentration columns when a matching calibration model existed.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/samples_view.py:5-70`

Why it matters:

- This is a clean “single sample results” workflow that V2 should have again.

### 8. Peak Property Editing

What it did:

- Let users rename peaks.
- Change fill color.
- Change opacity.
- Delete peaks.
- View per-peak stats.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/samples_view.py:73-156`
- `../OLD_STREAMLIT_APP/ui/peaks_view.py:261-285`

Why it matters:

- This is a domain editing workflow.
- In V2 it should live in a real peak state service, not just on the figure.

### 9. Across-Sample Peak Comparison

What it did:

- Grouped peaks across samples by retention time window.
- Let the user adjust the matching window.
- Recolored grouped peaks to maintain compound identity across samples.
- Showed comparison tables for a selected group.
- Included “not detected” rows.
- Added quantification columns when calibration existed.
- Allowed CSV export.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/peaks_view.py:9-231`

Why it matters:

- V2 has started this area in `src/callbacks/tab_callbacks.py`, but the old app was still richer at the workflow level.

### 10. Calibration And Quantification

What it did:

- Built calibration models from grouped peaks.
- Supported linear, quadratic, and power-law fits.
- Supported force-through-zero.
- Supported units.
- Stored calibration models.
- Displayed calibration curves and residual plots.
- Imported and exported calibration JSON.
- Applied calibration models back into sample and comparison results.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/calibration_ui.py:13-34`
- `../OLD_STREAMLIT_APP/ui/calibration_ui.py:36-252`
- `../OLD_STREAMLIT_APP/ui/calibration_ui.py:253-755`
- `../OLD_STREAMLIT_APP/ui/calibration_ui.py:756-839`

This is the largest functional workflow still missing in Dash V2.

### 11. Export

What it did:

- Exported figure-ready data.
- Generated publication-style Matplotlib figures.
- Supported data export formats.
- Exposed export options and debug information.

Where to find it:

- `../OLD_STREAMLIT_APP/ui/export_options.py:17-384`
- `../OLD_STREAMLIT_APP/ui/export_options.py:385-625`

Why it matters:

- V2 has some export plumbing but not a true export product surface yet.

### 12. LC-MS Exploration

What it did:

- Detected whether a CDF contained spectra.
- Extracted TIC.
- Retrieved mass spectra at scan or time.
- Built an interactive TIC + mass spectrum viewer.
- Extracted and plotted EICs.
- Supported richer LC-MS analysis flows inside the plot UI.

Where to find it:

- `../OLD_STREAMLIT_APP/lcms/lcms_plot.py:15-31`
- `../OLD_STREAMLIT_APP/lcms/lcms_plot.py:33-52`
- `../OLD_STREAMLIT_APP/lcms/lcms_plot.py:53-125`
- `../OLD_STREAMLIT_APP/lcms/lcms_plot.py:127-274`
- `../OLD_STREAMLIT_APP/lcms/lcms_plot.py:276-375`

This is another major gap area for V2.

## What Dash V2 Already Has

The current Dash rewrite already has several structural advantages that the Streamlit app never had.

### 1. A Clear Four-Panel Shell

Where:

- `app.py:97-260`

What it gives you:

- File tree
- Toolbox
- Main visualization
- Bottom analysis/content tabs

This is a better long-term shell than the Streamlit sidebar/rerun model.

### 2. Explicit Front-End Stores

Where:

- `app.py:100-117`

What it already stores:

- active file
- active tab
- view mode
- per-file UI state
- plot settings
- shared selections
- shared plot settings
- mirrored table data

This is exactly the right direction.

### 3. A Real DataManager

Where:

- `src/services/storage_manager.py:148-299`

What it already does:

- reader-based loading
- bundling
- LC-MS bundle tracking
- per-file UI state
- persistent JSON state for file-level settings

This is already far better than `st.session_state`.

### 4. File-Driven Panel Synchronization

Where:

- `src/callbacks/viz_callbacks.py:88-315`

What it already does:

- treats file selection as the controller
- loads data/metadata/table for the active file
- handles shared tabs differently from per-file tabs

This is the correct architecture principle.

### 5. Shared-Tab Routing

Where:

- `src/callbacks/context_callbacks.py:10-89`
- `src/callbacks/tab_callbacks.py:19-149`

What it already solves:

- the app no longer treats every view as per-file
- peak-analysis and across-samples can now behave as shared contexts

This is an important step the Streamlit app never modeled explicitly.

## What Dash V2 Still Needs Architecturally

The current V2 is promising, but it is not “architecturally complete” yet for the rich feature set you want.

### 1. A Strict State Hierarchy

The app needs three clearly separated state domains:

- runtime data state
- per-file UI state
- shared analysis state

Recommended split:

- `loaded_data`, bundles, parsed metadata, derived tables: runtime data state
- view mode, toolbox tab, publication mappings, file-specific plot settings: per-file UI state
- peak-analysis table selection, across-sample comparison settings, shared plot settings: shared analysis state

The important rule:

- no callback should guess which state domain it should mutate
- every state write should have one explicit owner

### 2. Domain Services Instead Of Callback Logic Sprawl

Right now too much scientific behavior still lives in callbacks.

For the rich feature set, V2 needs explicit service modules such as:

- `peak_service`
- `calibration_service`
- `export_service`
- `plot_settings_service`
- `lcms_analysis_service`
- `table_analysis_service`

Callbacks should orchestrate inputs and outputs.
Scientific logic should live in services.

### 3. A Stable Peak Model

Peaks need to become first-class data objects, not just transient plot annotations.

A good peak model should support:

- stable peak IDs
- source file ID
- peak boundaries
- apex
- area
- height
- width
- width at half height
- user label
- user color/opacity
- grouped compound identity across samples
- calibration linkage

Without this, calibration, comparison, editing, and export stay fragile.

### 4. A Proper Calibration Domain

Calibration should not be a tab-only behavior.
It should be a proper app subsystem with:

- grouped analyte definitions
- standard assignments
- model definitions
- fit results
- residuals
- predicted concentration functions
- import/export serialization

This needs a dedicated service and persistent state structure.

### 5. Plot Tools Need To Become Real, Not Placeholder

The Plot Tools panel should become a real layer for:

- axis bounds
- plot style
- line thickness
- legend visibility and position
- separate subplots
- grid control
- theme control
- font/title control
- baseline visibility
- plot height/size

These settings should be state-driven and reusable across raw plots and publication plots.

### 6. Integration Needs Its Own Architecture

The Integration tab cannot stay a placeholder if you want old functionality plus richer future workflows.

It should eventually own:

- threshold settings
- slope threshold
- extension factor
- baseline method
- manual add/edit/delete peaks
- auto-detect peaks
- peak grouping preferences
- per-file integration state

### 7. Export Must Be A First-Class Workflow

Export is not just “download current figure”.
The architecture needs:

- data export
- table export
- plot export
- publication figure export
- calibration export
- session/state export

This should have a dedicated export contract instead of ad hoc callbacks.

### 8. LC-MS Needs A Separate Feature Track

The current reader support is a good start, but old LC-MS behavior was much richer.

For a full feature set, V2 needs:

- TIC view
- UV channel view
- scan-linked mass spectrum viewer
- EIC extraction
- peak-centric MS visualization
- optional background subtraction and averaged-peak MS modes

This should become a dedicated LC-MS analysis service plus a focused UI slice, not hidden inside one giant plotting callback.

### 9. Persistence Needs To Be Intentional

Current file-level persistence in `file_state.json` is useful, but eventually you will want to distinguish:

- ephemeral UI state
- reusable project/session state
- exported scientific results

That means:

- small local UI persistence for convenience
- a real project/session save format later
- deliberate export models for scientific outputs

### 10. Testing Needs To Grow With The Feature Set

For the future rich feature set, the most important test layers are:

- reader tests
- state helper tests
- peak grouping and calibration tests
- tab routing tests
- regression tests for switching files while staying on shared tabs
- export contract tests

## Optimal Target Architecture For GeckoPlotter V2

### Layer 1. Data Ingestion

Responsibilities:

- file decoding
- reader dispatch
- metadata extraction
- bundle creation
- runtime IDs

Current status:

- mostly present

Main files:

- `src/services/storage_manager.py`
- `src/services/readers/`
- `src/services/bundle_manager.py`

### Layer 2. Domain Services

Responsibilities:

- chromatogram preprocessing
- peak detection/integration
- LC-MS analysis
- calibration modeling
- export generation
- table analytics

Current status:

- partial
- needs significant growth

### Layer 3. State Orchestration

Responsibilities:

- active file
- per-file UI state
- shared tab state
- plot settings
- selection routing

Current status:

- promising
- this is the strongest part of the current direction

Main files:

- `app.py`
- `src/callbacks/context_callbacks.py`
- `src/callbacks/publication_callbacks.py`
- `src/callbacks/viz_callbacks.py`
- `src/callbacks/tab_callbacks.py`

### Layer 4. View Components

Responsibilities:

- file tree
- table editor
- publication plotter
- future plot tools / calibration / export / integration UIs

Current status:

- shell exists
- feature panels still need to be made real

### Layer 5. Persistence And Project State

Responsibilities:

- convenience persistence
- future project/session save
- calibration import/export
- scientific results export

Current status:

- small per-file persistence exists
- full project persistence does not yet exist

## Recommended Architectural Rules Going Forward

To avoid repeating the Streamlit problems, keep these rules fixed:

- File tree selection is the primary controller.
- Shared tabs and per-file tabs must never share the same state bucket.
- Callbacks should orchestrate, not contain scientific algorithms.
- Peaks, calibrations, and exports should become first-class domain objects.
- UI state and scientific result state should stay separate.
- Any new rich feature should declare:
  - what state domain it uses
  - which service owns its logic
  - which callbacks only route or render it

## Recommended Build Order

If the goal is “best architecture first, rich features second”, the best implementation order is:

1. Finish state architecture for per-file vs shared workflows.
2. Turn Plot Tools into a real, state-driven feature panel.
3. Extract a dedicated peak/integration service.
4. Rebuild sample results and peak property editing on top of that peak service.
5. Rebuild calibration as a dedicated subsystem.
6. Rebuild export as a dedicated subsystem.
7. Rebuild advanced LC-MS exploration on top of a dedicated LC-MS service.

## Practical Summary

The old Streamlit app proves the product direction is rich and scientifically useful.
It also proves that functionality without architecture eventually becomes a trap.

The Dash rewrite already has the better long-term foundation:

- a true multi-panel app shell
- explicit stores
- a `DataManager`
- modular callbacks
- growing separation between per-file and shared analysis contexts

That means the correct strategy is:

- preserve the old feature ideas
- do not preserve the old state model
- rebuild the features only after their ownership and state model are clear

This is the path that gives you both richness and stability.
