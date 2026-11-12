"""Colours belong to signals and named compounds, including separate deconvolutions."""
import plotly.graph_objects as go

from callbacks.viz_callbacks import _trace_color_slots, _tab_id_from_group, _get_active_file_group
from services.data_store import Bundle, BundleType, DataStore
from services.peak_service import Peak, PeakService
from services.plot_settings_service import COLOR_PALETTES, PlotSettingsService, palette_options
from test_file_controls import component


def named_fits():
    ps = PeakService()
    for fid, names in [('a', ['TPA', 'MHET', 'BHET']), ('b', ['MHET', 'BHET']),
                       ('c', ['TPA-like', 'MHET'])]:
        ps._peaks[fid] = [Peak(f'{fid}-{i}', fid, name, 1.83 + i*.03, 1.8, 2., 1., 5., .2,
                              color=ps._palette[i], source='deconvolved', label=name,
                              group_id=f'deconv_1.9_c{i}', deconv_group=f'deconv_1.9_c{i}')
                          for i, name in enumerate(names)]
    ps.group_peaks_across_samples()
    return ps


def test_named_deconvolution_colours_follow_compounds_not_component_number():
    ps = named_fits()
    ids = {p.peak_id: (p.group_id, p.deconv_group, p.area, p.rt) for pp in ps._peaks.values() for p in pp}
    ps.sync_named_colors()
    by_name = {}
    for pp in ps._peaks.values():
        for p in pp:
            by_name.setdefault(p.label, set()).add(p.color)
    assert all(len(colors) == 1 for colors in by_name.values())
    assert len({next(iter(colors)) for colors in by_name.values()}) == 4
    assert {p.peak_id: (p.group_id, p.deconv_group, p.area, p.rt) for pp in ps._peaks.values() for p in pp} == ids
    original = {p.peak_id: p.color for pp in ps._peaks.values() for p in pp}
    restored = PeakService()
    restored.deserialize(ps.serialize())
    restored._peaks = dict(reversed(list(restored._peaks.items())))
    restored.sync_named_colors()
    assert {p.peak_id: p.color for pp in restored._peaks.values() for p in pp} == original


def test_named_colours_respect_distinct_extracted_ion_scopes():
    ps = named_fits()
    ps._color_scope_resolver = lambda fid: 'other-ion' if fid == 'c' else 'main'
    ps.sync_named_colors()
    main = ps._peaks['a'][1]
    other = ps._peaks['c'][1]
    before = main.color
    other.label = other.name = 'Different compound'
    ps.sync_named_colors()
    assert main.color == before


def signals():
    store = DataStore()
    for bid, name in [('a', 'sample B'), ('b', 'sample C')]:
        store.add_bundle(Bundle(bid, name, BundleType.GENERIC, component_list=[component(bid+'-signal')]))
    return store


def test_trace_slots_survive_sorting_and_new_samples():
    store = signals()
    group = _get_active_file_group(store, 'a')
    records = store.get_loaded_files_list()
    before = _trace_color_slots(store, group, records, None)
    reverse_order = {_tab_id_from_group(group): {'order': ['b', 'a'], 'sort_dir': 'desc'}}
    assert _trace_color_slots(store, group, records, reverse_order) == before
    store.add_bundle(Bundle('c', 'sample A', BundleType.GENERIC, component_list=[component('c-signal')]))
    after = _trace_color_slots(store, group, store.get_loaded_files_list(), None)
    assert all(after[key] == slot for key, slot in before.items())
    store.visibility_state['a'] = False
    assert _trace_color_slots(store, group, store.get_loaded_files_list(), None) == after


def test_trace_slots_survive_project_round_trip():
    from services import session_service as ss
    store = signals()
    group = _get_active_file_group(store, 'a')
    records = store.get_loaded_files_list()
    original = _trace_color_slots(store, group, records, None)
    data = ss.build_session(store)
    restored = DataStore()
    report = ss.restore_session(restored, data)
    assert report.ok, report.errors
    reverse_order = {_tab_id_from_group(group): {'order': ['b', 'a']}}
    assert _trace_color_slots(restored, group, restored.get_loaded_files_list(), reverse_order) == original


def test_black_trace_preset_keeps_muted_peak_fills_and_publication_style():
    preset = 'muted_black'
    assert preset in {option['value'] for option in palette_options()}
    assert COLOR_PALETTES[preset] == COLOR_PALETTES['muted']
    peak = go.Scatter(x=[0, 1, 2, 0], y=[0, 3, 0, 0], fill='toself',
                      fillcolor='rgba(238, 133, 74, 0.3)', line={'color': '#EE854A'},
                      name='peak:MHET', meta='peak_overlay')
    figure = go.Figure([go.Scatter(x=[0, 1], y=[1, 2], name='sample', meta={'file_id':'a'}), peak])
    settings = {'palette': preset}
    PlotSettingsService.apply_to_figure(figure, PlotSettingsService.from_dict(settings))
    assert figure.data[0].line.color == '#000000'
    assert figure.data[1].line.color == '#EE854A'
    assert figure.data[1].fillcolor == peak.fillcolor
    from services.publication_figure import editable_publication_figure
    publication = editable_publication_figure(figure.to_plotly_json(), settings)
    assert publication.data[0].line.color == '#000000'
    import re
    rgba_values = lambda color: tuple(map(float, re.findall(r'[\d.]+', color)))
    assert rgba_values(publication.data[1].fillcolor) == rgba_values(peak.fillcolor)


def test_switching_to_black_traces_preserves_compound_colours():
    ps = named_fits()
    ps.sync_named_colors()
    before = {p.peak_id: p.color for pp in ps._peaks.values() for p in pp}
    ps._peaks = dict(reversed(list(ps._peaks.items())))
    ps.set_palette('muted_black', COLOR_PALETTES['muted'])
    ps.group_peaks_across_samples()
    ps.sync_named_colors()
    assert {p.peak_id: p.color for pp in ps._peaks.values() for p in pp} == before


def test_rekeying_a_source_keeps_its_trace_colour():
    store = signals()
    group = _get_active_file_group(store, 'a')
    before = _trace_color_slots(store, group, store.get_loaded_files_list(), None)
    store.rekey_bundle('a', 'renamed-a')
    after = _trace_color_slots(store, group, store.get_loaded_files_list(), None)
    assert after['renamed-a|signal'] == before['a|signal']


def test_multichannel_composer_keeps_colours_when_hiding_and_reordering_samples(monkeypatch):
    import sys
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    from test_channel_visibility import samples
    from callbacks.viz_callbacks import compose_raw_figure
    from services.plot_manager import PlotManager
    from services.channel_visibility import set_sample_visibility
    store = samples()
    records = store.get_loaded_files_list()
    group = _get_active_file_group(store, 'a263')
    tab = _tab_id_from_group(group)
    for layout in ('stacked', 'overlay'):
        settings = {**PlotSettingsService.get_defaults().__dict__, 'layout_mode': layout}
        def draw(order=None):
            fig = compose_raw_figure(store, PlotManager(), tab, group, settings, 'a263', records, file_order=order)
            return {t.meta['file_id']: t.line.color for t in fig.data if isinstance(t.meta, dict)}
        set_sample_visibility(store, 'a', True)
        before = draw()
        set_sample_visibility(store, 'a', False)
        after = draw({tab: {'order': ['b', 'a']}})
        assert after
        assert all(after[fid] == before[fid] for fid in after)
        set_sample_visibility(store, 'a', True)
        assert draw({tab: {'order': ['b', 'a']}}) == before
