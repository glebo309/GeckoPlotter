# Clean version of upload_callbacks.py with just the essential functions
from typing import List, Dict, Any
import dash
from dash import dcc, html, Input, Output, State, dash_table
import pandas as pd


def register_upload_callbacks(app: dash.Dash, data_manager) -> None:
    """Register upload-related callbacks."""
    
    # File types that have a dedicated raw-data plot
    KNOWN_RAW_TYPES = {
        'chromatogram', 'text', 'uvvis_csv',
        'lcms_cdf', 'lcms_ms_positive', 'lcms_ms_negative',
        'lcms_vwd_cdf', 'lcms_uv_a', 'lcms_uv_b', 'lcms_bundle',
    }

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('view-mode', 'data', allow_duplicate=True)],
        Input('upload-button', 'contents'),
        [State('upload-button', 'filename'),
         State('upload-button', 'last_modified'),
         State('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def handle_file_upload(contents_list: List[str], filenames: List[str],
                          last_modified_list: List[int], existing_files: List[Dict[str, Any]]) -> tuple:
        """Handle file upload and processing."""

        if not contents_list or not filenames:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            # Clear bundle manager to prevent stale bundles
            data_manager.bundle_manager.clear_bundles()
            
            # Create file records from uploaded files
            from services.storage_manager import create_file_records
            new_records = create_file_records(contents_list, filenames, last_modified_list)

            # Load data for each file and track successes
            success_count = 0
            for record in new_records:
                try:
                    file_data = data_manager.load_file_data(record)
                    if file_data:
                        print(f"✅ Successfully loaded {record['name']}")
                        success_count += 1
                    else:
                        print(f"❌ Failed to process {record['name']}")
                except Exception as e:
                    print(f"❌ Error loading {record['name']}: {str(e)}")

            # Prevent duplicates - merge files by name
            merged_files = []
            existing_names = set()
            
            # Add existing files first
            for f in (existing_files or []):
                fname = f.get('name')
                if fname and fname not in existing_names:
                    merged_files.append(f)
                    existing_names.add(fname)
            
            # Add new files that aren't duplicates
            for record in new_records:
                fname = record.get('name')
                if fname and fname not in existing_names:
                    merged_files.append(record)
                    existing_names.add(fname)
                else:
                    print(f"⚠️ Skipping duplicate file: {fname}")
            
            print(f"📊 Merged files: {len(merged_files)} total ({len(existing_names)} unique names)")
            
            # Get bundled tree items (this handles bundling logic)
            bundled_items = data_manager.get_bundled_tree_items(merged_files)
            
            # Auto-select and plot the last uploaded file
            auto_plot = dash.no_update
            auto_active_file = dash.no_update
            auto_table = dash.no_update
            file_data = None  # ensure defined for table editor block below

            if bundled_items:
                last_item = bundled_items[-1]
                last_file_id = last_item.get('id')

                if last_file_id:
                    auto_active_file = last_file_id

                    try:
                        from services.plot_manager import PlotManager
                        plot_manager = PlotManager()

                        main_file_id = last_file_id.split('|')[0] if '|' in last_file_id else last_file_id

                        file_data = data_manager.get_data_by_id(main_file_id)
                        if file_data:
                            auto_plot = plot_manager.get_plot_for_file(file_data)

                            from callbacks.viz_callbacks import create_data_table, create_bundle_data_table
                            bundle = data_manager.get_bundle_by_id(main_file_id)
                            if bundle:
                                auto_table = create_bundle_data_table(bundle, file_data, data_manager)
                            else:
                                auto_table = create_data_table(file_data)
                    except Exception as e:
                        print(f"Error auto-plotting: {e}")
                        import traceback
                        traceback.print_exc()

            # Render tree with selection highlighting
            tree_items = render_file_tree_with_bundles_selected(merged_files, data_manager, auto_active_file)

            # Create table editor for the auto-selected file
            table_editor = None
            pub_data = None
            if auto_active_file and auto_active_file != dash.no_update and file_data:
                from callbacks.viz_callbacks import prepare_table_data
                from components.data_table_editor import create_data_table_editor

                table_data = prepare_table_data(file_data, file_id=auto_active_file)
                table_editor = create_data_table_editor(table_data, table_id='pub-table')
                pub_data = table_data.to_json(orient='split') if table_data is not None else None
            
            # Simple success message
            if success_count > 0:
                print(f"🎉 Successfully uploaded {success_count} files!")

            # Auto-switch to analysis mode for generic/unknown file types
            # Exception: generic CSVs with auto-detected axes have a good raw plot
            auto_view_mode = dash.no_update
            if file_data and auto_active_file and auto_active_file != dash.no_update:
                ft = (file_data.get('metadata', {}).get('file_type')
                      or file_data.get('type')
                      or file_data.get('record', {}).get('type', ''))
                if ft not in KNOWN_RAW_TYPES:
                    sr = file_data.get('standardized')
                    has_auto_axes = False
                    if sr is not None:
                        has_auto_axes = bool(sr.x_columns and sr.y_columns)
                    else:
                        has_auto_axes = bool(
                            file_data.get('metadata', {}).get('auto_x')
                            and file_data.get('metadata', {}).get('auto_y')
                        )
                    if has_auto_axes:
                        auto_view_mode = 'raw'
                        print(f"📊 Showing raw plot for uploaded generic CSV with auto-detected axes")
                    else:
                        auto_view_mode = 'analysis'
                        print(f"🔀 Auto-switching to analysis mode for uploaded file type: {ft}")

            return merged_files, tree_items, auto_plot, auto_active_file, auto_table, table_editor, pub_data, auto_view_mode

        except Exception as e:
            print(f"❌ Upload failed: {str(e)}")
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


    # Mirror of handle_file_upload that triggers from drag-and-drop zone
    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('view-mode', 'data', allow_duplicate=True)],
        Input('drop-zone', 'contents'),
        [State('drop-zone', 'filename'),
         State('drop-zone', 'last_modified'),
         State('loaded-files', 'data')],
        prevent_initial_call=True
    )
    def handle_drop_upload(contents_list, filenames, last_modified_list, existing_files):
        if not contents_list or not filenames:
            return (dash.no_update,) * 8
        return handle_file_upload(contents_list, filenames, last_modified_list, existing_files)


