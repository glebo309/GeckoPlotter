import numpy as np
import pandas as pd
import plotly.graph_objects as go

from services import pda_service as pda
from services.data_store import DataStore, Bundle, BundleType, Component, ComponentRole, SourceCategory, ColumnRole
from callbacks.viz_callbacks import _apply_pda_main_preview
from src.ingestion.types import StandardizedResult, FileIdentity


def series_store():
    store = DataStore()
    for name, scale in [('a', 1), ('b', 10), ('outside', 100)]:
        matrix = np.array([[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]]) * scale
        payload = {'time_min': np.array([0., .5, 1.]), 'wavelength_nm': np.array([200., 220., 280.]),
                   'absorbance_mau': matrix}
        components = []
        for suffix, wavelength in [('uv', 280), ('extra', 200)]:
            metadata = {'sample_name': name, 'wavelength_nm': wavelength,
                        'auto_x': 'Time (min)', 'auto_y': ['Absorbance (mAU)']}
            metadata.update({'pda': payload} if suffix == 'uv' else {'pda_source_id': name + '-uv'})
            components.append(Component(name + '-' + suffix, ComponentRole.PRIMARY, name + '.txt',
                dataframe=pd.DataFrame({'Time (min)': [0., .5, 1.], 'Absorbance (mAU)': [3., 6., 9.]}),
                column_roles={'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y},
                source_category=SourceCategory.CHROMATOGRAM, metadata=metadata))
        store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM, component_list=components))
    store.group_overrides = {'outside': ('different', 'time', 'domain')}
    return store


def test_add_series_adds_one_channel_per_same_group_sample_and_is_idempotent():
    store = series_store()
    original = {b.bundle_id: b.primary.metadata['pda'] for b in store.iter_bundles()}
    added = pda.add_pda_series(store, 'a-extra', 219.)
    assert set(added) == {'a', 'b'}
    assert pda.add_pda_series(store, 'a-extra', 221.) == added
    for name, component_id in added.items():
        entry = store.get_data_by_id(component_id)
        assert entry['metadata']['wavelength_nm'] == 220.
        assert entry['metadata']['pda_source_id'] == name + '-uv'
        np.testing.assert_array_equal(entry['data']['Absorbance (mAU)'], np.array([2., 5., 8.]) * (1 if name == 'a' else 10))
        assert store.get_bundle(name).primary.metadata['pda'] is original[name]
        assert len(store.get_bundle(name).component_list) == 3
    assert len(store.get_bundle('outside').component_list) == 2


def test_series_preview_replaces_matching_uv_only_preserving_other_channels_and_data():
    store = series_store()
    fig = go.Figure()
    for owner in ['a-uv', 'a-extra', 'b-uv', 'b-extra', 'outside-uv', 'tic']:
        fig.add_trace(go.Scatter(x=[0., .5, 1.], y=[3., 6., 9.], name=owner,
                                meta={'file_id': owner}, line={'color': '#123456'}))
    replaced = _apply_pda_main_preview(fig, store, {'owner_id': 'a-uv', 'source_id': 'a-uv', 'wavelength_nm': 220.})
    assert set(replaced) == {'a-uv', 'b-uv'}
    np.testing.assert_array_equal(fig.data[0].y, [2., 5., 8.])
    np.testing.assert_array_equal(fig.data[2].y, [20., 50., 80.])
    assert fig.data[0].name != fig.data[2].name
    assert fig.data[2].meta['pda_source_id'] == 'b-uv'
    assert fig.data[2].line.color == '#123456'
    for index in [1, 3, 4, 5]:
        assert list(fig.data[index].y) == [3., 6., 9.]
        assert not fig.data[index].meta.get('pda_preview')
    assert list(store.get_data_by_id('b-uv')['data']['Absorbance (mAU)']) == [3., 6., 9.]


def test_preview_chromatograms_cover_every_sample_in_the_plot_and_stay_small():
    store = series_store()
    series = pda.preview_chromatograms(store, 'a-extra', 219.)
    assert [item['source_id'] for item in series] == ['a-uv', 'b-uv']      # the selected sample first; 'outside' excluded
    assert series[0]['wavelength_nm'] == 220.
    assert series[0]['y'] == [2., 5., 8.] and series[1]['y'] == [20., 50., 80.]


