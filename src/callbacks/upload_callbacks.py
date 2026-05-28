# Clean version of upload_callbacks.py with just the essential functions
import logging
import os

from typing import List, Dict, Any
import dash
from dash import dcc, html, Input, Output, State, dash_table
import pandas as pd



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
         Output('render-trigger', 'data', allow_duplicate=True)],
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
            return (dash.no_update,) * 7

        try:
            import base64
            import tempfile
            from ingestion import ingest_file
            from services.bundling_service import assign_bundles

            parsed_files = []
            failed_names = set()

            for contents, fname in zip(contents_list, filenames):
                try:
                    _, encoded = contents.split(",", 1)
                    raw_bytes = base64.b64decode(encoded)

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{fname}")
                    tmp.write(raw_bytes)
                    tmp.close()
                    data_manager.temp_files.append(tmp.name)

                    sr = ingest_file(tmp.name, fname)
                    if sr is None:
                        log.warning(f"Pipeline could not parse {fname}")
                        failed_names.add(fname)
                        continue

                    parsed_files.append((fname, raw_bytes, sr))
                except Exception as e:
                    log.error(f"Error parsing {fname}: {e}")
                    failed_names.add(fname)

            if not parsed_files:
                return (dash.no_update,) * 7

            new_bundles = assign_bundles(parsed_files)

            last_bundle_id = None
            for bundle in new_bundles:
                data_manager.add_bundle(bundle)
                last_bundle_id = bundle.bundle_id
                log.debug(f"Created bundle '{bundle.name}' ({bundle.bundle_type.value}) "
                          f"with {len(bundle.component_list)} components")

                if bundle.has_integration_data():
                    _auto_import_peaks(data_manager, bundle)

            loaded_files = data_manager.get_loaded_files_list()

            auto_active_file = last_bundle_id or dash.no_update
            auto_table = dash.no_update
            table_editor = None
            pub_data = None

            if auto_active_file and auto_active_file != dash.no_update:
                file_data = data_manager.get_data_by_id(auto_active_file)
                if file_data:
                    try:
                        from callbacks.viz_callbacks import create_data_table, create_bundle_data_table
                        bundle = data_manager.get_bundle(auto_active_file)
                        if bundle and bundle.bundle_type.value != 'generic':
                            compat = data_manager.get_bundle_by_id(auto_active_file)
                            auto_table = create_bundle_data_table(compat, file_data, data_manager)
                        else:
                            auto_table = create_data_table(file_data)
                    except Exception:
                        log.exception("Error building metadata table")

                    from callbacks.viz_callbacks import prepare_table_data
                    from components.data_table_editor import create_data_table_editor

                    table_data = prepare_table_data(file_data, file_id=auto_active_file)
                    sheet_names = file_data.get('metadata', {}).get('sheet_names')
                    active_sheet = file_data.get('metadata', {}).get('active_sheet')
                    table_editor = create_data_table_editor(
                        table_data, table_id='pub-table',
                        sheet_names=sheet_names, active_sheet=active_sheet,
                    )
                    pub_data = table_data.to_json(orient='split') if table_data is not None else None

            tree_items = render_file_tree_with_bundles_selected(
                loaded_files, data_manager, auto_active_file)

            log.debug(f"Upload complete: {len(new_bundles)} bundles from {len(parsed_files)} files")
            return (loaded_files, tree_items, auto_active_file, auto_table,
                    table_editor, pub_data, (render_counter or 0) + 1)

        except Exception as e:
            log.exception(f"Upload failed: {str(e)}")
            return (dash.no_update,) * 7

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True)],
        Input('drop-zone', 'contents'),
        [State('drop-zone', 'filename'),
         State('drop-zone', 'last_modified'),
         State('loaded-files', 'data'),
         State('render-trigger', 'data')],
        prevent_initial_call=True
    )
    def handle_drop_upload(contents_list, filenames, last_modified_list, existing_files, render_counter):
        if not contents_list or not filenames:
            return (dash.no_update,) * 7
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
            groups[tid] = {'label': _tab_label_from_group(group), 'items': []}
        groups[tid]['items'].append(item)

    tree_items = []
    for tid, group_info in groups.items():
        is_active_group = tid == active_plot_tab
        group_order = file_order.get(tid, {})
        sort_dir = group_order.get('sort_dir', 'asc')
        sorted_items = _sort_group_items(group_info['items'], group_order)

        tree_items.append(_render_group_header(
            group_info['label'], tid, is_active_group, sort_dir=sort_dir))

        group_container_children = []
        for item in sorted_items:
            file_id = item.get('id')
            if item.get('is_bundle'):
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


