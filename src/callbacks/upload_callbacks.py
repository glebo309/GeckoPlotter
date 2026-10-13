# Clean version of upload_callbacks.py with just the essential functions
import logging
import os
from services.dataset_names import display_name

from typing import List, Dict, Any
import dash
from dash import dcc, html, Input, Output, State, dash_table
import pandas as pd
from urllib.parse import quote

def _icon(name, width=14, height=14, color='#333', **kw):
    paths = {
        'tabler:eye': '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
        'tabler:eye-off': '<path d="m3 3 18 18M10 5a12 12 0 0 1 12 7 17 17 0 0 1-4 5M6 6a17 17 0 0 0-4 6s3.5 7 10 7a13 13 0 0 0 5-1M10 10a3 3 0 0 0 4 4"/>',
        'tabler:trash': '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
        'tabler:chart-line': '<path d="M3 3v18h18M5 16l5-6 4 3 6-8"/>',
        'tabler:spectrum': '<path d="M3 20h18M4 18l3-3 3 3 2-14 3 14 3-7 2 7"/>',
    }
    if name in paths:
        def source(icon_name):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                   f'fill="none" stroke="{color}" stroke-width="1.8" '
                   f'stroke-linecap="round" stroke-linejoin="round">{paths[icon_name]}</svg>')
            return 'data:image/svg+xml,' + quote(svg)
        if name in ('tabler:eye', 'tabler:eye-off'):
            kw.update({'data-visible-src': source('tabler:eye'),
                       'data-hidden-src': source('tabler:eye-off')})
        return html.Img(src=source(name), alt='',
                        style={'width': f'{max(width, 18)}px', 'height': f'{max(height, 18)}px'}, **kw)
    glyphs = {
        'tabler:eye': '○',
        'tabler:trash': '×',
        'tabler:table': '▦',
        'tabler:layout-grid': '▦',
        'tabler:photo': '□',
        'tabler:chart-line': '⌁',
        'tabler:chart-area-line': '⌁',
        'tabler:flask': '◇',
        'tabler:plus': '+',
        'tabler:minus': '-',
        'tabler:spectrum': '⌁',
        'tabler:file-text': '□',
        'tabler:file-code': '{}',
        'tabler:file-question': '?',
    }
    style = {
        'display': 'inline-flex',
        'alignItems': 'center',
        'justifyContent': 'center',
        'width': f'{width}px',
        'height': f'{height}px',
        'color': color,
        'fontSize': f'{max(10, min(width, height))}px',
        'lineHeight': '1',
        'fontFamily': 'Arial, sans-serif',
    }
    extra_style = kw.pop('style', None)
    if isinstance(extra_style, dict):
        style.update(extra_style)
    return html.Span(glyphs.get(name, '□'), style=style, **kw)


def _visibility_button(file_id, data_manager=None):
    visible = getattr(data_manager, 'visibility_state', {}).get(file_id, True)
    label = 'Hide trace' if visible else 'Show trace'
    return html.Button(
        _icon('tabler:eye' if visible else 'tabler:eye-off', width=18),
        id={'type': 'visibility-btn', 'index': file_id},
        title=label, className='tree-action-btn', n_clicks=0,
        style={'background': 'none', 'border': 'none', 'cursor': 'pointer',
               'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'},
        **{'aria-label': label, 'aria-pressed': str(visible).lower()}
    )



def build_active_file_views(data_manager, file_id):
    """Metadata table, table editor and publication data of one file, as shown right after an import or restore.

    Returns ``(metadata_children, table_editor, pub_data_json)``; the first is ``dash.no_update`` when the file
    has no data.
    """
    auto_table, table_editor, pub_data = dash.no_update, None, None
    file_data = data_manager.get_data_by_id(file_id)
    if not file_data:
        return auto_table, table_editor, pub_data
    try:
        from callbacks.viz_callbacks import create_data_table, create_bundle_data_table
        bundle = (data_manager.get_bundle(file_id)
                  or data_manager.get_bundle_for_component(file_id))
        if bundle and bundle.bundle_type.value != 'generic':
            compat = data_manager.get_bundle_by_id(bundle.bundle_id)
            auto_table = create_bundle_data_table(compat, file_data, data_manager)
        else:
            auto_table = create_data_table(file_data)
    except Exception:
        log.exception("Error building metadata table")

    from callbacks.viz_callbacks import prepare_table_data
    from components.data_table_editor import create_data_table_editor

    table_data = prepare_table_data(file_data, file_id=file_id)
    sheet_names = file_data.get('metadata', {}).get('sheet_names')
    active_sheet = file_data.get('metadata', {}).get('active_sheet')
    table_editor = create_data_table_editor(
        table_data, table_id='pub-table',
        sheet_names=sheet_names, active_sheet=active_sheet,
    )
    pub_data = table_data.to_json(orient='split') if table_data is not None else None
    return auto_table, table_editor, pub_data


