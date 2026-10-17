"""How an analytical chemist decides: the playbooks an agent reads before a judgement call (gecko_mcp analysis_guide).

Each topic is what the agent should check and in which order, with the numbers that decide. They follow common
chromatography practice (ICH Q2(R2) validation, FDA/EMA bioanalytical guidance for back-calculated standards) and what
this app can and cannot do. Keep them short: an agent reads one at the moment it needs it.
"""

GUIDES = {
    'wavelength': """Choosing the detection wavelength (PDA data: list_samples shows pda=true)
1. Use compare_wavelengths(peak, standards): it screens every common recorded PDA wavelength directly, using
   one fixed window and a straight baseline in every standard. Inspect screen.points (every 10 nm plus chosen
   candidates) and screen.ranges_nm for the full response, flank S/N and linearity picture. It then evaluates
   up to eight candidates from S/N maxima, best linearity/plateaus, absorbance maxima, unsaturated range ends
   and the original channel, or your supplied list. Do not pick the default channel or absorbance maximum blindly.
2. What decides, in this order:
   a. Not saturated: the highest standard's peak height below about 1000 mAU (1 AU); above 1.5 AU most PDA detectors
      are no longer linear. A maximum that saturates the top standard is worse than a weaker wavelength that does not.
   b. Selective: purity is a peak-level warning about possible co-elution, not a wavelength rejection. It compares
      upslope/apex/downslope spectra using >10% of the apex maximum and pixels below 1000 mAU in every spectrum
      used (including baseline endpoints). Report purity.standards wavelength_ranges_nm; too few clear pixels
      means unassessed, not pure. Also inspect neighbouring peaks relative to the analyte at each candidate.
   c. Quiet baseline: below about 220 nm mobile-phase absorbance (formic acid, TFA, methanol, acetate) raises noise and
      gradient drift. Prefer a wavelength where the blank is flat at the analyte's retention time.
   d. Sensitive enough: the lowest standard at S/N >= 10 (its LOQ); S/N 3 is only a detection limit.
   e. Most linear: lowest maximum back-calculated error over the standards, no curvature in the residuals. R2 alone
      does not decide (0.999 can hide a curved response).
3. Tell the user which wavelength you chose and why, with the numbers (height of top standard, S/N of lowest,
   max back-calculated error), which candidates you rejected, and the screen's saturated, noisy and non-linear
   ranges (non-linear flags R2 < 0.99 or max error >15%, or no positive fit; it is a diagnostic, not a rejection).""",

    'integration': """Integrating peaks for quantitation
1. Use the same rule in every sample that will be compared or calibrated: the same window and the same baseline type.
   integrate() snaps each end to the nearest valley; for a calibration series pass the same rt_start/rt_end and
   snap_to_valleys=False when the snapped ends differ much between standards (compare rt_start/rt_end in the result).
2. A peak on the tail of a bigger one: a straight baseline under both overestimates the small one; deconvolve instead
   (analysis_guide('deconvolution')).
3. Check one figure(rt_start, rt_end) of the lowest and the highest sample before reporting areas: the baseline should
   follow the trace on both sides of the peak.
4. A peak in the blank at the analyte's time: report its area; quantitation then needs blank correction or a reason
   to ignore it (carry-over: was the blank injected after the highest standard?).
5. Never delete or exclude a peak the user made by hand without saying so.""",

    'analyte': """Finding which peak is the analyte in a calibration series
1. The analyte's peak grows with the concentration in the standards and is absent (or far smaller) in the blank.
   detect_peaks in every sample on one channel, then peak_table: line up the peaks by retention time and compare
   their areas with the concentrations (a steady rise, roughly proportional). Report the candidates with their areas.
2. A peak that SHRINKS as the concentration rises is often a reagent being used up (derivatisation) or a matrix
   peak: not the analyte, but a sign the analyte is derivatised and elutes nearby.
3. Nothing scales? Look for shoulders and small peaks on the flanks of big ones (figure of the region at two
   concentrations): the analyte may co-elute; deconvolve and compare the components' areas with concentration.
4. Check the candidate's UV spectrum (uv_spectrum at its apex) against what the compound or its derivative should
   absorb, and that it is the same in every standard. Underivatised amino acids absorb only below ~210 nm.
5. Say how sure you are and why (scaling, blank, spectrum); if two peaks fit, name both and let the user decide.""",

    'deconvolution': """Overlapping peaks and shoulders
1. Deconvolve when the valley between two peaks is above about 10 % of the smaller peak's height (resolution below
   about 1.5), or a shoulder or tail kink is visible; otherwise integrate normally.
2. deconvolve(rt_start, rt_end, n_peaks=2): the window must include baseline on both sides. Name the components.
3. Trust a component only when: its width (FWHM) is similar to the main peak's (the tool warns when it is under about
   1/3), it is above a few % of the total area, R2 > 0.99 and the residuals show no structure. A component that only
   exists at the low concentrations, or whose width jumps between samples, is fitting noise: say so.
4. Show figure() of the fit for the lowest and the highest standard before using the areas.""",

    'calibration': """Building and judging a calibration curve
1. At least 5 levels spanning the expected unknowns; the concentrations from the sample names or what the user says,
   never invented. One analyte peak per standard (calibrate matches the peak by name first).
2. Acceptance (ICH / bioanalytical practice): every standard back-calculates within +-15 % of its nominal value
   (+-20 % at the lowest); residuals scatter randomly around zero; R2 >= 0.99 is necessary, not sufficient.
3. Linear first. A curve (residuals positive in the middle, negative at the ends, or the reverse) suggests saturation
   at the top or adsorption at the bottom: check the top standard's height (analysis_guide('wavelength')) before
   switching to a quadratic fit. Through zero only when the intercept is small against the lowest standard's response
   and the blank is clean.
4. An outlier: do not drop it silently. Report it with its back-calculated error and a likely cause (injection order,
   carry-over, a different injection volume or dilution in its Metadata, integration window), then offer a fit without
   it. Wide ranges (>2 decades) would need 1/x weighting, which this app does not do yet: say so.
5. Unknowns are only reported inside the calibrated range; outside it, say "above/below the calibrated range".
6. The Calibration tab shows the curve; tell the user to look at it.""",

    'identification': """Identifying a compound by LC-MS (single quadrupole)
1. Positive mode: [M+H]+, [M+Na]+ (+22.99 vs [M+H]+), [M+K]+ (+37.96), [M+NH4]+ (+17.03), [2M+H]+. Negative mode:
   [M-H]-, [M+HCOO]- (+46.01 vs [M-H]-, formate from formic acid), [M+Cl]-. Two ions 21.98 apart (Na vs H), or 46.01 apart
   in negative mode (formate vs H), are usually the same compound.
2. Isotopes: one Cl gives M+2 at about 32 % of M, one Br about 97 % (1:1), two Cl about 64 % plus M+4. Many carbons
   raise M+1 (about 1.1 % per carbon).
3. This instrument reads about 0.4-0.5 below the exact mass: compare with the expected m/z minus about 0.45.
4. Confirm with more than the mass: the EIC of the ion peaks at the same time as the UV peak, the ion is absent or
   much smaller in the blank or control, and its PDA spectrum matches a standard when there is one.
5. Background ions (plasticisers, PEG ladders 44 Da apart, solvent clusters) are flat across the run in their EIC.""",

    'conversion': """Conversion, yield and ratios (biocatalysis)
1. Peak areas are not moles: substrate and product absorb differently. Conversion from areas alone
   (product / (product + substrate)) is only an estimate; say so unless both have calibrations or a measured response
   factor.
2. With calibrations for both: conversion = [product] / ([product] + [substrate remaining]) in molar units, and the
   mass balance ([product] + [substrate]) should match the starting concentration within about 10 %; if not, report
   the gap (side products, precipitation, adsorption).
3. In LC-MS, ionisation efficiency differs even more between compounds: EIC area ratios are for comparing the same
   compound across samples, not for conversion, unless calibrated.
4. Compare samples only when they were measured with the same method and injection volume (Metadata).""",
}

TOPICS = sorted(GUIDES)


def guide(topic: str) -> dict:
    key = (topic or '').strip().lower()
    if key not in GUIDES:
        return {'topics': TOPICS, 'error': f'No guide "{topic}". Topics: ' + ', '.join(TOPICS)}
    return {'topic': key, 'guide': GUIDES[key]}
