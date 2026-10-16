"""PDA calibration comparisons use identical windows and leave only the chosen channel."""
import json

import numpy as np
import pandas as pd
import pytest

from gecko_api import GeckoError, Workspace
from services.data_store import Bundle, BundleType, Component, ComponentRole
from services.live_agent import METHODS, READS, _DOING
from services.live_focus import FOLLOWED, focus


@pytest.fixture
def workspace():
    ws = Workspace()
    t = np.linspace(0, 4, 2001)
    nm = np.arange(200., 291.)
    profile = np.exp(-((t - 1.75) / .045) ** 2)
    for level in [1., 2., 4., 8., 10.]:
        spectrum = 100 * np.exp(-((nm - 254) / 9) ** 2) + .01
        spectrum[nm == 205] = 400
        spectrum[nm == 230] = 140 / (1 + .08 * level)
        matrix = level * profile[:, None] * spectrum + 2 + .05 * np.sin(t[:, None] * 179)
        frame = pd.DataFrame({'Time (min)': t, 'Absorbance (mAU)': matrix[:, 54]})
        meta = {'pda': {'time_min': t, 'wavelength_nm': nm, 'absorbance_mau': matrix},
                'wavelength_nm': 254, 'auto_x': 'Time (min)', 'auto_y': ['Absorbance (mAU)']}
        source = Component(f'{level}-uv', ComponentRole.PRIMARY, f'{level}.txt', dataframe=frame, metadata=meta)
        ws.store.add_bundle(Bundle(str(level), str(level), BundleType.CHROMATOGRAM, component_list=[source]))
    ws.integrate(1.62, 1.92, name='PEA', snap_to_valleys=False)
    return ws


def standards(ws):
    return {b.name: float(b.name) for b in ws._bundles()}


def test_ranks_linearity_after_saturation_and_noise_and_preserves_workspace(workspace):
    ws = workspace
    old_peaks = ws.peaks()
    old_ids = {c.component_id for b in ws._bundles() for c in b.component_list}
    result = ws.compare_wavelengths('PEA', standards(ws), [205, 230, 254, 280], detail=True)
    rows = {r['wavelength_nm']: r for r in result['wavelengths']}
    assert result['recommendation']['wavelength_nm'] == 254
    assert result['recommendation']['eligible']
    assert rows[254]['r_squared'] > .99999
    assert rows[254]['max_back_calculated_error_percent'] < .1
    assert rows[254]['slope'] == pytest.approx(100 * .045 * np.sqrt(np.pi), rel=.002)
    assert rows[205]['saturated'] and not rows[205]['eligible']
    assert rows[230]['curvature']['significant']
    assert rows[230]['max_back_calculated_error_percent'] > 10
    assert rows[280]['snr_low'] < 10 and not rows[280]['eligible']
    assert rows[254]['loq_estimate'] == pytest.approx(10 / rows[254]['snr_low'])
    for row in rows.values():
        assert all(p['rt_start'] == 1.62 and p['rt_end'] == 1.92 for p in row['standards'])
        assert row['purity']['min_correlation'] > .999
        assert 'drift_mau' in row['baseline']
    assert ws.peaks() == old_peaks
    new_ids = {c.component_id for b in ws._bundles() for c in b.component_list} - old_ids
    assert len(new_ids) == 5
    ws.compare_wavelengths('PEA', standards(ws), [205, 230, 254, 280], detail=True)
    assert {c.component_id for b in ws._bundles() for c in b.component_list} == old_ids | new_ids
    json.dumps(result, allow_nan=False)


def test_automatic_candidates_and_agent_focus(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'] += (float(bundle.name) * 50 *
            np.exp(-((pda['time_min'][:, None] - 1.75) / .045) ** 2) *
            np.exp(-((pda['wavelength_nm'] - 268) / 2) ** 2))
    result = workspace.compare_wavelengths('PEA', standards(workspace), detail=True)
    candidates = {r['wavelength_nm'] for r in result['wavelengths']}
    assert 254 in candidates and 205 in candidates and len(candidates) <= 8
    assert 268 in candidates  # Weaker analyte maxima must not all be crowded out by fixed points.
    assert 'compare_wavelengths' in METHODS & FOLLOWED
    assert 'compare_wavelengths' not in READS
    assert _DOING['compare_wavelengths'] == 'comparing wavelengths'
    view = focus(workspace, 'compare_wavelengths', ['PEA', standards(workspace)], {}, result)
    entry = workspace.store.get_data_by_id(view['active'])
    assert entry['metadata']['wavelength_nm'] == result['recommendation']['wavelength_nm']


def test_spectral_change_and_neighbour_are_reported(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        t, nm = pda['time_min'], pda['wavelength_nm']
        contaminant = 300 * np.exp(-((nm - 240) / 8) ** 2)
        pda['absorbance_mau'] += np.exp(-((t[:, None] - 1.79) / .025) ** 2) * contaminant
        pda['absorbance_mau'] += 50 * np.exp(-((t[:, None] - 2.08) / .025) ** 2)
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254], detail=True)
    row = result['wavelengths'][0]
    assert row['purity']['impure']                       # the peak's purity warns; it does not reject a wavelength
    assert row['selectivity']['neighbours'][0]['relative_height'] > 0
    assert any('changes across the peak' in w for w in result['warnings'])