def _render_group_header(label: str, group_id: str, is_active: bool, sort_dir: str = 'asc') -> html.Div:
    """Render a group header in the file tree with sort toggle."""
    arrow = '↑' if sort_dir == 'asc' else '↓'
    return html.Div([
        html.Span(label, style={
            'fontWeight': '600' if is_active else '500',
            'fontSize': '11px',
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'color': '#ff6b35' if is_active else '#888',
        }),
        html.Button(arrow, id={'type': 'group-sort-btn', 'index': group_id},
            n_clicks=0,
            style={
                'padding': '0 4px', 'fontSize': '10px', 'lineHeight': '14px',
                'border': '1px solid #ccc', 'borderRadius': '3px',
                'backgroundColor': 'white', 'color': '#888', 'cursor': 'pointer',
                'marginLeft': '6px', 'verticalAlign': 'middle',
            }),
    ], className='file-group-header active' if is_active else 'file-group-header',
        style={
            'padding': '6px 8px 3px 8px',
            'marginTop': '6px',
            'borderBottom': '1px solid #ff6b35' if is_active else '1px solid #e0e0e0',
            'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between',
        },
    )


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

    # Selection highlighting colors
    bg_color = '#fff5f0' if is_selected else '#ffffff'
    opacity = '0.5' if dimmed and not is_selected else '1.0'
    
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
                    title='Collapse/Expand',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0 4px',
                        'fontSize': '12px',
                        'width': '20px',
                        'height': '20px',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'center'
                    }
                )
            ], style={'gridArea': 'expand', 'display': 'flex', 'alignItems': 'center'}),
            
            # Bundle content (clickable for selection)
            html.Div([
                html.Span(os.path.splitext(bundle_item.get('name', ''))[0], style={
                    'fontWeight': '600', 'overflow': 'hidden', 'textOverflow': 'ellipsis',
                    'whiteSpace': 'nowrap', 'flex': '1',
                }),
                html.Span(bundle_item.get('size_display', ''), style={
                    'fontSize': '10px', 'color': '#999', 'marginLeft': '6px', 'flexShrink': '0',
                }),
            ],
            className='file-tree-item',
            id={'type': 'file-tree-item', 'index': bundle_id},
            n_clicks=0,
            style={
                'gridArea': 'content',
                'display': 'flex',
                'alignItems': 'center',
                'cursor': 'pointer',
                'padding': '1px 6px',
                'borderRadius': '3px',
                'backgroundColor': bg_color,
                'borderLeft': f'2px solid {"#ff6b35" if is_selected else "transparent"}',
                'transition': 'all 0.15s',
                'flex': '1',
                'lineHeight': '1.4',
            }),

            # Control buttons
            html.Div([
                html.Button(
                    '👁',
                    id={'type': 'visibility-btn', 'index': bundle_id},
                    title='Toggle visibility',
                    className='tree-action-btn',
                    style={
                        'background': 'none', 'border': 'none', 'cursor': 'pointer',
                        'padding': '0', 'fontSize': '11px',
                        'width': '18px', 'height': '18px',
                        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    }
                ),
                html.Button(
                    '🗑',
                    id={'type': 'delete-btn', 'index': bundle_id},
                    title='Delete bundle',
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
            'gridTemplateColumns': 'auto 1fr auto',
            'gridTemplateAreas': '"expand content buttons"',
            'alignItems': 'center',
            'gap': '2px',
            'padding': '2px',
            'margin': '1px 0',
            'borderRadius': '3px',
            'transition': 'all 0.2s'
        }),

        # Children (initially collapsed)
        html.Div([
            render_individual_file_item(child, is_child=True, data_manager=data_manager)
            for child in bundle_item.get('children', [])
        ], style={'marginLeft': '16px', 'display': children_display},
          id={'type': 'bundle-children', 'index': bundle_id})
    ], className='bundle-item', style={'opacity': opacity})


