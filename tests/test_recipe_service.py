"""Recipes: capture a batch's analysis and apply it to new samples."""
import json

import numpy as np
import pytest

from services import recipe_service as rs
from services.data_store import DataStore
from session_helpers import chromatogram_csv, load_files


def integrate(store, bundle, sensitivity_threshold=0.05):
    frame = bundle.dataframe
    t, y = frame.iloc[:, 0].to_numpy(float), frame.iloc[:, 1].to_numpy(float)
    store.peak_service.detect_peaks(bundle.bundle_id, y, t, threshold=sensitivity_threshold)


@pytest.fixture
def reference():
    store = DataStore()
    a, b = load_files(store, [('ref_a.csv', chromatogram_csv([3.0, 6.0])),
                              ('ref_b.csv', chromatogram_csv([3.05, 6.1], amplitude=70.0))])
    for bundle in (a, b):
        integrate(store, bundle)
    store.peak_service.group_peaks_across_samples()
    for peak in store.peak_service.get_peaks(a.bundle_id):
        store.peak_service.rename_peak(a.bundle_id, peak.peak_id, 'Alanine' if peak.rt < 4 else 'Glycine')
    return store


def test_recipe_records_named_windows_settings_and_is_plain_json(reference):
    recipe = rs.build_recipe(reference, name='Amino acids', rt_tolerance=0.25)
    assert recipe['format'] == rs.RECIPE_FORMAT and recipe['schema_version'] == 1 and recipe['rt_tolerance'] == 0.25
    (signal,) = recipe['signals']
    assert [w['name'] for w in signal['windows']] == ['Alanine', 'Glycine']
    assert [round(w['rt']) for w in signal['windows']] == [3, 6] and all(w['samples'] == 2 for w in signal['windows'])
    assert signal['settings']['baseline_method'] == 'snip'
    json.loads(rs.dumps(recipe))


def test_a_recipe_needs_integrated_peaks():
    store = DataStore()
    load_files(store, [('x.csv', chromatogram_csv([3.0]))])
    with pytest.raises(rs.RecipeError):
        rs.build_recipe(store)


def test_applying_to_new_samples_names_groups_and_reports_what_is_missing(reference):
    recipe = rs.build_recipe(reference)
    fresh = DataStore()
    c, d, e = load_files(fresh, [('new_c.csv', chromatogram_csv([3.02, 6.04])),
                                 ('new_d.csv', chromatogram_csv([3.1, 6.05, 8.0], amplitude=50.0)),
                                 ('new_e.csv', chromatogram_csv([6.0]))])
    report = rs.apply_recipe(fresh, recipe)
    peaks = {fid: fresh.peak_service.get_peaks(fid) for fid in (c.bundle_id, d.bundle_id, e.bundle_id)}
    assert [p.name for p in peaks[c.bundle_id]] == ['Alanine', 'Glycine']
    assert [p.name for p in peaks[d.bundle_id]] == ['Alanine', 'Glycine']        # the extra 8.0 min peak is dropped
    assert [p.name for p in peaks[e.bundle_id]] == ['Glycine']
    by_sample = {s['sample']: s for s in report['samples']}
    assert by_sample['new_e'] == {**by_sample['new_e'], 'found': ['Glycine'], 'missing': ['Alanine']}
    assert not by_sample['new_c']['missing']
    groups = {p.group_id for plist in peaks.values() for p in plist if p.name == 'Glycine'}
    assert len(groups) == 1                                                      # one compound across the samples
    assert 'Missing: new_e: no Alanine' in rs.summarize(report)


def test_applying_twice_is_stable_and_keeps_manual_peaks(reference):
    recipe = rs.build_recipe(reference)
    fresh = DataStore()
    (c,) = load_files(fresh, [('new_c.csv', chromatogram_csv([3.0, 6.0]))])
    manual = fresh.peak_service.add_baseline_peak(
        c.bundle_id, area=12.5, height=40.0, apex_x=8.0, poly_x=[7.5, 8.0, 8.5], poly_y=[0.0, 40.0, 0.0],
        p_line=[(7.5, 0.0), (8.5, 0.0)], q1=(7.5, 0.0), q2=(8.5, 0.0), source='manual')
    rs.apply_recipe(fresh, recipe)
    first = [(p.name, round(p.area, 6)) for p in fresh.peak_service.get_peaks(c.bundle_id)]
    rs.apply_recipe(fresh, recipe)
    second = [(p.name, round(p.area, 6)) for p in fresh.peak_service.get_peaks(c.bundle_id)]
    assert first == second
    sources = sorted(p.source for p in fresh.peak_service.get_peaks(c.bundle_id))
    assert sources.count('detected') == 2 and sources.count('manual') == 1
    assert manual.peak_id in {p.peak_id for p in fresh.peak_service.get_peaks(c.bundle_id)}


def test_a_recipe_for_another_kind_of_signal_is_refused_without_changing_anything(reference):
    recipe = rs.build_recipe(reference)
    recipe['signals'][0]['signal_key'] = 'something else'
    fresh = DataStore()
    (c,) = load_files(fresh, [('new_c.csv', chromatogram_csv([3.0]))])
    with pytest.raises(rs.RecipeError):
        rs.apply_recipe(fresh, recipe)
    assert fresh.peak_service.get_peaks(c.bundle_id) == []


@pytest.mark.parametrize('text', ['not json', '[]', '{"format": "other"}',
                                  json.dumps({'format': rs.RECIPE_FORMAT, 'schema_version': 99, 'signals': [{}]}),
                                  json.dumps({'format': rs.RECIPE_FORMAT, 'schema_version': 1, 'signals': []})])
def test_unreadable_recipes_are_rejected(text):
    with pytest.raises(rs.RecipeError):
        rs.loads(text)


def test_a_small_compound_below_the_recorded_threshold_is_still_found_and_the_report_says_so(reference):
    for file_id in list(reference.peak_service.get_all_peaks()):
        reference.integration_service.update_settings(file_id, peak_threshold=0.5)
    recipe = rs.build_recipe(reference)
    assert recipe['signals'][0]['settings']['peak_threshold'] == 0.5
    # One strong and one weak compound: the weak one is under 50 % of the tallest peak.
    t = np.linspace(0, 10, 501)
    y = 100 * np.exp(-((t - 6.0) / 0.15) ** 2) + 20 * np.exp(-((t - 3.0) / 0.15) ** 2)
    text = 'Time (min),Signal (mAU)\n' + ''.join(f'{a:.4f},{b:.6f}\n' for a, b in zip(t, y))
    fresh2 = DataStore()
    (d,) = load_files(fresh2, [('mixed.csv', text.encode())])
    report = rs.apply_recipe(fresh2, recipe)
    assert [p.name for p in fresh2.peak_service.get_peaks(d.bundle_id)] == ['Alanine', 'Glycine']
    assert report['samples'][0]['threshold_lowered'] is True and not report['samples'][0]['missing']
    assert 'threshold had to be lowered' in rs.summarize(report)