@pytest.mark.parametrize('wavelengths', [[500], [], [float('nan')]])
def test_invalid_wavelengths_do_not_mutate(workspace, wavelengths):
    before = workspace.samples()
    with pytest.raises(GeckoError):
        workspace.compare_wavelengths('PEA', standards(workspace), wavelengths, detail=True)
    assert workspace.samples() == before


def test_missing_peak_and_shifted_standards_are_not_silently_dropped(workspace):
    with pytest.raises(GeckoError, match='peak'):
        workspace.compare_wavelengths('Absent', standards(workspace), detail=True)
    workspace.store.peak_service.get_peaks('1.0-uv')[0].rt += .4
    with pytest.raises(GeckoError, match='tolerance'):
        workspace.compare_wavelengths('PEA', standards(workspace), detail=True)


def test_saturated_spectral_pixels_do_not_reject_an_unsaturated_channel(workspace):
    for bundle in workspace._bundles():
        matrix = bundle.primary.metadata['pda']['absorbance_mau']
        np.minimum(matrix, 1800, out=matrix)
    result = workspace.compare_wavelengths('PEA', standards(workspace), [205, 254], detail=True)
    assert result['recommendation']['wavelength_nm'] == 254
    assert result['wavelengths'][0]['purity']['excluded_saturated_wavelengths'] > 0


def test_neighbour_inside_the_integration_window_is_not_hidden(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'] += 30 * np.exp(-((pda['time_min'][:, None] - 1.86) / .009) ** 2)
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254], detail=True)
    neighbours = result['wavelengths'][0]['selectivity']['neighbours']
    assert any(abs(n['rt'] - 1.86) < .01 for n in neighbours)


def test_low_wavelength_baseline_warns_of_solvent_absorbance(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'][:, pda['wavelength_nm'] == 205] += 60
    row = workspace.compare_wavelengths('PEA', standards(workspace), [205], detail=True)['wavelengths'][0]
    assert row['baseline']['gradient_or_solvent']


def test_mcp_forwards_comparison_parameters(monkeypatch):
    import gecko_mcp
    from unittest.mock import Mock
    run = Mock(return_value={'recommendation': None})
    monkeypatch.setattr(gecko_mcp, '_run', run)
    assert gecko_mcp.compare_wavelengths('PEA', {'a': 1, 'b': 2}, [254], ['unknown'], .1, detail=True) == run.return_value
    run.assert_called_once_with('compare_wavelengths', 'PEA', {'a': 1, 'b': 2}, [254], ['unknown'], .1, True, ctx=None)


def test_failure_after_extraction_leaves_no_channels_or_visibility_changes(workspace):
    before = workspace.samples()
    visibility = dict(workspace.store.visibility_state)
    workspace._bundles()[-1].primary.metadata['pda']['absorbance_mau'][875, 54] = np.nan
    with pytest.raises(GeckoError, match='nonfinite'):
        workspace.compare_wavelengths('PEA', standards(workspace), [205, 254], detail=True)
    assert workspace.samples() == before
    assert workspace.store.visibility_state == visibility


def test_automatic_comparison_includes_the_original_peak_channel(workspace):
    workspace.remove_peak(None, 'PEA')  # Avoid cross-channel group renaming of the fixture's original peak.
    workspace.add_uv_channel(263)
    workspace.integrate(1.62, 1.92, channel='263', name='Reference', snap_to_valleys=False)
    result = workspace.compare_wavelengths('Reference', standards(workspace), detail=True)
    assert 263 in {r['wavelength_nm'] for r in result['wavelengths']}


def test_full_screen_matches_scalar_areas_and_fits_at_every_recorded_wavelength(workspace):
    from services.wavelength_comparison import _screen, _trace, _fit
    from services.pda_service import _arrays
    bundles = workspace._bundles()
    arrays = [_arrays(b.primary.metadata['pda']) for b in bundles]
    concentrations = np.array([float(b.name) for b in bundles])
    screen = _screen(arrays, concentrations, 1.621, 1.919, 1.75)
    assert screen['wavelengths'].tolist() == list(np.arange(200., 291.))
    for j, nm in enumerate(screen['wavelengths']):
        traces = [_trace(t, z[:, j], 1.621, 1.919) for t, _, z in arrays]
        areas = np.array([r['area'] for r in traces])
        fit, _, _ = _fit(concentrations, areas)
        assert screen['areas'][:, j] == pytest.approx(areas, abs=1e-10)
        assert screen['height_high'][j] == pytest.approx(traces[-1]['height'])
        assert screen['r_squared'][j] == pytest.approx(fit['r_squared'], abs=1e-10)
        assert screen['max_error'][j] == pytest.approx(fit['max_back_calculated_error_percent'], abs=1e-7)


def test_screen_finds_quiet_off_maximum_band_and_returns_compact_ranges(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        t = pda['time_min']
        # A narrow quiet band is neither an absorbance maximum nor a fixed benchmark.
        pda['absorbance_mau'][:, pda['wavelength_nm'] == 247] -= .049 * np.sin(t[:, None] * 179)
    result = workspace.compare_wavelengths('PEA', standards(workspace), detail=True)
    screen = result['screen']
    candidates = {r['wavelength_nm'] for r in result['wavelengths']}
    assert 247 in candidates
    assert screen['wavelength_count'] == 91
    assert screen['range_nm'] == [200, 290]
    points = {r['wavelength_nm']: r for r in screen['points']}
    assert set(range(200, 291, 10)) | candidates <= points.keys()
    assert len(points) <= 18
    assert points[247]['candidate_reasons']
    assert len(points[247]['areas']) == 5
    assert screen['ranges_nm']['saturated'] == [[205, 205]]
    assert any(a <= 280 <= b for a, b in screen['ranges_nm']['too_noisy'])
    assert any(a <= 230 <= b for a, b in screen['ranges_nm']['non_linear'])
    assert screen['elapsed_seconds'] >= 0
    json.dumps(result, allow_nan=False)


def test_purity_excludes_1000_mau_pixels_and_weak_apex_absorbance(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        t, nm = pda['time_min'], pda['wavelength_nm']
        profile = np.exp(-((t - 1.75) / .045) ** 2)
        uv = nm <= 220
        pda['absorbance_mau'][:, uv] = np.minimum(
            float(bundle.name) * profile[:, None] * np.linspace(400, 250, uv.sum()) + 2, 1200)
        # Weak wavelength-dependent disturbance must not dominate the correlation.
        pda['absorbance_mau'][:, nm >= 280] += (
            20 * np.exp(-((t[:, None] - 1.78) / .02) ** 2) * np.linspace(0, 1, (nm >= 280).sum()))
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254], detail=True)
    purity = result['purity']
    assert not purity['impure'] and purity['assessed']
    assert purity['min_correlation'] > .999
    high = purity['standards'][-1]
    assert high['excluded_saturated_wavelengths'] >= 21
    assert high['wavelength_count'] >= 3
    assert all(220 < a <= b < 280 for a, b in high['wavelength_ranges_nm'])
    assert high['apex_absorbance_fraction'] == .05 and high['minimum_mau'] == 3.0
    assert high['saturation_limit_mau'] == 1000


def test_purity_insufficient_clear_pixels_is_unassessed(workspace):
    for bundle in workspace._bundles():
        bundle.primary.metadata['pda']['absorbance_mau'] += 2000
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254], detail=True)
    purity = result['purity']
    assert not purity['assessed'] and purity['min_correlation'] is None
    assert all(r['wavelength_ranges_nm'] == [] for r in purity['standards'])
    assert any('could not be assessed' in w for w in result['warnings'])


