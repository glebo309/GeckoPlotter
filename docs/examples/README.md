# Example data

These examples are synthetic. They contain no experimental measurements, real sample identities, or unpublished results. Use them to explore GeckoPlotter, reproduce the README screenshots, or test an installation.

## Reaction progress

**[Open the ready-to-use project](reaction-progress.gecko)** with GeckoPlotter's Open button or drop it into the workspace. It contains three overlaid samples with named, integrated peaks and the original CSV files embedded.

To start from the data, import these three files together:

- [01_start.csv](01_start.csv)
- [02_midpoint.csv](02_midpoint.csv)
- [03_endpoint.csv](03_endpoint.csv)

Each file contains 721 time points from 0 to 12 minutes, with absorbance in mAU. The synthetic substrate peak decreases, the product peak increases, and the reference peak stays constant. These curves illustrate the interface and do not imply a measured conversion or a validated response factor.

Select a sample, open **Integration**, and use **Detect peaks** or Shift-drag across a peak. Rename peaks in the table, compare the samples, then try **Publication**, figure export, or Save.

## PDA mixture

Import **[synthetic_pda.txt](synthetic_pda.txt)**, a sectioned LabSolutions-style ASCII fixture containing:

- 721 time points across 0 to 12 minutes.
- 96 wavelengths from 210 to 400 nm, every 2 nm.
- Three synthetic components with different UV spectra.
- Two exported chromatogram channels, 254 and 305 nm.

Open **PDA** in the right panel. Select a retention time and wavelength in the heatmap, inspect the corresponding UV spectrum, and preview or add a wavelength channel. The screenshot selects 5.8 minutes and the measured 304 nm wavelength.

The fixture uses the reader's verified LabSolutions 5.141 ASCII convention: encoded wavelength values are hundredths of nm, and encoded absorbance is converted to mAU by the reader. It is a demonstration fixture, not an export from a physical instrument.

## LC-MS mixture

Open **[lcms-mixture.gecko](lcms-mixture.gecko)** for a workspace containing three named, integrated TIC peaks. Or import **[synthetic_lcms_pos.cdf](synthetic_lcms_pos.cdf)** to start from the source data.

The synthetic positive-mode ANDI-MS netCDF contains 361 scans from 0 to 12 minutes. Each scan has 22 centroid mass/intensity pairs. Three components elute near 2.45, 5.8, and 8.35 minutes with different mass spectra; these are demonstration signals with no chemical identity assigned.

1. In **Peaks**, select **Component B** and open **Peak mass** in the right panel. Its spectrum is averaged over the selected integration window.
2. Use **MS scan** to inspect a single scan at a retention time.
3. Open **EIC**, enter target m/z `269.12` and tolerance `0.2`, then click **Extract**. The extracted trace peaks near 5.8 minutes.

## Publication preview and FAIR-data export

From the reaction-progress project, choose **Publication** and **Single-column (84 mm)**. The figure appears inside a paper layout and remains editable through the figure inspector. Full-width and presentation presets show other intended contexts.

Open **Export** to try **FAIR-data package**. The ZIP collects the original sources, results, figure, metadata, processing history, and report. This is a local export, with repository details available to complete before sharing or deposition.

## Screenshots

The README screenshots show the actual application on a separate local server, using only the files in this folder. The reaction-progress SVG is exported from the displayed figure. The ready-to-use project is saved through the application's Save control.
