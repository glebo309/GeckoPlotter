"""
Generic CSV Reader for simple tabular data files.

Smart parsing: detects header rows, trailing delimiters, European number
formats (semicolon-separated, comma decimals), instrument metadata footers,
and auto-identifies X/Y columns for immediate plotting.
"""
import re
import pandas as pd
import numpy as np
import os
from io import StringIO
from typing import Optional, Dict, Any, List, Tuple
from .base_reader import BaseReader

# Patterns that identify a column as an X-axis candidate (ranked by priority)
_X_PATTERNS = [
    (r'\btime\b', 'time'),
    (r'\bretention\b', 'time'),
    (r'\brt\b', 'time'),
    (r'\bmin\b', 'time'),
    (r'\bwavelength\b', 'wavelength'),
    (r'\bnm\b', 'wavelength'),
    (r'\bconcentration\b', 'concentration'),
    (r'\bsample\b', 'category'),
    (r'\bindex\b', 'index'),
    (r'\bcycle\b', 'cycle'),
    (r'\btemp\b', 'temperature'),
]

# Patterns that identify a column as a Y-axis candidate
_Y_PATTERNS = [
    (r'\babs\b', 'absorbance'),
    (r'\babsorbance\b', 'absorbance'),
    (r'\bintensity\b', 'intensity'),
    (r'\bmau\b', 'intensity'),
    (r'\bsignal\b', 'signal'),
    (r'\bvalue\b', 'value'),
    (r'\barea\b', 'area'),
    (r'\bconversion\b', 'conversion'),
    (r'\byield\b', 'yield'),
    (r'\bactivity\b', 'activity'),
    (r'\brate\b', 'rate'),
    (r'\bpeak\b', 'peak'),
    (r'\bau\b', 'absorbance'),
    (r'\bod\b', 'absorbance'),
]

# Patterns that mark the start of a metadata/footer section
_FOOTER_MARKERS = [
    r'^Collection Time:',
    r'^Operator Name',
    r'^Kinetics Version',
    r'^Parameter List',
    r'^Instrument\s',
    r'^Method Name',
    r'^Date/Time stamp',
    r'^Saved as ',
    r'^End Method',
    r'^<.*>',
]


