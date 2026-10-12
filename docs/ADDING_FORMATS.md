# Adding instrument formats

GeckoPlotter converts instrument exports into a shared data model so plotting, integration, and export can work across instruments. Each new format should reuse that route. An AI agent can write and validate an adapter from representative files; importing those files afterwards requires no AI service.

This is the canonical implementation guide for people and coding agents. The optional local `$geckoplotter-format` skill points here. Supply a representative export, the instrument/software version if known, and the operations the user expects to perform.

## Design intent and current contract

The design is documented in [the ingestion plan](superpowers/plans/2026-05-20-ingestion-pipeline.md) and [the single-path architecture plan](superpowers/plans/2026-05-23-pipeline-single-path.md). Their central requirement remains useful: convert once into `StandardizedResult`, then consume semantic column roles, categories, and capabilities. These are historical plans; check the live code for signatures and ownership.

A simple new format usually needs a preset, registry entry, and tests. A new measurement dimension can also need a data capability and its visible controls. The earlier goal of adding every instrument through one file is too broad for multidimensional data. Configurable delimiters, header rows, and column mappings suit ordinary tables; sectioned and binary exports need parsing code.

| Responsibility | Current implementation |
| --- | --- |
| Extension normalization | `src/ingestion/stage_1_detect.py` |
| Content matching and preset interface | `src/ingestion/stage_2_registry.py` |
| Preset registration | `src/ingestion/presets/__init__.py`, `load_all_presets()` |
| Shared result types | `src/ingestion/types.py` |
| Pipeline and fallback | `src/ingestion/pipeline.py` |
| Upload, original bytes, parse dispatch | `src/callbacks/upload_callbacks.py` |
| Samples and detector components | `src/services/bundling_service.py`, `data_store.py` |
| Shared plotting | `src/services/plot_manager.py`, `src/callbacks/viz_callbacks.py` |
| FAIR package | `src/services/research_package.py` |

Use an existing working preset as a structural example. `chromeleon_txt.py` shows a time/intensity export, `agilent_lcms_csv.py` shows instrument metadata and detector identity, and `lcms_cdf.py` shows a specialized parsing backend. Copy the relevant contract, then verify the new file's conventions independently.

A preset subclasses `FormatPreset` and declares `name`, `extensions` (lowercase, without dots), and `priority`. Its current methods are:

```python
@staticmethod
def sniff(path: str, head_bytes: bytes, head_lines: list[str]) -> bool:
    ...

def parse(self, path: str) -> dict:
    ...
```

`sniff` must identify content. The registry currently supplies the first 4096 bytes and up to 50 decoded lines, and tests higher priorities first. Check encoding and markers against other presets sharing the extension. A `.txt` suffix alone is insufficient. Add an extension to stage 1 when it would otherwise normalize to `unknown`.

`parse` returns a dictionary containing `data` (a DataFrame) and `column_roles` (`ColumnRole` values). Set `plot_hint`, `source_category`, `sample_name`, and `metadata` when applicable. The pipeline constructs `StandardizedResult` and its `FileIdentity`; a preset does not construct that identity itself. Category describes the measurement, such as chromatogram or spectrum. Vendor identity belongs in the detected format and metadata.

## Establish the evidence before parsing

Read a real file and locate any existing parser before implementing a new one. Record the export version, encoding, delimiters, decimal notation, section markers, time basis, detector units, and matrix orientation. Check declared row and column counts against actual values. Preserve negative measurements unless the format explicitly defines them as missing values.

Keep acquisition time separate from import and analysis time. Retain the source sample name, injection information, detector channel, wavelength, and original metadata keys where useful. Missing metadata should stay absent or explicitly unknown. Do not infer a detector wavelength or a time unit from the appearance of a plot.

Scaling needs evidence. A heading can conflict with the stored integer scale. Compare a documented multiplier, a paired export, or an instrument result with known units. Record both the conversion and its basis. Do not apply one instrument's scaling convention to every export from that vendor.

Keep the uploaded bytes unchanged through the existing upload and component path. Use small synthetic or anonymized fixtures for repository tests; do not copy a full private instrument export into tests merely for convenience.

## Preserve dimensions and channel ownership

Keep a time × wavelength matrix together with its time and wavelength coordinates. A trace extracted from it needs a record of the wavelength, extraction method, and source dataset. A spectrum at one time point and a spectrum averaged over an interval are different operations and should be labeled accordingly.

