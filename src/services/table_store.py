"""The Data table lives on the server; the browser holds a small reference and one page of rows.

A file's table used to travel to the browser in full twice (as DataTable rows and as ``pub-data-store`` JSON) and
back again with every cell click. Now :func:`remember` keeps the full frame here and returns a reference
(``{'table_ref', 'rows', 'columns'}``) that ``pub-data-store`` and ``pub-table-source`` carry instead. The Data tab
asks for one page at a time, and edits made on a page are applied to the full frame by ``_row_id``, so a page can
never be written back over the whole table. :func:`frame` also accepts the JSON (``orient='split'``) that the peak
tables and saved custom plots still use.
"""
from __future__ import annotations

import io
import math
import threading
import uuid
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

MAX_TABLES = 16
PAGE_SIZE = 50

_lock = threading.Lock()
_frames: 'OrderedDict[str, pd.DataFrame]' = OrderedDict()


def remember(df: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
    """Keep ``df`` (with a ``_row_id`` column) and return its reference, or None for no table."""
    if df is None:
        return None
    if '_row_id' not in df.columns:
        df = df.copy()
        df.insert(0, '_row_id', range(len(df)))
    ref = uuid.uuid4().hex
    with _lock:
        _frames[ref] = df
        while len(_frames) > MAX_TABLES:
            _frames.popitem(last=False)
    return {'table_ref': ref, 'rows': int(len(df)), 'columns': [str(c) for c in df.columns]}


def is_reference(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get('table_ref'), str)


def _stored(value: Any) -> Optional[pd.DataFrame]:
    with _lock:
        df = _frames.get(value['table_ref'])
        if df is not None:
            _frames.move_to_end(value['table_ref'])
        return df


def frame(value: Any) -> Optional[pd.DataFrame]:
    """The full table behind a ``pub-data-store`` value (a reference or split JSON), as a copy; None if unknown."""
    if not value:
        return None
    if is_reference(value):
        df = _stored(value)
        return None if df is None else df.copy()
    if isinstance(value, str):
        return pd.read_json(io.StringIO(value), orient='split')
    return None


def as_json(value: Any) -> Optional[str]:
    """Split JSON of the table behind ``value``, for places that keep the data itself (saved custom plots)."""
    if isinstance(value, str):
        return value
    df = frame(value)
    return None if df is None else df.to_json(orient='split')


def sorted_frame(df: pd.DataFrame, sort_by: Optional[List[Dict[str, Any]]]) -> pd.DataFrame:
    """``df`` in the order the table shows it (DataTable ``sort_by``)."""
    for spec in reversed(sort_by or []):
        col = spec.get('column_id')
        if col not in df.columns:
            continue
        ascending = spec.get('direction', 'asc') == 'asc'
        try:
            df = df.sort_values(col, ascending=ascending, kind='stable', na_position='last')
        except TypeError:                       # mixed text and numbers in an edited column
            df = df.sort_values(col, ascending=ascending, kind='stable', na_position='last',
                                key=lambda s: s.astype(str))
    return df


def page(value: Any, page_current: Optional[int], page_size: Optional[int] = None,
         sort_by: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], int, int]:
    """Rows of one page, the page count and the page actually served (clamped to the table)."""
    df = _stored(value) if is_reference(value) else frame(value)
    if df is None:
        return [], 1, 0
    size = max(1, int(page_size or PAGE_SIZE))
    count = max(1, math.ceil(len(df) / size))
    current = min(max(0, int(page_current or 0)), count - 1)
    shown = sorted_frame(df, sort_by).iloc[current * size:(current + 1) * size]
    return shown.to_dict('records'), count, current


def _cell_value(series: pd.Series, value: Any) -> Tuple[pd.Series, Any]:
    """Value to store for an edited cell; a number column takes the number typed, or turns into text."""
    if pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype):
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return series.astype(float) if pd.api.types.is_integer_dtype(series.dtype) else series, float('nan')
        try:
            number = float(value)
        except (TypeError, ValueError):
            return series.astype(object), value
        if pd.api.types.is_integer_dtype(series.dtype) and not number.is_integer():
            series = series.astype(float)
        return series, number
    return series, value


def apply_page_edits(value: Any, rows: Optional[List[Dict[str, Any]]],
                     previous: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Apply what the user changed on the shown page (edited cells, deleted rows) to the full table.

    ``rows``/``previous`` are the page after and before the edit (DataTable ``data``/``data_previous``). Returns the
    new reference, or None when nothing on the page was edited (for example the page itself changed).
    """
    df = frame(value)
    if df is None or rows is None or not previous or '_row_id' not in df.columns:
        return None
    before = {r.get('_row_id'): r for r in previous if isinstance(r, dict)}
    after_ids = [r.get('_row_id') for r in rows if isinstance(r, dict)]
    if None in before or None in after_ids or any(rid not in before for rid in after_ids):
        return None                             # a different page was served, not an edit
    changed = False
    deleted = [rid for rid in before if rid not in set(after_ids)]
    if deleted:
        df = df[~df['_row_id'].isin(deleted)].reset_index(drop=True)
        changed = True
    positions = {rid: i for i, rid in enumerate(df['_row_id'].tolist())}
    for row in rows:
        old = before[row['_row_id']]
        for col, new in row.items():
            if col == '_row_id' or col not in df.columns or old.get(col) == new:
                continue
            pos = positions.get(row['_row_id'])
            if pos is None:
                continue
            series, stored = _cell_value(df[col], new)
            if series is not df[col]:
                df[col] = series
            df.iloc[pos, df.columns.get_loc(col)] = stored
            changed = True
    if not changed:
        return None
    return remember(df)


def drop_columns(value: Any, kept: List[str]) -> Optional[Dict[str, Any]]:
    """Remove the columns the user deleted in the table header; None when none was removed."""
    df = frame(value)
    if df is None:
        return None
    gone = [c for c in df.columns if c != '_row_id' and c not in set(kept)]
    if not gone:
        return None
    return remember(df.drop(columns=gone))
