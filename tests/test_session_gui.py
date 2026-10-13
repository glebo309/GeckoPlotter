"""Project (.gecko) GUI: save / open / autosave / restore banner callbacks, called directly with a real DataStore."""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import dash
import pytest
from dash.exceptions import PreventUpdate

from callbacks import session_callbacks as sc
from callbacks.upload_callbacks import register_upload_callbacks
from services import session_files as sf
from services import session_service as ss
from services.data_store import DataStore
from session_helpers import chromatogram_csv, edit_json, load_files
from test_lcms_peak_table import App
from test_session_service import A_NAME, B_NAME, synthetic_store

OUT = {key: i for i, key in enumerate(sc.OPEN_OUTPUT_KEYS)}


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_AUTOSAVE_DIR', str(tmp_path / 'auto'))
    monkeypatch.setattr(sf, 'sessions_temp_dir', lambda: _temp(tmp_path))


def _temp(tmp_path):
    folder = tmp_path / 'stash'
    folder.mkdir(exist_ok=True)
    return folder


def trigger(monkeypatch, prop_id):
    monkeypatch.setattr(sc, 'callback_context', SimpleNamespace(triggered=[{'prop_id': prop_id, 'value': 1}]))


def callbacks(store):
    app = App()
    sc.register_session_callbacks(app, store)
    return app.functions


def client_values(**given):
    return [given.get(key) for key in sc.CLIENT_STATE_KEYS]


SAVED_CLIENT_STATE = dict(
    **{'plot-tabs': [{'id': 'tab-chromatogram_time', 'label': 'Chromatograms', 'type': 'raw',
                      'group_key': ['chromatogram', 'time']}],
       'active-plot-tab': 'tab-chromatogram_time', 'file-order': {'tab-x': {'order': ['b', 'a']}},
       'tab-zoom-memory': {'tab-chromatogram_time': {'x': [1, 2]}}, 'tab-panel-memory': {'tab-chromatogram_time': 'peak-analysis'},
       'current-plot-settings': {'_context_key': 'shared:raw:tab-chromatogram_time', 'layout_mode': 'stacked', 'title': 'T'},
       'plot-settings-cache': {'shared:raw:tab-chromatogram_time': {'title': 'T'}},
       'analysis-tabs.value': 'peak-analysis', 'analysis-dock.value': 'right', 'pda-colormap': 'Magma',
       'integration-baseline.value': 'zero'})


def stored_workspace():
    store, a, b = synthetic_store()
    return store, a, b


def upload_of(data: bytes) -> str:
    return 'data:application/octet-stream;base64,' + base64.b64encode(data).decode()


def result_for(result, key):
    return result[OUT[key]]


def download_bytes(update):
    assert update['base64'] is True
    return base64.b64decode(update['content'])


# --------------------------------------------------------------------------- Save

def test_save_downloads_a_gecko_named_from_the_project_with_the_client_state(monkeypatch):
    store, a, b = stored_workspace()
    save = callbacks(store)['save_project']
    trigger(monkeypatch, 'session-save-btn.n_clicks')
    state = client_values(**SAVED_CLIENT_STATE, **{'active-file': a.bundle_id})
    out = save(1, None, 'Run: 12/3', None, *state)
    download, modal, name, dirty, stamp, hidden, title, body = out
    assert download['filename'] == 'Run_ 12_3.gecko'
    assert (modal, name, dirty) == (False, 'Run: 12/3', False)
    assert stamp['kind'] == 'saved' and ':' in stamp['at']
    assert hidden is dash.no_update                                       # no notes: the message is left alone
    data = download_bytes(download)
    info = ss.inspect_session(data)
    assert info.project_name == 'Run: 12/3' and info.raw_embedded and info.has_client_state
    fresh = DataStore()
    report = ss.restore_session(fresh, data)
    assert report.ok
    assert report.client_state == {**SAVED_CLIENT_STATE, 'active-file': a.bundle_id}
    assert store.session_meta['project_name'] == 'Run: 12/3'              # Save-again keeps name and creation time
    assert store.session_meta['created_at'] == info.created_at


