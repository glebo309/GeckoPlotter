"""Shared styling for dash_table.DataTable instances
(pub-table, peak-table, cross-sample-table).

Only the *static* style props live here. Dynamic per-cell styling
(zebra striping + selection highlight) is managed by the callbacks via
``style_data_conditional`` and must not be set here.
"""

TABLE_STYLE_TABLE = {
    'overflowX': 'auto',
    'overflowY': 'auto',
    'maxHeight': '500px',
    'borderRadius': '6px',
    'border': '1px solid rgba(0, 0, 0, 0.12)',
}

TABLE_STYLE_CELL = {
    'textAlign': 'center',
    'padding': '6px 10px',
    'fontSize': '12px',
    'fontFamily': 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
    'minWidth': '80px',
    'whiteSpace': 'normal',
    'color': '#1d1d1f',
}

TABLE_STYLE_HEADER = {
    'backgroundColor': '#1d1d1f',
    'color': '#fff',
    'fontWeight': '600',
    'fontSize': '10px',
    'letterSpacing': '0.05em',
    'textTransform': 'uppercase',
    'padding': '7px 10px',
    'cursor': 'pointer',
    'borderBottom': '1px solid #000',
    'fontFamily': '-apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif',
}

TABLE_STYLE_DATA = {
    'border': '1px solid rgba(0, 0, 0, 0.06)',
}
