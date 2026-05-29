"""Shared modern styling for the dash_table.DataTable instances
(pub-table, peak-table, cross-sample-table).

Only the *static* style props live here. Dynamic per-cell styling
(zebra striping + selection highlight) is managed by the callbacks via
``style_data_conditional`` and must not be set here.
"""

# Scroll container: rounded, lightly bordered card.
TABLE_STYLE_TABLE = {
    'overflowX': 'auto',
    'overflowY': 'auto',
    'maxHeight': '500px',
    'borderRadius': '8px',
    'border': '1px solid #e3e8ee',
}

# Data cells: roomy, monospace for clean numeric alignment.
TABLE_STYLE_CELL = {
    'textAlign': 'center',
    'padding': '8px 10px',
    'fontSize': '12px',
    'fontFamily': 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
    'minWidth': '80px',
    'whiteSpace': 'normal',
}

# Header: refined slate, uppercase, letter-spaced, orange accent rule.
TABLE_STYLE_HEADER = {
    'backgroundColor': '#2f3e4e',
    'color': '#ffffff',
    'fontWeight': '600',
    'fontSize': '11px',
    'letterSpacing': '0.05em',
    'textTransform': 'uppercase',
    'padding': '10px',
    'cursor': 'pointer',
    'borderBottom': '2px solid #ff6b35',
    'fontFamily': '-apple-system, "Segoe UI", Roboto, sans-serif',
}

# Data rows: soft separators (backgrounds come from the highlight callback).
TABLE_STYLE_DATA = {
    'border': '1px solid #eef1f5',
}
