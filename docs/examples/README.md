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

## Screenshots

The README screenshots show the actual application on a separate local server, using only the files in this folder. The reaction-progress SVG is exported from the displayed figure. The ready-to-use project is saved through the application's Save control.
