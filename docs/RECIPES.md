# Recipes

A recipe (`.geckorecipe`, plain JSON) is the analysis of one batch without the data, ready to apply to the next batch.
Integration inspector, section **Recipe**: **Save recipe** and **Apply recipe…**.

## What is saved

- Integration settings per kind of signal (smoothing, baseline, detection threshold, baseline mode).
- The compounds found in the reference samples as retention-time windows (median apex, range, name, label, how many
  samples had it). One window per cross-sample peak group. The match tolerance is the "Match RT" value of the inspector.
- The calibration curves (the existing portable calibration format).

Not saved: shoulder splits (deconvolved peaks), manual baselines, figure settings, the data itself.

## What applying does

For every loaded signal whose identity matches the recipe (detector category, axes, wavelength, channel; never the
sample or file name):

1. Integrates with the recipe's settings.
2. Keeps the detected peaks that fall in a compound window, names them, and removes the other detected peaks.
   Manual and deconvolved peaks are left alone.
3. If a compound is not found, lowers the detection threshold in steps (20, 10, 5, 2 % of the tallest peak) until it is;
   the status line says when this was needed. A compound that is still absent is listed as missing for that sample.
4. Groups the peaks across samples and adds the recipe's calibration curves the workspace does not have yet, then
   recalculates concentrations.

Applying twice gives the same result.
