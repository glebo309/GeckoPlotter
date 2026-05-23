"""
Data Table Editor Component
Interactive table with cell selection for publication plotting
"""

import logging

from dash import dash_table, html
import pandas as pd



log = logging.getLogger(__name__)

def create_data_table_editor(df=None, table_id='pub-table', default_selected_columns=None):
    """Create an editable data table with cell selection capabilities.

    Args:
        default_selected_columns: list of column IDs to pre-select (header highlight).
    """
    
    if df is None:
        # Empty state — includes a hidden empty DataTable so callbacks
        # referencing 'pub-table' never hit a nonexistent component.
        return html.Div([
            html.Div(
                [
                    html.Span('📊', className='empty-state__icon'),
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
    
    # DEBUG: Check data shape before creating table
    log.debug(f"create_data_table_editor: df.shape = {df.shape}")
    log.debug(f"Columns: {list(df.columns)}")
    log.debug(f"First row: {df.iloc[0].to_dict() if len(df) > 0 else 'empty'}")
    
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
    data_dict = df.to_dict('records')

    # Filter default_selected_columns to only include valid column IDs
    sel_cols = []
    if default_selected_columns:
        valid_ids = {c['id'] for c in columns}
        sel_cols = [c for c in default_selected_columns if c in valid_ids]

    # Return just the table - buttons are now in the toolbox (axis_mapper.py)
    return html.Div([
        dash_table.DataTable(
            id=table_id,
            columns=columns,
            data=data_dict,
            editable=True,
            cell_selectable=True,
            column_selectable='single',
            row_deletable=True,
            sort_action='native',
            selected_columns=sel_cols if sel_cols else [],
            style_table={
                'overflowX': 'auto',
                'overflowY': 'auto',
                'maxHeight': '500px',
            },
            style_cell={
                'textAlign': 'center',
                'padding': '6px',
                'fontSize': '11px',
                'fontFamily': 'monospace',
                'minWidth': '80px',
                'whiteSpace': 'normal',
            },
            style_header={
                'backgroundColor': '#37474F',
                'color': 'white',
                'fontWeight': '600',
                'fontSize': '11px',
                'padding': '10px',
                'cursor': 'pointer',
                'textDecoration': 'underline dotted',
                'textUnderlineOffset': '3px',
            },
            style_header_conditional=[
                {'if': {'column_id': '_row_id'}, 'display': 'none'}
            ],
            style_data={
                'border': '1px solid #e0e0e0',
            },
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