def render_file_tree_with_bundles(records: List[dict], data_manager) -> List[html.Div]:
    """Render file tree with bundles from records."""
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    # Get bundled tree items
    bundled_items = data_manager.get_bundled_tree_items(records)
    
    tree_items = []
    for item in bundled_items:
        if item.get('is_bundle'):
            # Render bundle item
            tree_items.append(render_bundle_item(item, data_manager=data_manager))
        else:
            # Render individual file item
            tree_items.append(render_individual_file_item(item, data_manager=data_manager))
    
    return tree_items


def render_file_tree_with_bundles_selected(records: List[dict], data_manager, active_file_id: str = None) -> List[html.Div]:
    """Render file tree with bundles and selection highlighting from records."""
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    # Get bundled tree items
    bundled_items = data_manager.get_bundled_tree_items(records)
    
    tree_items = []
    for item in bundled_items:
        if item.get('is_bundle'):
            # Render bundle item with selection
            is_selected = active_file_id == item.get('id')
            tree_items.append(render_bundle_item_selected(item, is_selected, data_manager=data_manager))
        else:
            # Render individual file item with selection
            is_selected = active_file_id == item.get('id')
            tree_items.append(render_individual_file_item_selected(item, is_selected, data_manager=data_manager))
    
    return tree_items


def render_bundle_item(bundle_item: dict, data_manager=None) -> html.Div:
    """Render a bundle item."""
    return render_bundle_item_selected(bundle_item, is_selected=False, data_manager=data_manager)


def render_individual_file_item(item: dict, is_child: bool = False, data_manager=None) -> html.Div:
    """Render an individual file item."""
    return render_individual_file_item_selected(item, is_selected=False, is_child=is_child, data_manager=data_manager)


