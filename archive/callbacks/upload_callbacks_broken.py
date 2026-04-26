# =============================================================================
# File: callbacks/upload_callbacks.py
# =============================================================================
"""
Simple file upload callbacks for GeckoPlotter V2.
"""

from typing import List, Dict, Any
import time
import dash
from dash import Input, Output, State, html
from services.storage_manager import create_file_records, merge_records, DataManager


def register_upload_callbacks(app: dash.Dash, data_manager: DataManager) -> None:
    """Register file upload related callbacks."""

    @app.callback(
        [Output('loaded-files', 'data'),
         Output('file-tree', 'children'),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('data-table-container', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True)],
        Input('upload-button', 'contents'),
        State('upload-button', 'filename'),
        State('upload-button', 'last_modified'),
        State('loaded-files', 'data'),
        prevent_initial_call=True
    )
    def handle_file_upload(contents_list: List[str], filenames: List[str],
                          last_modified_list: List[int], existing_files: List[Dict[str, Any]]) -> tuple:
        """Handle file upload and processing."""

        if not contents_list or not filenames:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            # Clear bundle manager to prevent stale bundles
            data_manager.bundle_manager.clear_bundles()
            
            # Create file records from uploaded files
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
            tree_items = render_file_tree_with_bundles(merged_files, data_manager)
            
            # AUTO-PLOT THE LAST BUNDLE OR FILE
            plot_fig = None
            data_table = html.Div("Select a file to view data details", 
                                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'})
            selected_id = None  # Track what we auto-selected
            
            # Find the last bundle created from new files (use bundled_items for logic)
            for item in reversed(bundled_items):
                if item.get('is_bundle'):
                    bundle_id = item.get('id')
                    bundle = data_manager.bundle_manager.get_bundle_by_id(bundle_id)
                    if bundle and bundle.main_file:
                        main_file_id = bundle.main_file.get('id')
                        # Check if this main file was just uploaded
                        for record in new_records:
                            if record.get('id') == main_file_id:
                                # AUTO-PLOT THIS BUNDLE
                                file_data = data_manager.get_data_by_id(main_file_id)
                                if file_data:
                                    from services.plot_manager import PlotManager
                                    from callbacks.viz_callbacks import create_bundle_data_table
                                    
                                    plot_manager = PlotManager()
                                    plot_fig = plot_manager.get_plot_for_file(file_data)
                                    data_table = create_bundle_data_table(bundle, file_data)
                                    selected_id = bundle_id  # Set the selected ID to the bundle
                                    
                                    print(f"🎯 AUTO-PLOTTED BUNDLE: {bundle_id}")
                                    break
                    if plot_fig:
                        break
            # If no bundle, auto-plot the last successfully loaded file
            if not plot_fig:
                for record in reversed(new_records):
                    file_data = data_manager.get_data_by_id(record['id'])
                    if file_data:
                        from services.plot_manager import PlotManager
                        from callbacks.viz_callbacks import create_data_table
                        
                        plot_manager = PlotManager()
                        plot_fig = plot_manager.get_plot_for_file(file_data)
                        data_table = create_data_table(file_data)
                        selected_id = record['id']  # Set the selected ID to the file
                        
                        print(f"🎯 AUTO-PLOTTED FILE: {record['name']}")
                        break

            print(f"📊 Upload complete: {success_count}/{len(new_records)} files processed")
            
            # Return default plot if nothing to plot
            if not plot_fig:
                import plotly.graph_objects as go
                plot_fig = go.Figure(layout=go.Layout(
                    title='Upload files to start visualizing data',
                    xaxis={'title': 'X Axis'},
                    yaxis={'title': 'Y Axis'},
                    template='plotly_white',
                    height=400,
                ))
            
            return merged_files, tree_items, plot_fig, data_table, selected_id

        except Exception as e:
            print(f"❌ Upload failed: {str(e)}")
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


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
            tree_items.append(render_bundle_item(item))
        else:
            # Render individual file item
            tree_items.append(render_individual_file_item(item, data_manager=data_manager))
    
    return tree_items


def render_file_tree_with_bundles_selected(records: List[dict], data_manager, selected_id: str = None) -> List[html.Div]:
    """Render file tree with bundles and highlight selected item."""
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
            # Check if this bundle is selected
            is_selected = (selected_id == item.get('id'))
            tree_items.append(render_bundle_item_selected(item, is_selected))
        else:
            # Check if this file is selected
            is_selected = (selected_id == item.get('id'))
            tree_items.append(render_individual_file_item_selected(item, is_selected, data_manager=data_manager))
    
    return tree_items


def render_bundle_item_selected(bundle_item: dict, is_selected: bool = False) -> html.Div:
    """Render a bundle item with selection highlighting."""
    bundle_icon = bundle_item.get('icon', '📦')
    bundle_id = bundle_item.get('id')
    
    # Highlight if selected
    background_color = '#fff5f0' if is_selected else '#ffffff'
    border_color = '#ff6b35' if is_selected else '#e0e0e0'
    name_color = '#ff6b35' if is_selected else '#333'
    
    return html.Div([
        html.Div([
            # Expand/collapse button
            html.Button(
                '▶',
                id={'type': 'expand-btn', 'index': bundle_id},
                style={
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '12px',
                    'color': '#666'
                }
            ),
            # Bundle icon and name
            html.Span(bundle_icon, style={'marginRight': '8px'}),
            html.Div([
                html.Div(bundle_item.get('name'), style={'fontWeight': '600', 'color': name_color}),
                html.Div(
                    f"{bundle_item.get('type', 'bundle').capitalize()} · {bundle_item.get('size_display')}",
                    style={'fontSize': '12px', 'color': '#666'},
                ),
            ], style={'flex': '1'}),
            # Control buttons
            html.Div([
                html.Button(
                    '👁',
                    id={'type': 'visibility-btn', 'index': bundle_id},
                    title='Toggle visibility',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0 4px',
                        'fontSize': '14px'
                    }
                ),
                html.Button(
                    '🗑',
                    id={'type': 'delete-btn', 'index': bundle_id},
                    title='Delete bundle',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0 4px',
                        'fontSize': '14px',
                        'color': '#dc3545'
                    }
                ),
            ], style={'display': 'flex', 'gap': '4px'}),
        ], style={
            'padding': '8px',
            'cursor': 'pointer',
            'borderRadius': '4px',
            'margin': '2px 0',
            'display': 'flex',
            'alignItems': 'center',
            'backgroundColor': background_color,
            'border': f'1px solid {border_color}',
            'transition': 'all 0.2s',
        }, id={'type': 'file-tree-item', 'index': bundle_id}, n_clicks=0),
        # Children (initially collapsed)
        html.Div([
            render_individual_file_item(child, is_child=True, data_manager=data_manager) 
            for child in bundle_item.get('children', [])
        ], style={'marginLeft': '20px', 'display': 'none'}, 
          id={'type': 'bundle-children', 'index': bundle_id})
    ], className='bundle-item')