Independent detector channels need independent selection, visibility, and analysis ownership. Check the existing component model before placing several Y columns in one table: a plotted second channel does not prove that peak integration uses that channel. Do not overwrite an existing component because both channels share the same role. Avoid interpolating distinct acquisition grids just to make one rectangular table unless interpolation is an explicit, recorded operation.

Extend the shared model for a reusable capability when necessary, then expose that capability in the UI. Route a PDA explorer by the presence of PDA data, not by a vendor name in a figure callback. Keep vendor section parsing inside the preset or its parsing backend. Reuse the existing selection, peak handles, processing, and export behavior.

## Verify the complete workflow

Write a failing test for the new behavior before implementation, then test these outcomes at the relevant layer:

- Recognition accepts the real signature and rejects competing formats with the same suffix. Declared dimensions and a few known numeric values survive parsing with the correct units.
- A malformed recognized file cannot quietly become a plausible generic table. Presets with `strict = True` return an import failure after a recognized parse error; other presets can still reach heuristic fallback. Use strict recognition for structured scientific exports where fallback would misrepresent damaged data, and test `ingest_file()` as well as the parser.
- Upload creates the intended sample and independently selectable channels. The displayed trace values match the parsed values. Overlay and Separate views preserve source ownership, and selecting or hiding one channel affects its own peaks.
- Integration, smoothing, or extraction uses the selected signal. New controls remain reachable, labeled with units, and visually consistent with existing controls. Inspect a browser screenshot when the UI changes.
- A FAIR package retains the original upload, untouched imported values, derived results, metadata, and relevant processing parameters. New matrices need accessible numeric exports with coordinates, rather than only a rendered image. Check serialization and downloaded contents, not merely the export callback's return value.

Use the project's environment and focused tests first. For example, run `.venv/bin/python -m pytest tests/ingestion/test_pipeline.py tests/ingestion/test_presets.py -q` from the checkout, followed by the new adapter and affected integration tests. Verify a real upload in a temporary app instance. A new Dash layout request can reset the workspace in this app; do not use the user's loaded session as a disposable test fixture.

State the supported export variants and any unverified conventions. Update the supported-format documentation. A successful parser test is not evidence that an explorer, session reload, or live deployment works.

## Worked example: Shimadzu LabSolutions ASCII

The reference export identified in Glenn's notes is:

```text
/Volumes/Paradisi/Group_Members/Glenn-Synology/SHIMZU/7302026_HEPE-FMOC__ONG_HFR_003.txt
```

The existing standalone parser is `~/Documents/SecondBrain/_SYSTEM/scripts/shimadzu_plot.py`. Read the vault instructions before using vault files. The sample is a sectioned ASCII `.txt` export containing exported chromatogram channels, peak tables, sample/instrument metadata, and `[PDA 3D]`. The recorded matrix size is 196 time points × 412 wavelengths; verify that count against the actual file when using it.

The standalone script defaults to dividing signal values by 1000 to obtain mAU and documents a paired CDF comparison as its basis. That is evidence to inspect during migration, not a universal Shimadzu rule. Preserve the source values and expose any uncertain conversion clearly.

The application adapter lives in `src/ingestion/presets/shimadzu_ascii.py`. The relevant capability fields are:

| Field | Meaning |
| --- | --- |
| `metadata['chromatogram_channels']` | List of channel dictionaries containing `name`, `data` (DataFrame), `column_roles`, and channel `metadata` |
| `metadata['pda']['time_min']` | Measured time coordinates |
| `metadata['pda']['wavelength_nm']` | Measured wavelength coordinates |
| `metadata['pda']['absorbance_mau']` | Matrix indexed as `[time][wavelength]` |
| `intensity_scaling`, `wavelength_scaling` | Conversion factors and their stated basis |

Read the adapter and `tests/ingestion/test_shimadzu_ascii.py` for the complete schema and accepted variants. The verified 5.141 profile handles the conflicting mAU header; unknown intensity profiles fail explicitly. Imported instrument peak tables remain source metadata with their original result units, separate from peaks integrated in GeckoPlotter.

Bundling expands channels into a `BundleType.CHROMATOGRAM` with independent components. The primary component holds the PDA matrix and original upload; siblings reference its `component_id` through `pda_source_id` and `source_file_id`. Preserve both data retrieval and provenance linkage for extracted signals. The explorer in `src/services/pda_service.py` selects the nearest measured wavelength and time, and records extracted chromatograms in analysis history.

The example is complete when a LabSolutions file can be imported through the normal file control, its channels can be selected and integrated separately, the PDA controls expose the matrix's traces and spectra, and the FAIR package retains both source data and the resulting analysis. None of these steps should create a second vendor-specific plotting pipeline.