def test_save_of_an_untitled_project_asks_for_a_name_then_saves_with_it(monkeypatch):
    store, *_ = stored_workspace()
    save = callbacks(store)['save_project']
    trigger(monkeypatch, 'session-save-btn.n_clicks')
    out = save(1, None, '', None, *client_values())
    assert out[0] is dash.no_update and out[1] is True                    # name dialog opens, nothing downloaded
    trigger(monkeypatch, 'session-name-confirm.n_clicks')
    empty = save(1, 1, '', '   ', *client_values())
    assert empty[0] is dash.no_update and empty[1] is True                # still asks while the field is blank
    out = save(1, 2, '', '  Ala series ', *client_values())
    assert out[0]['filename'] == 'Ala series.gecko' and out[1] is False and out[2] == 'Ala series'


def test_save_refuses_an_empty_workspace_politely(monkeypatch):
    save = callbacks(DataStore())['save_project']
    trigger(monkeypatch, 'session-save-btn.n_clicks')
    out = save(1, None, 'x', None, *client_values())
    assert out[0] is dash.no_update and out[4]['kind'] == 'failed' and out[5] is False and out[6] == 'Nothing to save yet'


def test_filename_sanitising():
    assert sf.safe_project_filename('My run: 12/3') == 'My run_ 12_3.gecko'
    assert sf.safe_project_filename('../../etc/passwd') == 'etc_passwd.gecko'
    assert sf.safe_project_filename('  ') == 'project.gecko' and sf.safe_project_filename(None) == 'project.gecko'
    assert sf.safe_project_filename('Ålänin 5 mM (rep 2)') == 'Ålänin 5 mM (rep 2).gecko'
    assert len(sf.safe_project_filename('x' * 300)) <= 80 + len('.gecko')
    assert sf.is_session_filename('A.GECKO') and not sf.is_session_filename('a.csv') and not sf.is_session_filename(None)


# --------------------------------------------------------------------------- Open

def saved_project(**state):
    store, a, b = stored_workspace()
    data = ss.build_session(store, {**SAVED_CLIENT_STATE, 'active-file': a.bundle_id, **state}, project_name='Ala series')
    return store, a, b, data


def test_open_restores_the_workspace_and_every_client_store(monkeypatch):
    original, a, b, data = saved_project()
    target = DataStore()
    fns = callbacks(target)
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(data), None, None, None, None, 'Ala series.gecko', None, None, None, 7)
    assert len(out) == len(sc.OPEN_OUTPUT_KEYS)
    assert [f['id'] for f in result_for(out, 'loaded-files.data')] == [a.bundle_id, b.bundle_id]
    assert result_for(out, 'active-file.data') == a.bundle_id
    assert result_for(out, 'render-trigger.data') == 8
    assert result_for(out, 'pt-layout-mode.value') == 'stacked'
    assert result_for(out, 'plot-tabs.data') == SAVED_CLIENT_STATE['plot-tabs']
    assert result_for(out, 'active-plot-tab.data') == 'tab-chromatogram_time'
    assert result_for(out, 'file-order.data') == SAVED_CLIENT_STATE['file-order']
    assert result_for(out, 'tab-zoom-memory.data') == SAVED_CLIENT_STATE['tab-zoom-memory']
    assert result_for(out, 'current-plot-settings.data') == SAVED_CLIENT_STATE['current-plot-settings']
    assert result_for(out, 'analysis-tabs.value') == 'peak-analysis'
    assert result_for(out, 'analysis-dock.value') == 'right'
    assert result_for(out, 'pda-colormap.data') == 'Magma'
    assert result_for(out, 'integration-baseline.value') == 'zero'
    # Stores the file does not mention are reset (nothing of the previous workspace survives) or left as the user has them.
    assert result_for(out, 'zoom-state.data') is None and result_for(out, 'custom-plot-figures.data') == {}
    assert result_for(out, 'toolbox-tab.data') is dash.no_update
    assert b.bundle_id in result_for(out, 'hidden-files.data')            # derived from the restored visibility state
    assert result_for(out, 'session-name.data') == 'Ala series'
    assert result_for(out, 'session-dirty.data') is False
    assert result_for(out, 'session-stamp.data')['kind'] == 'opened'
    late = result_for(out, 'session-restore-late.data')
    assert late['active_plot_tab'] == 'tab-chromatogram_time' and late['plot_settings_cache']
    assert result_for(out, 'session-banner.hidden') is True
    assert result_for(out, 'session-message.hidden') is True               # nothing to report
    assert result_for(out, 'session-missing-modal.opened') is False
    assert result_for(out, 'session-source.data') is None
    # The server workspace is the saved one, with the saved ids and peaks.
    assert [x.bundle_id for x in target.iter_bundles()] == [a.bundle_id, b.bundle_id]
    assert target.peak_service.serialize() == original.peak_service.serialize()
    assert not list(_temp(Path(os.environ['GECKO_AUTOSAVE_DIR']).parent).iterdir()), 'temp copy removed when complete'