def render_individual_file_item_selected(item: dict, is_selected: bool = False, is_child: bool = False, data_manager=None) -> html.Div:
    """Render an individual file item with selection highlighting."""
    # For now, just call the regular function - we can enhance this later if needed
    return render_individual_file_item(item, is_child, data_manager)


def render_bundle_item(bundle_item: dict) -> html.Div:
    """Render a bundle item."""
    bundle_icon = bundle_item.get('icon', '📦')
    bundle_id = bundle_item.get('id')
    
    return html.Div([
        html.Div([
            html.Button(
                '▼',  # Expanded by default
                id={'type': 'expand-btn', 'index': bundle_id},
                title='Collapse/Expand',
                style={
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '12px',
                    'marginRight': '4px'
                }
            ),
            html.Span(bundle_icon, style={'marginRight': '8px'}),
            html.Div([
                html.Div(bundle_item.get('name'), style={'fontWeight': 'bold'}),
                html.Div(bundle_item.get('size_display', ''), style={'fontSize': '12px', 'color': '#666'}),
            ], style={'flex': '1'}),
            # Control buttons
            html.Div([
                html.Button(
                    '👁',
                    id={'type': 'visibility-btn', 'index': bundle_id},
                    title='Toggle visibility',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0 4px',
                        'fontSize': '14px'
                    }
                ),
                html.Button(
                    '🗑',
                    id={'type': 'delete-btn', 'index': bundle_id},
                    title='Delete bundle',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '0 4px',
                        'fontSize': '14px',
                        'color': '#dc3545'
                    }
                ),
            ], style={'display': 'flex', 'gap': '4px'}),
        ], style={
            'padding': '8px',
            'cursor': 'pointer',
            'borderRadius': '4px',
            'margin': '2px 0',
            'display': 'flex',
            'alignItems': 'center',
            'backgroundColor': '#ffffff',
            'border': '1px solid #e0e0e0',
            'transition': 'all 0.2s',
        }, id={'type': 'file-tree-item', 'index': bundle_id}, n_clicks=0),
        # Children (initially collapsed)
        html.Div([
            render_individual_file_item(child, is_child=True, data_manager=None) 
            for child in bundle_item.get('children', [])
        ], style={'marginLeft': '20px', 'display': 'none'}, 
          id={'type': 'bundle-children', 'index': bundle_id})
    ], className='bundle-item')