def test_purity_requires_all_three_spectral_pairs_to_be_assessable(workspace):
    from services.wavelength_comparison import _purity
    for bundle in workspace._bundles():
        component, peak = workspace._find_peak(bundle, 'PEA')
        pda = bundle.primary.metadata['pda']
        row = _purity(workspace, bundle, component, peak, pda, 1.62, 1.92)
        t, z = pda['time_min'], pda['absorbance_mau']
        scan = np.argmin(abs(t - row['times_min'][0]))
        lo, hi = [np.argmin(abs(t - ti)) for ti in (1.62, 1.92)]
        weight = (t[scan] - t[lo]) / (t[hi] - t[lo])
        z[scan] = (1 - weight) * z[lo] + weight * z[hi]
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254], detail=True)
    assert not result['purity']['assessed']
    assert any('could not be assessed' in w for w in result['warnings'])


def test_screen_preserves_float32_precision_at_interpolated_endpoints(workspace):
    from services.wavelength_comparison import _screen, _trace
    from services.pda_service import _arrays
    bundles = workspace._bundles()
    for bundle in bundles:
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'] = pda['absorbance_mau'].astype(np.float32)
    arrays = [_arrays(b.primary.metadata['pda']) for b in bundles]
    concentrations = np.array([float(b.name) for b in bundles])
    screen = _screen(arrays, concentrations, 1.62131, 1.91971, 1.75)
    for j in [5, 30, 54]:
        for i, (t, _, z) in enumerate(arrays):
            scalar = _trace(t, z[:, j].astype(float), 1.62131, 1.91971)
            assert screen['areas'][i, j] == pytest.approx(scalar['area'], abs=1e-10)


def test_the_default_answer_is_short_enough_for_an_agent(workspace):
    """The full result is tens of thousands of characters: an agent's client saves such an answer to a file and the
    agent ends up parsing it in a shell. The default is the compact summary."""
    import json
    result = workspace.compare_wavelengths('PEA', standards(workspace))
    assert len(json.dumps(result, default=str)) < 12000
    assert {'recommendation', 'candidates', 'screen', 'purity', 'warnings'} <= set(result)
    assert 'standards' not in result['candidates'][0] and result['screen']['ranges_nm'] is not None