def test_open_onto_a_busy_workspace_replaces_it_and_ignores_a_stale_active_file(monkeypatch):
    _, a, b, data = saved_project(**{'active-file': 'gone-id'})
    busy = DataStore()
    load_files(busy, [('other.csv', chromatogram_csv([2.0]))])
    fns = callbacks(busy)
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(data), None, None, None, None, 'p.gecko', None, None, None, 0)
    assert {x.bundle_id for x in busy.iter_bundles()} == {a.bundle_id, b.bundle_id}
    fallback = result_for(out, 'active-file.data')
    assert fallback and fallback != 'gone-id'
    assert busy.get_data_by_id(fallback) or busy.get_bundle(fallback)


def test_open_rejects_a_bad_file_and_leaves_the_workspace_alone(monkeypatch):
    busy, a, b = stored_workspace()
    fns = callbacks(busy)
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(b'not a zip'), None, None, None, None, 'x.gecko', None, None, None, 0)
    assert result_for(out, 'session-message.hidden') is False
    assert 'not a GeckoPlotter session' in result_for(out, 'session-message-body.children')
    assert result_for(out, 'session-stamp.data')['kind'] == 'failed'
    assert result_for(out, 'loaded-files.data') is dash.no_update
    assert [x.bundle_id for x in busy.iter_bundles()] == [a.bundle_id, b.bundle_id]
    too_new = edit_json(saved_project()[3], 'manifest.json', lambda m: m.update(schema_version=99))
    out = fns['open_project'](upload_of(too_new), None, None, None, None, 'new.gecko', None, None, None, 0)
    assert 'newer version of GeckoPlotter' in result_for(out, 'session-message-body.children')
    assert len(list(busy.iter_bundles())) == 2


def test_open_failing_after_the_reset_rolls_back_and_rebuilds_every_output_from_the_store(monkeypatch):
    _, a, b, data = saved_project()
    busy = DataStore()
    (other,) = load_files(busy, [('other.csv', chromatogram_csv([2.0]))])
    fns = callbacks(busy)
    real, calls = ss._apply_state, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('boom')
        return real(*args, **kwargs)
    monkeypatch.setattr(ss, '_apply_state', flaky)
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(data), None, None, None, None, 'p.gecko', None, None, None, 0)
    assert [x.bundle_id for x in busy.iter_bundles()] == [other.bundle_id]          # previous workspace is back
    assert result_for(out, 'loaded-files.data') == busy.get_loaded_files_list()      # outputs rebuilt from the store
    assert result_for(out, 'file-tree.children') is not dash.no_update
    assert result_for(out, 'session-message.hidden') is False
    assert 'boom' in str(result_for(out, 'session-message-body.children'))
    assert result_for(out, 'session-stamp.data')['kind'] == 'failed'
    assert result_for(out, 'session-name.data') is dash.no_update