def render_bundle_item_selected(bundle_item: dict, is_selected: bool = False) -> html.Div:
    """Render a bundle item with selection highlighting."""
    # For now, just call the regular function - we can enhance this later if needed
    return render_bundle_item(bundle_item)


def render_file_tree(records: List[dict]) -> List[html.Div]:
    """Render file tree from records."""
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#888', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    tree_items = []
    for record in records:
        tree_items.append(render_individual_file_item(record))
    
    return tree_items
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '14px'
                }
            ),
            html.Button(
                '🗑',
                id={'type': 'delete-btn', 'index': file_id},
                title='Delete file',
                style={
                    'background': 'none',
                    'border': 'none',
                    'cursor': 'pointer',
                    'padding': '0 4px',
                    'fontSize': '14px',
                    'color': '#dc3545'
                }
            ),
        ], style={'display': 'flex', 'gap': '4px'}) if not is_child else html.Div(),
    ], style={
        'padding': '6px 8px' if is_child else '8px',
        'cursor': 'pointer',
        'borderRadius': '4px',
        'margin': '1px 0',
        'display': 'flex',
        'alignItems': 'center',
        'transition': 'background-color 0.2s',
        'backgroundColor': '#f8f9fa' if is_child else 'transparent',
    },
    className='file-tree-item',
    id={'type': 'file-tree-item', 'index': file_id},
    n_clicks=0,
    )
    
    # Return main item with children (initially collapsed)
    if children:
        return html.Div([
            main_item,
            html.Div(children, style={'marginLeft': '20px', 'display': 'none'}, 
                    id={'type': 'file-children', 'index': file_id})
        ])
    else:
        return main_item


def render_file_tree(records: List[dict]) -> List[html.Div]:
    """Render file tree from records."""
    if not records:
        return [
            html.Div(
                'No files loaded',
                style={'color': '#888', 'padding': '20px', 'textAlign': 'center'},
            )
        ]

    # Define icons for different file types
    TYPE_ICONS = {
        'table': '📊',
        'structured': '🧩',
        'image': '🖼️',
        'chromatogram': '🌊',
        'spectra': '📈',
        'uvvis_csv': '🧪',
        'text': '📄',
        'binary': '💾',
        'unknown': '❓',
    }

    tree_items = []
    for record in records:
        icon = TYPE_ICONS.get(record.get('type'), TYPE_ICONS['unknown'])
        tree_items.append(
            html.Div(
                [
                    html.Span(icon, style={'marginRight': '8px'}),
                    html.Div(
                        [
                            html.Div(record.get('name'), style={'fontWeight': '500'}),
                            html.Div(
                                f"{record.get('type', 'unknown').capitalize()} · {record.get('size_display')}",
                                style={'fontSize': '12px', 'color': '#666'},
                            ),
                        ],
                    ),
                ],
                style={
                    'padding': '8px',
                    'cursor': 'pointer',
                    'borderRadius': '4px',
                    'margin': '2px 0',
                    'display': 'flex',
                    'alignItems': 'center',
                    'transition': 'background-color 0.2s',
                },
                className='file-tree-item',
                id={'type': 'file-tree-item', 'index': record.get('id')},
                n_clicks=0,
            )
        )
    return tree_items


def register_clear_callbacks(app: dash.Dash, data_manager: DataManager) -> None:

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('main-plot', 'figure', allow_duplicate=True),
         Output('data-table-container', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True)],
        Input('clear-files-btn', 'n_clicks'),
        State('loaded-files', 'data'),
        prevent_initial_call=True
    )
    def clear_all_files(n_clicks: int, current_files: List[Dict[str, Any]]) -> tuple:
        """Clear all loaded files and reset the entire interface."""
        if n_clicks and current_files:
            # Clear data manager completely
            data_manager.clear_data()
            
            # Create empty plot
            import plotly.graph_objects as go
            empty_fig = go.Figure(layout=go.Layout(
                title='Upload files to start visualizing data',
                xaxis={'title': 'X Axis'},
                yaxis={'title': 'Y Axis'},
                template='plotly_white',
                height=400,
            ))
            
            # Create empty data table
            empty_table = html.Div(
                'Select a file to view data details',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
            )
            
            # Empty file tree
            empty_tree = [html.Div(
                'No files loaded',
                style={'color': '#666', 'padding': '20px', 'textAlign': 'center'}
            )]

            print(f"🗑️ Cleared {len(current_files)} file(s) and reset interface")
            return [], empty_tree, empty_fig, empty_table, None

        return current_files, dash.no_update, dash.no_update, dash.no_update, dash.no_update
