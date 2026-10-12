"""Browser-side plot switching: wiring of the clientside callbacks and JS/Python parity."""
import json
import shutil
import subprocess
from pathlib import Path

import dash
import pytest

from callbacks import plot_settings_callbacks as module
from services.data_store import DataStore
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS

SCRIPT = Path(__file__).resolve().parent.parent / 'src' / 'assets' / 'js' / 'plot-settings-cache.js'
NODE = shutil.which('node')


def build(store=None):
    store = store or DataStore()
    store._shared_plot_settings = {}
    app = dash.Dash(__name__)
    module.register_plot_settings_callbacks(app, store)
    return app, store


def entries(app):
    server = {v['callback'].__wrapped__.__name__: v for v in app.callback_map.values() if v.get('callback')}
    client = [v for v in app.callback_map.values() if not v.get('callback')]
    return server, client


def output_ids(entry):
    outputs = entry['output']
    outputs = outputs if isinstance(outputs, list) else [outputs]
    return [(o.component_id, o.component_property) for o in outputs]


def client_entry(app, first_output):
    return next(v for v in entries(app)[1] if output_ids(v)[0] == first_output)


def test_hydrated_control_list_matches_the_server_hydrator_order():
    app, _ = build()
    server_outputs = output_ids(entries(app)[0]['hydrate_plot_settings'])
    series_builder = {'y1-series-count', 'y1-series-container', 'y1-count'}
    controls = tuple(o for o in server_outputs[1:] if o[0] not in series_builder)
    assert controls == module.HYDRATED_CONTROLS


def test_switching_is_clientside_and_the_server_hydrator_only_serves_cache_misses():
    app, _ = build()
    server, _ = entries(app)
    assert server['hydrate_plot_settings']['inputs'] == [{'id': 'plot-settings-miss', 'property': 'data'}]
    assert server['persist_plot_settings']['inputs'] == [{'id': 'plot-settings-persist', 'property': 'data'}]
    assert 'resolve_plot_context' not in server and 'update_panel_visibility' not in server


def test_clientside_hydrator_writes_the_same_controls_and_reads_their_current_values():
    app, _ = build()
    hydrate = client_entry(app, ('current-plot-settings', 'data'))
    assert output_ids(hydrate) == ([('current-plot-settings', 'data')] + list(module.HYDRATED_CONTROLS)
                                   + [('plot-settings-miss', 'data')])
    assert hydrate['inputs'] == [{'id': 'active-plot-context', 'property': 'data'}]
    states = [(s['id'], s['property']) for s in hydrate['state']]
    live = [c for c in module.HYDRATED_CONTROLS if c[0] not in module.HIDDEN_ECHO_CONTROLS]
    assert states == [('plot-settings-cache', 'data'), ('y1-series-count', 'data')] + live


def test_every_hydrated_control_is_a_user_edit_input_except_the_hidden_mirrors():
    app, _ = build()
    edit_inputs = {(i['id'], i['property']) for i in entries(app)[0]['user_edit_settings']['inputs']}
    live = {c for c in module.HYDRATED_CONTROLS if c[0] not in module.HIDDEN_ECHO_CONTROLS}
    assert live <= edit_inputs


def test_cache_gate_listens_to_settings_and_file_list_and_feeds_the_persister():
    app, _ = build()
    gate = client_entry(app, ('plot-settings-cache', 'data'))
    assert output_ids(gate) == [('plot-settings-cache', 'data'), ('plot-settings-persist', 'data')]
    assert [i['id'] for i in gate['inputs']] == ['current-plot-settings', 'loaded-files']


def test_panel_gate_reads_every_context_panel():
    app, _ = build()
    gate = client_entry(app, ('plot-panel-sync', 'data'))
    assert [s['id'] for s in gate['state']] == ['plot-panel-sync', *module.CONTEXT_PANELS]


def test_context_menu_panels_sync_through_the_gate_not_the_raw_settings_input():
    from callbacks.plot_context_menu_callbacks import register_plot_context_menu_callbacks
    app = dash.Dash(__name__)
    register_plot_context_menu_callbacks(app, DataStore())
    server, _ = entries(app)
    for name in ('open_or_sync_axis_panel', 'open_or_sync_legend_panel', 'open_or_sync_trace_panel',
                 'open_or_sync_title_panel', 'open_or_sync_label_panel', 'sync_toolbox_axis_controls',
                 'sync_toolbox_legend_controls'):
        ids = [i['id'] for i in server[name]['inputs']]
        assert 'current-plot-settings' not in ids, name
        assert 'plot-panel-sync' in ids, name
        assert ('current-plot-settings', 'data') in [(s['id'], s['property']) for s in server[name]['state']], name


def test_panel_sync_callbacks_still_return_nothing_while_closed_and_sync_while_open():
    from callbacks.plot_context_menu_callbacks import register_plot_context_menu_callbacks
    app = dash.Dash(__name__)
    register_plot_context_menu_callbacks(app, DataStore())
    server, _ = entries(app)
    sync = server['sync_toolbox_legend_controls']['callback'].__wrapped__
    with pytest.raises(dash.exceptions.PreventUpdate):
        sync(1, {'show_legend': False}, {'display': 'none'})
    assert sync(1, {'show_legend': False, 'legend_pos': 'bottom-left'}, {'display': 'block'}) == (False, 'bottom-left')


def test_describe_figure_no_longer_reruns_for_unrelated_setting_edits():
    from callbacks.workspace_callbacks import register_workspace_callbacks
    app = dash.Dash(__name__)
    register_workspace_callbacks(app, DataStore())
    server, _ = entries(app)
    inputs = [i['id'] for i in server['describe_figure']['inputs']]
    assert 'plot-settings-figure-key' in inputs and 'current-plot-settings' not in inputs