def render_individual_file_item_selected(item: dict, is_selected: bool = False, is_child: bool = False, data_manager=None, dimmed: bool = False) -> html.Div:
    """Render an individual file item with selection highlighting using clean grid layout."""
    # Define icons for different file types
    TYPE_ICONS = {
        'table': '📊',
        'csv': '📊',
        'generic_csv': '📊',
        'structured': '🧩',
        'image': '🖼️',
        'chromatogram': '🌊',
        'spectra': '📈',
        'uvvis_csv': '🧪',
        'lcms_bundle': '🧪',
        'lcms_ms_positive': '➕',
        'lcms_ms_negative': '➖',
        'lcms_uv_a': '🌈',
        'lcms_uv_b': '🌈',
        'text': '📄',
        'binary': '💾',
        'unknown': '❓',
    }

    icon = TYPE_ICONS.get(item.get('type'), TYPE_ICONS.get('unknown', '❓'))
    file_id = item.get('id')

    # Selection highlighting colors
    bg_color = '#fff5f0' if is_selected else '#ffffff'
    border_color = '#ff6b35' if is_selected else '#e0e0e0'
    
    # Check if this item has children (like UV-Vis wells)
    children = []
    has_children = 'children' in item and item['children'] and not is_child
    
    if has_children:
        for child in item['children']:
            child_id = child.get('id')
            
            # Default visibility state for child
            is_child_visible = True
            child_icon = '👁'
            child_opacity = '1.0'
            
            # Use grid layout for child items too
            child_icon_symbol = child.get('icon', '🧪')
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
                    html.Div(style={'gridArea': 'expand', 'width': '20px'}),
                    
                    # Child content (clickable for selection)
                    html.Div([
                        html.Span(child_icon_symbol, style={'marginRight': '8px'}),
                        html.Div([
                            html.Div(os.path.splitext(child.get('name', ''))[0], style={'fontWeight': '500'}),
                            html.Div(child_info, style={'fontSize': '12px', 'color': '#666'}),
                        ], style={'flex': '1'})
                    ], 
                    className='file-tree-item',
                    id={'type': 'file-tree-item', 'index': child_id}, 
                    n_clicks=0,
                    style={
                        'gridArea': 'content',
                        'display': 'flex',
                        'alignItems': 'center',
                        'cursor': 'pointer',
                        'padding': '4px 8px',
                        'borderRadius': '4px',
                        'backgroundColor': '#f8f9fa',
                        'border': '1px solid #e0e0e0',
                        'transition': 'all 0.2s'
                    }),
                    
                    # Control buttons for child items
                    html.Div([
                        html.Button(
                            child_icon,
                            id={'type': 'visibility-btn', 'index': child_id},
                            title='Toggle visibility',
                            style={
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'padding': '0 4px',
                                'fontSize': '14px',
                                'opacity': child_opacity,
                                'width': '24px',
                                'height': '24px',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center',
                                'borderRadius': '3px'
                            }
                        ),
                        html.Button(
                            '🗑',
                            id={'type': 'delete-btn', 'index': child_id},
                            title='Delete component',
                            style={
                                'background': 'none',
                                'border': 'none',
                                'cursor': 'pointer',
                                'padding': '0 4px',
                                'fontSize': '14px',
                                'color': '#dc3545',
                                'width': '24px',
                                'height': '24px',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center',
                                'borderRadius': '3px'
                            }
                        ),
                    ], style={
                        'gridArea': 'buttons',
                        'display': 'flex',
                        'gap': '2px',
                        'alignItems': 'center'
                    })
                ], style={
                    'display': 'grid',
                    'gridTemplateColumns': 'auto 1fr auto',
                    'gridTemplateAreas': '"expand content buttons"',
                    'alignItems': 'center',
                    'gap': '2px',
                    'padding': '2px',
                    'margin': '1px 0',
                    'borderRadius': '3px',
                    'transition': 'all 0.2s'
                })
            ])
            children.append(child_item)
    
    # Add collapse button if has children
    collapse_button_area = html.Div(style={'gridArea': 'expand', 'width': '20px'})
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
                title='Expand/Collapse',
                style={
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '12px',
                    'width': '20px',
                    'height': '20px',
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
                html.Span(icon, style={'marginRight': '6px', 'fontSize': '11px', 'flexShrink': '0'}),
                html.Span(os.path.splitext(item.get('name', ''))[0], style={
                    'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap', 'flex': '1',
                    'fontWeight': '500' if is_selected else '400',
                }),
                html.Span(item.get('size_display', ''), style={
                    'fontSize': '10px', 'color': '#999', 'marginLeft': '6px', 'flexShrink': '0',
                }),
            ],
            className='file-tree-item',
            id={'type': 'file-tree-item', 'index': file_id},
            n_clicks=0,
            title=f"{(item.get('type') or 'unknown').capitalize()} · {item.get('size_display', '')}",
            style={
                'gridArea': 'content',
                'display': 'flex',
                'alignItems': 'center',
                'cursor': 'pointer',
                'padding': '1px 6px',
                'borderRadius': '3px',
                'backgroundColor': bg_color,
                'borderLeft': f'2px solid {"#ff6b35" if is_selected else "transparent"}',
                'transition': 'all 0.15s',
                'flex': '1',
                'lineHeight': '1.4',
            }),
            
            # Control buttons
            html.Div([
                html.Button(
                    '👁',
                    id={'type': 'visibility-btn', 'index': file_id},
                    title='Toggle visibility',
                    className='tree-action-btn',
                    style={
                        'background': 'none', 'border': 'none', 'cursor': 'pointer',
                        'padding': '0', 'fontSize': '11px',
                        'width': '18px', 'height': '18px',
                        'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    }
                ),
                html.Button(
                    '🗑',
                    id={'type': 'delete-btn', 'index': file_id},
                    title='Delete file',
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
            'gridTemplateColumns': 'auto 1fr auto',
            'gridTemplateAreas': '"expand content buttons"',
            'alignItems': 'center',
            'padding': '2px',
            'margin': '1px 0',
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
            html.Div(children, style={'marginLeft': '20px', 'display': initial_display},
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
         Output('pub-selections', 'data', allow_duplicate=True)],
        Input('clear-files-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def clear_all_files(n_clicks):
        """Clear all loaded files.  Sets active-file to None; master_render
        picks up the change and shows the empty-state plot."""
        if not n_clicks:
            return (dash.no_update,) * 7

        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        data_manager.clear_data()

        empty_tree = [html.Div(
            'No files loaded',
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )]

        empty_table = html.Div(
            "No file selected",
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )

        empty_table_editor = create_data_table_editor(None, table_id='pub-table')

        return [], empty_tree, None, empty_table, empty_table_editor, None, get_empty_selections()

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
