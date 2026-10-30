"""Workspace undo/redo and capture of edits made through Dash callbacks."""
import logging

import dash
from dash import Input, Output, State, callback_context, no_update, set_props
from flask import g, request

from services.workspace_history import clone, history_for

log = logging.getLogger(__name__)
CLIENT_FIELDS = {'file-order': 'data', 'plot-tabs': 'data', 'custom-plot-figures': 'data',
                 'custom-plot-counter': 'data', 'area-display-unit': 'data', 'zoom-state': 'data',
                 'tab-zoom-memory': 'data', 'pub-selections': 'data', 'peak-shared-selections': 'data',
                 'cross-shared-selections': 'data', 'pda-colormap': 'data',
                 'pub-table-source': 'data', 'pub-data-store': 'data'}
TABLE_EDITS = {'serve_table_page', 'add_new_row', 'add_new_column', 'transpose_data'}
NAVIGATION = {'active-file', 'active-plot-tab', 'active-plot-context', 'active-tab'}


def _label(name):
    if name == 'persist_plot_settings':
        return 'Figure settings'
    return name.replace('_', ' ').removeprefix('handle ').removeprefix('persist ').capitalize()


def register_history_capture(app, store):
    from callbacks.research_export_callbacks import _READ_ONLY_CALLBACKS
    exceptions = {'persist_plot_settings', 'handle_visibility_toggles', 'toggle_group_channel',
                  'toggle_group_sort', 'handle_drag_reorder'}

    navigation_only = {'hydrate_plot_settings', 'sync_axis_label_controls', 'save_selections_for_file',
                       'sync_plot_tabs', 'load_selections_for_context', 'sync_table_to_active_file',
                       'handle_file_selection', 'auto_switch_tab_and_remember', 'restore_file_on_tab_switch',
                       'save_zoom_per_tab'}

    @app.server.before_request
    def before_edit():
        if request.path != '/_dash-update-component':
            return
        body = request.get_json(silent=True) or {}
        cb = app.callback_map.get(body.get('output'), {}).get('callback')
        name, module = getattr(cb, '__name__', ''), getattr(cb, '__module__', '')
        if not cb or not body.get('changedPropIds') or module in {__name__, 'callbacks.session_callbacks'}:
            return
        history = history_for(store)
        readonly = ((name in _READ_ONLY_CALLBACKS.get(module, set()) and name not in exceptions)
                    or name in navigation_only)
        if name in {'handle_peak_table_selection', 'handle_cross_sample_table_selection', 'update_selections'}:
            readonly = not any(prop.endswith(('.selected_cells', '.selected_columns', '.active_cell'))
                               for prop in body.get('changedPropIds', []))
        if not readonly:
            history.lock.acquire()
        try:
            values = {d['id']: d.get('value') for d in body.get('state', []) + body.get('inputs', [])
                      if isinstance(d, dict) and isinstance(d.get('id'), str)}
            for key in NAVIGATION:
                if values.get(key) is not None:
                    history.navigation[key] = values[key]
            for key in CLIENT_FIELDS:
                if key not in history.client and key in values:
                    history.client[key] = clone(values[key])
            if name in TABLE_EDITS:
                for key in ('pub-table-source', 'pub-data-store'):
                    if key in values:
                        _remember_table(history, key, values[key])
            g.gecko_edit = (history, None if readonly else history.capture(), _label(name), body)
        except Exception:
            if not readonly:
                history.lock.release()
            raise

    @app.server.after_request
    def after_edit(response):
        pending = getattr(g, 'gecko_edit', None)
        if not pending:
            return response
        history, before, label, body = pending
        try:
            outputs = body.get('outputs', [])
            outputs = outputs if isinstance(outputs, list) else [outputs]
            if response.status_code == 200 and any(isinstance(o, dict) and isinstance(o.get('id'), str) and (o['id'] in CLIENT_FIELDS or o['id'] in NAVIGATION)
                                                   for o in outputs):
                result = (response.get_json(silent=True) or {}).get('response', {})
                for key, prop in CLIENT_FIELDS.items():
                    if prop in result.get(key, {}):
                        history.client[key] = clone(result[key][prop])
                        if key in ('pub-table-source', 'pub-data-store'):
                            _remember_table(history, key, result[key][prop])
                callback = app.callback_map.get(body.get('output'), {}).get('callback')
                if getattr(callback, '__name__', '') in TABLE_EDITS and 'data' in result.get('pub-data-store', {}):
                    _remember_table(history, 'pub-table-source', result['pub-data-store']['data'])
                for key in NAVIGATION:
                    if 'data' in result.get(key, {}):
                        history.navigation[key] = result[key]['data']
            if before is not None:
                history.commit(before, label)
        except Exception:
            log.exception('Could not record workspace undo')
        finally:
            if before is not None:
                history.lock.release()
        return response