def test_preview_chromatograms_keep_narrow_peaks_when_downsampled():
    n = 5000
    times = np.linspace(0, 3.5, n)
    matrix = np.zeros((n, 3))
    matrix[2500, 1] = 900.                       # one-sample spike at 220 nm
    payload = {'time_min': times, 'wavelength_nm': np.array([200., 220., 280.]), 'absorbance_mau': matrix}
    store = DataStore()
    comp = Component('s-uv', ComponentRole.PRIMARY, 's.txt', dataframe=pd.DataFrame({'Time (min)': [0.], 'Absorbance (mAU)': [0.]}),
                     column_roles={'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y},
                     source_category=SourceCategory.CHROMATOGRAM,
                     metadata={'sample_name': 's', 'wavelength_nm': 220, 'pda': payload,
                               'auto_x': 'Time (min)', 'auto_y': ['Absorbance (mAU)']})
    store.add_bundle(Bundle('s', 's', BundleType.CHROMATOGRAM, component_list=[comp]))
    series = pda.preview_chromatograms(store, 's-uv', 220., limit=400)
    assert len(series[0]['x']) <= 400 and max(series[0]['y']) == 900.


# ---- every visible sample of the plot gets exactly one preview trace, matching what the endpoint returns ----------
def many_store(n=5):
    """n samples; each has a 280 nm primary (carries the PDA matrix) and a 200 nm sibling channel."""
    store = DataStore()
    for k in range(n):
        name = f's{k}'
        matrix = np.array([[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]]) * (k + 1)
        payload = {'time_min': np.array([0., .5, 1.]), 'wavelength_nm': np.array([200., 220., 280.]),
                   'absorbance_mau': matrix}
        components = []
        for suffix, wavelength in [('uv', 280), ('extra', 200)]:
            metadata = {'sample_name': name, 'wavelength_nm': wavelength, 'auto_x': 'Time (min)', 'auto_y': ['Absorbance (mAU)']}
            metadata.update({'pda': payload} if suffix == 'uv' else {'pda_source_id': name + '-uv'})
            frame = pd.DataFrame({'Time (min)': [0., .5, 1.], 'Absorbance (mAU)': [3., 6., 9.]})
            roles = {'Time (min)': ColumnRole.X, 'Absorbance (mAU)': ColumnRole.Y}
            identity = FileIdentity(original_name=name + '.txt', extension='.txt', detected_format='pda', detection_stage=0)
            standardized = StandardizedResult(frame, roles, identity, source_category=SourceCategory.CHROMATOGRAM,
                                              sample_name=name, metadata=metadata)
            components.append(Component(f'{name}-{suffix}', ComponentRole.PRIMARY, name + '.txt', dataframe=frame,
                column_roles=roles, source_category=SourceCategory.CHROMATOGRAM, metadata=metadata,
                standardized=standardized))
        store.add_bundle(Bundle(name, name, BundleType.CHROMATOGRAM, component_list=components))
    return store


def plotted(store, active):
    """Visible components of the active plot group -> one trace each, with the meta PlotManager gives (file_id, ...)."""
    from callbacks.viz_callbacks import _collect_visible_files, _get_active_file_group
    visible = _collect_visible_files(store, active, store.get_loaded_files_list(),
                                     target_group_override=_get_active_file_group(store, active))
    fig = go.Figure()
    for entries in visible.values():
        for name, entry in entries:
            record = entry['record']
            fig.add_trace(go.Scatter(x=[0., .5, 1.], y=[3., 6., 9.], name=name, line={'color': '#123456'},
                meta={'file_id': record['id'], 'rename_file_id': entry['metadata'].get('parent_bundle_id', ''),
                      'y_column': 'Absorbance (mAU)'}))
    return fig


def preview_traces(fig):
    return [t for t in fig.data if isinstance(t.meta, dict) and t.meta.get('pda_preview')]


def show_only(store, visible_ids):
    for bundle in store.iter_bundles():
        for component in bundle.component_list:
            store.visibility_state[store.peak_owner_id(component.component_id)] = component.component_id in visible_ids


def test_every_visible_sample_is_previewed_once_with_the_id_the_endpoint_returns():
    store = many_store(5)
    show_only(store, {f's{k}-uv' for k in range(5)})
    fig = plotted(store, 's0-uv')
    assert len(fig.data) == 5
    replaced = _apply_pda_main_preview(fig, store, {'owner_id': 's0-uv', 'source_id': 's0-uv', 'wavelength_nm': 220.})
    assert sorted(replaced) == [f's{k}-uv' for k in range(5)]
    traces = preview_traces(fig)
    assert len(traces) == 5
    served = {item['source_id']: item for item in pda.preview_chromatograms(store, 's0-uv', 200.)}
    assert {t.meta['pda_source_id'] for t in traces} == set(served) == {f's{k}-uv' for k in range(5)}
    for t in traces:                                              # what the browser restyles is what the server drew
        assert t.name.endswith('PDA 220 nm · preview')


def test_samples_showing_their_second_channel_or_hidden_are_handled():
    store = many_store(5)
    # s0 shows only its 200 nm sibling (the inspected owner is the hidden primary), s1 only its primary,
    # s2 shows both channels, s3 is hidden altogether, s4 shows only its sibling.
    show_only(store, {'s0-extra', 's1-uv', 's2-uv', 's2-extra', 's4-extra'})
    fig = plotted(store, 's1-uv')
    assert len(fig.data) == 5
    replaced = _apply_pda_main_preview(fig, store, {'owner_id': 's0-uv', 'source_id': 's0-uv', 'wavelength_nm': 220.})
    traces = preview_traces(fig)
    by_source = {t.meta['pda_source_id']: t for t in traces}
    assert set(by_source) == {'s0-uv', 's1-uv', 's2-uv', 's4-uv'}          # s3 hidden: no trace
    assert len(traces) == 4 and len(replaced) == 4
    assert by_source['s0-uv'].meta['pda_owner_id'] == 's0-extra'          # a hidden owner falls back to the visible channel
    assert by_source['s2-uv'].meta['pda_owner_id'] == 's2-uv'
    assert len(fig.data) == 5 and sum(1 for t in fig.data if not t.meta.get('pda_preview')) == 1   # s2's other channel untouched
    for t in traces:
        scale = int(t.meta['pda_source_id'][1]) + 1
        np.testing.assert_array_equal(t.y, np.array([2., 5., 8.]) * scale)


def test_owner_given_as_sample_id_still_previews_every_sample():
    store = many_store(3)
    show_only(store, {f's{k}-uv' for k in range(3)})
    fig = plotted(store, 's0-uv')
    _apply_pda_main_preview(fig, store, {'owner_id': 's0', 'source_id': 's0-uv', 'wavelength_nm': 220.})
    assert {t.meta['pda_source_id'] for t in preview_traces(fig)} == {'s0-uv', 's1-uv', 's2-uv'}


def test_a_wavelength_the_instrument_already_exports_reuses_that_channel_instead_of_adding_a_duplicate():
    store = series_store()
    channel = store.get_bundle('a').component_list[0]
    channel.metadata.update(detector_channel='Ch2', wavelength_nm=219.6)
    before = len(store.get_bundle('a').component_list)
    assert pda.add_pda_chromatogram(store, 'a-extra', 220.) == channel.component_id
    assert len(store.get_bundle('a').component_list) == before
    assert pda.add_pda_chromatogram(store, 'a-extra', 200.) != channel.component_id      # a new wavelength still adds one


def test_a_preview_at_the_channels_own_wavelength_keeps_the_channel_and_its_peaks():
    store = series_store()
    fig = go.Figure()
    for owner in ['a-uv', 'b-uv']:
        fig.add_trace(go.Scatter(x=[0., .5, 1.], y=[3., 6., 9.], name=owner, meta={'file_id': owner}))
    replaced = _apply_pda_main_preview(fig, store, {'owner_id': 'a-uv', 'source_id': 'a-uv', 'wavelength_nm': 280.})
    assert replaced is None                                   # nothing hidden: the 280 nm channels are the preview
    assert [t.name for t in fig.data] == ['a-uv', 'b-uv']
