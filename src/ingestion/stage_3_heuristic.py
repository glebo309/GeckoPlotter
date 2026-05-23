"""Stage 3: smart heuristic fallback for files not matched by any preset.

Handles: delimiter detection, header row detection, footer stripping,
European number format, auto X/Y column detection.

For messy lab spreadsheets (multiple data regions, calculations mixed with
data), falls back to sub-table extraction: finds the densest rectangular
block of numeric data and extracts it as a clean table.

Returns the same dict shape as FormatPreset.parse() or None if the
file cannot be parsed as tabular data.
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict, Any, List, Optional, Tuple

from .types import ColumnRole, PlotHint, SourceCategory

_X_PATTERNS = [
    (r"\btime\b", "time"),
    (r"\bretention\b", "time"),
    (r"\brt\b", "time"),
    (r"\bmin\b", "time"),
    (r"\bwavelength\b", "wavelength"),
    (r"\bnm\b", "wavelength"),
    (r"\bconcentration\b", "concentration"),
    (r"\bsample\b", "category"),
    (r"\bindex\b", "index"),
    (r"\bcycle\b", "cycle"),
    (r"\btemp\b", "temperature"),
]

_Y_PATTERNS = [
    (r"\babs\b", "absorbance"),
    (r"\babsorbance\b", "absorbance"),
    (r"\bintensity\b", "intensity"),
    (r"\bmau\b", "intensity"),
    (r"\bsignal\b", "signal"),
    (r"\bvalue\b", "value"),
    (r"\barea\b", "area"),
    (r"\bconversion\b", "conversion"),
    (r"\byield\b", "yield"),
    (r"\bactivity\b", "activity"),
    (r"\brate\b", "rate"),
    (r"\bpeak\b", "peak"),
    (r"\bau\b", "absorbance"),
    (r"\bod\b", "absorbance"),
]

_WELL_PATTERN = re.compile(r"^[A-H]\d{1,2}$")

_FOOTER_MARKERS = [
    r"^Collection Time:",
    r"^Operator Name",
    r"^Kinetics Version",
    r"^Parameter List",
    r"^Instrument\s",
    r"^Method Name",
    r"^Date/Time stamp",
    r"^Saved as ",
    r"^End Method",
    r"^<.*>",
]


def heuristic_parse(path: str, extension: str) -> Optional[dict]:
    lines = _read_raw_lines(path)
    if not lines:
        return None

    delimiter = _detect_delimiter(lines)
    header_row, sample_name = _find_header_row(lines, delimiter)
    data_end = _find_data_end(lines, header_row, delimiter)
    instrument_meta = _extract_instrument_metadata(lines, data_end)

    data_lines = lines[header_row:data_end]
    if len(data_lines) < 2:
        return None

    data_text = "\n".join(data_lines)
    is_european = _detect_european_format(data_lines, delimiter)

    first_row_fields = [f.strip().strip('"') for f in data_lines[0].split(delimiter)]
    first_row_fields = [f for f in first_row_fields if f]
    first_row_all_numeric = all(_looks_numeric(f) for f in first_row_fields if f)
    has_header = not first_row_all_numeric

    try:
        if is_european:
            if has_header:
                df = pd.read_csv(StringIO(data_text), sep=delimiter, decimal=",")
            else:
                df = pd.read_csv(StringIO(data_text), sep=delimiter, decimal=",", header=None)
        else:
            if has_header:
                df = pd.read_csv(StringIO(data_text), sep=delimiter)
            else:
                df = pd.read_csv(StringIO(data_text), sep=delimiter, header=None)
    except Exception:
        return None

    df = _clean_dataframe(df)
    df = _coerce_numerics(df)

    if df.empty:
        return None

    # Check data quality — if mostly garbage, try sub-table extraction
    if _is_poor_quality(df):
        subtables = _extract_all_subtables(path, delimiter)
        if subtables:
            df = _merge_subtables(subtables)

    column_roles = _detect_column_roles(df)
    cat = _infer_source_category(df, column_roles)
    plot_hint = _choose_plot_hint(df, column_roles)

    metadata: Dict[str, Any] = {}
    if sample_name:
        metadata["sample_name"] = sample_name
    if instrument_meta:
        metadata["instrument"] = instrument_meta
        inst = instrument_meta.get("Instrument", "")
        if inst:
            metadata["instrument_name"] = inst
        wl = instrument_meta.get("Current Wavelength (nm)", "") or instrument_meta.get("Current Wavelength", "")
        if wl:
            metadata["wavelength"] = wl

    return {
        "data": df,
        "column_roles": column_roles,
        "plot_hint": plot_hint,
        "source_category": cat,
        "sample_name": sample_name,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Sub-table extraction for messy spreadsheets
# ---------------------------------------------------------------------------

def _is_poor_quality(df: pd.DataFrame) -> bool:
    """Check if a parsed DataFrame is mostly garbage."""
    if len(df) < 3:
        return True
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(numeric_cols) < 2:
        return True
    total_cells = len(df) * len(numeric_cols)
    nan_cells = sum(df[c].isna().sum() for c in numeric_cols)
    if total_cells > 0 and nan_cells / total_cells > 0.3:
        return True
    # Any numeric column mostly empty → likely a messy spreadsheet
    for c in numeric_cols:
        if df[c].isna().sum() > len(df) * 0.7:
            return True
    # Very few complete rows (no NaN across all numeric cols)
    complete = df[numeric_cols].dropna().shape[0]
    if complete < len(df) * 0.3:
        return True
    return False


def _extract_all_subtables(path: str, delimiter: str) -> List[pd.DataFrame]:
    """Find ALL rectangular blocks of numeric data in a messy CSV.

    Returns a list of clean DataFrames, one per detected column group.
    """
    try:
        raw = pd.read_csv(path, header=None, sep=delimiter, dtype=str,
                          on_bad_lines="skip", engine="python")
    except Exception:
        return []

    if raw.empty or raw.shape[1] < 2:
        return []

    nrows, ncols = raw.shape

    time_pattern = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
    col_scores = []
    for c in range(ncols):
        data_count = 0
        for r in range(nrows):
            val = raw.iat[r, c]
            if pd.notna(val):
                s = str(val).strip()
                if _looks_numeric(s) or time_pattern.match(s):
                    data_count += 1
        col_scores.append(data_count)

    min_density = max(5, nrows * 0.15)
    groups = _find_column_groups(col_scores, min_density)

    if not groups:
        return []

    results = []
    global_col_names: set = set()

    for group in groups:
        if len(group) < 2:
            continue

        sub = _extract_one_subtable(raw, group, global_col_names)
        if sub is not None:
            results.append(sub)

    return results


def _extract_one_subtable(
    raw: pd.DataFrame, col_group: List[int], global_col_names: set
) -> Optional[pd.DataFrame]:
    """Extract and clean a single sub-table from a column group."""
    header_row = _find_subtable_header(raw, col_group)

    start_col = col_group[0]
    end_col = col_group[-1] + 1
    sub_raw = raw.iloc[:, start_col:end_col].copy()

    if header_row is not None:
        headers = [str(sub_raw.iat[header_row, i]).strip() for i in range(sub_raw.shape[1])]
        seen = {}
        clean_headers = []
        for h in headers:
            if not h or h == "nan":
                h = f"col_{start_col + len(clean_headers)}"
            # De-duplicate within this group AND across all groups
            base = h
            if h in seen or h in global_col_names:
                suffix = seen.get(h, 0) + 1
                while f"{base}_{suffix}" in global_col_names:
                    suffix += 1
                seen[base] = suffix
                h = f"{base}_{suffix}"
            else:
                seen[h] = 0
            global_col_names.add(h)
            clean_headers.append(h)
        sub_raw.columns = clean_headers
        sub_raw = sub_raw.iloc[header_row + 1:]
    else:
        cols = [f"col_{start_col + i}" for i in range(sub_raw.shape[1])]
        sub_raw.columns = cols
        for c in cols:
            global_col_names.add(c)

    sub_raw = sub_raw.reset_index(drop=True)

    # Drop empty rows/cols BEFORE coercion so thresholds work on actual data
    sub_raw = sub_raw.dropna(axis=0, how="all")
    sub_raw = sub_raw.dropna(axis=1, how="all")
    sub_raw = sub_raw.reset_index(drop=True)

    for col in list(sub_raw.columns):
        if sub_raw[col].dtype == object:
            converted = _try_convert_time_column(sub_raw[col])
            if converted is not None:
                sub_raw[col] = converted
                if "time" not in col.lower() and "t " not in col.lower():
                    new_name = f"{col} (s)"
                    global_col_names.discard(col)
                    global_col_names.add(new_name)
                    sub_raw = sub_raw.rename(columns={col: new_name})
                continue
            numeric = pd.to_numeric(sub_raw[col], errors="coerce")
            if numeric.notna().sum() > len(sub_raw) * 0.3:
                sub_raw[col] = numeric

    # Drop rows that are entirely non-numeric (stray text rows)
    numeric_mask = sub_raw.apply(lambda row: any(
        pd.api.types.is_number(v) for v in row if pd.notna(v)
    ), axis=1)
    sub_raw = sub_raw[numeric_mask].reset_index(drop=True)

    if len(sub_raw) < 3 or sub_raw.shape[1] < 2:
        return None

    return sub_raw


def _merge_subtables(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple sub-tables into one wide DataFrame.

    Tables with different row counts are joined by index (outer join),
    so shorter tables get NaN-padded.
    """
    if len(tables) == 1:
        return tables[0]

    merged = tables[0]
    for t in tables[1:]:
        merged = pd.merge(merged, t, left_index=True, right_index=True, how="outer")

    return merged


