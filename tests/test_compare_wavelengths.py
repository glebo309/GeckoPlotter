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
    result = ws.compare_wavelengths('PEA', standards(ws), [205, 230, 254, 280])
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
    ws.compare_wavelengths('PEA', standards(ws), [205, 230, 254, 280])
    assert {c.component_id for b in ws._bundles() for c in b.component_list} == old_ids | new_ids
    json.dumps(result, allow_nan=False)


def test_automatic_candidates_and_agent_focus(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'] += (float(bundle.name) * 50 *
            np.exp(-((pda['time_min'][:, None] - 1.75) / .045) ** 2) *
            np.exp(-((pda['wavelength_nm'] - 268) / 2) ** 2))
    result = workspace.compare_wavelengths('PEA', standards(workspace))
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
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254])
    row = result['wavelengths'][0]
    assert row['purity']['impure']                       # the peak's purity warns; it does not reject a wavelength
    assert row['selectivity']['neighbours'][0]['relative_height'] > 0
    assert any('changes across the peak' in w for w in result['warnings'])


@pytest.mark.parametrize('wavelengths', [[500], [], [float('nan')]])
def test_invalid_wavelengths_do_not_mutate(workspace, wavelengths):
    before = workspace.samples()
    with pytest.raises(GeckoError):
        workspace.compare_wavelengths('PEA', standards(workspace), wavelengths)
    assert workspace.samples() == before


def test_missing_peak_and_shifted_standards_are_not_silently_dropped(workspace):
    with pytest.raises(GeckoError, match='peak'):
        workspace.compare_wavelengths('Absent', standards(workspace))
    workspace.store.peak_service.get_peaks('1.0-uv')[0].rt += .4
    with pytest.raises(GeckoError, match='tolerance'):
        workspace.compare_wavelengths('PEA', standards(workspace))


def test_saturated_spectral_pixels_do_not_reject_an_unsaturated_channel(workspace):
    for bundle in workspace._bundles():
        matrix = bundle.primary.metadata['pda']['absorbance_mau']
        np.minimum(matrix, 1800, out=matrix)
    result = workspace.compare_wavelengths('PEA', standards(workspace), [205, 254])
    assert result['recommendation']['wavelength_nm'] == 254
    assert result['wavelengths'][0]['purity']['excluded_saturated_wavelengths'] > 0


def test_neighbour_inside_the_integration_window_is_not_hidden(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'] += 30 * np.exp(-((pda['time_min'][:, None] - 1.86) / .009) ** 2)
    result = workspace.compare_wavelengths('PEA', standards(workspace), [254])
    neighbours = result['wavelengths'][0]['selectivity']['neighbours']
    assert any(abs(n['rt'] - 1.86) < .01 for n in neighbours)


def test_low_wavelength_baseline_warns_of_solvent_absorbance(workspace):
    for bundle in workspace._bundles():
        pda = bundle.primary.metadata['pda']
        pda['absorbance_mau'][:, pda['wavelength_nm'] == 205] += 60
    row = workspace.compare_wavelengths('PEA', standards(workspace), [205])['wavelengths'][0]
    assert row['baseline']['gradient_or_solvent']


def test_mcp_forwards_comparison_parameters(monkeypatch):
    import gecko_mcp
    from unittest.mock import Mock
    run = Mock(return_value={'recommendation': None})
    monkeypatch.setattr(gecko_mcp, '_run', run)
    assert gecko_mcp.compare_wavelengths('PEA', {'a': 1, 'b': 2}, [254], ['unknown'], .1) == run.return_value
    run.assert_called_once_with('compare_wavelengths', 'PEA', {'a': 1, 'b': 2}, [254], ['unknown'], .1, ctx=None)


def test_failure_after_extraction_leaves_no_channels_or_visibility_changes(workspace):
    before = workspace.samples()
    visibility = dict(workspace.store.visibility_state)
    workspace._bundles()[-1].primary.metadata['pda']['absorbance_mau'][875, 54] = np.nan
    with pytest.raises(GeckoError, match='nonfinite'):
        workspace.compare_wavelengths('PEA', standards(workspace), [205, 254])
    assert workspace.samples() == before
    assert workspace.store.visibility_state == visibility


def test_automatic_comparison_includes_the_original_peak_channel(workspace):
    workspace.remove_peak(None, 'PEA')  # Avoid cross-channel group renaming of the fixture's original peak.
    workspace.add_uv_channel(263)
    workspace.integrate(1.62, 1.92, channel='263', name='Reference', snap_to_valleys=False)
    result = workspace.compare_wavelengths('Reference', standards(workspace))
    assert 263 in {r['wavelength_nm'] for r in result['wavelengths']}