def render_bundle_item_selected(bundle_item: dict, is_selected: bool = False, data_manager=None) -> html.Div:
    """Render a bundle item with selection highlighting."""
    bundle_icon = bundle_item.get('icon', '📦')
    bundle_id = bundle_item.get('id')
    
    # Selection highlighting colors
    bg_color = '#fff5f0' if is_selected else '#ffffff'  # Light orange when selected
    border_color = '#ff6b35' if is_selected else '#e0e0e0'  # Orange border when selected
    
    # Check stored collapse state for expansion button and child visibility
    initial_icon = '▶'
    children_display = 'none'
    if data_manager and hasattr(data_manager, 'collapse_state'):
        stored_state = data_manager.collapse_state.get(bundle_id, 'collapsed')
        if stored_state == 'expanded':
            initial_icon = '▼'
            children_display = 'block'
            print(f"🔓 Restoring expanded LCMS bundle state for {bundle_id}")
    
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
                html.Span(bundle_icon, style={'marginRight': '6px', 'fontSize': '11px', 'flexShrink': '0'}),
                html.Span(bundle_item.get('name'), style={
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
                        'padding': '0', 'fontSize': '11px', 'opacity': '0.6',
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
                        'padding': '0', 'fontSize': '11px', 'opacity': '0.4',
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
    ], className='bundle-item')


def render_individual_file_item_selected(item: dict, is_selected: bool = False, is_child: bool = False, data_manager=None) -> html.Div:
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
    file_type = item.get('type')
    
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
                            html.Div(child.get('name', ''), style={'fontWeight': '500'}),
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
                print(f"🔓 Restoring expanded button for {file_id}")
        
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
                html.Span(item.get('name'), style={
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
            title=f"{item.get('type', 'unknown').capitalize()} · {item.get('size_display', '')}",
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
                        'padding': '0', 'fontSize': '11px', 'opacity': '0.6',
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
                        'padding': '0', 'fontSize': '11px', 'opacity': '0.4',
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

    # Return main item with children (initially collapsed)
    if children:
        # Check if this file should be expanded based on stored collapse state
        initial_display = 'none'  # Default collapsed
        if data_manager and hasattr(data_manager, 'collapse_state'):
            stored_state = data_manager.collapse_state.get(file_id, 'collapsed')
            if stored_state == 'expanded':
                initial_display = 'block'
                print(f"🔓 Restoring expanded state for {file_id}")
        
        return html.Div([
            main_item,
            html.Div(children, style={'marginLeft': '20px', 'display': initial_display}, 
                    id={'type': 'file-children', 'index': file_id})
        ])
    else:
        return main_item


def render_individual_file_item(item: dict, is_child: bool = False, data_manager=None) -> html.Div:
    """Render an individual file item."""
    # Just call the selected version without selection highlighting
    return render_individual_file_item_selected(item, is_selected=False, is_child=is_child, data_manager=data_manager)


def register_clear_callbacks(app: dash.Dash, data_manager) -> None:
    """Register clear-related callbacks."""
    
    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('pub-selections', 'data', allow_duplicate=True)],
        Input('clear-files-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def clear_all_files(n_clicks):
        """Clear all loaded files."""
        if not n_clicks:
            return (dash.no_update,) * 8

        from components.data_table_editor import create_data_table_editor
        from components.axis_mapper import get_empty_selections

        # Clear data manager
        data_manager.clear_data()

        # Return empty states
        import plotly.graph_objects as go
        empty_fig = go.Figure()
        empty_fig.add_annotation(
            text="Upload files to get started",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False,
            font=dict(size=16, color="#666")
        )
        empty_fig.update_layout(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=0, r=0, t=0, b=0)
        )

        empty_tree = [html.Div(
            'No files loaded',
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )]

        empty_table = html.Div(
            "No file selected",
            style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
        )

        empty_table_editor = create_data_table_editor(None, table_id='pub-table')

        return [], empty_tree, empty_fig, None, empty_table, empty_table_editor, None, get_empty_selections()

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