def _find_column_groups(scores: List[int], min_density: float) -> List[List[int]]:
    """Find contiguous groups of column indices where score >= min_density."""
    groups: List[List[int]] = []
    current: List[int] = []
    for i, score in enumerate(scores):
        if score >= min_density:
            current.append(i)
        else:
            if len(current) >= 2:
                groups.append(current)
            current = []
    if len(current) >= 2:
        groups.append(current)
    return groups


def _find_subtable_header(raw: pd.DataFrame, col_group: List[int]) -> Optional[int]:
    """Find the header row for a numeric column group.

    Scans rows looking for one where most cells in the group are text (not
    numeric) and the rows below are predominantly numeric.
    """
    nrows = len(raw)
    for r in range(min(nrows - 1, 30)):
        text_count = 0
        total = 0
        for c in col_group:
            val = raw.iat[r, c]
            if pd.notna(val):
                total += 1
                s = str(val).strip()
                if s and not _looks_numeric(s):
                    text_count += 1

        if total == 0:
            continue

        # Header: mostly text labels
        if text_count >= max(2, total * 0.5):
            # Verify row below is numeric
            if r + 1 < nrows:
                num_below = sum(
                    1 for c in col_group
                    if pd.notna(raw.iat[r + 1, c]) and _looks_numeric(str(raw.iat[r + 1, c]))
                )
                if num_below >= len(col_group) * 0.5:
                    return r
    return None


