# GeckoPlotter v2 (Dash)

Interactive data visualization and analysis tool for analytical chemistry — built with Plotly Dash.

Supports **HPLC chromatograms**, **LC-MS** (TIC + mass spectra), and **UV-VIS spectroscopy** data.

## Quick Start

```bash
# Clone
git clone git@github.com:glebo309/GeckoPlotter.git
cd GeckoPlotter

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run
python app.py
# Open http://localhost:8050
```

## Project Structure

```
├── app.py                         # Entry point — creates Dash app, registers callbacks
├── data_manager.py                # Central hub — file type detection, reader dispatch
├── file_tree_manager.py           # File browser sidebar component
├── requirements.txt               # Dependencies
│
├── callbacks/                     # Dash callbacks (event handlers)
│   ├── upload_callbacks.py        # File upload & clear
│   ├── viz_callbacks.py           # Chart rendering & updates
│   ├── sidebar_callbacks.py       # Sidebar tab switching
│   ├── plot_settings_callbacks.py # Axis, font, color settings
│   ├── peak_detection_callbacks.py# Peak detection triggers
│   ├── baseline_integration_callbacks.py  # Baseline correction & integration
│   ├── draw_mode_callbacks.py     # Manual baseline drawing
│   ├── interaction_callbacks.py   # Click, hover, selection events
│   ├── hplc_callbacks.py          # HPLC-specific logic
│   └── resize_callbacks.py        # Responsive layout
│
├── layouts/
│   └── main_layout.py             # Full UI structure (header, sidebar, plot area)
│
├── readers/                       # File format parsers
│   ├── base_reader.py             # Abstract base class
│   ├── chromatogram_reader.py     # HPLC .txt (Chromeleon)
│   ├── chromeleon_bundle_reader.py # Chromeleon export bundles
│   ├── uvvis_csv_reader.py        # UV-VIS CSV
│   ├── spectra_reader.py          # General spectral data
│   ├── lcms_cdf_reader.py         # LC-MS CDF (mass spec)
│   ├── lcms_vwd_cdf_reader.py     # LC-MS CDF (UV detector)
│   └── lcms_bundle_reader.py      # LC-MS bundle manager
│
├── plot/                          # Plotly figure builders
│   ├── hplc.py                    # HPLC chromatogram plots
│   ├── lcms.py                    # LC-MS TIC + mass spectrum
│   └── uvis.py                    # UV-VIS spectrum plots
│
├── utils/                         # Shared utilities
│   ├── peak_integration.py        # Peak area integration algorithms
│   ├── plot_settings.py           # Plot option management
│   ├── sample_management.py       # Sample tracking
│   ├── toast_system.py            # Notification toasts
│   ├── fonts_labels.py            # Typography
│   └── export_options.py          # CSV/image export
│
├── interactions/
│   └── base_interactions.py       # Plot interaction handling
│
└── assets/                        # Static CSS/JS
    ├── style.css                  # Main stylesheet
    ├── tabs.js                    # Tab switching logic
    └── resize.js                  # Responsive handling
```

## How It Works

1. **Upload** — Drop HPLC (.txt), CSV, or LC-MS (.cdf) files via the sidebar
2. **Auto-detect** — `DataManager` identifies file type and dispatches to the right reader
3. **Plot** — Plotly renders interactive chromatograms/spectra in the main area
4. **Analyze** — Click peaks to detect them, draw baselines, integrate peak areas
5. **Export** — Download results as CSV

## Architecture

```
User uploads file
       ↓
  DataManager.detect_type()
       ↓
  readers/<format>_reader.py  →  parsed data
       ↓
  callbacks/viz_callbacks.py  →  triggers plot rebuild
       ↓
  plot/hplc.py (or lcms.py, uvis.py)  →  Plotly figure
       ↓
  Browser renders interactive chart
```

All state lives in the `DataManager` instance (created once in `app.py` and passed to every callback module).

## Contributing

### Workflow

1. **Pull latest**: `git pull origin main`
2. **Create a branch**: `git checkout -b feature/your-feature-name`
3. **Make changes, test locally**: `python app.py` → check http://localhost:8050
4. **Commit & push**: `git push -u origin feature/your-feature-name`
5. **Open a Pull Request** on GitHub → get it reviewed before merging

### What's safe to change

- **`readers/`** — Add new file format support (just subclass `BaseReader`)
- **`plot/`** — Adjust chart styling, add new plot types
- **`assets/`** — CSS/JS tweaks
- **`utils/`** — Helper functions

### Be careful with

- **`app.py`** — Entry point. Changes here affect everything.
- **`data_manager.py`** — Central state. Breaking this breaks the whole app.
- **`callbacks/viz_callbacks.py`** — Main rendering pipeline. Test thoroughly.
- **`utils/peak_integration.py`** — Math-heavy. Changes affect all peak analysis results.
- **`callbacks/baseline_integration_callbacks.py`** — Core analysis feature, actively being worked on.

### Rules

- Always test with a real file upload before pushing
- Don't commit `.DS_Store`, `__pycache__/`, `.venv/`, or log files (`.gitignore` handles this)
- One feature per branch, one PR per feature
