"""Sample letters survive saves and route signals and peaks to linked panes."""
import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from gecko_api import Workspace, GeckoError
from test_first_paint import _run
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS, PlotSettings
from services.plot_manager import PlotManager
from callbacks.viz_callbacks import compose_raw_figure, _get_active_file_group

@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path))
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)
    w = Workspace()
    for name in ('main', 'standard', 'reference', 'other'):
        w.store.add_bundle(_run(name, n=1001))
    return w

def figure(ws, **settings):
    group = _get_active_file_group(ws.store, 'main')
    return compose_raw_figure(ws.store, PlotManager(), 'test', group,
        {**DEFAULT_PLOT_SETTINGS, 'smooth_window': 0, **settings}, 'main', ws.store.get_loaded_files_list())

def signals(fig):
    return {t.meta['file_id']: t for t in fig.data if isinstance(t.meta, dict) and t.meta.get('file_id')}

def test_letters_overlay_and_clear_with_linked_x_and_independent_y(ws, tmp_path):
    ws.set_subplot(['standard', 'reference'], 'a')
    ws.set_subplot(['other'], 'B')
    f = figure(ws)
    traces = signals(f)
    assert traces['main'].yaxis == 'y'
    assert traces['standard'].yaxis == traces['reference'].yaxis == 'y3'
    assert traces['other'].yaxis == 'y2'  # File-list order: main, other, reference, standard.
    assert f.layout.xaxis2.matches == f.layout.xaxis3.matches == 'x'
    assert f.layout.yaxis2.matches is None and f.layout.yaxis3.matches is None
    assert {a.text for a in f.layout.annotations} >= {'A', 'B'}
    assert next(s for s in ws.samples() if s['name'] == 'standard')['subplot'] == 'A'
    ws.save(str(tmp_path / 'panes.gecko'))
    restored = Workspace()
    restored.open(str(tmp_path / 'panes.gecko'))
    assert next(s for s in restored.samples() if s['name'] == 'standard')['subplot'] == 'A'
    ws.set_subplot(['standard', 'reference', 'other'], '')
    assert {t.yaxis for t in signals(figure(ws)).values()} == {'y'}

@pytest.mark.parametrize('letter', ['AB', '1', '!', 'é'])
def test_invalid_letter_does_not_mutate(ws, letter):
    before = ws.samples()
    with pytest.raises(GeckoError):
        ws.set_subplot(['standard'], letter)
    assert ws.samples() == before

def test_peaks_follow_their_pane_and_labels_repeat_per_pane(ws):
    ws.integrate(3.8, 4.2, name='product')
    ws.set_subplot(['standard', 'reference'], 'A')
    f = figure(ws)
    rows = {r['sample']: r['peak_id'] for r in ws.peaks()}
    for name, pid in rows.items():
        overlays = [t for t in f.data if t.customdata is not None and len(t.customdata)
                    and (t.customdata[0] == pid if isinstance(t.customdata[0], str) else t.customdata[0][0] == pid)]
        assert overlays
        assert {t.yaxis for t in overlays} == ({'y2'} if name in ('standard', 'reference') else {'y'})
    labels = [t for t in f.data if t.mode == 'text' and t.visible is not False]
    assert {t.yaxis for t in labels} == {'y', 'y2'}

def test_default_black_signals_with_coloured_peaks(ws):
    assert DEFAULT_PLOT_SETTINGS['palette'] == PlotSettings().palette == 'muted_black'
    ws.integrate(3.8, 4.2, name='product')
    f = figure(ws)
    assert {t.line.color for t in signals(f).values()} == {'#000000'}
    assert any(t.fillcolor and '72, 120, 208' in t.fillcolor for t in f.data)

def test_mcp_and_live_bridge_expose_subplot_assignment(monkeypatch):
    from services.live_agent import METHODS, READS
    assert 'set_subplot' in METHODS and 'set_subplot' not in READS
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import gecko_mcp
    calls = []
    monkeypatch.setattr(gecko_mcp, '_run', lambda *a, **k: calls.append(a))
    gecko_mcp.set_subplot(['standard'], 'A')
    assert calls == [('set_subplot', ['standard'], 'A')]

