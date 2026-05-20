"""Stage 3: smart heuristic fallback for files not matched by any preset.

Handles: delimiter detection, header row detection, footer stripping,
European number format, auto X/Y column detection.

Returns the same dict shape as FormatPreset.parse() or None if the
file cannot be parsed as tabular data.
"""
from __future__ import annotations
import re
import pandas as pd
from io import StringIO
from typing import Dict, Any, List, Optional, Tuple

from .types import ColumnRole, PlotHint

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

    # Determine if the first row is a real header or just data
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

    column_roles = _detect_column_roles(df)
    plot_hint = _choose_plot_hint(df, column_roles)

    metadata: Dict[str, Any] = {}
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
        "sample_name": sample_name,
        "metadata": metadata,
    }


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

    # Score each delimiter by how consistently it appears across ALL sample rows.
    # A structural separator (like `;` in European CSVs) appears in every row
    # with the same count. A decimal comma appears only in data rows and at
    # varying counts — so cross-row consistency separates the two.
    best, best_score = ",", -1
    for delim in candidates:
        counts = [line.count(delim) for line in sample]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            continue
        median_count = sorted(nonzero)[len(nonzero) // 2]
        if median_count == 0:
            continue
        # Strict consistency: fraction of ALL rows (including zeros) at median
        consistent = sum(1 for c in counts if c == median_count) / len(counts)
        # Score = median * consistency^2; squaring penalises rows where the
        # count is absent (zeros hurt more), favouring true structural delimiters
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