def register_history_callbacks(app, store):
    @app.callback(
        Output('figure-action-status', 'children', allow_duplicate=True),
        [Input('undo-trigger', 'data'), Input('redo-trigger', 'data')],
        [State('active-file', 'data'), State('active-plot-context', 'data'), State('active-plot-tab', 'data'),
         State('plot-settings-cache', 'data'), State('loaded-files', 'data'), State('render-trigger', 'data'),
         State('peak-change-trigger', 'data'), State('cal-revision', 'data')],
        prevent_initial_call=True,
    )
    def handle_workspace_history(undo, redo, active_file, context, plot_tab, cache, files, render, peaks, calibration):
        history = history_for(store)
        trigger = callback_context.triggered_id
        action = history.undo() if trigger == 'undo-trigger' else history.redo()
        if not action:
            return 'Nothing to undo' if trigger == 'undo-trigger' else 'Nothing to redo'
        _restore_browser(store, history, active_file, context, plot_tab, cache, files, render, peaks, calibration)
        return ('Undid: ' if trigger == 'undo-trigger' else 'Redid: ') + action

    # These preferences can change entirely in the browser, so they have no server edit callback to capture.
    @app.callback(Output('history-client-sink', 'data'),
                  [Input('area-display-unit', 'data'), Input('zoom-state', 'data'), Input('pda-colormap', 'data')],
                  prevent_initial_call=False)
    def track_browser_preferences(area_unit, zoom, colormap):
        history = history_for(store)
        values = {'area-display-unit': area_unit, 'zoom-state': zoom, 'pda-colormap': colormap}
        key = callback_context.triggered_id
        if key not in values:
            for field, value in values.items():
                history.client.setdefault(field, clone(value))
            return no_update
        value = values[key]
        if key not in history.client:
            history.client[key] = clone(value)
            return no_update
        with history.edit({'area-display-unit': 'Area units', 'zoom-state': 'Zoom',
                           'pda-colormap': 'PDA colour map'}[key]):
            history.client[key] = clone(value)
        return no_update


def _restore_browser(store, history, active_file, context, plot_tab, cache, files, render, peaks, calibration):
    from callbacks.plot_settings_callbacks import settings_for_context
    from callbacks.upload_callbacks import build_active_file_views, render_file_tree_with_bundles_selected
    from services.channel_visibility import visible_component_id

    nav = history.navigation
    active_file = nav.get('active-file', active_file)
    context = nav.get('active-plot-context', context)
    plot_tab = nav.get('active-plot-tab', plot_tab)
    if not active_file or not store.get_data_by_id(active_file):
        bundle = next(iter(store.iter_bundles()), None)
        active_file = visible_component_id(store, bundle) if bundle else None
    current_files = store.get_loaded_files_list()
    updates = {key: {CLIENT_FIELDS[key]: value} for key, value in history.client.items() if key in CLIENT_FIELDS}
    if current_files != (files or []):
        updates['loaded-files'] = {'data': current_files}
    updates.update({
        'active-file': {'data': active_file},
        'hidden-files': {'data': [key for key, visible in store.visibility_state.items() if not visible]},
        'render-trigger': {'data': (render or 0) + 1},
        'peak-change-trigger': {'data': (peaks or 0) + 1},
        'cal-revision': {'data': (calibration or 0) + 1},
        'selected-peak-idx': {'data': None},
        'session-dirty': {'data': True},
        'undo-file-removal-btn': {'disabled': True},
    })
    if plot_tab:
        updates['active-plot-tab'] = {'data': plot_tab}
    if nav.get('active-tab'):
        updates['active-tab'] = {'data': nav['active-tab']}
    if context:
        contexts = set(cache or {}) | set(store._shared_plot_settings) | {context}
        restored_cache = {key: settings_for_context(store, key, active_file) for key in contexts}
        updates['plot-settings-cache'] = {'data': restored_cache}
        updates['current-plot-settings'] = {'data': restored_cache[context]}
        updates['active-plot-context'] = {'data': context}
        updates['plot-settings-miss'] = {'data': context}
    updates['file-tree'] = {'children': render_file_tree_with_bundles_selected(
        current_files, store, active_file, active_plot_tab=plot_tab, file_order=history.client.get('file-order') or {})}
    if active_file:
        metadata, editor, data = build_active_file_views(store, active_file)
        updates['metadata-container'] = {'children': metadata}
        updates['table-editor-container'] = {'children': editor}
        updates['pub-data-store'] = {'data': data}
    from services import table_store
    from components.data_table_editor import create_data_table_editor
    for key, frame in history.tables.items():
        if frame is not None:
            source = table_store.remember(frame)
            updates[key] = {'data': source}
            if key == 'pub-table-source':
                updates['table-editor-container'] = {'children': create_data_table_editor(frame.copy(), source=source)}
    for key, value in updates.items():
        set_props(key, value)


def _remember_table(history, key, source):
    from services import table_store
    frame = table_store._stored(source) if table_store.is_reference(source) else table_store.frame(source)
    if frame is not None:
        history.tables[key] = frame
        history.client[key] = clone(source)