# --------------------------------------------------------------------------
# JS <-> Python parity (the browser re-implements the hydrator, so keep it honest)
# --------------------------------------------------------------------------

SAVED_CASES = [
    {},
    {'x_label': 'Wavelength / nm'},
    {'y1_label': 'Absorbance', 'axis_label_modes': {'y': 'auto'}},
    {'line_width': 3, 'show_frame': False, 'show_grid_x': True, 'plot_type': 'scatter', 'y1_stats': ['mean'],
     'x_min': 1, 'x_max': 9.5, 'auto_range': False, 'y1_series_count': 3, 'theme': 'plotly_dark'},
    {'show_minor_ticks': True, 'legend_pos': 'bottom-left', 'link_x': False, 'title': 'T', 'bold_title': False,
     'layout_mode': 'stacked', 'shared_axis_labels': False, 'subplot_spacing': 0.2, 'trace_overrides': {'a': {'color': '#fff'}},
     'show_raw_points': True, 'y2_enable': True, 'pub_dpi': 600, 'figure_width_mm': 174.5, '_axis_range_revision': 4},
]


def run_js(program, payload):
    code = ("const fs=require('fs'),vm=require('vm');const noUpdate={__no_update:true};"
            "const window={dash_clientside:{no_update:noUpdate,callback_context:{triggered:[]}}};"
            f"vm.runInNewContext(fs.readFileSync({json.dumps(str(SCRIPT))},'utf8'),{{window}});"
            "const c=window.dash_clientside.plotSettingsCache;"
            "const input=JSON.parse(fs.readFileSync(0,'utf8'));" + program)
    result = subprocess.run([NODE, '-e', code], input=json.dumps(payload), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason='node is not installed')


@needs_node
def test_js_hydration_matches_the_server_hydrator_for_every_control():
    app, store = build()
    hydrate = entries(app)[0]['hydrate_plot_settings']
    series_builder = {'y1-series-count', 'y1-series-container', 'y1-count'}
    keep = [i for i, o in enumerate(output_ids(hydrate)) if o[0] not in series_builder]
    expected = []
    for n, saved in enumerate(SAVED_CASES):
        key = f'shared:raw:case{n}'
        if saved:
            module._save_settings(store, key, saved)
        result = hydrate['callback'].__wrapped__(key, None)
        expected.append(json.loads(json.dumps([result[i] for i in keep])))
    cases = [[f'shared:raw:case{n}', saved] for n, saved in enumerate(SAVED_CASES)]
    got = run_js("""
        console.log(JSON.stringify(input.cases.map(([key, saved]) => {
            const s = c.normalize(input.defaults, saved, key);
            return [s].concat(c.controlValues(s));
        })));""", {'cases': cases, 'defaults': DEFAULT_PLOT_SETTINGS})
    assert [len(row) for row in got] == [len(module.HYDRATED_CONTROLS) + 1] * len(SAVED_CASES)
    for want, have in zip(expected, got):
        assert have == want


@needs_node
def test_js_context_resolution_matches_the_python_reference():
    grid = [(f, v, t, p, cur)
            for f in (None, 'file1') for v in (None, 'raw', 'analysis')
            for t in ('data-overview', 'peak-analysis', 'across-samples')
            for p in (None, '', 'tab1')
            for cur in (None, 'shared:raw', 'shared:raw:tab1', 'file:file1:tab1', 'file:file1', 'x')]
    def reference(row):
        result = module.resolve_plot_context(*row)
        return 'NO_UPDATE' if result is dash.no_update else result
    want = [reference(row) for row in grid]
    got = run_js("""
        console.log(JSON.stringify(input.map(r => { const v = c.resolveContext(...r); return v === noUpdate ? 'NO_UPDATE' : v; })));
        """, [list(row) for row in grid])
    assert got == want


@needs_node
def test_js_panel_visibility_matches_the_python_reference():
    cases = [(v, s) for v in (None, 'raw', 'analysis') for s in (
        None, {}, {'_context_key': 'shared:raw:publication-x'}, {'plot_type': 'line'}, {'plot_type': 'scatter'},
        {'plot_type': 'bar', 'auto_range': False}, {'show_legend': False}, {'show_grid_x': True},
        {'show_tick_marks': False, 'show_grid_y': False}, {'show_tick_marks': False, 'show_grid_y': True})]
    want = [json.loads(json.dumps(module.panel_visibility(v, s))) for v, s in cases]
    got = run_js("""
        console.log(JSON.stringify(input.cases.map(([v, s]) => c.panelVisibility(input.defaults, v, s))));
        """, {'cases': [list(case) for case in cases], 'defaults': DEFAULT_PLOT_SETTINGS})
    assert got == want


@needs_node
def test_cached_switch_round_trips_what_the_server_persisted():
    """A settings value cached from an edit hydrates back to the same settings object."""
    app, store = build()
    server = entries(app)[0]
    hydrate = server['hydrate_plot_settings']['callback'].__wrapped__
    first = hydrate('shared:raw:a', None)[0]
    edited = {**first, 'line_width': 4, 'title': 'kept'}
    got = run_js("""
        const cache = {[input.edited._context_key]: input.edited};
        const out = c.hydrate(input.defaults, input.edited._context_key, cache, 1);
        console.log(JSON.stringify(out[0]));""", {'edited': edited, 'defaults': DEFAULT_PLOT_SETTINGS})
    module._save_settings(store, 'shared:raw:a', edited)
    assert got == hydrate('shared:raw:a', None)[0]
