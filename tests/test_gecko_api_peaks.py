"""Agent peak editing and noise rejection on synthetic chromatograms."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gecko_api import GeckoError, Workspace
from services.data_store import Bundle, BundleType, Component, ComponentRole


def _sample(ws, name, x, y):
    component = Component(name + '-uv', ComponentRole.PRIMARY, name + '.csv',
                          dataframe=pd.DataFrame({'time': x, 'signal': y}),
                          metadata={'auto_x': 'time', 'auto_y': ['signal']})
    ws.store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM, component_list=[component]))


@pytest.fixture
def peaks():
    ws = Workspace()
    x = np.linspace(0, 5, 1001)
    y = 10 + 20 * np.exp(-((x - 2.25) / .04) ** 2) + 30 * np.exp(-((x - 4) / .04) ** 2)
    for name in ('standard', 'sample', 'blank'):
        _sample(ws, name, x, y)
    ws.integrate(2.07, 2.42, samples=['standard', 'sample'], name='alanine')
    ws.integrate(3.8, 4.2, name='other')
    return ws


@pytest.mark.parametrize('by_id', [False, True])
def test_remove_peak_only_deletes_the_selected_sample_and_records_history(peaks, by_id):
    ws = peaks
    before = ws.peaks()
    target = next(r for r in before if r['sample'] == 'sample' and r['name'] == 'alanine')
    ws.agent = {'client': 'test-agent'}
    rows = ws.remove_peak('sample', target['peak_id'] if by_id else 'ALANINE')
    assert {r['peak_id'] for r in rows} == {r['peak_id'] for r in before} - {target['peak_id']}
    assert ws.store.analysis_history[-1]['agent'] == ws.agent
    assert 'Removed peak' in ws.store.analysis_history[-1]['trigger'][0]
    assert ws.store.peak_service.undo()
    assert {r['peak_id'] for r in ws.peaks()} == {r['peak_id'] for r in before}


def test_remove_named_peak_everywhere_skips_samples_without_it_and_is_one_undo(peaks):
    ws = peaks
    before = ws.peaks()
    rows = ws.remove_peak(None, 'alanine')
    assert len(rows) == 3 and all(r['name'] == 'other' for r in rows)
    assert ws.store.peak_service.undo()
    assert {r['peak_id'] for r in ws.peaks()} == {r['peak_id'] for r in before}


@pytest.mark.parametrize('sample', ['sample', None])
def test_remove_unknown_peak_does_not_change_the_workspace(peaks, sample):
    before, history = peaks.peaks(), len(peaks.store.analysis_history)
    with pytest.raises(GeckoError, match='no peak|No peak'):
        peaks.remove_peak(sample, 'missing')
    assert peaks.peaks() == before and len(peaks.store.analysis_history) == history


@pytest.mark.parametrize('snap', [False, True])
def test_integrate_rejects_a_small_bump_in_noise_but_keeps_a_small_standard(snap):
    ws = Workspace()
    x = np.linspace(0, 5, 1001)
    noise = np.random.default_rng(42).normal(0, 1, x.size)
    window = (x >= 2.07) & (x <= 2.42)
    noise[window] = 0
    bump = np.exp(-((x - 2.25) / .04) ** 2)
    for name, height in [('blank', 1.5), ('standard', 8)]:
        _sample(ws, name, x, 20 + noise + height * bump)
    rows = ws.integrate(2.07, 2.42, name='alanine', snap_to_valleys=snap)
    assert rows[0]['sample'] == 'blank'
    assert rows[0]['error'] == 'No peak above the noise between 2.07 and 2.42 min'
    assert rows[1]['sample'] == 'standard' and rows[1]['height'] > 6
    assert [r['sample'] for r in ws.peaks()] == ['standard']


def test_smooth_baseline_fluctuations_are_noise_even_when_first_differences_are_tiny():
    ws = Workspace()
    x = np.linspace(0, 5, 10001)
    baseline = 20 + 4 * np.cos(2 * np.pi * (x - 2.25) / .5)
    _sample(ws, 'blank', x, baseline)
    rows = ws.integrate(2.07, 2.42)
    assert rows[0]['error'].startswith('No peak above the noise')
    assert ws.peaks() == [] and not ws.store.peak_service.can_undo


@pytest.mark.parametrize('slope', [0, 10])
def test_a_small_clean_peak_survives_a_sloping_baseline_and_a_large_neighbour(slope):
    ws = Workspace()
    x = np.linspace(0, 5, 1001)
    y = 20 + slope * x + .1 * np.exp(-((x - 2.25) / .04) ** 2)
    y += 1000 * np.exp(-((x - 2.8) / .01) ** 2)
    _sample(ws, 'standard', x, y)
    row = ws.integrate(2.07, 2.42, snap_to_valleys=False)[0]
    assert row['height'] == pytest.approx(.1, rel=.001)


def test_noise_estimation_also_works_without_points_outside_the_window():
    ws = Workspace()
    x = np.linspace(2.07, 2.42, 101)
    y = 20 + 8 * np.exp(-((x - 2.25) / .04) ** 2)
    _sample(ws, 'standard', x, y)
    assert ws.integrate(2.07, 2.42)[0]['height'] > 7


def test_remove_peak_mcp_tool_routes_through_run(monkeypatch):
    pytest.importorskip('mcp')
    import gecko_mcp
    calls = []
    monkeypatch.setattr(gecko_mcp, '_run', lambda *args, **kwargs: calls.append((args, kwargs)) or [])
    assert gecko_mcp.remove_peak(None, 'alanine') == []
    assert calls == [(('remove_peak', None, 'alanine'), {'ctx': None})]