def test_instrument_project_keeps_letter_when_parser_shares_metadata(ws):
    from services.session_service import _metadata_overrides
    component = ws._sample('standard').primary
    component.standardized.metadata = component.metadata
    ws.set_subplot(['standard'], 'A')
    assert _metadata_overrides(component)['subplot_letter'] == 'A'

def test_tree_box_calls_the_shared_assignment_and_normalizes_letters(ws, monkeypatch):
    from callbacks.upload_callbacks import _subplot_box
    from callbacks.file_tree_callbacks import register_file_tree_callbacks
    box = _subplot_box(ws._sample('standard')).children
    assert box.value == '' and box.id == {'type': 'sample-subplot', 'index': 'standard'}
    class App:
        functions = {}
        def callback(self, *args, **kwargs):
            def wrap(fn):
                self.functions[fn.__name__] = fn
                return fn
            return wrap
        def clientside_callback(self, *args, **kwargs):
            pass
    app = App()
    register_file_tree_callbacks(app, ws.store)
    updates = []
    monkeypatch.setattr('dash.set_props', lambda key, props: updates.append((key, props)))
    value = app.functions['assign_sample_subplot']('b', box.id, 7)
    assert value == 'B' and updates == [('render-trigger', {'data': 8})]
    assert _subplot_box(ws._sample('standard')).children.value == 'B'
    assert signals(figure(ws))['standard'].yaxis == 'y2'

@pytest.mark.parametrize('mode,expected', [('overlay', 2), ('stacked', 3)])
def test_layout_switch_only_splits_samples_without_letters(ws, mode, expected):
    ws.integrate(3.8, 4.2, name='product')
    ws.set_subplot(['standard', 'reference'], 'K')
    f = figure(ws, layout_mode=mode)
    tr = signals(f)
    assert len({t.yaxis for t in tr.values()}) == expected
    assert tr['standard'].yaxis == tr['reference'].yaxis
    assert (tr['main'].yaxis == tr['other'].yaxis) == (mode == 'overlay')
    assert tr['main'].yaxis != tr['standard'].yaxis
    assert {a.text for a in f.layout.annotations if str(a.name or '').startswith('subplot-letter:')} == {'K'}
    for sample in ws.peaks():
        pid = sample['peak_id']
        own = [t for t in f.data if t.customdata is not None and len(t.customdata)
               and (t.customdata[0] == pid if isinstance(t.customdata[0], str) else t.customdata[0][0] == pid)]
        assert own and {t.yaxis for t in own} == {tr[sample['sample']].yaxis}
    for key in f.layout:
        if key.startswith('xaxis') and key != 'xaxis':
            assert f.layout[key].matches == 'x'


@pytest.mark.parametrize('mode,expected_axes', [('overlay', ['y', 'y', 'y2', 'y2']),
                                               ('stacked', ['y', 'y', 'y2', 'y3'])])
def test_subplot_order_follows_first_sample_in_file_list(ws, mode, expected_axes):
    ws.set_subplot(['standard', 'reference'], 'K')
    files = [(name, ws.store.get_data_by_id(name)) for name in ['standard', 'reference', 'main', 'other']]
    fig = PlotManager().create_multi_file_plot({'chromatogram': files}, mode)
    tr = signals(fig)
    assert [tr[name].yaxis for name, _ in files] == expected_axes
    assert fig.layout.annotations[0].text == 'K'
    assert fig.layout.annotations[0].yref == 'y domain'


def test_separate_unassigned_samples_keep_their_positions_between_groups(ws):
    ws.set_subplot(['standard', 'reference'], 'K')
    order = ['main', 'standard', 'other', 'reference']
    files = [(name, ws.store.get_data_by_id(name)) for name in order]
    tr = signals(PlotManager().create_multi_file_plot({'chromatogram': files}, 'stacked'))
    assert [tr[name].yaxis for name in order] == ['y', 'y2', 'y3', 'y2']