def test_open_failing_after_the_reset_without_a_snapshot_still_rebuilds_from_the_store(monkeypatch):
    _, a, b, data = saved_project()
    busy = DataStore()
    load_files(busy, [('other.csv', chromatogram_csv([2.0]))])
    fns = callbacks(busy)
    monkeypatch.setattr(ss, 'ROLLBACK_MAX_BYTES', 0)
    monkeypatch.setattr(ss, '_apply_state', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(data), None, None, None, None, 'p.gecko', None, None, None, 0)
    assert {x.bundle_id for x in busy.iter_bundles()} == {a.bundle_id, b.bundle_id}
    assert result_for(out, 'loaded-files.data') == busy.get_loaded_files_list()
    assert len(result_for(out, 'loaded-files.data')) == 2
    assert result_for(out, 'file-tree.children') is not dash.no_update
    assert result_for(out, 'session-message.hidden') is False


def test_missing_originals_open_the_locate_dialog_and_retry_finds_them(monkeypatch, tmp_path):
    store, a, b = stored_workspace()
    data = ss.build_session(store, {'active-plot-tab': 'tab-chromatogram_time'}, project_name='Big', embed_raw=False)
    fns = callbacks(DataStore())
    trigger(monkeypatch, 'session-open-upload.contents')
    out = fns['open_project'](upload_of(data), None, None, None, None, 'Big.gecko', None, None, None, 0)
    assert result_for(out, 'session-missing-modal.opened') is True
    listing = result_for(out, 'session-missing-list.children')
    assert len(listing) == 2 and A_NAME in str(listing) and B_NAME in str(listing)
    source = result_for(out, 'session-source.data')
    assert source and Path(source['path']).exists()                         # kept for Retry
    assert result_for(out, 'session-message.hidden') is False               # the warning is also listed
    # Retry without a folder: still missing, still offered.
    trigger(monkeypatch, 'session-retry-btn.n_clicks')
    out = fns['open_project'](None, None, None, None, 1, None, source, '  ', None, 0)
    assert result_for(out, 'session-missing-modal.opened') is True
    # Retry with the folder that holds the raw data.
    folder = tmp_path / 'raw data'
    folder.mkdir()
    (folder / A_NAME).write_bytes(chromatogram_csv([3.0, 6.0]))
    (folder / B_NAME).write_bytes(chromatogram_csv([3.05, 6.1], amplitude=70.0))
    out = fns['open_project'](None, None, None, None, 2, None, source, str(folder), None, 0)
    assert result_for(out, 'session-missing-modal.opened') is False
    assert result_for(out, 'session-source.data') is None
    assert len(result_for(out, 'loaded-files.data')) == 2
    assert not Path(source['path']).exists()


def test_recent_pick_and_banner_restore_open_autosaves_by_path(monkeypatch):
    store, a, b = stored_workspace()
    path = ss.save_autosave(store, {'active-plot-tab': 'tab-chromatogram_time'})
    fns = callbacks(DataStore())
    trigger(monkeypatch, 'session-recent-pick.data')
    out = fns['open_project'](None, None, {'path': str(path), 'ts': 1}, None, None, None, None, None, None, 0)
    assert len(result_for(out, 'loaded-files.data')) == 2
    assert result_for(out, 'session-name.data') == ''                      # 'Autosave' is not a project name
    trigger(monkeypatch, 'session-recent-pick.data')
    with pytest.raises(PreventUpdate):                                      # only .gecko paths are accepted
        fns['open_project'](None, None, {'path': '/etc/passwd'}, None, None, None, None, None, None, 0)
    trigger(monkeypatch, 'session-banner-restore.n_clicks')
    fresh = DataStore()
    out = callbacks(fresh)['open_project'](None, None, None, 1, None, None, None, None, str(path), 3)
    assert len(list(fresh.iter_bundles())) == 2 and result_for(out, 'session-banner.hidden') is True
    assert path.exists(), 'restoring never deletes the autosave'


