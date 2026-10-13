# Research export

Implemented locally on 2026-10-12. Open the Export inspector, set figure dimensions and resolution, then use FAIR-data package. All loaded signals and the currently displayed figure are included. Repository details are optional when making a working package; missing details are listed in its README.

The ZIP contains original uploaded bytes when available, immutable parsed CSV captured at import, current tables, exact displayed figure source values, complete peak geometry and calibration models, detector/column metadata, UTC analysis history with before/after values, a readable HTML report, and publication figures in the selected formats. Acquisition dates remain separate from import, analysis and export timestamps. Source text columns are preserved without guessing their meaning. LC-MS mass points and scan indices have open CSV representations in addition to the original instrument files.

Display smoothing is documented as Savitzky-Golay, with requested and effective point windows, polynomial order and edge mode. Detection has a separate processing record. Changing display smoothing can also influence detection settings when detection is rerun; neither overwrites imported source values. Data-table revisions retain their values in the history. History begins with the current workspace import and cannot reconstruct instrument-side or earlier-session edits.

SVG and PDF preserve vector output. PNG and TIFF use the selected physical dimensions and DPI. All formats use the displayed figure and viewport, with editing handles removed. With **Include analysis code** enabled under Repository details, `analysis/reproduce_figure.py` recreates the figure exports from the saved figure and recipe, using the included code and recorded dependencies. Static Plotly rendering also requires a compatible Chrome installation.

The manifest links package paths and sources and records SHA-256 hashes. `metadata/zenodo.json` is a metadata draft, not a submitted record. Nothing is uploaded. Authors, ORCID, licensing, dataset DOI, related article DOI, funding and methods can be entered in the UI. Structure files, funding treatment, complete author identifiers and community eligibility still need review before submission. Multi-figure collection and direct deposition are future work. UV-MS timing correction remains unimplemented and is explicitly recorded as not applied.

Sources consulted:

- [NCCR Catalysis curation policy](https://zenodo.org/communities/nccr-catalysis/curation-policy), checked 2026-10-12.
- [NCCR Catalysis data documentation](https://data.nccr-catalysis.ch/docs).
- Glenn's SecondBrain DataSteward notes: FAIR_DATA_LAB_GUIDE, NCCR Catalysis Data Steward, NCCR Catalysis Zenodo Curation Policy, Documentation, Notes, T_Chromeleon_FAIR_Auto_Export, submit_ChemSci_Zenodo.
- Existing Going-full-circle dataset README as a practical packaging reference.

The NCCR policy distinguishes the dataset DOI from the article DOI, requires a root README linking back to the record, and asks for open representations, sufficient descriptions, a license, author identifiers and appropriate funding acknowledgement. The app prepares the files and exposes the missing metadata without claiming repository acceptance.

The default package omits bundled source code and per-signal metadata copies. Signal metadata remains in dataset.json and the sample mapping. Unchanged current tables link to the raw CSV; edited tables keep their own copy. Complete edit history remains included. The ? link opens assets/fair-data.html in a new tab.

The package also contains `session/project.gecko`, the workspace as a GeckoPlotter project. Open the package ZIP in GeckoPlotter (Open, or drop it in) to keep editing the figure and analysis years later; the instrument files are read from `raw_data/originals/` inside the ZIP. If it could not be built or is very large it is left out and the README and report say why. See `docs/SESSION_FORMAT.md`.
