"""
Data Table Editor Component
Interactive table with cell selection for publication plotting
"""

import logging

from dash import dash_table, html, dcc
import pandas as pd

from dash_iconify import DashIconify
from components.table_styles import (
    TABLE_STYLE_TABLE, TABLE_STYLE_CELL, TABLE_STYLE_HEADER, TABLE_STYLE_DATA,
)



log = logging.getLogger(__name__)

def create_data_table_editor(df=None, table_id='pub-table', default_selected_columns=None,
                             sheet_names=None, active_sheet=None, source=None):
    """Create an editable data table with cell selection capabilities.

    The rows stay on the server (services/table_store.py): the table is created empty and the Data tab asks for one
    page at a time while it is shown.

    Args:
        default_selected_columns: list of column IDs to pre-select (header highlight).
        source: the table_store reference of ``df``; made here when not given.
    """
    from services import table_store

    if df is None:
        # Empty state — includes a hidden empty DataTable so callbacks
        # referencing 'pub-table' never hit a nonexistent component.
        return html.Div([
            dcc.Store(id='active-sheet-name', data=None),
            dcc.Store(id='pub-table-source', data=None),
            html.Div(
                [
                    DashIconify(icon='tabler:table', width=36, height=36, style={'color': '#bbb'}),
                    html.H4('No data loaded', className='empty-state__title'),
                    html.P('Select a file from the explorer to view and edit data', className='empty-state__subtitle'),
                ],
                className='empty-state'
            ),
            dash_table.DataTable(
                id=table_id,
                columns=[],
                data=[],
                style_table={'display': 'none'},
            ),
        ])
    
    # Add row identifier if not present
    if '_row_id' not in df.columns:
        df.insert(0, '_row_id', range(len(df)))
    if source is None:
        source = table_store.remember(df)

    # Prepare data for table — mark columns as selectable/deletable/renamable
    # (except _row_id which is internal). This is critical for column header
    # click-to-select to work with column_selectable='single'.
    columns = [
        {
            "name": col,
            "id": col,
            "editable": col != '_row_id',
            "selectable": col != '_row_id',
            "deletable": col != '_row_id',
            "renamable": col != '_row_id',
        }
        for col in df.columns
    ]

    # Filter default_selected_columns to only include valid column IDs
    sel_cols = []
    if default_selected_columns:
        valid_ids = {c['id'] for c in columns}
        sel_cols = [c for c in default_selected_columns if c in valid_ids]

    # Sheet tabs for multi-sheet Excel files
    sheet_tabs = []
    if sheet_names and len(sheet_names) > 1:
        tabs = []
        for sname in sheet_names:
            is_active = sname == active_sheet
            tabs.append(html.Button(
                sname,
                id={'type': 'sheet-tab', 'index': sname},
                n_clicks=0,
                style={
                    'padding': '4px 12px',
                    'fontSize': '11px',
                    'border': 'none',
                    'borderBottom': '2px solid #1a1a1a' if is_active else '2px solid transparent',
                    'backgroundColor': '#2a2a2a' if is_active else '#1a1a1a',
                    'color': '#ddd' if is_active else '#777',
                    'cursor': 'pointer',
                    'fontWeight': '600' if is_active else '400',
                    'marginRight': '2px',
                    'borderRadius': '4px 4px 0 0',
                },
            ))
        sheet_tabs = [html.Div(tabs, style={
            'display': 'flex',
            'backgroundColor': '#1a1a1a',
            'padding': '4px 4px 0',
            'borderRadius': '4px 4px 0 0',
            'overflowX': 'auto',
        })]

    # Store active sheet name for the callback
    active_sheet_store = dcc.Store(id='active-sheet-name', data=active_sheet)

    # Return just the table - buttons are now in the toolbox (axis_mapper.py)
    return html.Div(sheet_tabs + [
        active_sheet_store,
        dcc.Store(id='pub-table-source', data=source),
        dash_table.DataTable(
            id=table_id,
            columns=columns,
            data=[],
            editable=True,
            cell_selectable=True,
            column_selectable='single',
            row_deletable=True,
            sort_action='custom',
            sort_by=[],
            page_size=table_store.PAGE_SIZE,
            page_current=0,
            page_count=max(1, -(-len(df) // table_store.PAGE_SIZE)),
            page_action='custom',
            selected_columns=sel_cols if sel_cols else [],
            style_table=TABLE_STYLE_TABLE,
            style_cell=TABLE_STYLE_CELL,
            style_header=TABLE_STYLE_HEADER,
            style_header_conditional=[
                {'if': {'column_id': '_row_id'}, 'display': 'none'}
            ],
            style_data=TABLE_STYLE_DATA,
            style_cell_conditional=[
                {'if': {'column_id': '_row_id'}, 'display': 'none'}
            ],
            style_data_conditional=[
                {'if': {'column_id': '_row_id'}, 'display': 'none'}
            ],
        )
    ], style={'height': '100%'})


def transpose_dataframe(df):
    """Transpose dataframe while preserving row IDs"""
    # Remove _row_id column temporarily
    df_no_id = df.drop(columns=['_row_id']) if '_row_id' in df.columns else df
    
    # Transpose
    df_t = df_no_id.T
    
    # Use first column as new column names if they're all strings/numbers
    try:
        df_t.columns = [str(c) for c in df_t.iloc[0]]
        df_t = df_t.iloc[1:]
    except:
        pass
    
    # Reset index to become a column
    df_t = df_t.reset_index()
    df_t.columns = ['Variable'] + list(df_t.columns[1:])
    
    # Replace None, NaN, "None" with empty string
    df_t = df_t.fillna('')
    df_t = df_t.replace(['None', 'nan', 'NaN'], '')
    
    # Add new row IDs
    df_t.insert(0, '_row_id', range(len(df_t)))
    
    return df_t