def test_gecko_in_the_file_import_zones_is_routed_to_open_not_ingested(monkeypatch):
    store = DataStore()
    app = App()
    register_upload_callbacks(app, store)
    _, _, _, data = saved_project()
    out = app.functions['handle_file_upload']([upload_of(data)], ['Run 1.GECKO'], [0], [], 0)
    assert len(out) == 9 and all(x is dash.no_update for x in out[:8])
    handoff = out[8]
    assert handoff['name'] == 'Run 1' and handoff['upload'] and Path(handoff['path']).read_bytes() == data
    assert not list(store.iter_bundles())
    for name in ('handle_drop_upload', 'handle_global_drop_upload'):
        out = app.functions[name]([upload_of(data), upload_of(b'x')], ['p.gecko', 'a.csv'], [0, 0], [], 0)
        assert out[8]['path'] and all(x is dash.no_update for x in out[:8])
    # And that handoff opens the project.
    trigger(monkeypatch, 'session-upload-handoff.data')
    fresh = DataStore()
    out = callbacks(fresh)['open_project'](None, handoff, None, None, None, None, None, None, None, 0)
    assert len(result_for(out, 'loaded-files.data')) == 2


def test_fair_package_zip_is_routed_to_open_and_opens_the_project(monkeypatch):
    from services.research_package import build_research_package
    store = DataStore()
    app = App()
    register_upload_callbacks(app, store)
    source, _, _ = stored_workspace()
    package = build_research_package(source, {'title': 'Deposit'}, None, [])
    out = app.functions['handle_file_upload']([upload_of(package)], ['Deposit.zip'], [0], [], 0)
    assert all(x is dash.no_update for x in out[:8]) and out[8]['path'].endswith('.zip')
    assert not list(store.iter_bundles())
    handoff = out[8]
    trigger(monkeypatch, 'session-upload-handoff.data')
    fresh = DataStore()
    out = callbacks(fresh)['open_project'](None, handoff, None, None, None, None, None, None, None, 0)
    assert len(result_for(out, 'loaded-files.data')) == 2
    assert result_for(out, 'session-name.data') == 'Deposit'
    assert not Path(handoff['path']).exists()                              # temp copy is dropped after opening


def test_ordinary_files_still_load_through_the_upload_callback(monkeypatch):
    import src.ingestion as real_ingestion      # tests/ingestion would shadow the package the callback imports
    monkeypatch.setitem(sys.modules, 'ingestion', real_ingestion)
    store = DataStore()
    app = App()
    register_upload_callbacks(app, store)
    content = 'data:text/csv;base64,' + base64.b64encode(chromatogram_csv([3.0])).decode()
    out = app.functions['handle_file_upload']([content], ['one.csv'], [0], [], 4)
    assert len(out) == 9 and out[6] == 5 and out[8] is dash.no_update and len(list(store.iter_bundles())) == 1


# ------------------------------------------------------------------------- Autosave

def test_autosave_writes_silently_with_the_client_state_and_skips_an_empty_workspace(monkeypatch, tmp_path):
    with pytest.raises(PreventUpdate):
        callbacks(DataStore())['autosave_project'](123, '', *client_values())
    store, a, b = stored_workspace()
    auto = callbacks(store)['autosave_project']
    with pytest.raises(PreventUpdate):
        auto(None, '', *client_values())
    stamp = auto(1700000000000, 'My project', *client_values(**{'active-plot-tab': 'tab-a'}))
    assert stamp['kind'] == 'autosaved' and stamp['fired'] == 1700000000000
    path = ss.latest_autosave()
    info = ss.inspect_session(path)
    assert info.project_name == 'My project' and info.raw_cache and not info.raw_embedded
    assert ss.restore_session(DataStore(), path).client_state == {'active-plot-tab': 'tab-a'}
    for _ in range(7):                                                      # keeps the last five
        auto(1, '', *client_values())
        os.utime(ss.latest_autosave(), (1_000_000 + _, 1_000_000 + _))
    assert len(list((tmp_path / 'auto').glob('*.gecko'))) == 5
    # The 7th autosave of an unchanged workspace reuses the cached originals instead of rewriting them.
    cached = {p.name: p.stat().st_mtime_ns for p in (tmp_path / 'auto' / 'raw').iterdir()}
    auto(2, '', *client_values())
    assert {p.name: p.stat().st_mtime_ns for p in (tmp_path / 'auto' / 'raw').iterdir()} == cached


