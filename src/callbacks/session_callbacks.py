"""Save / Open / autosave of project (.gecko) files.

The engine is ``services/session_service.py``; this module is the Dash glue. Server round trips are limited to
Save, Open, autosave and one check at page load. Everything else (dirty flag, status text, debounce, keyboard,
rename) is clientside, see ``assets/js/session-io.js``. Format and decisions: ``docs/SESSION_FORMAT.md``.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import dash
from dash import ClientsideFunction, Input, Output, State, callback_context, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import session_service as ss
from services import session_files as sf

log = logging.getLogger(__name__)

_KEEP = object()   # restore leaves the control as the user has it when the file does not say

# What the browser holds that belongs to "the same screen": (client_state key, component id, property, restore default).
# The key is the component id for ``data`` properties and ``id.property`` otherwise. The restore default is what a
# file without that key resets the store to (so nothing of the previous workspace survives), or _KEEP.
# Not captured on purpose: file-multi-selection (a transient selection), rendered-plot-tabs and the figures
# themselves (recomputed), selected-peak/menu/trigger stores (transient), undo state.
CLIENT_STATE_STORES = [
    ('plot-tabs', 'plot-tabs', 'data', []),
    ('active-plot-tab', 'active-plot-tab', 'data', None),
    ('active-file', 'active-file', 'data', None),
    ('hidden-files', 'hidden-files', 'data', []),
    ('file-order', 'file-order', 'data', {}),
    ('zoom-state', 'zoom-state', 'data', None),
    ('tab-zoom-memory', 'tab-zoom-memory', 'data', {}),
    ('tab-panel-memory', 'tab-panel-memory', 'data', {}),
    ('tab-file-memory', 'tab-file-memory', 'data', {}),
    ('current-plot-settings', 'current-plot-settings', 'data', {}),
    ('plot-settings-cache', 'plot-settings-cache', 'data', None),   # applied late by session-io.js
    ('pda-colormap', 'pda-colormap', 'data', _KEEP),
    ('analysis-tabs.value', 'analysis-tabs', 'value', _KEEP),
    ('side-tabs.value', 'side-tabs', 'value', _KEEP),
    ('analysis-dock.value', 'analysis-dock', 'value', _KEEP),
    ('custom-plot-figures', 'custom-plot-figures', 'data', {}),
    ('custom-plot-counter', 'custom-plot-counter', 'data', 0),
    ('toolbox-tab', 'toolbox-tab', 'data', _KEEP),
    ('integration-baseline.value', 'integration-baseline', 'value', _KEEP),
    ('int-display-opts.value', 'int-display-opts', 'value', _KEEP),
]
CLIENT_STATE_KEYS = [spec[0] for spec in CLIENT_STATE_STORES]
# Written back by the Open callback directly. 'active-file' and 'hidden-files' are derived from the restored server
# state (validated); the settings cache is applied late so the browser's own flush on `loaded-files` cannot eat it.
_RESTORE_OUTPUTS = [spec for spec in CLIENT_STATE_STORES
                    if spec[0] not in ('active-file', 'hidden-files', 'plot-settings-cache')]

# Stores whose change means "the project changed" (documented here, enforced in session-io.js).
CHANGE_INPUTS = ['loaded-files', 'peak-change-trigger', 'current-plot-settings', 'file-order', 'plot-tabs',
                 'cal-revision', 'hidden-files']

AUTOSAVE_MAX_AGE_DAYS = sf.AUTOSAVE_MAX_AGE_DAYS


def gather_client_state(values: Sequence[Any]) -> Dict[str, Any]:
    """Zip the States of :data:`CLIENT_STATE_STORES` into the ``client_state`` dict (``None`` entries are left out)."""
    return {key: value for key, value in zip(CLIENT_STATE_KEYS, values) if value is not None}


def _clock() -> str:
    return datetime.now().strftime('%H:%M')


def _stamp(kind: str, **extra) -> Dict[str, Any]:
    return {'kind': kind, 'at': _clock(), 'ts': int(time.time() * 1000), **extra}


def _has_data(store) -> bool:
    return next(iter(store.iter_bundles()), None) is not None


def _state_inputs():
    return [State(cid, prop) for _, cid, prop, _ in CLIENT_STATE_STORES]


def _notes(items: Sequence[str], limit: int = 12):
    shown = [html.Li(str(text)) for text in list(items)[:limit]]
    if len(items) > limit:
        shown.append(html.Li(f'… and {len(items) - limit} more'))
    return html.Ul(shown, className='session-message-list')


def _size_text(size: Optional[int]) -> str:
    if not size:
        return ''
    for unit, scale in (('MB', 1e6), ('kB', 1e3)):
        if size >= scale:
            return f' ({size / scale:.1f} {unit})'
    return f' ({size} B)'


def missing_items(missing_files: Sequence[dict]):
    return [html.Li([html.Strong(m['name']), _size_text(m.get('size')),
                     ' – used by ' + (', '.join(m.get('bundles') or []) or 'a sample'),
                     html.Div(m['original_path'], className='session-missing-path') if m.get('original_path') else None])
            for m in missing_files]


# Output order of the Open callback.
_OPEN_CORE = [('loaded-files', 'data'), ('file-tree', 'children'), ('active-file', 'data'),
              ('metadata-container', 'children'), ('table-editor-container', 'children'),
              ('pub-data-store', 'data'), ('render-trigger', 'data'), ('pt-layout-mode', 'value'),
              ('hidden-files', 'data')]
_OPEN_SESSION = [('session-name', 'data'), ('session-dirty', 'data'), ('session-stamp', 'data'),
                 ('session-source', 'data'), ('session-restore-late', 'data'), ('session-banner', 'hidden'),
                 ('session-message', 'hidden'), ('session-message-title', 'children'),
                 ('session-message-body', 'children'), ('session-missing-modal', 'opened'),
                 ('session-missing-list', 'children'),
                 ('session-open-upload', 'contents')]   # cleared so choosing the same file again fires again
OPEN_OUTPUT_KEYS = ([f'{cid}.{prop}' for cid, prop in _OPEN_CORE]
                    + [f'{cid}.{prop}' for _, cid, prop, _ in _RESTORE_OUTPUTS]
                    + [f'{cid}.{prop}' for cid, prop in _OPEN_SESSION])


def _ordered_open_outputs(values: Dict[str, Any]) -> tuple:
    values = {'session-open-upload.contents': None, **values}
    return tuple(values.get(key, no_update) for key in OPEN_OUTPUT_KEYS)


def _failure_outputs(title: str, body, stamp_message: str) -> tuple:
    return _ordered_open_outputs({
        'session-stamp.data': _stamp('failed', message=stamp_message),
        'session-message.hidden': False,
        'session-message-title.children': title,
        'session-message-body.children': body,
    })


def register_session_callbacks(app, data_manager) -> None:
    """Register the project callbacks. ``app`` only needs ``callback`` and ``clientside_callback``."""

    # ------------------------------------------------------------------ Save
    @app.callback(
        [Output('session-download', 'data'),
         Output('session-name-modal', 'opened'),
         Output('session-name', 'data'),
         Output('session-dirty', 'data', allow_duplicate=True),
         Output('session-stamp', 'data'),
         Output('session-message', 'hidden'),
         Output('session-message-title', 'children'),
         Output('session-message-body', 'children')],
        [Input('session-save-btn', 'n_clicks'),
         Input('session-name-confirm', 'n_clicks')],
        [State('session-name', 'data'),
         State('session-name-input', 'value')] + _state_inputs(),
        prevent_initial_call=True,
    )
    def save_project(save_clicks, confirm_clicks, name, name_input, *client_values):
        """Download the project as ``<name>.gecko`` (self-contained: originals embedded)."""
        triggered = (callback_context.triggered or [{}])[0].get('prop_id', '').split('.')[0]
        if triggered not in ('session-save-btn', 'session-name-confirm'):
            raise PreventUpdate
        def only(**changes):
            order = ('download', 'modal', 'name', 'dirty', 'stamp', 'hidden', 'title', 'body')
            return tuple(changes.get(key, no_update) for key in order)

        if not _has_data(data_manager):
            return only(stamp=_stamp('failed', message='Nothing to save yet'), hidden=False,
                        title='Nothing to save yet', body='Load some data first, then save the project.')
        chosen = ((name_input if triggered == 'session-name-confirm' else name) or '').strip()
        if not chosen:
            return only(modal=True)   # first save of an untitled project: ask for a name (its Save comes back here)
        try:
            data = ss.build_session(data_manager, gather_client_state(client_values), project_name=chosen)
        except Exception as exc:
            log.exception('Save failed')
            return only(stamp=_stamp('failed', message='Save failed'), hidden=False,
                        title='Could not save the project', body=f'{exc}')
        info = ss.inspect_session(data)
        data_manager.session_meta.update(project_name=chosen, created_at=info.created_at, saved_at=info.saved_at)
        result = dict(download=dcc.send_bytes(data, sf.safe_project_filename(chosen)), modal=False, name=chosen,
                      dirty=False, stamp=_stamp('saved'))
        if info.notes:   # e.g. originals too large to embed: the user must know reopening needs them
            result.update(hidden=False, title='Saved with notes', body=_notes(info.notes))
        return only(**result)

    # ------------------------------------------------------------------ Open
    open_outputs = ([Output(cid, prop, allow_duplicate=True) for cid, prop in _OPEN_CORE]
                    + [Output(cid, prop, allow_duplicate=True) for _, cid, prop, _ in _RESTORE_OUTPUTS]
                    + [Output(cid, prop, allow_duplicate=True) for cid, prop in _OPEN_SESSION])

    @app.callback(
        open_outputs,
        [Input('session-open-upload', 'contents'),
         Input('session-upload-handoff', 'data'),
         Input('session-recent-pick', 'data'),
         Input('session-banner-restore', 'n_clicks'),
         Input('session-retry-btn', 'n_clicks')],
        [State('session-open-upload', 'filename'),
         State('session-source', 'data'),
         State('session-search-dir', 'value'),
         State('session-autosave-target', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def open_project(contents, handoff, recent, banner_clicks, retry_clicks,
                     upload_name, source, search_dir, autosave_target, render_counter):
        """Replace the workspace with a .gecko project and rebuild the screen from it."""
        triggered = (callback_context.triggered or [{}])[0].get('prop_id', '').split('.')[0]
        search_dirs: List[str] = []
        if triggered == 'session-open-upload':
            if not contents:
                raise PreventUpdate
            try:
                new_source = sf.stash_session_upload(contents, upload_name or 'project.gecko')
            except Exception as exc:
                return _failure_outputs('Could not open the file', f'{exc}', 'Could not open the file')
        elif triggered == 'session-upload-handoff':
            if not handoff:
                raise PreventUpdate
            new_source = handoff
        elif triggered == 'session-recent-pick':
            path = (recent or {}).get('path')
            if not path or not sf.is_session_filename(path):
                raise PreventUpdate
            new_source = {'path': path, 'name': Path(path).stem, 'upload': False}
        elif triggered == 'session-banner-restore':
            if not autosave_target:
                raise PreventUpdate
            new_source = {'path': autosave_target, 'name': Path(autosave_target).stem, 'upload': False}
        elif triggered == 'session-retry-btn':
            if not source:
                raise PreventUpdate
            new_source = source
            if (search_dir or '').strip():
                search_dirs.append((search_dir or '').strip())
        else:
            raise PreventUpdate

        if triggered != 'session-retry-btn' and source and source.get('path') != new_source.get('path'):
            sf.forget_stash(source)
        path = new_source['path']
        try:
            report = ss.restore_session(data_manager, path, search_dirs=search_dirs)
        except ss.SessionFormatError as exc:       # bad / too-new file: the workspace was not touched
            sf.forget_stash(new_source)
            return _failure_outputs('Could not open this file', str(exc), 'Could not open the file')
        except Exception as exc:
            log.exception('Open failed')
            sf.forget_stash(new_source)
            return _failure_outputs('Could not open this file', f'Unexpected error: {exc}', 'Could not open the file')
        if new_source.get('upload'):
            data_manager.session_meta.pop('path', None)        # a temp copy is not "the project file"
        # Whenever the store changed (even if the report is not ok) every output is rebuilt from it, so the
        # browser never shows a tree that disagrees with the server.
        return _restore_outputs(report, new_source, render_counter)

    def _restore_outputs(report, source, render_counter):
        from callbacks.upload_callbacks import build_active_file_views, render_file_tree_with_bundles_selected
        from components.data_table_editor import create_data_table_editor
        from services.channel_visibility import visible_component_id
        from services.data_store import BundleType

        restored = report.restored.get('bundles', 0) > 0
        rolled_back = bool(getattr(report, 'rolled_back', False))
        cs = dict(report.client_state or {}) if restored and not rolled_back else {}
        files = data_manager.get_loaded_files_list()
        name = (report.info.project_name or '').strip()
        name = '' if name == 'Autosave' else name
        if not name and source.get('upload'):
            name = source.get('name') or ''

        def exists(file_id):
            return bool(file_id and (data_manager.get_data_by_id(file_id) or data_manager.get_bundle(file_id)))

        active = cs.get('active-file')
        if not exists(active):
            active = None
            bundles = list(data_manager.iter_bundles())
            shown = [b for b in bundles if data_manager.visibility_state.get(b.bundle_id, True)]
            bundles = shown or bundles                  # never open on a hidden sample: its peaks are not drawn
            if bundles:
                last = bundles[-1]
                if last.bundle_type in (BundleType.CHROMATOGRAM, BundleType.LCMS):
                    active = visible_component_id(data_manager, last)
                else:
                    active = last.bundle_id
        table, editor, pub_data = (dash.no_update, create_data_table_editor(None, table_id='pub-table'), None)
        if active:
            table, editor, pub_data = build_active_file_views(data_manager, active)
        else:
            table = html.Div('No file selected', style={'color': '#666', 'padding': '20px', 'textAlign': 'center'})
        tree = render_file_tree_with_bundles_selected(
            files, data_manager, active, active_plot_tab=cs.get('active-plot-tab'), file_order=cs.get('file-order') or {})
        hidden = [fid for fid, visible in data_manager.visibility_state.items() if not visible]
        layout_mode = (cs.get('current-plot-settings') or {}).get('layout_mode')

        values: Dict[str, Any] = {
            'loaded-files.data': files, 'file-tree.children': tree, 'active-file.data': active,
            'metadata-container.children': table, 'table-editor-container.children': editor,
            'pub-data-store.data': pub_data, 'render-trigger.data': (render_counter or 0) + 1,
            'pt-layout-mode.value': layout_mode if layout_mode in ('overlay', 'stacked') else no_update,
            'hidden-files.data': hidden,
        }
        for key, cid, prop, default in _RESTORE_OUTPUTS:
            value = cs.get(key, default)
            # A rolled-back Open put the previous workspace back: the browser's own state still matches it.
            values[f'{cid}.{prop}'] = no_update if value is _KEEP or rolled_back else value

        warnings = list(report.errors) + [w for w in report.warnings if not w.startswith('Original file not found')]
        late = ({'active_plot_tab': cs.get('active-plot-tab'), 'plot_settings_cache': cs.get('plot-settings-cache') or None,
                 'ts': int(time.time() * 1000)} if restored else None)
        if rolled_back:
            title, body = 'Could not open this project', _notes(warnings)
        elif not restored:
            title, body = 'Nothing could be restored', _notes(warnings or ['The project contains no samples.'])
        elif warnings:
            title, body = f"Opened with {sf.plural(len(warnings), 'note')}", _notes(warnings)
        else:
            title, body = '', ''
        needs_files = bool(report.missing_files) and not rolled_back
        if not needs_files:
            sf.forget_stash(source)
        values.update({
            'session-name.data': name, 'session-dirty.data': False, 'session-stamp.data': _stamp('opened'),
            'session-source.data': source if needs_files else None,
            'session-restore-late.data': late, 'session-banner.hidden': True,
            'session-message.hidden': not (warnings or not restored or rolled_back),
            'session-message-title.children': title, 'session-message-body.children': body,
            'session-missing-modal.opened': needs_files,
            'session-missing-list.children': missing_items(report.missing_files) if needs_files else [],
        })
        if rolled_back:   # the project that is open is still the previous one, unchanged
            values.update({'session-name.data': no_update, 'session-dirty.data': no_update,
                           'session-stamp.data': _stamp('failed', message='Could not open the file')})
        return _ordered_open_outputs(values)

    # -------------------------------------------------------------- Autosave
    @app.callback(
        Output('session-stamp', 'data', allow_duplicate=True),
        Input('session-autosave-fire', 'data'),
        [State('session-name', 'data')] + _state_inputs(),
        prevent_initial_call=True,
    )
    def autosave_project(fired, name, *client_values):
        """Silent autosave ~20 s after the last change (debounced in the browser). Skips an empty workspace."""
        if not fired or not _has_data(data_manager):
            raise PreventUpdate
        try:
            ss.save_autosave(data_manager, gather_client_state(client_values),
                             project_name=(name or '').strip() or None)
        except Exception:
            log.exception('Autosave failed')
            return _stamp('failed', message='Autosave failed')
        return _stamp('autosaved', fired=fired)

    # ------------------------------------------------------ Page-load check
    @app.callback(
        [Output('session-banner', 'hidden'),
         Output('session-banner-text', 'children'),
         Output('session-autosave-target', 'data'),
         Output('session-recent-list', 'children')],
        Input('session-page-load', 'data'),
    )
    def check_last_session(_):
        """Offer to restore the newest autosave (<= 14 days old) when the workspace is empty. Never automatic."""
        entries = sf.recent_autosaves(limit=5)
        recent = ([html.Button(
            f"{sf.project_title(e['name'] if e['name'] != 'Autosave' else '')} · "
            f"{sf.plural(e['samples'], 'sample')} · {sf.humanize_age(e['age'])}",
            type='button', role='menuitem', className='gecko-menu-item',
            **{'data-session-recent': e['path']}) for e in entries]
            or html.Div('None yet', className='session-menu-empty'))
        newest = entries[0] if entries else None
        fresh = (newest is not None and not _has_data(data_manager)
                 and (newest['age'] is None or newest['age'] <= AUTOSAVE_MAX_AGE_DAYS * 86400)
                 and newest['samples'] > 0)
        if not fresh:
            return True, '', None, recent
        text = (f"Restore last session? {sf.plural(newest['samples'], 'sample')}, "
                f"saved {sf.humanize_age(newest['age'])}")
        return False, text, newest['path'], recent

    _register_clientside(app)


def _register_clientside(app) -> None:
    cs = ClientsideFunction
    app.clientside_callback(
        cs(namespace='sessionIO', function_name='trackChange'),
        Output('session-dirty', 'data'),
        [Input('loaded-files', 'data'), Input('peak-change-trigger', 'data'),
         Input('current-plot-settings', 'data'), Input('file-order', 'data'), Input('plot-tabs', 'data'),
         Input('cal-revision', 'data'), Input('hidden-files', 'data'),
         Input('active-file', 'data'), Input('active-plot-tab', 'data')],
        State('session-dirty', 'data'),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        cs(namespace='sessionIO', function_name='armRestore'),
        Output('session-late-go', 'data'),
        Input('session-restore-late', 'data'),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        cs(namespace='sessionIO', function_name='finishRestore'),
        Output('session-dirty', 'data', allow_duplicate=True),
        Input('session-late-go', 'data'),
        [State('session-restore-late', 'data'), State('active-plot-tab', 'data'), State('plot-tabs', 'data'),
         State('active-plot-context', 'data'), State('plot-settings-cache', 'data')],
        prevent_initial_call=True,
    )
    app.clientside_callback(
        cs(namespace='sessionIO', function_name='statusText'),
        Output('session-status', 'children'),
        [Input('session-dirty', 'data'), Input('session-stamp', 'data')],
        prevent_initial_call=True,
    )
    app.clientside_callback(
        cs(namespace='sessionIO', function_name='nameLabel'),
        Output('session-name-btn', 'children'),
        Input('session-name', 'data'),
        prevent_initial_call=True,
    )
    # Trivial dismissals.
    for output_id, prop, button, value in (
            ('session-banner', 'hidden', 'session-banner-dismiss', 'true'),
            ('session-message', 'hidden', 'session-message-close', 'true'),
            ('session-name-modal', 'opened', 'session-name-cancel', 'false'),
            ('session-missing-modal', 'opened', 'session-missing-close', 'false')):
        app.clientside_callback(
            f'function(n){{return n ? {value} : window.dash_clientside.no_update;}}',
            Output(output_id, prop, allow_duplicate=True), Input(button, 'n_clicks'),
            prevent_initial_call=True)
