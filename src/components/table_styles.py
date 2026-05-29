"""Shared modern styling for the dash_table.DataTable instances
(pub-table, peak-table, cross-sample-table).

Only the *static* style props live here. Dynamic per-cell styling
(zebra striping + selection highlight) is managed by the callbacks via
``style_data_conditional`` and must not be set here.
"""

TABLE_STYLE_TABLE = {
    'overflowX': 'auto',
    'overflowY': 'auto',
    'maxHeight': '500px',
    'borderRadius': '4px',
    'border': '1px solid #d4d4d4',
}

TABLE_STYLE_CELL = {
    'textAlign': 'center',
    'padding': '6px 10px',
    'fontSize': '12px',
    'fontFamily': 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
    'minWidth': '80px',
    'whiteSpace': 'normal',
    'color': '#1a1a1a',
}

TABLE_STYLE_HEADER = {
    'backgroundColor': '#1a1a1a',
    'color': '#e0e0e0',
    'fontWeight': '600',
    'fontSize': '11px',
    'letterSpacing': '0.04em',
    'textTransform': 'uppercase',
    'padding': '8px 10px',
    'cursor': 'pointer',
    'borderBottom': '1px solid #333',
    'fontFamily': '-apple-system, "Segoe UI", Roboto, sans-serif',
}

TABLE_STYLE_DATA = {
    'border': '1px solid #ebebeb',
}