def test_autosave_failure_is_reported_not_raised(monkeypatch):
    store, *_ = stored_workspace()
    monkeypatch.setattr(ss, 'save_autosave', lambda *a, **k: (_ for _ in ()).throw(OSError('disk full')))
    stamp = callbacks(store)['autosave_project'](5, '', *client_values())
    assert stamp['kind'] == 'failed' and stamp['message'] == 'Autosave failed'


# ------------------------------------------------------------ Page load / banner

def _age(path, days):
    """Rewrite the manifest so the autosave looks `days` old."""
    from datetime import datetime, timedelta, timezone
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds')
    path.write_bytes(edit_json(path.read_bytes(), 'manifest.json', lambda m: m.update(saved_at=when)))


def test_page_load_offers_restore_only_for_a_fresh_autosave_and_an_empty_workspace():
    store, *_ = stored_workspace()
    ss.save_autosave(store, {})
    check = callbacks(DataStore())['check_last_session']
    hidden, text, target, recent = check(0)
    assert hidden is False
    assert text == 'Restore last session? 2 samples, saved just now'
    assert target == str(ss.latest_autosave())
    assert recent[0].to_plotly_json()['props']['data-session-recent'] == target
    # A non-empty workspace never gets the banner (the recent list is still there).
    busy_hidden, _, busy_target, busy_recent = callbacks(store)['check_last_session'](0)
    assert busy_hidden is True and busy_target is None and busy_recent
    # Older than 14 days: no banner.
    _age(ss.latest_autosave(), 15)
    assert callbacks(DataStore())['check_last_session'](0)[0] is True
    _age(ss.latest_autosave(), 13)
    assert callbacks(DataStore())['check_last_session'](0)[0] is False


def test_page_load_without_any_autosave_shows_nothing_and_never_creates_the_folder(tmp_path):
    hidden, text, target, recent = callbacks(DataStore())['check_last_session'](0)
    assert hidden is True and target is None and not (tmp_path / 'auto').exists()
    assert recent.children == 'None yet'


def test_humanized_age():
    assert sf.humanize_age(5) == 'just now'
    assert sf.humanize_age(12 * 60) == '12 min ago'
    assert sf.humanize_age(3 * 3600) == '3 h ago'
    assert sf.humanize_age(86400) == '1 day ago' and sf.humanize_age(3 * 86400) == '3 days ago'
    assert sf.humanize_age(None) == 'a while ago'


# ------------------------------------------------------------------ client_state

def test_client_state_covers_the_screen_and_excludes_transient_selections():
    keys = set(sc.CLIENT_STATE_KEYS)
    assert {'plot-tabs', 'active-plot-tab', 'active-file', 'hidden-files', 'file-order', 'zoom-state', 'tab-zoom-memory',
            'tab-panel-memory', 'current-plot-settings', 'plot-settings-cache', 'pda-colormap', 'analysis-tabs.value',
            'analysis-dock.value', 'custom-plot-figures'} <= keys
    assert not {'file-multi-selection', 'rendered-plot-tabs', 'selected-peak-idx', 'render-trigger'} & keys
    assert sc.gather_client_state([None, 'x'] + [None] * (len(sc.CLIENT_STATE_KEYS) - 2)) == {'active-plot-tab': 'x'}


# ------------------------------------------------------------------------ layout