def _try_convert_time_column(series: pd.Series) -> Optional[pd.Series]:
    """Convert H:MM:SS or M:SS time strings to numeric seconds."""
    sample = series.dropna().head(10)
    if len(sample) == 0:
        return None

    time_pattern = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
    match_count = sum(1 for v in sample if time_pattern.match(str(v).strip()))
    if match_count < len(sample) * 0.6:
        return None

    def _to_seconds(val):
        s = str(val).strip()
        parts = s.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
        except (ValueError, IndexError):
            pass
        return None

    converted = series.apply(_to_seconds)
    if converted.notna().sum() > len(series) * 0.3:
        return converted.astype(float)
    return None


# ---------------------------------------------------------------------------
# Original heuristic helpers
# ---------------------------------------------------------------------------

def _read_raw_lines(path: str) -> List[str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, "r", encoding=enc) as f:
                return [line.rstrip("\n\r") for line in f.readlines()]
        except UnicodeDecodeError:
            continue
    return []


def _detect_delimiter(lines: List[str]) -> str:
    candidates = ["\t", ";", ","]
    sample = [l for l in lines[:20] if l.strip()]
    if not sample:
        return ","

    best, best_score = ",", -1
    for delim in candidates:
        counts = [line.count(delim) for line in sample]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            continue
        median_count = sorted(nonzero)[len(nonzero) // 2]
        if median_count == 0:
            continue
        consistent = sum(1 for c in counts if c == median_count) / len(counts)
        score = median_count * (consistent ** 2)
        if score > best_score:
            best, best_score = delim, score
    return best


def _find_header_row(
    lines: List[str], delimiter: str
) -> Tuple[int, Optional[str]]:
    sample_name = None
    for i, line in enumerate(lines[:20]):
        fields = [f.strip().strip('"') for f in line.split(delimiter)]
        fields = [f for f in fields if f]
        if len(fields) < 2:
            if len(fields) == 1 and i == 0:
                sample_name = fields[0]
            continue
        numeric_count = sum(1 for f in fields if _looks_numeric(f))
        text_count = len(fields) - numeric_count
        if text_count >= 2 and text_count > numeric_count:
            return i, sample_name
    return 0, sample_name


def _find_data_end(lines: List[str], header_row: int, delimiter: str) -> int:
    if header_row + 1 >= len(lines):
        return len(lines)
    for i in range(header_row + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            return i
        for pattern in _FOOTER_MARKERS:
            if re.match(pattern, line, re.IGNORECASE):
                return i
        fields = [f.strip() for f in line.split(delimiter)]
        non_empty = [f for f in fields if f]
        if len(non_empty) < 2:
            if not any(_looks_numeric(f) for f in non_empty):
                return i
    return len(lines)


def _extract_instrument_metadata(lines: List[str], data_end: int) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for line in lines[data_end:]:
        line = line.strip()
        if not line:
            continue
        for sep in [":", "  "]:
            if sep in line:
                parts = line.split(sep, 1)
                key = parts[0].strip().strip("<>")
                val = parts[1].strip() if len(parts) > 1 else ""
                if key and val:
                    meta[key] = val
                break
    return meta


def _detect_european_format(data_lines: List[str], delimiter: str) -> bool:
    if delimiter == ",":
        return False
    for line in data_lines[1:6]:
        fields = [f.strip() for f in line.split(delimiter)]
        for f in fields:
            if f and "," in f and "." not in f:
                try:
                    float(f.replace(",", "."))
                    return True
                except ValueError:
                    pass
    return False


def _looks_numeric(s: str) -> bool:
    s = s.strip().replace(",", ".")
    try:
        float(s)
        return True
    except ValueError:
        return False


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().rstrip(",") for c in df.columns]
    cols_to_drop = [
        c for c in df.columns if c.startswith("Unnamed") or c == "" or c.isspace()
    ]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")
    return df


def _coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            cleaned = df[col].astype(str).str.strip().str.replace(",", ".", regex=False)
            converted = pd.to_numeric(cleaned, errors="coerce")
            if converted.notna().sum() > len(df) * 0.5:
                df[col] = converted
    return df


def _infer_source_category(
    df: pd.DataFrame, roles: Dict[str, ColumnRole]
) -> SourceCategory:
    x_col = next((c for c, r in roles.items() if r == ColumnRole.X), None)
    if x_col is None:
        return SourceCategory.GENERIC
    lower = str(x_col).lower()
    for pat, kind in _X_PATTERNS:
        if re.search(pat, lower):
            if kind == "time":
                return SourceCategory.KINETICS
            if kind == "wavelength":
                return SourceCategory.SPECTRUM
            break
    return SourceCategory.GENERIC


def _detect_column_roles(df: pd.DataFrame) -> Dict[str, ColumnRole]:
    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and c != "_row_id"
    ]

    def _match(col_name: str, patterns) -> Optional[str]:
        lower = str(col_name).lower()
        for pat, kind in patterns:
            if re.search(pat, lower):
                return kind
        return None

    x_candidates = []
    y_candidates = []
    for col in numeric_cols:
        xk = _match(col, _X_PATTERNS)
        yk = _match(col, _Y_PATTERNS)
        if xk:
            x_candidates.append(col)
        if yk:
            y_candidates.append(col)

    roles: Dict[str, ColumnRole] = {}

    if x_candidates:
        roles[x_candidates[0]] = ColumnRole.X
    elif len(numeric_cols) >= 2:
        roles[numeric_cols[0]] = ColumnRole.X

    x_col = next((c for c, r in roles.items() if r == ColumnRole.X), None)

    if y_candidates:
        for c in y_candidates[:8]:
            if c != x_col:
                roles[c] = ColumnRole.Y
    elif len(numeric_cols) >= 2:
        for c in numeric_cols[:8]:
            if c != x_col:
                roles[c] = ColumnRole.Y

    for col in df.columns:
        if col not in roles:
            if col == "_row_id":
                roles[col] = ColumnRole.IGNORE
            elif pd.api.types.is_numeric_dtype(df[col]):
                roles[col] = ColumnRole.UNKNOWN
            else:
                roles[col] = ColumnRole.LABEL

    return roles


def _choose_plot_hint(df: pd.DataFrame, roles: Dict[str, ColumnRole]) -> PlotHint:
    y_count = sum(1 for r in roles.values() if r == ColumnRole.Y)
    if y_count > 3:
        return PlotHint.MULTI_Y
    return PlotHint.LINE
