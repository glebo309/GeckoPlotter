import copy
import json

import pandas as pd
import pytest

from test_lcms_peak_table import fixture
from test_peak_owner_aliases import add


def uv_fixture():
    dm, app, table = fixture()
    for component in dm.get_bundle('bundle').component_list:
        component.metadata.update(auto_x='Time (min)', auto_y=['Absorbance (mAU)'])
    peak = add(dm.peak_service, 'component')
    peak.area = 244.42
    return dm, app, table, peak


@pytest.mark.parametrize('unit,factor', [('mAU·min', 1), ('mAU·s', 60), ('µAU·s', 60000)])
def test_table_units_convert_only_display_and_mirror_without_changing_analysis(unit, factor):
    dm, app, table, peak = uv_fixture()
    before = copy.deepcopy(dm.peak_service.serialize())
    rows, columns, style, mirror = table('component', 1, 0, 0, 'peak-analysis', 0,
                                         area_display_unit=unit)
    assert rows[0]['Area'] == pytest.approx(244.42 * factor)
    assert next(c['name'] for c in columns if c['id'] == 'Area') == f'Area ({unit})'
    assert rows[0]['Relative Area (%)'] == 100
    assert not any(c['id'].startswith('_area_') for c in columns)
    frame = pd.DataFrame(**{k: v for k, v in json.loads(mirror).items() if k in ('data', 'columns', 'index')})
    assert frame['Area'][0] == pytest.approx(244.42 * factor)
    assert dm.peak_service.serialize() == before


def test_unit_switching_restarts_from_source_area_and_default_is_mau_minutes():
    dm, app, table, peak = uv_fixture()
    for unit in ['µAU·s', 'mAU·s', 'mAU·min', 'µAU·s']:
        table('component', 1, 0, 0, 'peak-analysis', 0, area_display_unit=unit)
    rows, columns, *_ = table('component', 1, 0, 0, 'peak-analysis', 0)
    assert rows[0]['Area'] == peak.area == 244.42
    assert next(c['name'] for c in columns if c['id'] == 'Area') == 'Area (mAU·min)'


def test_shimadzu_scale_displays_full_counts_instead_of_scientific_notation():
    dm, app, table, peak = uv_fixture()
    rows, columns, *_ = table('component', 1, 0, 0, 'peak-analysis', 0, area_display_unit='µAU·s')
    area_column = next(c for c in columns if c['id'] == 'Area')
    assert area_column['format']['specifier'] == ',.0f'
    assert rows[0]['Area'] == 14665200


def test_unidentified_or_mixed_detector_units_are_not_relabelled_as_absorbance():
    dm, app, table = fixture()
    peak = add(dm.peak_service, 'component')
    rows, columns, *_ = table('component', 1, 0, 0, 'peak-analysis', 0, area_display_unit='µAU·s')
    assert rows[0]['Area'] == peak.area
    assert next(c['name'] for c in columns if c['id'] == 'Area') == 'Area'
    assert not rows[0].get('_area_display_unit')


def test_publication_selection_and_export_carry_displayed_units_without_mutating_selection():
    from services.area_display_units import publication_area_units
    from components.publication_plot import create_publication_plot
    from callbacks.publication_callbacks import _build_default_selections
    df = pd.DataFrame([{'_row_id': 0, 'RT (min)': 8.03, 'Area': 14665200,
                        '_area_display_unit': 'µAU·s'}])
    selection = _build_default_selections(df, 'RT (min)', 'Area')
    original = copy.deepcopy(selection)
    frame, selected = publication_area_units(df, selection)
    assert selected['y1']['series'][0]['column_id'] == 'Area (µAU·s)'
    assert frame['Area (µAU·s)'][0] == 14665200
    assert selection == original and 'Area' in df.columns
    _, exported = create_publication_plot(frame, None, selected, {'type': 'scatter', 'categorical_x': False})
    assert 'Area (µAU·s)' in str(exported)