@pytest.fixture(scope='module')
def layout_facts():
    script = '''
import json
import app
from components.workspace_layout import walk
nodes = list(walk(app.app.layout))
ids = {n.id for n in nodes if isinstance(getattr(n, 'id', None), str)}
def strip(i):
    return i.split('@')[0]
referenced = set()
mine = []
for cb in app.app._callback_list:
    outputs = [strip(o.rsplit('.', 1)[0]) for o in (cb['output'][2:-2].split('...') if cb['output'].startswith('..') else [cb['output']])]
    deps = [d['id'] for d in cb['inputs'] + cb.get('state', []) if isinstance(d['id'], str)]
    if any(x.startswith('session-') for x in outputs + deps):
        referenced.update(strip(x) for x in outputs + deps)
        mine.append(cb['output'][:40])
print(json.dumps({
    'ids': sorted(ids), 'missing': sorted(referenced - ids), 'count': len(mine),
    'types': sorted({type(n).__name__ for n in nodes}),
    'menu_hidden': next(n.hidden for n in nodes if getattr(n, 'id', None) == 'session-open-menu'),
    'banner_hidden': next(n.hidden for n in nodes if getattr(n, 'id', None) == 'session-banner'),
    'upload_accept': next(n.accept for n in nodes if getattr(n, 'id', None) == 'session-open-upload'),
    'header': [getattr(n, 'id', None) for n in walk(next(n for n in nodes if getattr(n, 'className', '') == 'app-header'))
               if isinstance(getattr(n, 'id', None), str)],
    'status_bar': [getattr(n, 'id', None) for n in walk(next(n for n in nodes if getattr(n, 'className', '') == 'status-bar'))
                   if isinstance(getattr(n, 'id', None), str)],
    'legacy': [i for i in ids if i.startswith('exp-session')],
}))
'''
    out = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_layout_has_the_project_controls_in_the_header(layout_facts):
    header = layout_facts['header']
    assert 'session-status' in layout_facts['status_bar'] and 'session-status' not in header   # bottom status bar
    for needed in ('session-bar', 'session-name-btn', 'session-open-upload', 'session-open-btn',
                   'session-open-menu', 'session-recent-list', 'session-save-btn'):
        assert needed in header, needed
    assert layout_facts['upload_accept'] == '.gecko,.zip'   # .zip: a FAIR package that holds a project
    assert layout_facts['menu_hidden'] is True and layout_facts['banner_hidden'] is True
    ids = set(layout_facts['ids'])
    assert {'session-name', 'session-dirty', 'session-stamp', 'session-source', 'session-upload-handoff',
            'session-autosave-fire', 'session-download', 'session-name-modal', 'session-name-input',
            'session-missing-modal', 'session-search-dir', 'session-retry-btn', 'session-banner',
            'session-banner-restore', 'session-banner-dismiss', 'session-message', 'session-confirm',
            'session-confirm-text'} <= ids
    assert not layout_facts['legacy'], 'the old placeholder Save/Load Session stubs are gone'


def test_every_component_the_project_callbacks_use_exists_and_no_slow_mantine_types_were_added(layout_facts):
    assert layout_facts['missing'] == []
    assert layout_facts['count'] >= 12
    assert not {'Menu', 'MenuDropdown', 'MenuItem', 'MenuTarget', 'MenuDivider', 'Tooltip'} & set(layout_facts['types'])
    assert 'Modal' in layout_facts['types']


def test_integration_inspector_keeps_every_section_in_order():
    script = r'''
import json, sys
sys.path.insert(0, 'src'); sys.path.insert(0, '.')
import app
nodes = {}
def walk(n):
    yield n
    for c in (getattr(n, 'children', None) if isinstance(getattr(n, 'children', None), (list, tuple)) else [getattr(n, 'children', None)]):
        if hasattr(c, 'to_plotly_json'):
            yield from walk(c)
ids = {n.id for n in walk(app._layout_body) if isinstance(getattr(n, 'id', None), str)}
box = next(n for n in walk(app._layout_body) if getattr(n, 'id', None) == 'integration-container')
print(json.dumps({'classes': [str(getattr(c, 'className', '')) for c in box.children],
                  'ids': [i for i in ('deconv-btn', 'deconv-results-container', 'deconv-accept-btn', 'deconv-cancel-btn',
                                      'recipe-save-btn', 'recipe-apply-upload', 'int-display-opts') if i in ids]}))
'''
    out = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True,
                         cwd=str(Path(__file__).resolve().parents[1])).stdout
    facts = json.loads(out.strip().splitlines()[-1])
    classes = [c.split()[-1] if c else '' for c in facts['classes']]
    assert classes.index('integration-deconv') < classes.index('integration-recipe') < classes.index('integration-display')
    assert len(facts['ids']) == 7                       # nothing the callbacks write to is missing
