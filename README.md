# GeckoPlotter

A browser-based scientific data workstation for chromatography, spectroscopy, and kinetics data. Upload files from any instrument, overlay and compare traces, pick and integrate peaks, and export publication-ready figures.

Built with [Dash](https://dash.plotly.com/) + [Plotly](https://plotly.com/python/) + [Dash Mantine Components](https://www.dash-mantine-components.com/).

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8052 and drag files onto the drop zone.

### Install for the group (one click)

Download [GeckoPlotter-Launcher.zip](https://github.com/glebo309/GeckoPlotter/raw/main/deploy/launcher/GeckoPlotter-Launcher.zip),
unzip it, and double-click **Start GeckoPlotter** (`.bat` on Windows, `.command` on Mac, `start-geckoplotter.sh` on
Linux). The first start installs a private Python and the packages (about 600 MB, a few minutes); every later start takes
seconds and pulls the newest version from this repository's `main` branch by itself. Everything runs on that person's own
computer, so it is as fast as their laptop. Nothing is installed system-wide and no admin rights are needed. Details and
the first-run warnings (Windows SmartScreen, macOS "Open") are in `deploy/launcher/README.txt`; if the Start scripts change,
rebuild the zip with `deploy/launcher/make-zip.sh`.

### Run one shared copy on a server

Everyone who opens a running copy gets a workspace of their own (a cookie in their browser): their files, peaks and
autosaves are separate, and refreshing one page never touches another person's work. Idle workspaces are dropped from
memory after 8 hours (the autosave stays on disk), and at most 12 are kept at once.

All calculations (reading `.lcd` files, integration, plots) run on the computer that hosts the app, the browser only
draws. A shared copy is therefore as fast as the host: for heavy Shimadzu data it is quicker to run your own copy.

```bash
git clone https://github.com/glebo309/GeckoPlotter.git
cd GeckoPlotter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The repository is private: collaborators need to be added on GitHub first. Settings: `GECKO_PORT` (default 8052),
`GECKO_HOST` (`0.0.0.0` makes it reachable from the local network), `GECKO_SLOW_MS` (log callbacks slower than this,
default 500), `GECKO_DEBUG=1` (development only: slower in the browser, exposes the debugger).
On Windows, `deploy/windows/run-gecko.bat` keeps it running and updated.

## Supported Formats

| Format | Instrument / Source | Extension |
|--------|-------------------|-----------|
| Chromeleon chromatogram | Thermo Chromeleon HPLC | `.txt` |
| LC-MS (TIC + mass spectra) | Agilent/generic netCDF | `.cdf` |
| LC-MS VWD (UV detector) | Agilent VWD netCDF | `.cdf` |
| UV-Vis plate reader | SpectraMax, Tecan, Synergy H1 | `.csv` |
| Cary kinetics | Agilent Cary 300/3500 | `.csv` |
| Excel workbooks | Any | `.xlsx`, `.xls` |
| Generic CSV | Any X/Y tabular data | `.csv` |

Files are auto-detected by a three-stage ingestion pipeline (magic bytes, preset matching, heuristic fallback). Multi-file bundles (e.g. a Chromeleon sample with `.txt` + `.cdf` from the same injection) are grouped automatically.

## Features

### Data Viewing
- **Multi-tab plot workspace** with auto-grouping by data type
- **Overlay** or **subplot** layout modes with adjustable spacing
- **File tree** with drag-and-drop reorder, group sorting, and visibility toggles
- **Data table editor** with cell/column selection, transpose, and row/column add

### Peak Analysis
- **Automatic peak detection** (scipy) and **manual peak drawing**
- **Right-click context menu** on peaks: delete, rename, deconvolve, cross-file integrate
- **EMG peak deconvolution** via lmfit (one-click from context menu)
- **Across Samples** tab for cross-file peak comparison
- **Undo/redo** (50 levels) with Ctrl+Z / Ctrl+Shift+Z

### LC-MS
- **TIC and EIC extraction** with target ion input
- **Mass spectrum viewer** with scan cursor scrubber
- **Scan line overlay** constrained to the MS Viewer tab

### Plot Settings
- **Axis labels** (editable, clearable, shared across subplots)
- **Color palettes**: Okabe-Ito (colorblind-safe), Plotly, D3, Pastel, Crameri scientific (Batlow, Hawaii, Roma)
- **Typography**: font family, sizes for title/ticks/labels
- **Grid, frame, tick marks** with direction and minor tick control
- **Legend** show/hide for all subplots, position presets

### Publication Export
- **Send any plot** to a Publication tab (snapshot-based, one per click)
- **Export formats**: PNG, SVG, TIFF (LZW, configurable DPI)
- **Presentation preset**: 16:9 slide mock with title and bullet placeholders
- **Subplot grid** with configurable rows/columns and zoom sync

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Delete / Backspace / X | Remove selected peak |
| Ctrl+Z / Cmd+Z | Undo |
| Ctrl+Shift+Z / Cmd+Shift+Z | Redo |
| Escape | Deselect peak, exit draw/edit mode |
| Left / Right arrows | Cycle through peaks |
| S | Toggle overlay/subplot layout |

## Architecture

```
app.py                  Dash layout + top-level callbacks
src/
  callbacks/            Event handling (19 modules, one per feature domain)
  components/           UI component factories (axis mapper, data table, publication mock)
  services/             Business logic and data models
    readers/            File format readers (CSV, Chromeleon, netCDF)
  ingestion/            Three-stage format detection pipeline
    presets/            Instrument-specific format presets
  assets/               CSS and client-side JavaScript
tests/                  pytest suite (142 tests)
```

### Design Principles

**Format-agnostic pipeline.** Every file goes through the same three stages: detect (extension + magic bytes), match preset (Chromeleon, Cary, plate reader, LCMS, Excel), or fall back to a conservative generic heuristic. All paths output a `StandardizedResult` with typed column roles and plot hints. No downstream code touches raw file formats.

**Single render owner.** The `master_render` callback in `viz_callbacks.py` is the sole writer of `main-plot.figure`. All other callbacks communicate via `dcc.Store` data; only `master_render` reads the stores and produces the figure. This eliminates race conditions between plot-modifying callbacks.

**Bundle-first data model.** `DataStore` groups related files into bundles (e.g. a Chromeleon `.txt` chromatogram with its `.cdf` mass spectrum). The UI shows bundles as single items; internally each component file has its own UUID. The `active-file` store always holds a real file UUID, never a bundle ID.

**Per-file UI state.** Switching files restores the full UI context (zoom, selected tab, peak selection, panel layout) via `context_callbacks.py`. State is saved on switch-away and restored on switch-to, so each file feels like its own workspace.

**Settings pipeline.** Plot settings flow through four callbacks: resolve context, hydrate controls from saved state, merge user edits into a normalized dict, persist to the data manager. `PlotSettingsService.apply_to_figure()` is the single entry point for styling any Plotly figure.

### Adding a New File Format

Follow [Adding instrument formats](docs/ADDING_FORMATS.md) for the current adapter contract, validation workflow, and Shimadzu ASCII example. Coding agents can use the local `$geckoplotter-format` skill, which points to that guide.

A preset implements `sniff(path, head_bytes, head_lines)` and `parse(path)`, and is registered in `src/ingestion/presets/__init__.py`. The pipeline builds `StandardizedResult` from the parsed fields. New data dimensions may also need shared data capabilities and visible controls; verify upload, analysis, and export together.

## Development

```bash
# Run tests
pytest tests/ -q

# Verify app imports cleanly (catches callback registration errors)
python -c "import app"

# Run with debug mode
python app.py
```

### Dependencies

| Package | Purpose |
|---------|---------|
| dash 3.0.4 | Web framework |
| plotly 6.1+ | Interactive plots |
| dash-mantine-components 2.3.0 | UI components |
| pandas 2.0+ | Data handling |
| numpy, scipy | Peak detection, smoothing, integration |
| cdflib 1.3.1 | netCDF file reading (LC-MS) |
| kaleido 1.0+ | Static figure export |
| Pillow 10.0+ | TIFF export with DPI metadata |
| lmfit | EMG peak deconvolution |

## Roadmap

### In Progress
- [ ] Figure style presets (Prism, Nature, ACS, Angewandte, Presentation, Dark)
- [ ] Focus mode (collapse panels when entering Publication tab)
- [ ] Right-click context menus on figure elements (axes, title, body)
- [ ] Click-to-edit axis labels and title on the figure

### Planned
- [ ] **Calibration UI** -- service exists, needs UI rebuild (multi-point table, weighted regression, LOD/LOQ)
- [ ] **HMS data analysis** -- port from Streamlit version
- [ ] **Session save/load** -- full project persistence
- [ ] **Report generation** -- Jinja2 HTML templates, PDF via weasyprint, FAIR data export

### Done (recent)
- [x] Shared axis labels with centered Y annotation
- [x] Subplot spacing slider
- [x] Legend toggle for all subplots
- [x] Publication snapshot workflow (send any plot to a new Publication tab)
- [x] Persistence opt-in (no stale file_state.json on reload)
- [x] Peak color stability for imported peaks
- [x] Spectrum/plate reader CSV classification fix
- [x] LC-MS scan cursor constrained to MS Viewer
- [x] Crameri scientific color palettes
- [x] DMC UI modernization
- [x] Right-click peak context menu
- [x] EMG peak deconvolution
- [x] Format-agnostic ingestion pipeline
- [x] Multi-tab plot workspace with bidirectional sync
- [x] Undo/redo (50 levels)

### Not Planned
- System Suitability Testing (SST metrics)
- Peak purity assessment (requires DAD/PDA data)
- Live Data Selector plot updates (the "Create Plot" workflow is intentional)