log = logging.getLogger(__name__)

def register_upload_callbacks(app: dash.Dash, data_manager) -> None:
    """Register upload-related callbacks."""
    
    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('pt-layout-mode', 'value', allow_duplicate=True),
         Output('session-upload-handoff', 'data', allow_duplicate=True)],
        Input('upload-button', 'contents'),
        [State('upload-button', 'filename'),
         State('upload-button', 'last_modified'),
         State('loaded-files', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_file_upload(contents_list: List[str], filenames: List[str],
                          last_modified_list: List[int], existing_files: List[Dict[str, Any]],
                          render_counter) -> tuple:
        """Handle file upload via Bundle-first pipeline.

        1. Decode + parse each file via ingestion pipeline
        2. Group into Bundles via BundlingService
        3. Register Bundles in DataStore
        4. Auto-import peaks from Integration.txt components
        """
        if not contents_list or not filenames:
            return (dash.no_update,) * 9

        # A project file (.gecko, or a FAIR package .zip that holds one) is never ingested as data: hand it to the
        # Open flow (callbacks/session_callbacks.py).
        from services.session_files import is_project_upload, stash_session_upload
        project = next(((c, f) for c, f in zip(contents_list, filenames) if is_project_upload(c, f)), None)
        if project is not None:
            try:
                return (dash.no_update,) * 8 + (stash_session_upload(*project),)
            except Exception:
                log.exception("Could not read the project file %s", project[1])
                return (dash.no_update,) * 9

        try:
            import base64
            import tempfile
            from ingestion import ingest_file
            from services.bundling_service import assign_bundles
            from services.data_store import BundleType

            parsed_files = []
            failed_names = set()

            for contents, fname in zip(contents_list, filenames):
                try:
                    _, encoded = contents.split(",", 1)
                    raw_bytes = base64.b64decode(encoded)

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{fname}")
                    try:
                        tmp.write(raw_bytes)
                        tmp.close()
                        sr = ingest_file(tmp.name, fname)
                    finally:
                        # Parsers read the whole file during ingestion and the original bytes stay in memory,
                        # so the copy is not needed afterwards (it used to leak one full copy per upload).
                        tmp.close()
                        try:
                            os.unlink(tmp.name)
                        except OSError:
                            pass
                    if sr is None:
                        log.warning(f"Pipeline could not parse {fname}")
                        failed_names.add(fname)
                        continue

                    parsed_files.append((fname, raw_bytes, sr))
                except Exception as e:
                    log.error(f"Error parsing {fname}: {e}")
                    failed_names.add(fname)

            if not parsed_files:
                return (dash.no_update,) * 9

            new_bundles = assign_bundles(parsed_files)

            last_bundle_id = None
            auto_layout_mode = dash.no_update
            for bundle in new_bundles:
                data_manager.add_bundle(bundle)
                last_bundle_id = bundle.bundle_id
                log.debug(f"Created bundle '{bundle.name}' ({bundle.bundle_type.value}) "
                          f"with {len(bundle.component_list)} components")

                if bundle.has_integration_data():
                    _auto_import_peaks(data_manager, bundle)

                if bundle.bundle_type == BundleType.LCMS and len(bundle.component_list) > 1:
                    auto_layout_mode = 'stacked'

            from services.channel_visibility import initialize_imported_channels, visible_component_id
            initialize_imported_channels(data_manager, new_bundles)
            loaded_files = data_manager.get_loaded_files_list()

            last_bundle = data_manager.get_bundle(last_bundle_id) if last_bundle_id else None
            if last_bundle and last_bundle.bundle_type in (BundleType.CHROMATOGRAM, BundleType.LCMS):
                auto_active_file = visible_component_id(data_manager, last_bundle) or dash.no_update
            else:
                auto_active_file = last_bundle_id or dash.no_update
            auto_table, table_editor, pub_data = dash.no_update, None, None
            if auto_active_file and auto_active_file != dash.no_update:
                auto_table, table_editor, pub_data = build_active_file_views(data_manager, auto_active_file)

            tree_items = render_file_tree_with_bundles_selected(
                loaded_files, data_manager, auto_active_file)

            log.debug(f"Upload complete: {len(new_bundles)} bundles from {len(parsed_files)} files")
            return (loaded_files, tree_items, auto_active_file, auto_table,
                    table_editor, pub_data, (render_counter or 0) + 1, auto_layout_mode, dash.no_update)

        except Exception as e:
            log.exception(f"Upload failed: {str(e)}")
            return (dash.no_update,) * 9

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('pt-layout-mode', 'value', allow_duplicate=True),
         Output('session-upload-handoff', 'data', allow_duplicate=True)],
        Input('drop-zone', 'contents'),
        [State('drop-zone', 'filename'),
         State('drop-zone', 'last_modified'),
         State('loaded-files', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_drop_upload(contents_list, filenames, last_modified_list, existing_files, render_counter):
        if not contents_list or not filenames:
            return (dash.no_update,) * 9
        return handle_file_upload(contents_list, filenames, last_modified_list, existing_files, render_counter)

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('pt-layout-mode', 'value', allow_duplicate=True),
         Output('session-upload-handoff', 'data', allow_duplicate=True)],
        Input('global-drop-zone', 'contents'),
        [State('global-drop-zone', 'filename'),
         State('global-drop-zone', 'last_modified'),
         State('loaded-files', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_global_drop_upload(contents_list, filenames, last_modified_list, existing_files, render_counter):
        if not contents_list or not filenames:
            return (dash.no_update,) * 9
        return handle_file_upload(contents_list, filenames, last_modified_list, existing_files, render_counter)


def _auto_import_peaks(data_manager, bundle):
    """Import peaks from a Chromeleon Integration.txt component."""
    try:
        from callbacks.tab_callbacks import parse_integration_results
        text = bundle.get_integration_text()
        if not text:
            return

        parsed = parse_integration_results(text)
        if not parsed:
            return

        time_arr, signal_arr = data_manager.get_xy_arrays(bundle.bundle_id)
        if time_arr is None:
            return

        data_manager.peak_service.import_instrument_peaks(
            file_id=bundle.bundle_id,
            parsed_results=parsed,
            time_axis=time_arr,
            signal=signal_arr,
        )
        data_manager.peak_service.group_peaks_across_samples(
            file_overlay_map=data_manager.build_file_overlay_map())
        log.debug(f"Auto-imported {len(parsed)} peaks for bundle '{bundle.name}'")
    except Exception as e:
        log.warning(f"Could not auto-import peaks for '{bundle.name}': {e}")


def render_file_tree_with_bundles(records: List[dict], data_manager) -> List[html.Div]:
    """Render file tree with bundles from records (no selection or grouping)."""
    return render_file_tree_with_bundles_selected(records, data_manager)


def _sort_group_items(items, file_order_info):
    """Sort items within a group based on file-order store entry."""
    if not file_order_info:
        items.sort(key=lambda it: (it.get('name') or '').lower())
        return items

    explicit_order = file_order_info.get('order')
    if explicit_order:
        order_map = {fid: idx for idx, fid in enumerate(explicit_order)}
        items.sort(key=lambda it: order_map.get(it.get('id'), 999999))
        return items

    sort_dir = file_order_info.get('sort_dir', 'asc')
    reverse = sort_dir == 'desc'
    items.sort(key=lambda it: (it.get('name') or '').lower(), reverse=reverse)
    return items


def render_file_tree_with_bundles_selected(records: List[dict], data_manager, active_file_id: str = None, active_plot_tab: str = None, file_order: dict = None) -> List[html.Div]:
    """Render file tree grouped by overlay group, with group headers.

    Files are sorted into groups matching plot tabs. Generic/unrecognized
    files go into an 'Unplotted' section at the bottom.
    """
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    from callbacks.viz_callbacks import (
        _get_overlay_group, _tab_id_from_group, _tab_label_from_group,
    )
    from collections import OrderedDict

    file_order = file_order or {}
    bundled_items = data_manager.get_bundled_tree_items(records)

    groups = OrderedDict()
    ungrouped = []

    for item in bundled_items:
        file_id = item.get('id')
        fdata = data_manager.get_data_by_id(file_id)
        if not fdata:
            bundle = data_manager.get_bundle_by_id(file_id)
            if bundle and bundle.main_file:
                fdata = data_manager.get_data_by_id(bundle.main_file.get('id'))
        if not fdata or fdata.get('standardized') is None:
            ungrouped.append(item)
            continue
        metadata = fdata.get('metadata', {})
        group = _get_overlay_group(metadata, fdata, file_id=file_id, dm=data_manager)
        tid = _tab_id_from_group(group)
        if tid not in groups:
            groups[tid] = {'label': _tab_label_from_group(group, data_manager), 'items': []}
        groups[tid]['items'].append(item)

    tree_items = []
    for tid, group_info in groups.items():
        is_active_group = tid == active_plot_tab
        group_order = file_order.get(tid, {})
        sort_dir = group_order.get('sort_dir', 'asc')
        sorted_items = _sort_group_items(group_info['items'], group_order)

        collapsed = data_manager.collapse_state.get(tid) == 'collapsed'
        tree_items.append(_render_group_header(
            group_info['label'], tid, is_active_group, sort_dir=sort_dir, collapsed=collapsed))

        group_container_children = []
        for item in sorted_items:
            file_id = item.get('id')
            source_bundle = data_manager.get_bundle(file_id)
            if source_bundle and source_bundle.bundle_type.value in ('chromatogram', 'lcms'):
                rendered = _render_sample_item(source_bundle, data_manager, active_file_id,
                                               dimmed=not is_active_group)
            elif item.get('is_bundle'):
                is_selected = active_file_id == file_id
                rendered = render_bundle_item_selected(
                    item, is_selected, data_manager=data_manager,
                    dimmed=not is_active_group)
            else:
                is_selected = active_file_id == file_id
                rendered = render_individual_file_item_selected(
                    item, is_selected, data_manager=data_manager,
                    dimmed=not is_active_group)
            group_container_children.append(
                html.Div(rendered, className='draggable-file-item',
                         **{'data-file-id': file_id}))

        tree_items.append(html.Div(
            group_container_children,
            className='file-group-container',
            id={'type': 'file-group', 'index': tid},
            style={'display': 'none' if collapsed else 'block'},
        ))

    for item in ungrouped:
        if item.get('is_bundle'):
            is_selected = active_file_id == item.get('id')
            tree_items.append(render_bundle_item_selected(
                item, is_selected, data_manager=data_manager, dimmed=False))
        else:
            is_selected = active_file_id == item.get('id')
            tree_items.append(render_individual_file_item_selected(
                item, is_selected, data_manager=data_manager, dimmed=False))

    return tree_items


def _render_group_header(label: str, group_id: str, is_active: bool, sort_dir: str = 'asc', collapsed=False) -> html.Div:
    """Render a group header in the file tree with sort toggle."""
    arrow = '↑' if sort_dir == 'asc' else '↓'
    return html.Div([
        html.Button([html.Span('▶' if collapsed else '▼', className='group-disclosure-indicator'),
                     html.Span(label)], id={'type': 'group-collapse-btn', 'index': group_id},
            n_clicks=0, className='group-disclosure-btn',
            **{'aria-expanded': str(not collapsed).lower(), 'aria-label': 'Expand or collapse ' + label},
            style={
            'fontWeight': '600' if is_active else '500',
            'fontSize': '11px',
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'color': '#1a1a1a' if is_active else '#888',
        }),
        html.Button(arrow, id={'type': 'group-sort-btn', 'index': group_id},
            n_clicks=0,
            style={
                'padding': '0 4px', 'fontSize': '10px', 'lineHeight': '14px',
                'border': '1px solid #ccc', 'borderRadius': '3px',
                'backgroundColor': 'white', 'color': '#888', 'cursor': 'pointer',
                'marginLeft': '6px', 'verticalAlign': 'middle',
            }),
    ], className='file-group-header native-disclosure active' if is_active else 'file-group-header native-disclosure',
        style={
            'padding': '3px 6px 2px 6px',
            'marginTop': '4px',
            'borderBottom': '1px solid #1a1a1a' if is_active else '1px solid #e0e0e0',
            'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between',
        },
    )


def _render_channel_controls(controls, group_id):
    import json
    return html.Div([
        html.Button([html.Span('−' if c['state'] == 'mixed' else '✓' if c['state'] == 'true' else '',
                               className='channel-check'), html.Span(c['label'])],
                    id={'type': 'group-channel-btn', 'group': group_id, 'channel': c['key']},
                    n_clicks=0, role='checkbox', className='group-channel-toggle',
                    title=f"{c['label']}: {c['visible']} of {len(c['sources'])} shown",
                    **{'aria-checked': c['state'], 'aria-label': c['label'],
                       'data-channel-sources': json.dumps(c['sources']), 'data-channel-label': c['label']})
        for c in controls
    ], className='group-channel-controls', role='group', **{'aria-label': 'Detector channels'})


def _render_channel_manager(controls, group_id):
    import dash_mantine_components as dmc
    return dmc.Popover([
        dmc.PopoverTarget(html.Button('Channels…', className='plot-tool',
            title='View and remove channels', **{'aria-label': 'Manage channels'})),
        dmc.PopoverDropdown([
            html.Div('Channels', style={'fontWeight':600, 'marginBottom':'8px'}),
            *[html.Div([
                html.Span(c['label']),
                html.Span(f"{len(c['sources'])} sample" + ('s' if len(c['sources']) != 1 else ''),
                          style={'color':'#777','fontSize':'11px','marginLeft':'auto'}),
                html.Button(_icon('tabler:trash'),
                    id={'type':'remove-channel-btn','group':group_id,'channel':c['key']},
                    n_clicks=0, title=f"Remove {c['label']} channel from these samples",
                    **{'aria-label': f"Remove {c['label']} channel"},
                    style={'border':'none','background':'none','display':'flex',
                           'padding':'5px','cursor':'pointer'})
                ], style={'display':'flex','alignItems':'center','gap':'12px','minHeight':'32px'})
              for c in controls]
        ], style={'fontSize':'12px'})
    ], width=260, position='bottom-start', shadow='md', withinPortal=True)


def _render_sample_item(bundle, data_manager, active_file_id=None, dimmed=False):
    from services.channel_visibility import visible_component_id
    selected = visible_component_id(data_manager, bundle, active_file_id)
    return html.Div([
        html.Div([_icon('tabler:chart-line'),
                  html.Span(display_name(bundle.name), className='dataset-name',
                            **{'data-file-id': bundle.bundle_id})],
                 id={'type': 'file-tree-item', 'index': selected}, n_clicks=0,
                 className='file-tree-item sample-tree-content', role='button', tabIndex=0,
                 title=display_name(bundle.name),
                 **{'data-file-key': bundle.bundle_id,
                    'data-sample-sources': __import__('json').dumps([c.component_id for c in bundle.component_list])}),
        html.Div([_visibility_button(bundle.bundle_id, data_manager),
                  html.Button(_icon('tabler:trash', width=12, height=12),
                      id={'type': 'delete-btn', 'index': bundle.bundle_id}, n_clicks=0,
                      title='Remove sample from workspace', className='tree-action-btn',
                      style={'background': 'none', 'border': 'none', 'cursor': 'pointer',
                             'padding': '0', 'fontSize': '11px',
                             'width': '18px', 'height': '18px',
                             'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center'})],
                 className='tree-action-group'),
        # Existing legend interactions address the source eye. Keep their targets
        # without presenting detector channels as separate files.
        html.Div([_visibility_button(c.component_id, data_manager) for c in bundle.component_list],
                 style={'display': 'none'}, **{'aria-hidden': 'true'}),
    ], className='sample-tree-row', style={'opacity': .5 if dimmed else 1})


def render_bundle_item(bundle_item: dict, data_manager=None, dimmed=False) -> html.Div:
    """Render a bundle item."""
    return render_bundle_item_selected(bundle_item, is_selected=False, data_manager=data_manager, dimmed=dimmed)


def render_individual_file_item(item: dict, is_child: bool = False, data_manager=None, dimmed=False) -> html.Div:
    """Render an individual file item."""
    return render_individual_file_item_selected(item, is_selected=False, is_child=is_child, data_manager=data_manager, dimmed=dimmed)


def render_bundle_item_selected(bundle_item: dict, is_selected: bool = False, data_manager=None, dimmed: bool = False) -> html.Div:
    """Render a bundle item with selection highlighting."""
    bundle_icon = bundle_item.get('icon', '📦')
    bundle_id = bundle_item.get('id')

    opacity = '0.5' if dimmed else '1.0'
    
    # Check stored collapse state for expansion button and child visibility
    initial_icon = '▶'
    children_display = 'none'
    if data_manager and hasattr(data_manager, 'collapse_state'):
        stored_state = data_manager.collapse_state.get(bundle_id, 'collapsed')
        if stored_state == 'expanded':
            initial_icon = '▼'
            children_display = 'block'
            log.debug(f"Restoring expanded LCMS bundle state for {bundle_id}")
    
    return html.Div([
        # Main container using CSS Grid for clean layout
        html.Div([
            # Expand button (separate clickable area)
            html.Div([
                html.Button(
                    initial_icon,
                    id={'type': 'expand-btn', 'index': bundle_id},
                    title='Collapse bundle' if children_display == 'block' else 'Expand bundle',
                    className='tree-disclosure-btn',
                    **{'aria-expanded': str(children_display == 'block').lower(), 'aria-label': 'Expand or collapse bundle'},
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0',
                        'fontSize': '10px',
                        'width': '16px',
                        'height': '18px',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'center'
                    }
                )
            ], style={'gridArea': 'expand', 'display': 'flex', 'alignItems': 'center'}),
            
            # Bundle content (clickable for selection)
            html.Div([
                html.Span(display_name(bundle_item.get('name', '')), className='dataset-name', **{'data-file-id': bundle_id}, style={
                    'fontWeight': '600', 'overflow': 'hidden', 'textOverflow': 'ellipsis',
                    'whiteSpace': 'nowrap', 'flex': '1',
                }),
                html.Span(bundle_item.get('size_display', ''), style={
                    'fontSize': '10px', 'color': '#999', 'marginLeft': '6px', 'flexShrink': '0',
                }),
            ],
            className='file-tree-item',
            role='button', tabIndex=0,
            id={'type': 'file-tree-item', 'index': bundle_id},
            n_clicks=0,
            title=display_name(bundle_item.get('name', '')),
            **{'data-file-key': bundle_id},
            style={
                'gridArea': 'content',
                'display': 'flex',
                'alignItems': 'center',
                'cursor': 'pointer',
                'padding': '1px 6px',
                'borderRadius': '3px',
                'backgroundColor': '#ffffff',
                'borderLeft': '2px solid transparent',
                'transition': 'all 0.15s',
                'flex': '1',
                'lineHeight': '1.4',
            }),

            # Control buttons
            html.Div([
                _visibility_button(bundle_id, data_manager),
                html.Button(
                    _icon('tabler:trash', width=12, height=12, color='#333'),
                    id={'type': 'delete-btn', 'index': bundle_id},
                    title='Remove bundle from workspace',
                    className='tree-action-btn',
                    style={
                        'background': 'none', 'border': 'none', 'cursor': 'pointer',
                        'padding': '0', 'fontSize': '11px',
                        'width': '18px', 'height': '18px',
                        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    }
                ),
            ], className='tree-action-group', style={
                'gridArea': 'buttons', 'display': 'flex', 'gap': '0', 'alignItems': 'center'
            })
        ], style={
            'display': 'grid',
            'gridTemplateColumns': 'auto minmax(0, 1fr) auto',
            'gridTemplateAreas': '"expand content buttons"',
            'alignItems': 'center',
            'gap': '1px',
            'padding': '0 2px',
            'margin': '0',
            'borderRadius': '3px',
            'transition': 'all 0.2s'
        }),

        # Children (initially collapsed)
        html.Div([
            render_individual_file_item(child, is_child=True, data_manager=data_manager)
            for child in bundle_item.get('children', [])
        ], style={'marginLeft': '12px', 'display': children_display},
          id={'type': 'bundle-children', 'index': bundle_id})
    ], className='bundle-item', style={'opacity': opacity})


def render_individual_file_item_selected(item: dict, is_selected: bool = False, is_child: bool = False, data_manager=None, dimmed: bool = False) -> html.Div:
    """Render an individual file item with selection highlighting using clean grid layout."""
    # Define icons for different file types
    TYPE_ICON_NAMES = {
        'table': 'tabler:table',
        'csv': 'tabler:table',
        'generic_csv': 'tabler:table',
        'structured': 'tabler:layout-grid',
        'image': 'tabler:photo',
        'chromatogram': 'tabler:chart-line',
        'spectrum': 'tabler:chart-area-line',
        'spectra': 'tabler:chart-area-line',
        'uvvis_csv': 'tabler:flask',
        'lcms_bundle': 'tabler:flask',
        'lcms_ms_positive': 'tabler:plus',
        'lcms_ms_negative': 'tabler:minus',
        'lcms_uv_a': 'tabler:spectrum',
        'lcms_uv_b': 'tabler:spectrum',
        'ms_positive': 'tabler:chart-line',
        'ms_negative': 'tabler:chart-line',
        'vwd_a': 'tabler:spectrum',
        'vwd_b': 'tabler:spectrum',
        'text': 'tabler:file-text',
        'binary': 'tabler:file-code',
        'unknown': 'tabler:file-question',
    }

    file_id = item.get('id')
    icon_type = item.get('type')
    entry = data_manager.get_data_by_id(file_id) if data_manager else None
    if entry and entry.get('standardized') is not None:
        category = entry['standardized'].source_category.value
        if category in ('chromatogram', 'lcms_ms'):
            icon_type = 'chromatogram'
        elif category in ('spectrum', 'lcms_uv'):
            icon_type = 'spectrum'
    icon = _icon(TYPE_ICON_NAMES.get(icon_type, 'tabler:file-question'))

    # Check if this item has children (like UV-Vis wells)
    children = []
    has_children = 'children' in item and item['children'] and not is_child
    
    if has_children:
        for child in item['children']:
            child_id = child.get('id')
            
            # Default visibility state for child
            is_child_visible = True
            child_icon = _icon('tabler:eye', width=12, height=12)
            child_opacity = '1.0'
            
            # Use grid layout for child items too
            raw_icon = child.get('icon', '')
            child_icon_symbol = _icon('tabler:flask') if not raw_icon.startswith('tabler:') else _icon(raw_icon)
            child_info = child.get('size_display', '')
            child_type_label = child.get('component_type')
            if child_type_label:
                labels = {
                    'ms_positive': 'MS+ TIC',
                    'ms_negative': 'MS- TIC',
                    'vwd_a': 'UV Channel A',
                    'vwd_b': 'UV Channel B'
                }
                child_info = labels.get(child_type_label, child_info)
            child_item = html.Div([
                html.Div([
                    # No expand button for children
                    html.Div(style={'gridArea': 'expand', 'width': '8px'}),
                    
                    # Child content (clickable for selection)
                    html.Div([
                        html.Span(child_icon_symbol, style={'marginRight': '4px', 'display': 'inline-flex', 'flexShrink': '0'}),
                        html.Span(display_name(child.get('name', '')), className='dataset-name', **{'data-file-id': child_id}, style={
                            'fontWeight': '500', 'overflow': 'hidden', 'textOverflow': 'ellipsis',
                            'whiteSpace': 'nowrap', 'flex': '1',
                        }),
                        html.Span(child_info, style={
                            'fontSize': '10px', 'color': '#666', 'marginLeft': '6px', 'flexShrink': '0',
                        }),
                    ], 
                    className='file-tree-item',
            role='button', tabIndex=0,
                    id={'type': 'file-tree-item', 'index': child_id}, 
                    n_clicks=0,
                    title=f"{display_name(child.get('name', ''))} · {child_info}" if child_info else display_name(child.get('name', '')),
                    **{'data-file-key': child_id},
                    style={
                        'gridArea': 'content',
                        'display': 'flex',
                        'alignItems': 'center',
                        'cursor': 'pointer',
                        'padding': '1px 6px',
                        'borderRadius': '3px',
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #e0e0e0',
                        'transition': 'all 0.15s'
                    }),
                    
                    # Control buttons for child items
                    html.Div([
                        _visibility_button(child_id, data_manager),
                        html.Button(
                            _icon('tabler:trash', width=12, height=12, color='#333'),
                            id={'type': 'delete-btn', 'index': child_id},
                            title='Remove signal from workspace',
                            className='tree-action-btn',
                            style={
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'padding': '0',
                                'fontSize': '14px',
                                'color': '#dc3545',
                                'width': '18px',
                                'height': '18px',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center',
                                'borderRadius': '3px'
                            }
                        ),
                    ], style={
                        'gridArea': 'buttons',
                        'display': 'flex',
                        'gap': '0',
                        'alignItems': 'center'
                    })
                ], style={
                    'display': 'grid',
                    'gridTemplateColumns': 'auto minmax(0, 1fr) auto',
                    'gridTemplateAreas': '"expand content buttons"',
                    'alignItems': 'center',
                    'gap': '1px',
                    'padding': '0 2px',
                    'margin': '0',
                    'borderRadius': '3px',
                    'transition': 'all 0.2s'
                })
            ])
            children.append(child_item)
    
    # Add collapse button if has children
    collapse_button_area = html.Div(style={'gridArea': 'expand', 'width': '16px'})
    if has_children:
        # Check stored collapse state for button icon
        initial_icon = '▶'  # Default collapsed
        if data_manager and hasattr(data_manager, 'collapse_state'):
            stored_state = data_manager.collapse_state.get(file_id, 'collapsed')
            if stored_state == 'expanded':
                initial_icon = '▼'  # Expanded
                log.debug(f"Restoring expanded button for {file_id}")
        
        collapse_button_area = html.Div([
            html.Button(
                initial_icon,
                id={'type': 'collapse-btn', 'index': file_id},
                title='Collapse signals' if initial_icon == '▼' else 'Expand signals',
                className='tree-disclosure-btn',
                **{'aria-expanded': str(initial_icon == '▼').lower(), 'aria-label': 'Expand or collapse signals'},
                style={
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0',
                    'fontSize': '10px',
                    'width': '16px',
                    'height': '18px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center'
                }
            )
        ], style={'gridArea': 'expand', 'display': 'flex', 'alignItems': 'center'})
    
    main_item = html.Div([
        html.Div([
            # Collapse button area
            collapse_button_area,
            
            # File content (clickable for selection)
            html.Div([
                html.Span(icon, style={'marginRight': '4px', 'flexShrink': '0', 'display': 'inline-flex'}),
                html.Span(display_name(item.get('name', '')), className='dataset-name', **{'data-file-id': file_id}, style={
                    'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap', 'flex': '1',
                    'fontWeight': '400',
                }),
                html.Span(item.get('size_display', ''), style={
                    'fontSize': '10px', 'color': '#999', 'marginLeft': '6px', 'flexShrink': '0',
                }),
            ],
            className='file-tree-item',
            role='button', tabIndex=0,
            id={'type': 'file-tree-item', 'index': file_id},
            n_clicks=0,
            title=item.get('original_filename') or f"{(item.get('type') or 'unknown').capitalize()} · {item.get('size_display', '')}",
            **{'data-file-key': file_id},
            style={
                'gridArea': 'content',
                'display': 'flex',
                'alignItems': 'center',
                'cursor': 'pointer',
                'padding': '1px 6px',
                'borderRadius': '3px',
                'backgroundColor': '#ffffff',
                'borderLeft': '2px solid transparent',
                'transition': 'all 0.15s',
                'flex': '1',
                'lineHeight': '1.4',
            }),

            # Control buttons
            html.Div([
                _visibility_button(file_id, data_manager),
                html.Button(
                    _icon('tabler:trash', width=12, height=12, color='#333'),
                    id={'type': 'delete-btn', 'index': file_id},
                    title='Remove file from workspace',
                    className='tree-action-btn',
                    style={
                        'background': 'none', 'border': 'none', 'cursor': 'pointer',
                        'padding': '0', 'fontSize': '11px',
                        'width': '18px', 'height': '18px',
                        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    }
                ),
            ], className='tree-action-group', style={
                'gridArea': 'buttons', 'display': 'flex', 'gap': '0', 'alignItems': 'center',
            })
        ], style={
            'display': 'grid',
            'gridTemplateColumns': 'auto minmax(0, 1fr) auto',
            'gridTemplateAreas': '"expand content buttons"',
            'alignItems': 'center',
            'padding': '0 2px',
            'margin': '0',
            'borderRadius': '3px',
            'transition': 'all 0.2s'
        })
    ])

    dim_style = {'opacity': '0.5'} if dimmed and not is_selected else {}

    if children:
        initial_display = 'none'
        if data_manager and hasattr(data_manager, 'collapse_state'):
            stored_state = data_manager.collapse_state.get(file_id, 'collapsed')
            if stored_state == 'expanded':
                initial_display = 'block'

        return html.Div([
            main_item,
            html.Div(children, style={'marginLeft': '12px', 'display': initial_display},
                    id={'type': 'file-children', 'index': file_id})
        ], style=dim_style)
    else:
        return html.Div([main_item], style=dim_style) if dim_style else main_item




def register_clear_callbacks(app: dash.Dash, data_manager) -> None:
    """Register clear-related callbacks."""
    
    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('pub-selections', 'data', allow_duplicate=True),
         Output('file-removal-feedback', 'style', allow_duplicate=True),
         Output('file-removal-message', 'children', allow_duplicate=True),
         Output('undo-file-removal-btn', 'disabled', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('hidden-files', 'data', allow_duplicate=True)],
        Input('clear-files-btn', 'n_clicks'),
        State('active-file', 'data'), State('render-trigger', 'data'),
        prevent_initial_call=True
    )
    def clear_all_files(n_clicks, active_file, render_counter):
        """Clear all loaded files.  Sets active-file to None; master_render
        picks up the change and shows the empty-state plot."""
        if not n_clicks:
            return (dash.no_update,) * 12

        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        record = data_manager.file_removal_service.remove_all(active_file=active_file)
        if record is None:
            return (dash.no_update,) * 12

        empty_tree = [html.Div(
            'No files loaded',
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )]

        empty_table = html.Div(
            "No file selected",
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )

        empty_table_editor = create_data_table_editor(None, table_id='pub-table')

        return ([], empty_tree, None, empty_table, empty_table_editor, None, get_empty_selections(),
                {'display': 'flex'}, f'Removed {record.label}', False,
                (render_counter or 0) + 1, [])

    @app.callback(
        Output('status-text', 'children', allow_duplicate=True),
        Input('clear-cache-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_cache(n_clicks):
        """Delete file_state.json and clear in-memory persistent state."""
        if not n_clicks:
            return dash.no_update
        import os
        # Clear in-memory persistent state
        data_manager.file_ui_state.clear()
        data_manager.visibility_state.clear()
        data_manager.collapse_state.clear()
        data_manager.project.clear()
        data_manager._persistent_state.clear()
        if hasattr(data_manager, '_shared_plot_settings'):
            data_manager._shared_plot_settings.clear()
        # Delete the file on disk
        try:
            if os.path.exists(data_manager._STATE_FILE):
                os.remove(data_manager._STATE_FILE)
        except OSError:
            pass
        return 'Cache cleared — reload page to reset'