class GenericCSVReader(BaseReader):
    """Reader for generic CSV files with smart structure detection."""

    def __init__(self):
        super().__init__()
        self.metadata: Dict[str, Any] = {}
        self.x_column: Optional[str] = None
        self.y_columns: List[str] = []
        self.sample_name: Optional[str] = None
        self.instrument_metadata: Dict[str, str] = {}

    def load_file(self, path: str, extra_files: Optional[list] = None) -> bool:
        """Load generic CSV file with smart structure detection."""
        try:
            self.file_path = path
            self.file_name = os.path.basename(path).replace("temp_", "")

            raw_lines = self._read_raw_lines(path)
            if not raw_lines:
                print(f"⚠️ CSV file is empty: {path}")
                return False

            delimiter = self._detect_delimiter(raw_lines)
            header_row, self.sample_name = self._find_header_row(raw_lines, delimiter)
            data_end = self._find_data_end(raw_lines, header_row, delimiter)

            self.instrument_metadata = self._extract_instrument_metadata(
                raw_lines, data_end
            )

            data_lines = raw_lines[header_row:data_end]
            data_text = '\n'.join(data_lines)

            is_european = self._detect_european_format(data_lines, delimiter)

            if is_european:
                self.data = pd.read_csv(
                    StringIO(data_text),
                    sep=delimiter,
                    decimal=',',
                )
            else:
                self.data = pd.read_csv(
                    StringIO(data_text),
                    sep=delimiter,
                )

            self._clean_dataframe()
            self._coerce_numerics()
            self._auto_detect_axes()

            self.metadata = self._build_metadata()

            print(f"✅ Loaded generic CSV: {len(self.data)} rows × {len(self.data.columns)} columns")
            print(f"   Columns: {list(self.data.columns)}")
            if self.sample_name:
                print(f"   Sample: {self.sample_name}")
            if self.x_column:
                print(f"   Auto X: {self.x_column}")
            if self.y_columns:
                print(f"   Auto Y: {self.y_columns}")
            return True

        except Exception as e:
            print(f"❌ Failed to load generic CSV {path}: {e}")
            import traceback; traceback.print_exc()
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_raw_lines(path: str) -> List[str]:
        for enc in ('utf-8', 'latin-1', 'cp1252'):
            try:
                with open(path, 'r', encoding=enc) as f:
                    return [line.rstrip('\n\r') for line in f.readlines()]
            except UnicodeDecodeError:
                continue
        return []

    @staticmethod
    def _detect_delimiter(lines: List[str]) -> str:
        """Pick comma, semicolon, or tab based on which is most consistent."""
        candidates = [',', ';', '\t']
        best, best_score = ',', -1
        sample = lines[:min(20, len(lines))]
        for delim in candidates:
            counts = [line.count(delim) for line in sample if line.strip()]
            if not counts:
                continue
            median_count = sorted(counts)[len(counts) // 2]
            if median_count > best_score:
                best, best_score = delim, median_count
        return best

    def _find_header_row(
        self, lines: List[str], delimiter: str
    ) -> Tuple[int, Optional[str]]:
        """Find the row that contains column headers.

        Returns (header_row_index, sample_name_or_None).
        Heuristic: the header row is the first row where most fields are
        non-numeric text and ≥2 fields are present.
        """
        sample_name = None

        for i, line in enumerate(lines[:20]):
            fields = [f.strip().strip('"') for f in line.split(delimiter)]
            fields = [f for f in fields if f]
            if len(fields) < 2:
                if len(fields) == 1 and i == 0:
                    sample_name = fields[0]
                continue

            numeric_count = sum(1 for f in fields if self._looks_numeric(f))
            text_count = len(fields) - numeric_count

            if text_count >= 2 and text_count > numeric_count:
                return i, sample_name

        return 0, sample_name

    def _find_data_end(
        self, lines: List[str], header_row: int, delimiter: str
    ) -> int:
        """Find where the numeric data ends (before any footer/metadata)."""
        if header_row + 1 >= len(lines):
            return len(lines)

        header_fields = [
            f.strip() for f in lines[header_row].split(delimiter)
        ]
        expected_cols = len([f for f in header_fields if f])

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
                if not any(self._looks_numeric(f) for f in non_empty):
                    return i

        return len(lines)

    @staticmethod
    def _extract_instrument_metadata(
        lines: List[str], data_end: int
    ) -> Dict[str, str]:
        """Parse key-value metadata from the footer section."""
        meta = {}
        for line in lines[data_end:]:
            line = line.strip()
            if not line:
                continue
            for sep in [':', '  ']:
                if sep in line:
                    parts = line.split(sep, 1)
                    key = parts[0].strip().strip('<>')
                    val = parts[1].strip() if len(parts) > 1 else ''
                    if key and val:
                        meta[key] = val
                    break
        return meta

    @staticmethod
    def _detect_european_format(data_lines: List[str], delimiter: str) -> bool:
        """Check if numbers use comma as decimal separator."""
        if delimiter == ',':
            return False

        for line in data_lines[1:6]:
            fields = [f.strip() for f in line.split(delimiter)]
            for f in fields:
                if f and ',' in f and '.' not in f:
                    try:
                        float(f.replace(',', '.'))
                        return True
                    except ValueError:
                        pass
        return False

    @staticmethod
    def _looks_numeric(s: str) -> bool:
        s = s.strip().replace(',', '.')
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _clean_dataframe(self) -> None:
        """Drop empty/unnamed columns and strip whitespace from headers."""
        self.data.columns = [
            str(c).strip().rstrip(',') for c in self.data.columns
        ]

        cols_to_drop = [
            c for c in self.data.columns
            if c.startswith('Unnamed') or c == '' or c.isspace()
        ]
        if cols_to_drop:
            self.data.drop(columns=cols_to_drop, inplace=True)

        self.data.dropna(axis=1, how='all', inplace=True)
        self.data.dropna(axis=0, how='all', inplace=True)

    def _coerce_numerics(self) -> None:
        """Try to convert columns to numeric, handling comma decimals."""
        for col in self.data.columns:
            if self.data[col].dtype == object:
                cleaned = self.data[col].astype(str).str.strip()
                cleaned = cleaned.str.replace(',', '.', regex=False)
                converted = pd.to_numeric(cleaned, errors='coerce')
                if converted.notna().sum() > len(self.data) * 0.5:
                    self.data[col] = converted

    def _auto_detect_axes(self) -> None:
        """Identify X and Y columns from column names and data shape."""
        cols = list(self.data.columns)
        numeric_cols = [
            c for c in cols
            if pd.api.types.is_numeric_dtype(self.data[c]) and c != '_row_id'
        ]

        def _match(col_name: str, patterns):
            lower = col_name.lower()
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
                x_candidates.append((col, xk))
            if yk:
                y_candidates.append((col, yk))

        if x_candidates:
            self.x_column = x_candidates[0][0]
        elif len(numeric_cols) >= 2:
            self.x_column = numeric_cols[0]

        if y_candidates:
            self.y_columns = [c for c, _ in y_candidates]
        elif len(numeric_cols) >= 2:
            self.y_columns = [
                c for c in numeric_cols if c != self.x_column
            ][:8]

    def _build_metadata(self) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            'file_type': 'generic_csv',
            'file_name': self.file_name,
            'rows': len(self.data),
            'columns': len(self.data.columns),
            'column_names': list(self.data.columns),
        }
        if self.sample_name:
            meta['sample_name'] = self.sample_name
        if self.x_column:
            meta['auto_x'] = self.x_column
        if self.y_columns:
            meta['auto_y'] = self.y_columns
        if self.instrument_metadata:
            meta['instrument'] = self.instrument_metadata
            inst = self.instrument_metadata.get('Instrument', '')
            if inst:
                meta['instrument_name'] = inst
            wl = (
                self.instrument_metadata.get('Current Wavelength', '')
                or self.instrument_metadata.get('Wavelength (nm)', '')
            )
            if wl:
                meta['wavelength'] = wl
        return meta

    def _process_file(self) -> None:
        pass

    def get_data(self) -> Optional[pd.DataFrame]:
        return self.data

    def get_metadata(self) -> Dict[str, Any]:
        return self.metadata
