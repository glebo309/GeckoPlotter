"""Session save / restore engine: ``.gecko`` project files.

A session stores the *inputs and decisions* of a workspace, never the
figure: the original instrument files (or a path + SHA-256 for very large
sets), the user's parameters (peaks, calibrations, names, visibility, ...)
and an opaque ``client_state`` supplied by the GUI layer. Everything derived
(parsing, bundling, figures) is recomputed on load through the normal
ingestion pipeline, and the fresh objects are re-keyed to the saved ids so
nothing silently detaches.

No Dash imports. Format and policy: ``docs/SESSION_FORMAT.md``.

Public API
----------
``SCHEMA_VERSION``, ``MIGRATIONS``, ``build_session``, ``save_session``,
``inspect_session``, ``restore_session``, ``remap_ids``,
``autosave_dir``, ``latest_autosave``, ``save_autosave``, and the
``SessionInfo`` / ``SessionReport`` result types.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import io
import json
import logging
import os
import platform
import re
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from importlib.metadata import version as _package_version
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FORMAT_NAME = 'geckoplotter-session'
EXTENSION = '.gecko'
DEFAULT_RAW_LIMIT_BYTES = 400_000_000
#: Decompression caps (zip-bomb guard), checked against ``ZipInfo.file_size`` before anything is inflated.
MAX_JSON_BYTES = 64 * 1024 * 1024          # state.json, manifest.json, client_state.json (and tables)
MAX_TOTAL_BYTES = 4 * 1024 ** 3            # everything read from one session
RAW_SLACK_BYTES = 1_000_000                # a raw member may exceed its declared size by max(1 %, this)

MANIFEST_NAME = 'manifest.json'
STATE_NAME = 'state.json'
CLIENT_STATE_NAME = 'client_state.json'
#: Path of the embedded project inside a FAIR research package (``build_research_package``).
PACKAGE_SESSION = 'session/project.gecko'
PACKAGE_MARKER = 'dataset_manifest.csv'

#: ``{from_version: fn}``. ``fn(session) -> session`` upgrades the in-memory
#: ``{'manifest': dict, 'state': dict, 'client_state': dict}`` by exactly one
#: schema version; the framework stamps the new ``schema_version``.
MIGRATIONS: Dict[int, Callable[[dict], dict]] = {}

# Formats produced by the app itself (not by an instrument parser): such
# components cannot be rebuilt from raw bytes and are stored as tables.
_DERIVED_FORMATS = frozenset({'ms_extract'})
_PAYLOAD_KEYS = ('pda', 'instrument_status', 'instrument_peaks')
_POINTER_KEYS = ('pda_source_id', 'source_file_id')
_UUID_MIN_LEN = 8  # shorter ids are only remapped when a whole string equals them


# ----------------------------------------------------------------------------
# Errors and result types
# ----------------------------------------------------------------------------

class SessionFormatError(ValueError):
    """The file is not a readable GeckoPlotter session. ``str(err)`` is user-readable."""


class SessionVersionError(SessionFormatError):
    """The session was written by a newer GeckoPlotter than this one."""


@dataclass
class SessionInfo:
    """What a session contains, read from its manifest only (cheap)."""
    path: Optional[str] = None
    project_name: str = ''
    saved_at: str = ''
    created_at: str = ''
    schema_version: int = 0
    app_version: str = ''
    counts: Dict[str, int] = field(default_factory=dict)
    files: List[Dict[str, Any]] = field(default_factory=list)
    samples: List[str] = field(default_factory=list)
    raw_embedded: bool = True
    raw_cache: bool = False  # originals live in the autosave cache folder, not in the file
    from_package: bool = False  # read from a FAIR research package (.zip); originals live in the package
    has_client_state: bool = False
    size_bytes: Optional[int] = None
    compatible: bool = True
    problem: Optional[str] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class SessionReport:
    """Outcome of :func:`restore_session`.

    ``ok`` is True when nothing was lost: no missing files and no component
    that failed to restore. ``warnings`` never imply data loss (hash
    mismatches, parser differences, ...); ``errors`` and ``missing_files`` do.
    """
    ok: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    missing_files: List[Dict[str, Any]] = field(default_factory=list)
    missing_ids: List[str] = field(default_factory=list)
    client_state: Dict[str, Any] = field(default_factory=dict)
    info: SessionInfo = field(default_factory=SessionInfo)
    restored: Dict[str, int] = field(default_factory=dict)
    id_map: Dict[str, str] = field(default_factory=dict)  # only entries where saved id != final id
    workspace_replaced: bool = False   # the store's workspace was reset (it no longer is what it was before)
    rolled_back: bool = False          # opening failed midway and the previous workspace was put back


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SHA256_RE = re.compile(r'[0-9a-f]{64}')


def _valid_sha256(value) -> bool:
    """True only for a lowercase 64-hex SHA-256 string.

    Every digest read from a session file is untrusted: it is used as a dict key and joined onto the raw-cache
    folder, so ``../../x`` or an absolute path must never pass.
    """
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    raise TypeError(f'{type(value).__name__} is not JSON serialisable')


def _sanitize(value):
    """Last-resort copy that json can always write (odd keys / objects become strings)."""
    if isinstance(value, dict):
        return {(k if isinstance(k, (str, int, float, bool)) or k is None else str(k)): _sanitize(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(v) for v in value]
    try:
        json.dumps(value, default=_json_default)
        return value
    except (TypeError, ValueError):
        return str(value)


def _dumps(value, *, indent: Optional[int] = None) -> bytes:
    separators = None if indent else (',', ':')
    try:
        text = json.dumps(value, default=_json_default, ensure_ascii=False, indent=indent,
                          separators=separators)
    except (TypeError, ValueError):
        log.warning('Session state contained values JSON cannot store; converted them to text.')
        text = json.dumps(_sanitize(value), default=_json_default, ensure_ascii=False, indent=indent,
                          separators=separators)
    return text.encode('utf-8')


def _is_light(value, budget: Optional[List[int]] = None) -> bool:
    """Small JSON-able value (no arrays/frames/bytes), safe to keep in state.json."""
    budget = budget if budget is not None else [2000]
    budget[0] -= 1
    if budget[0] < 0:
        return False
    if value is None or isinstance(value, (str, bool, int, float, np.generic)):
        return True
    if isinstance(value, Enum):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_light(v, budget) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_light(v, budget) for k, v in value.items())
    return False


def _safe_equal(a, b) -> bool:
    if a is b:
        return True
    try:
        result = a == b
        return bool(result) if isinstance(result, (bool, np.bool_)) else False
    except Exception:
        return False


def _safe_zip_name(name: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f/\\:*?"<>|]+', '_', str(name)).strip(' .') or 'file'
    return cleaned[:150]


def _enum_value(value):
    return getattr(value, 'value', value)


def _package_versions() -> Dict[str, str]:
    versions = {'python': platform.python_version()}
    for package in ('numpy', 'pandas', 'scipy', 'plotly', 'dash'):
        try:
            versions[package] = _package_version(package)
        except Exception:
            pass
    return versions


def _types():
    """The ingestion types module data_store itself uses (enum identity matters)."""
    try:
        from src.ingestion import types
    except ImportError:
        from ingestion import types
    return types


def _ingest_file():
    try:
        from src.ingestion import ingest_file
    except ImportError:
        from ingestion import ingest_file
    return ingest_file


def _key_head(key: str) -> str:
    return key.split('|', 1)[0]


# ----------------------------------------------------------------------------
# Id remapping
# ----------------------------------------------------------------------------

def remap_ids(obj: Any, mapping: Mapping[str, str]) -> Any:
    """Deep copy of *obj* with ids replaced according to ``{old_id: new_id}``.

    Applies to dict keys and string values. A string equal to an old id is
    replaced; inside longer strings (``"tab-lcms_..._<id>"``,
    ``"id:<id>:name"``, ``"<id>|A1"``) ids of at least 8 characters are
    replaced as substrings. Identity entries are ignored. Tuples stay tuples.
    """
    mapping = {k: v for k, v in (mapping or {}).items() if k != v}
    if not mapping:
        return copy.deepcopy(obj)
    long_ids = sorted((k for k in mapping if len(k) >= _UUID_MIN_LEN), key=len, reverse=True)
    pattern = re.compile('|'.join(re.escape(k) for k in long_ids)) if long_ids else None

    def text(value: str) -> str:
        if value in mapping:
            return mapping[value]
        return pattern.sub(lambda m: mapping[m.group(0)], value) if pattern else value

    def visit(value):
        if isinstance(value, str):
            return text(value)
        if isinstance(value, dict):
            return {text(k) if isinstance(k, str) else k: visit(v) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        if isinstance(value, tuple):
            return tuple(visit(v) for v in value)
        return value

    return visit(obj)


# ----------------------------------------------------------------------------
# Migration framework
# ----------------------------------------------------------------------------

def migrate_session(session: dict, *, target: Optional[int] = None,
                    migrations: Optional[Mapping[int, Callable[[dict], dict]]] = None) -> dict:
    """Upgrade ``{'manifest','state','client_state'}`` to schema *target*.

    Each step ``from_version -> from_version + 1`` runs ``migrations[from_version]``
    in order; the framework stamps ``schema_version`` after every step. Raises
    ``SessionVersionError`` for a newer session and ``SessionFormatError`` for a
    missing step.
    """
    target = SCHEMA_VERSION if target is None else target
    migrations = MIGRATIONS if migrations is None else migrations
    version = _schema_version(session.get('manifest', {}))
    if version > target:
        raise _newer_error(version, target)
    while version < target:
        step = migrations.get(version)
        if step is None:
            raise SessionFormatError(
                f'This session uses an old format (version {version}) that this version of '
                f'GeckoPlotter can no longer upgrade.')
        upgraded = step(session)
        session = upgraded if upgraded is not None else session
        version += 1
        session['manifest']['schema_version'] = version
        if isinstance(session.get('state'), dict):
            session['state']['schema_version'] = version
    return session


def _schema_version(manifest: Mapping) -> int:
    value = manifest.get('schema_version')
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SessionFormatError('The session file has no valid format version; it may be damaged.')
    return value


def _newer_error(found: int, supported: int) -> SessionVersionError:
    return SessionVersionError(
        f'This session was saved by a newer version of GeckoPlotter (session format {found}; '
        f'this version understands up to format {supported}). Please update GeckoPlotter to open it. '
        f'The file has not been changed.')


# ----------------------------------------------------------------------------
# Archive access
# ----------------------------------------------------------------------------

def _unsafe_member(name: str) -> bool:
    """A ZIP member name that is absolute, has a drive letter or climbs out with ``..``."""
    text = str(name).replace('\\', '/')
    return text.startswith('/') or bool(re.match(r'^[A-Za-z]:', text)) or '..' in text.split('/')


class _Archive:
    """Read access to a .gecko file given as bytes or a path."""

    def __init__(self, data_or_path):
        self.path: Optional[Path] = None
        self.size: Optional[int] = None
        self.package: Optional[zipfile.ZipFile] = None   # the outer zip when opened through a FAIR package
        self.package_names: set = set()
        self._total_read = 0
        try:
            if isinstance(data_or_path, (bytes, bytearray, memoryview)):
                data = bytes(data_or_path)
                self.size = len(data)
                self.zip = zipfile.ZipFile(io.BytesIO(data))
            elif hasattr(data_or_path, 'read'):
                self.zip = zipfile.ZipFile(data_or_path)
            else:
                self.path = Path(data_or_path).expanduser()
                if not self.path.is_file():
                    raise SessionFormatError(f'Session file not found: {self.path}')
                self.size = self.path.stat().st_size
                self.zip = zipfile.ZipFile(self.path)
        except zipfile.BadZipFile as exc:
            raise SessionFormatError(
                'This is not a GeckoPlotter session file (.gecko), or it is damaged.') from exc
        self._names = set(self.zip.namelist())
        if MANIFEST_NAME not in self._names:
            self._enter_package()

    def _enter_package(self) -> None:
        """A FAIR package (.zip) carries the project as ``session/project.gecko``: read that instead."""
        outer = self.zip
        if PACKAGE_SESSION not in self._names:
            if PACKAGE_MARKER in self._names:
                outer.close()
                raise SessionFormatError(
                    'This FAIR package does not contain a GeckoPlotter project (session/project.gecko is '
                    'missing). It was exported without one, so it cannot be reopened for editing.')
            return    # not ours: manifest() reports "not a session file"
        unsafe = [n for n in self._names if _unsafe_member(n)]
        if unsafe:
            outer.close()
            raise SessionFormatError(
                'This ZIP has file names that point outside the package (absolute or ".." paths), so it was not '
                f'opened: {unsafe[0]!r}.')
        try:
            if outer.getinfo(PACKAGE_SESSION).file_size > MAX_TOTAL_BYTES:
                raise SessionFormatError(
                    f'The project file inside this FAIR package expands to more than '
                    f'{MAX_TOTAL_BYTES // 1_000_000_000} GB; it was not opened.')
            inner = outer.read(PACKAGE_SESSION)
            self.zip = zipfile.ZipFile(io.BytesIO(inner))
        except (zipfile.BadZipFile, zlib.error, KeyError) as exc:
            outer.close()
            raise SessionFormatError('The project file inside this FAIR package is damaged.') from exc
        self.package, self.package_names = outer, set(self._names)
        self._names = set(self.zip.namelist())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.zip.close()
        if self.package is not None:
            self.package.close()

    def has(self, name: str) -> bool:
        return name in self._names

    def _size_of(self, archive: zipfile.ZipFile, name: str) -> int:
        try:
            return archive.getinfo(name).file_size
        except KeyError as exc:
            raise SessionFormatError(f'The session file is incomplete (missing {name}).') from exc

    def _check_total(self, size: int, name: str) -> None:
        """Count decompressed bytes handed out; refuses a session that expands beyond MAX_TOTAL_BYTES."""
        self._total_read += size
        if self._total_read > MAX_TOTAL_BYTES:
            raise SessionFormatError(
                f'The session file expands to more than {MAX_TOTAL_BYTES // 1_000_000_000} GB ({name}); '
                f'it was not opened.')

    def read(self, name: str, *, max_size: Optional[int] = None) -> bytes:
        """Read one member, refusing it (before decompressing) when it is larger than ``max_size``.

        Default cap: ``MAX_JSON_BYTES`` (state, manifest, client state and tables are JSON/CSV).
        """
        limit = MAX_JSON_BYTES if max_size is None else max_size
        try:
            size = self._size_of(self.zip, name)
            if size > limit:
                raise SessionFormatError(
                    f'The session file is not safe to open: {name} expands to {size} bytes '
                    f'(limit {limit}).')
            self._check_total(size, name)
            return self.zip.read(name)
        except KeyError as exc:
            raise SessionFormatError(f'The session file is incomplete (missing {name}).') from exc
        except (zipfile.BadZipFile, zlib.error) as exc:
            raise SessionFormatError(f'The session file is damaged ({name}).') from exc

    @staticmethod
    def _raw_limit(declared) -> int:
        """Raw originals: the manifest's declared size plus 1 % or 1 MB (whichever is larger), else the total cap."""
        if isinstance(declared, int) and not isinstance(declared, bool) and declared >= 0:
            return declared + max(declared // 100, RAW_SLACK_BYTES)
        return MAX_TOTAL_BYTES

    def read_raw(self, name: str, declared_size=None) -> bytes:
        return self.read(name, max_size=self._raw_limit(declared_size))

    def read_package_member(self, name: str, declared_size=None) -> bytes:
        """One original stored next to the project inside a FAIR package (same size policy as ``read_raw``)."""
        size = self._size_of(self.package, name)
        limit = self._raw_limit(declared_size)
        if size > limit:
            raise SessionFormatError(
                f'The package is not safe to open: {name} expands to {size} bytes (limit {limit}).')
        self._check_total(size, name)
        return self.package.read(name)

    def read_json(self, name: str):
        try:
            return json.loads(self.read(name).decode('utf-8'))
        except SessionFormatError:
            raise
        except (ValueError, UnicodeDecodeError) as exc:
            raise SessionFormatError(f'The session file is damaged ({name} is not valid).') from exc

    def manifest(self) -> dict:
        if not self.has(MANIFEST_NAME):
            raise SessionFormatError('This is not a GeckoPlotter session file (no manifest).')
        manifest = self.read_json(MANIFEST_NAME)
        if not isinstance(manifest, dict) or manifest.get('format') != FORMAT_NAME:
            raise SessionFormatError('This is not a GeckoPlotter session file.')
        return manifest



def _load_session(archive: _Archive) -> dict:
    """Manifest + state + client_state, migrated to the current schema."""
    manifest = archive.manifest()
    version = _schema_version(manifest)
    if version > SCHEMA_VERSION:
        raise _newer_error(version, SCHEMA_VERSION)
    state = archive.read_json(STATE_NAME)
    if not isinstance(state, dict):
        raise SessionFormatError(f'The session file is damaged ({STATE_NAME} is not valid).')
    client = archive.read_json(CLIENT_STATE_NAME) if archive.has(CLIENT_STATE_NAME) else {}
    session = {'manifest': manifest, 'state': state, 'client_state': client if isinstance(client, dict) else {}}
    return migrate_session(session)


def _info_from_manifest(manifest: dict, archive: Optional[_Archive] = None) -> SessionInfo:
    version = manifest.get('schema_version') if isinstance(manifest.get('schema_version'), int) else 0
    info = SessionInfo(
        path=str(archive.path) if archive is not None and archive.path else None,
        project_name=str(manifest.get('project_name') or ''),
        saved_at=str(manifest.get('saved_at') or ''),
        created_at=str(manifest.get('created_at') or ''),
        schema_version=version,
        app_version=str((manifest.get('app') or {}).get('version', '')),
        counts=dict(manifest.get('counts') or {}),
        files=[dict(f) for f in manifest.get('files') or []],
        samples=list(manifest.get('samples') or []),
        raw_embedded=bool(manifest.get('raw_embedded', True)),
        raw_cache=bool(manifest.get('raw_cache')),
        has_client_state=bool(manifest.get('has_client_state')),
        from_package=archive is not None and archive.package is not None,
        size_bytes=archive.size if archive is not None else None,
        notes=list(manifest.get('notes') or []),
    )
    if version > SCHEMA_VERSION:
        info.compatible = False
        info.problem = str(_newer_error(version, SCHEMA_VERSION))
    return info


def inspect_session(data_or_path) -> SessionInfo:
    """Read only the manifest: project name, timestamps, files, counts.

    Cheap enough for a "restore last session?" prompt. A session from a newer
    schema does not raise here; ``info.compatible`` is False and
    ``info.problem`` holds the user-readable explanation. Raises
    ``SessionFormatError`` if the file is not a session at all.
    """
    with _Archive(data_or_path) as archive:
        manifest = archive.manifest()
        version = manifest.get('schema_version')
        if isinstance(version, int) and 0 <= version < SCHEMA_VERSION:
            # Old manifests may need upgrading before they are meaningful.
            manifest = _load_session(archive)['manifest']
        return _info_from_manifest(manifest, archive)


# ----------------------------------------------------------------------------
# Build (save)
# ----------------------------------------------------------------------------

@dataclass
class _Parts:
    manifest: dict
    state: dict
    client_state: dict
    tables: Dict[str, bytes]
    raw: Dict[str, bytes]      # zip path -> bytes, only when embedded


def _light_metadata(metadata: Mapping) -> Dict[str, Any]:
    return {k: v for k, v in metadata.items() if isinstance(k, str) and _is_light(v)}


def _metadata_overrides(component) -> Dict[str, Any]:
    """Metadata that differs from the freshly parsed values (renames, edits, pointers)."""
    base = getattr(component.standardized, 'metadata', None) or {}
    overrides = {}
    for key, value in component.metadata.items():
        if not isinstance(key, str) or not _is_light(value):
            continue
        if key in base and _safe_equal(base[key], value):
            continue
        overrides[key] = value
    for key in ('display_name', 'sample_name'):
        value = component.metadata.get(key)
        if isinstance(value, str):
            overrides[key] = value
    return overrides


def _table_dtypes(frame: pd.DataFrame) -> Dict[str, str]:
    return {str(column): str(dtype) for column, dtype in frame.dtypes.items()}


def _read_table(data: bytes, dtypes: Mapping[str, str]) -> pd.DataFrame:
    plain, dates = {}, []
    for column, dtype in (dtypes or {}).items():
        if dtype.startswith('datetime64'):
            dates.append(column)
        elif dtype != 'object':
            plain[column] = dtype
        else:
            plain[column] = 'object'
    try:
        return pd.read_csv(io.BytesIO(data), dtype=plain or None, parse_dates=dates or False)
    except (ValueError, TypeError):
        return pd.read_csv(io.BytesIO(data))


def _raw_digest(component) -> str:
    """SHA-256 of a component's original bytes, remembered on the component.

    The bytes object never changes once imported, so hashing a 100 MB workspace is paid once, not per save.
    """
    raw = component.raw_bytes
    cached = getattr(component, '_raw_digest', None)
    if cached is not None and cached[0] is raw:
        return cached[1]
    digest = _sha256(raw)
    try:
        component._raw_digest = (raw, digest)
    except AttributeError:
        pass
    return digest


def _store_raw(cache_dir: Path, sha: str, data: bytes) -> Path:
    """Write one original into the content-addressed cache (once; atomic)."""
    target = cache_dir / sha
    try:
        if target.is_file() and target.stat().st_size == len(data):
            return target
    except OSError:
        pass
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix='.' + sha[:12] + '.', suffix='.tmp', dir=cache_dir)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def _build_parts(store, client_state, project_name, embed_raw, raw_limit_bytes,
                 source_paths, raw_cache: Optional[Path] = None) -> _Parts:
    from .research_package import csv_bytes, _dataframe_sha256

    previous = dict(getattr(store, 'session_meta', None) or {})
    saved_at = _now()
    source_paths = dict(source_paths or {})
    files: Dict[Tuple[str, str], Dict[str, Any]] = {}
    tables: Dict[str, bytes] = {}
    notes: List[str] = []
    bundles_state: List[dict] = []

    def register(component) -> Tuple[str, str]:
        name = component.original_filename
        key = (_raw_digest(component), name)
        if key not in files:
            files[key] = {
                'name': name, 'size': len(component.raw_bytes), 'sha256': key[0],
                'original_path': (source_paths.get(key[0]) or source_paths.get(name)
                                  or source_paths.get(Path(name).name)),
                '_data': component.raw_bytes,
            }
            if files[key]['original_path'] is not None:
                files[key]['original_path'] = str(files[key]['original_path'])
        return key

    for bundle in store.iter_bundles():
        components = list(bundle.component_list)
        extracted = [c for c in components if not c.raw_bytes and (
            (c.metadata.get('pda_extracted') and c.metadata.get('pda_source_id'))
            or (c.metadata.get('eic_extracted') and c.metadata.get('source_file_id')))]
        base = [c for c in components if c not in extracted]
        derived = any(getattr(getattr(c.standardized, 'identity', None), 'detected_format', None)
                      in _DERIVED_FORMATS for c in base)
        has_raw = any(c.raw_bytes for c in base)
        recipe = 'ingest' if has_raw and not derived else 'frame'
        if recipe == 'frame':
            extracted = []
        comp_states = []
        bundle_files: List[Tuple[str, str]] = []
        for component in components:
            is_extracted = component in extracted
            kind = 'frame' if recipe == 'frame' else ('eic_extracted' if component.metadata.get('eic_extracted')
                                                      else 'pda_extracted') if is_extracted else 'ingested'
            raw_key = register(component) if component.raw_bytes else None
            if raw_key and recipe == 'ingest' and raw_key not in bundle_files:
                bundle_files.append(raw_key)
            parsed_sha = _sha256(component.imported_csv) if component.imported_csv else None
            frame = component.dataframe
            state = {
                'component_id': component.component_id,
                'role': _enum_value(component.role),
                'original_filename': component.original_filename,
                'kind': kind,
                'raw': {'sha256': raw_key[0], 'name': raw_key[1]} if raw_key else None,
                'parsed_sha256': parsed_sha,
                'imported_at': component.imported_at,
                'column_roles': {str(c): _enum_value(r) for c, r in component.column_roles.items()},
                'source_category': _enum_value(component.source_category),
                'plot_hint': _enum_value(component.plot_hint),
                'edited': False,
            }
            if kind == 'frame':
                if frame is not None:
                    path = f'tables/{_safe_zip_name(component.component_id)}.csv'
                    tables[path] = csv_bytes(frame)
                    state.update(table=path, dtypes=_table_dtypes(frame))
                state['metadata'] = _light_metadata(component.metadata)
                dropped = sorted(k for k in component.metadata if k not in state['metadata'])
                if dropped:
                    notes.append(f"{bundle.name}: metadata not saved for derived table "
                                 f"({', '.join(map(str, dropped))}).")
                identity = getattr(component.standardized, 'identity', None)
                if identity is not None:
                    state['identity'] = {'original_name': identity.original_name,
                                         'extension': identity.extension,
                                         'detected_format': identity.detected_format,
                                         'detection_stage': identity.detection_stage}
                if component.standardized is not None:
                    state['sample_name'] = component.standardized.sample_name
            else:
                state['metadata'] = _metadata_overrides(component)
                if is_extracted and kind == 'eic_extracted':
                    state['eic'] = {'source_id': component.metadata['source_file_id'],
                                    **component.metadata['eic']}
                elif is_extracted:
                    state['pda'] = {'source_id': component.metadata['pda_source_id'],
                                    'wavelength_nm': component.metadata.get('wavelength_nm')}
                if (frame is not None and parsed_sha is not None
                        and _dataframe_sha256(store, component) != parsed_sha):
                    path = f'edited/{_safe_zip_name(component.component_id)}.csv'
                    tables[path] = csv_bytes(frame)
                    state.update(edited=True, table=path, dtypes=_table_dtypes(frame))
            comp_states.append(state)
        bundles_state.append({
            'bundle_id': bundle.bundle_id, 'name': bundle.name,
            'bundle_type': _enum_value(bundle.bundle_type), 'recipe': recipe,
            'files': [{'sha256': sha, 'name': name} for sha, name in bundle_files],
            'component_order': [c.component_id for c in components],
            'components': comp_states,
        })

    unique_bytes = sum({e['sha256']: e['size'] for e in files.values()}.values())
    embedded = bool(embed_raw) and raw_cache is None and unique_bytes <= raw_limit_bytes
    if bool(embed_raw) and raw_cache is None and not embedded:
        notes.append(f'Original files total {unique_bytes} bytes, above the {raw_limit_bytes} byte '
                     f'limit: stored as name, size, SHA-256 and path only.')
    raw: Dict[str, bytes] = {}
    manifest_files = []
    for (sha, name), entry in files.items():
        path = f'raw/{sha}/{_safe_zip_name(name)}'
        if embedded:
            raw[path] = entry['_data']
        elif raw_cache is not None:
            _store_raw(raw_cache, sha, entry['_data'])
        manifest_files.append({'name': name, 'size': entry['size'], 'sha256': sha,
                               'embedded': embedded, 'path': path if embedded else None,
                               'original_path': entry['original_path']})

    for key, raw_method in (getattr(store, 'instrument_method_files', None) or {}).items():
        method = store.instrument_methods.get(key) or {}
        if method.get('sha256') and len(raw_method) <= MAX_METHOD_FILE_BYTES:
            tables[_method_path(method)] = raw_method

    peaks_state = store.peak_service.serialize()
    peak_count = sum(len(p) for p in peaks_state.get('peaks', {}).values())
    overlays = {}
    for file_id, items in store.lcms_eic_overlays.items():
        kept = [{k: v for k, v in item.items() if k not in ('time', 'intensity') and _is_light(v)}
                for item in items]
        if kept:
            overlays[file_id] = kept
    state = {
        'schema_version': SCHEMA_VERSION,
        'bundles': bundles_state,
        'group_overrides': {k: list(v) if isinstance(v, (tuple, list)) else v
                            for k, v in (getattr(store, 'group_overrides', None) or {}).items()},
        'visibility_state': dict(store.visibility_state),
        'collapse_state': dict(store.collapse_state),
        'file_ui_state': store.file_ui_state,
        'shared_plot_settings': store._shared_plot_settings,
        'analysis_history': store.analysis_history,
        'agent_clients': list(getattr(store, 'agent_clients', None) or []),
        'analysis_plot_settings': store.analysis_plot_settings,
        'analysis_previous': getattr(store, '_analysis_previous', {}),
        'lcms_eic_overlays': overlays,
        'hidden_sample_channels': getattr(store, '_hidden_sample_channels', {}),
        'channel_combine_modes': getattr(store, '_channel_combine_modes', {}),
        'peaks': peaks_state,
        'calibrations': store.calibration_service.serialize(),
        'integration_settings': store.integration_service.serialize(),
        'instrument_methods': dict(store.instrument_methods),
    }
    client_state = dict(client_state or {})
    name = (project_name if project_name is not None else previous.get('project_name')) or ''
    manifest = {
        'format': FORMAT_NAME,
        'schema_version': SCHEMA_VERSION,
        'app': {'name': 'GeckoPlotter', 'version': '2', **_package_versions()},
        'created_at': previous.get('created_at') or saved_at,
        'saved_at': saved_at,
        'project_name': name,
        'counts': {
            'bundles': len(bundles_state),
            'components': sum(len(b['components']) for b in bundles_state),
            'peaks': peak_count,
            'calibrations': len(state['calibrations']),
            'files': len(manifest_files),
            'edited_tables': sum(1 for b in bundles_state for c in b['components'] if c.get('edited')),
        },
        'samples': [b['name'] for b in bundles_state],
        'raw_embedded': embedded,
        'raw_cache': raw_cache is not None,
        'raw_limit_bytes': raw_limit_bytes,
        'files': manifest_files,
        'tables': sorted(tables),
        'has_client_state': bool(client_state),
        'notes': notes,
    }
    return _Parts(manifest, state, client_state, tables, raw)


MAX_METHOD_FILE_BYTES = 16_000_000


def _method_path(method: dict) -> str:
    return f"methods/{method['sha256']}/{_safe_zip_name(method.get('file_name') or 'method')}"


def _restore_method_files(store, archive) -> None:
    """Bring back the original .lcm/.lcd bytes saved with the project (for the FAIR package), verified by SHA-256."""
    store.instrument_method_files.clear()
    for key, method in store.instrument_methods.items():
        sha = method.get('sha256')
        if not (isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{64}', sha)):
            continue
        path = _method_path(method)
        if not archive.has(path):
            continue
        try:
            data = archive.read(path, max_size=MAX_METHOD_FILE_BYTES)
        except SessionFormatError:
            continue
        if hashlib.sha256(data).hexdigest() == sha:
            store.instrument_method_files[key] = data


def _write_archive(fileobj, parts: _Parts) -> None:
    with zipfile.ZipFile(fileobj, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as archive:
        archive.writestr(MANIFEST_NAME, _dumps(parts.manifest, indent=2))
        archive.writestr(STATE_NAME, _dumps(parts.state))
        archive.writestr(CLIENT_STATE_NAME, _dumps(parts.client_state))
        for path, data in sorted(parts.tables.items()):
            archive.writestr(path, data)
        for path, data in parts.raw.items():
            # Instrument exports are text: a lighter level keeps saving fast.
            archive.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=4)


def build_session(store, client_state: Optional[dict] = None, *, project_name: Optional[str] = None,
                  embed_raw: bool = True, raw_limit_bytes: int = DEFAULT_RAW_LIMIT_BYTES,
                  source_paths: Optional[Mapping[str, Any]] = None,
                  raw_cache: Optional[Path] = None) -> bytes:
    """Serialise the workspace of *store* into ``.gecko`` bytes.

    ``client_state`` is an opaque JSON-able dict from the GUI layer (plot tabs,
    zoom, ...) that :func:`restore_session` hands back. Originals are embedded
    (deduplicated by SHA-256) unless ``embed_raw`` is False or they exceed
    ``raw_limit_bytes`` in total; then only name, size, SHA-256 and the original
    path are stored. ``source_paths`` optionally maps file name or SHA-256 to the
    path the file was loaded from (the app itself only knows uploaded bytes).
    ``project_name`` defaults to the name the workspace was last saved/opened under.
    ``raw_cache`` (a folder) is what autosave uses: nothing is embedded, every original is written once to
    ``<raw_cache>/<sha256>`` and the session only references it (manifest ``raw_cache: true``).
    """
    parts = _build_parts(store, client_state, project_name, embed_raw, raw_limit_bytes, source_paths,
                         raw_cache=Path(raw_cache) if raw_cache is not None else None)
    buffer = io.BytesIO()
    _write_archive(buffer, parts)
    return buffer.getvalue()


def save_session(store, path, client_state: Optional[dict] = None, *, project_name: Optional[str] = None,
                 embed_raw: bool = True, raw_limit_bytes: int = DEFAULT_RAW_LIMIT_BYTES,
                 source_paths: Optional[Mapping[str, Any]] = None,
                 raw_cache: Optional[Path] = None) -> Path:
    """Write the workspace to *path* atomically (temp file in the same folder, then rename).

    A missing ``.gecko`` extension is added. Parent folders are created.
    Takes the keyword arguments of :func:`build_session`. Returns the path
    written and remembers it as the workspace's session (``store.session_meta``).
    """
    target = Path(path).expanduser()
    if not target.suffix:
        target = target.with_suffix(EXTENSION)
    if project_name is None and not (getattr(store, 'session_meta', None) or {}).get('project_name'):
        project_name = target.stem
    parts = _build_parts(store, client_state, project_name, embed_raw, raw_limit_bytes, source_paths,
                         raw_cache=Path(raw_cache) if raw_cache is not None else None)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix='.' + target.name + '.', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            _write_archive(handle, parts)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    meta = getattr(store, 'session_meta', None)
    if meta is None:
        meta = store.session_meta = {}
    meta.update(project_name=parts.manifest['project_name'], created_at=parts.manifest['created_at'],
                saved_at=parts.manifest['saved_at'], path=str(target))
    return target


# ----------------------------------------------------------------------------
# Autosave helpers
# ----------------------------------------------------------------------------

#: Set by the web app to a function returning the current browser's short id (or None): every browser then gets an
#: autosave folder of its own, so the "restore last session" offer never shows someone else's work.
autosave_scope = None


def autosave_dir(create: bool = True) -> Path:
    """Folder for autosaves: ``$GECKO_AUTOSAVE_DIR`` or ``~/Documents/GeckoPlotter/Autosave`` (+ a folder per browser)."""
    override = os.environ.get('GECKO_AUTOSAVE_DIR')
    folder = Path(override).expanduser() if override else Path.home() / 'Documents' / 'GeckoPlotter' / 'Autosave'
    scope = autosave_scope() if callable(autosave_scope) else None
    if scope and re.fullmatch(r'[0-9a-f]{8,32}', scope):
        folder = folder / scope
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def latest_autosave() -> Optional[Path]:
    """Newest ``*.gecko`` in the autosave folder (never creates it), or None."""
    folder = autosave_dir(create=False)
    try:
        candidates = [p for p in folder.glob(f'*{EXTENSION}') if p.is_file()]
    except OSError:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


RAW_CACHE_NAME = 'raw'


def raw_cache_dir(create: bool = False) -> Path:
    """Content-addressed store of original files used by autosaves (``<autosave_dir>/raw/<sha256>``)."""
    folder = autosave_dir(create=create) / RAW_CACHE_NAME
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    return folder


def _prune_raw_cache(folder: Path, keep_files: Sequence[Path]) -> None:
    """Delete cached originals that no remaining autosave refers to."""
    cache = folder / RAW_CACHE_NAME
    if not cache.is_dir():
        return
    wanted = set()
    for path in keep_files:
        try:
            info = inspect_session(path)
        except Exception:  # an unreadable autosave must not make us delete what it might need
            return
        wanted.update(f['sha256'] for f in info.files if f.get('sha256'))
    try:
        for entry in cache.iterdir():
            if entry.is_file() and not entry.name.startswith('.') and entry.name not in wanted:
                entry.unlink()
    except OSError:
        pass


def save_autosave(store, client_state: Optional[dict] = None, *, keep: int = 5, raw_cache: bool = True,
                  **kwargs) -> Path:
    """Save to a new ``autosave-<timestamp>.gecko`` and keep only the newest *keep* of them.

    By default the originals are not embedded: each is written once to ``<autosave_dir>/raw/<sha256>`` and the
    autosave only references it, so repeated autosaves of a large workspace cost the state files only (the
    first one also writes the originals). Such a file restores through :func:`restore_session` as long as the
    cache folder is next to it (or is the default autosave folder). Cached originals no remaining autosave
    refers to are deleted. ``raw_cache=False`` embeds like :func:`save_session`.
    """
    folder = autosave_dir()
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    path = folder / f'autosave-{stamp}{EXTENSION}'
    counter = 1
    while path.exists():
        counter += 1
        path = folder / f'autosave-{stamp}-{counter}{EXTENSION}'
    if kwargs.get('project_name') is None:
        kwargs['project_name'] = (getattr(store, 'session_meta', None) or {}).get('project_name') or 'Autosave'
    if raw_cache:
        kwargs['raw_cache'] = folder / RAW_CACHE_NAME
    written = save_session(store, path, client_state, **kwargs)
    # Autosaves are not "the" project file: do not make future Save default to them.
    meta = getattr(store, 'session_meta', None)
    if meta is not None and meta.get('path') == str(written):
        meta.pop('path', None)
    old = sorted((p for p in folder.glob(f'autosave-*{EXTENSION}') if p.is_file()),
                 key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in old[max(keep, 1):]:
        try:
            stale.unlink()
        except OSError:
            pass
    if raw_cache:
        _prune_raw_cache(folder, old[:max(keep, 1)])
    return written


# ----------------------------------------------------------------------------
# Restore
# ----------------------------------------------------------------------------

class _RawResolver:
    """Finds the bytes of every original file: embedded, stored path, search dirs, relocate()."""

    def __init__(self, archive: _Archive, manifest: dict, search_dirs: Iterable, relocate, report: SessionReport):
        self.archive, self.relocate, self.report = archive, relocate, report
        self.entries = {}
        for f in manifest.get('files') or []:
            if not isinstance(f, dict) or not _valid_sha256(f.get('sha256')) or not isinstance(f.get('name'), str):
                report.warnings.append(
                    f"Ignored a file entry in the session manifest with an invalid checksum "
                    f"({str(f.get('sha256') if isinstance(f, dict) else f)[:80]!r}).")
                continue
            self.entries[(f['sha256'], f['name'])] = f
        self.dirs = [Path(d).expanduser() for d in search_dirs or ()]
        self.cache_dirs: List[Path] = []
        if manifest.get('raw_cache'):
            if archive.path is not None:
                self.cache_dirs.append(archive.path.parent / RAW_CACHE_NAME)
            self.cache_dirs.append(raw_cache_dir(create=False))
        self.cache: Dict[Tuple[str, str], Optional[bytes]] = {}
        self.users: Dict[Tuple[str, str], List[str]] = {}

    def get(self, sha: str, name: str, bundle_name: str) -> Optional[bytes]:
        if not isinstance(sha, str):
            sha = str(sha)
        key = (sha, name)
        self.users.setdefault(key, [])
        if bundle_name not in self.users[key]:
            self.users[key].append(bundle_name)
        if key in self.cache:
            return self.cache[key]
        if not _valid_sha256(sha):
            self.report.warnings.append(
                f"{name}: the session refers to this file with an invalid checksum ({str(sha)[:80]!r}); "
                f"it was not read.")
            self.report.missing_files.append({
                'name': name, 'size': None, 'sha256': sha,
                'original_path': None, 'searched': [], 'bundles': self.users.get(key, [])})
            self.cache[key] = None
            return None
        entry = self.entries.get(key) or {'name': name, 'sha256': sha, 'size': None, 'embedded': False,
                                          'path': None, 'original_path': None}
        try:
            data = self._find(entry)
        except SessionFormatError as exc:     # oversize or damaged member: not fatal for the other files
            self.report.errors.append(f'{name}: {exc}')
            data = None
        self.cache[key] = data
        return data

    def _verify(self, data: bytes, entry: dict, origin: str) -> bool:
        ok = _sha256(data) == entry['sha256']
        if not ok:
            self.report.warnings.append(
                f"{entry['name']}: the content ({origin}) does not match the checksum stored in the "
                f"session; it changed or is damaged. It was used anyway, but results may differ "
                f"from when the session was saved.")
        return ok

    def _reject(self, entry: dict, origin) -> None:
        self.report.warnings.append(
            f"{entry['name']}: {origin} does not match the checksum stored in the session (it changed, is "
            f"damaged, or is a different file), so it was not used.")

    def _find(self, entry: dict) -> Optional[bytes]:
        # Bytes that travel inside the archive itself are the session's own data: a checksum mismatch is
        # reported but they are used. Bytes found outside (cache, stored path, search folders, relocate())
        # must match the stored SHA-256, otherwise they are rejected (docs/SESSION_FORMAT.md).
        if not _valid_sha256(entry.get('sha256')):
            return None
        if entry.get('embedded') and entry.get('path') and self.archive.has(entry['path']):
            data = self.archive.read_raw(entry['path'], entry.get('size'))
            self._verify(data, entry, 'embedded copy')
            return data
        searched: List[str] = []
        member = entry.get('original_path')
        if self.archive.package is not None and member in self.archive.package_names:
            # FAIR package: the original sits next to the project inside the same ZIP.
            try:
                data = self.archive.read_package_member(member, entry.get('size'))
            except (KeyError, zipfile.BadZipFile, zlib.error):
                data = None
            if data is not None:
                self._verify(data, entry, f'package file {member}')
                return data
        for folder in self.cache_dirs:
            cached = folder / entry['sha256']      # sha256 was validated as 64 hex characters above
            searched.append(str(cached))
            try:
                data = cached.read_bytes()
            except OSError:
                continue
            if _sha256(data) == entry['sha256']:
                return data
            self._reject(entry, f'the cached copy {cached}')
        declared = entry.get('size')
        for candidate in self._candidates(entry, searched):
            try:
                if isinstance(declared, int) and candidate.stat().st_size != declared:
                    self._reject(entry, f'the file {candidate} (size differs from the stored size)')
                    continue
                data = candidate.read_bytes()
            except OSError:
                continue
            if _sha256(data) == entry['sha256']:
                return data
            self._reject(entry, f'the file {candidate}')
        self.report.missing_files.append({
            'name': entry['name'], 'size': entry.get('size'), 'sha256': entry['sha256'],
            'original_path': entry.get('original_path'), 'searched': searched,
            'bundles': self.users.get((entry['sha256'], entry['name']), [])})
        return None

    def _candidates(self, entry: dict, searched: List[str]):
        name = Path(entry['name']).name
        seen = set()

        def offer(path: Optional[Path]):
            if path is None:
                return None
            searched.append(str(path))
            try:
                resolved = path.resolve()
            except OSError:
                return None
            if resolved in seen or not path.is_file():
                return None
            seen.add(resolved)
            return path

        if entry.get('original_path'):
            stored = Path(entry['original_path']).expanduser()
            if stored.is_absolute():
                hit = offer(stored)
                if hit:
                    yield hit
            else:
                # Relative to a FAIR package root (the project file sits in <root>/session/): never to the cwd.
                roots = ([self.archive.path.parent.parent]
                         if self.archive.path is not None and self.archive.package is None else [])
                for root in roots + self.dirs:
                    hit = offer(root / stored)
                    if hit:
                        yield hit
        for folder in self.dirs:
            hit = offer(folder / name)
            if hit:
                yield hit
        for folder in self.dirs:
            # One level of sub-folders only: never walk a whole disk.
            try:
                subfolders = sorted(p for p in folder.iterdir() if p.is_dir())[:200]
            except OSError:
                continue
            for sub in subfolders:
                hit = offer(sub / name)
                if hit:
                    yield hit
        if self.relocate is not None:
            try:
                answer = self.relocate(dict(entry))
            except Exception as exc:  # a broken callback must not abort the restore
                self.report.warnings.append(f"relocate() failed for {entry['name']}: {exc}")
                answer = None
            if answer:
                hit = offer(Path(answer).expanduser())
                if hit:
                    yield hit


def _ingest_bytes(name: str, data: bytes):
    """Parse one original through the normal ingestion pipeline (temp file, deleted at once)."""
    ingest_file = _ingest_file()
    fd, tmp = tempfile.mkstemp(suffix='_' + _safe_zip_name(name))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        return ingest_file(tmp, name)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _rebuild_roles(bundle) -> None:
    from .bundling_service import paired_tic_exports
    bundle.components = {}
    for component in bundle.component_list:
        bundle.components.setdefault(component.role, component)
    for _trace, spectral in paired_tic_exports(bundle):
        bundle.components[spectral.role] = spectral


def _component_key(component) -> Tuple[str, str]:
    return component.original_filename, str(_enum_value(component.role))


def _roles_from_saved(saved: Mapping[str, str], columns: Iterable[str]):
    types = _types()
    columns = {str(c) for c in columns}
    if not saved or not set(saved) <= columns:
        return None
    return {c: types.ColumnRole(v) if v in {r.value for r in types.ColumnRole} else types.ColumnRole.UNKNOWN
            for c, v in saved.items()}


def _apply_saved_component(component, saved: dict, archive: _Archive, report: SessionReport,
                           label: str, remap) -> bool:
    """Apply user-level changes to a freshly built component. Returns True if the table was replaced."""
    from dataclasses import replace
    from .research_package import csv_bytes
    replaced = False
    overrides = remap(saved.get('metadata') or {})
    if overrides:
        component.metadata.update(overrides)
    if saved.get('imported_at'):
        component.imported_at = saved['imported_at']
    frame = component.dataframe
    if saved.get('edited') and saved.get('table'):
        try:
            data = archive.read(saved['table'], max_size=MAX_TOTAL_BYTES)
            frame = _read_table(data, saved.get('dtypes') or {})
            if csv_bytes(frame) != data:
                report.warnings.append(f'{label}: the edited table could not be reproduced bit-for-bit.')
            component.dataframe = frame
            replaced = True
        except SessionFormatError as exc:
            report.errors.append(f'{label}: edited table missing ({exc}).')
    roles = _roles_from_saved(saved.get('column_roles'), frame.columns if frame is not None else [])
    if roles is not None and roles != component.column_roles:
        component.column_roles = roles
        replaced = True
    if replaced and component.standardized is not None:
        component.standardized = replace(component.standardized, data=component.dataframe,
                                         column_roles=dict(component.column_roles))
    return replaced


def _transfer_sources(dropped, kept_same_file) -> None:
    """A dropped component's raw bytes / payloads move to a kept sibling of the same file."""
    if kept_same_file is None:
        return
    sr_meta = getattr(kept_same_file.standardized, 'metadata', None)
    for key in _PAYLOAD_KEYS:
        if key in dropped.metadata and key not in kept_same_file.metadata:
            kept_same_file.metadata[key] = dropped.metadata[key]
            if isinstance(sr_meta, dict):
                sr_meta[key] = dropped.metadata[key]
    if dropped.raw_bytes and not kept_same_file.raw_bytes:
        kept_same_file.raw_bytes = dropped.raw_bytes


def _match_components(fresh_components, saved_components):
    """Pair freshly parsed components with saved ones.

    Pass 1 requires file name, role and the SHA-256 of the parsed table; pass 2
    falls back to file name + role in order (the parser may have changed).
    Returns (pairs, unmatched_saved, unmatched_fresh, parse_changed).
    """
    pairs, parse_changed = [], []
    free = list(fresh_components)

    def fresh_sha(component):
        return _sha256(component.imported_csv) if component.imported_csv else None

    pending = list(saved_components)
    for saved in list(pending):
        for fresh in free:
            if (_component_key(fresh) == (saved['original_filename'], saved['role'])
                    and saved.get('parsed_sha256') is not None
                    and fresh_sha(fresh) == saved['parsed_sha256']):
                pairs.append((fresh, saved))
                free.remove(fresh)
                pending.remove(saved)
                break
    for saved in list(pending):
        for fresh in free:
            if _component_key(fresh) == (saved['original_filename'], saved['role']):
                pairs.append((fresh, saved))
                free.remove(fresh)
                pending.remove(saved)
                if saved.get('parsed_sha256') != fresh_sha(fresh):
                    parse_changed.append(saved['original_filename'])
                break
    return pairs, pending, free, parse_changed


def _prune_state(state: dict, missing: set) -> None:
    """Drop saved state that belongs to components that could not be restored."""
    if not missing:
        return

    def gone(key) -> bool:
        return isinstance(key, str) and _key_head(key) in missing

    for name in ('visibility_state', 'collapse_state', 'file_ui_state', 'lcms_eic_overlays',
                 'group_overrides', 'hidden_sample_channels'):
        mapping = state.get(name)
        if isinstance(mapping, dict):
            state[name] = {k: v for k, v in mapping.items() if not gone(k)}
    peaks = state.get('peaks') or {}
    for field_name in ('peaks', 'file_color_index'):
        if isinstance(peaks.get(field_name), dict):
            peaks[field_name] = {k: v for k, v in peaks[field_name].items() if not gone(k)}
    if isinstance(peaks.get('imported_files'), list):
        peaks['imported_files'] = [k for k in peaks['imported_files'] if not gone(k)]
    if isinstance(state.get('integration_settings'), dict):
        state['integration_settings'] = {k: v for k, v in state['integration_settings'].items() if not gone(k)}


def _install_frame_bundle(store, saved: dict, archive: _Archive, resolver: _RawResolver,
                          report: SessionReport) -> Optional[Any]:
    from .data_store import Bundle, BundleType, Component, ComponentRole
    types = _types()
    components = []
    for saved_component in saved['components']:
        frame = None
        if saved_component.get('table'):
            frame = _read_table(archive.read(saved_component['table'], max_size=MAX_TOTAL_BYTES), saved_component.get('dtypes') or {})
        roles = _roles_from_saved(saved_component.get('column_roles'),
                                  frame.columns if frame is not None else []) or {}
        category = types.SourceCategory(saved_component.get('source_category') or 'generic')
        hint = types.PlotHint(saved_component.get('plot_hint') or 'line')
        metadata = dict(saved_component.get('metadata') or {})
        ident = saved_component.get('identity') or {}
        standardized = None
        if frame is not None and ident:
            standardized = types.StandardizedResult(
                frame, dict(roles),
                types.FileIdentity(ident.get('original_name', saved_component['original_filename']),
                                   ident.get('extension', ''), ident.get('detected_format', 'session'),
                                   ident.get('detection_stage', 0)),
                plot_hint=hint, source_category=category,
                sample_name=saved_component.get('sample_name'), metadata=dict(metadata))
        raw = b''
        if saved_component.get('raw'):
            raw_ref = saved_component['raw']
            raw = resolver.get(raw_ref['sha256'], raw_ref['name'], saved['name']) or b''
            if not raw:  # an unreachable external copy is not fatal for a stored table
                report.missing_files[:] = [m for m in report.missing_files
                                           if m.get('sha256') != raw_ref['sha256']]
        components.append(Component(
            component_id=saved_component['component_id'], role=ComponentRole(saved_component['role']),
            original_filename=saved_component['original_filename'], raw_bytes=raw, dataframe=frame,
            column_roles=roles, metadata=metadata, source_category=category, plot_hint=hint,
            standardized=standardized, imported_at=None))
    if not components:
        return None
    bundle = Bundle(bundle_id=saved['bundle_id'], name=saved['name'],
                    bundle_type=BundleType(saved['bundle_type']), component_list=components)
    store.add_bundle(bundle)
    for component, saved_component in zip(components, saved['components']):
        if saved_component.get('imported_at'):
            component.imported_at = saved_component['imported_at']
    return bundle


def _install_ingested_bundle(store, saved: dict, archive: _Archive, resolver: _RawResolver,
                             report: SessionReport, idmap: Dict[str, str], remap) -> Optional[Any]:
    from .bundling_service import assign_bundles
    parsed = []
    for ref in saved['files']:
        data = resolver.get(ref['sha256'], ref['name'], saved['name'])
        if data is None:
            continue
        try:
            result = _ingest_bytes(ref['name'], data)
        except Exception as exc:
            log.exception('Re-ingest failed for %s', ref['name'])
            report.errors.append(f"{ref['name']}: could not be read again ({exc}).")
            continue
        if result is None:
            report.errors.append(f"{ref['name']}: no parser recognised the file.")
            continue
        parsed.append((ref['name'], data, result))
    if not parsed:
        return None
    fresh_bundles = assign_bundles(parsed)
    bundle = fresh_bundles[0]
    for extra in fresh_bundles[1:]:
        bundle.component_list.extend(extra.component_list)
    if len(fresh_bundles) > 1:
        report.warnings.append(f"{saved['name']}: files are now grouped differently than when saved; merged.")
        bundle.components = {}
        for component in bundle.component_list:
            bundle.components.setdefault(component.role, component)
    store.add_bundle(bundle)          # also records imported_csv from the fresh parse

    saved_ingested = [c for c in saved['components'] if c['kind'] == 'ingested']
    pairs, unmatched_saved, unmatched_fresh, parse_changed = _match_components(
        bundle.component_list, saved_ingested)
    for name in dict.fromkeys(parse_changed):
        report.warnings.append(f"{name}: parses differently than when the session was saved "
                               f"(parser updated?). Saved edits were applied to the new parse.")
    for dropped in unmatched_fresh:
        # The user had removed this channel/component; keep its shared payloads alive.
        sibling = next((f for f, _ in pairs if f.original_filename == dropped.original_filename), None)
        _transfer_sources(dropped, sibling)
        for component in bundle.component_list:
            for key in _POINTER_KEYS:
                if component.metadata.get(key) == dropped.component_id and sibling is not None:
                    component.metadata[key] = sibling.component_id
                sr_meta = getattr(component.standardized, 'metadata', None)
                if isinstance(sr_meta, dict) and sr_meta.get(key) == dropped.component_id and sibling is not None:
                    sr_meta[key] = sibling.component_id
        store.remove_component(dropped.component_id)
    missing_names = {ref['name'] for ref in saved['files']
                     if resolver.cache.get((ref['sha256'], ref['name'])) is None}
    for saved_component in unmatched_saved:
        if saved_component['original_filename'] in missing_names:
            continue  # its file is missing: already reported
        report.errors.append(f"{saved['name']}: could not match saved component "
                             f"'{saved_component['original_filename']}' to the re-read data.")
    current = store.get_bundle(bundle.bundle_id)
    if current is None or not pairs:
        return None

    bundle_map = {fresh.component_id: saved_component['component_id'] for fresh, saved_component in pairs}
    try:
        store.rekey_bundle(bundle.bundle_id, saved['bundle_id'], bundle_map)
        idmap[saved['bundle_id']] = saved['bundle_id']
    except (KeyError, ValueError) as exc:
        report.warnings.append(f"{saved['name']}: kept new internal ids ({exc}).")
        idmap[saved['bundle_id']] = bundle.bundle_id
        for fresh, saved_component in pairs:
            idmap[saved_component['component_id']] = fresh.component_id
    for fresh, saved_component in pairs:
        idmap.setdefault(saved_component['component_id'], saved_component['component_id'])
    bundle = store.get_bundle(idmap.get(saved['bundle_id'], saved['bundle_id']))
    bundle.name = saved['name']
    by_id = {c.component_id: c for c in bundle.component_list}
    for fresh, saved_component in pairs:
        component = by_id[idmap[saved_component['component_id']]]
        _apply_saved_component(component, saved_component, archive, report,
                               f"{saved['name']} / {saved_component['original_filename']}", remap)

    # PDA wavelengths and ion chromatograms the user extracted: recreate them from the measured data.
    from . import eic_service, pda_service
    for saved_component in saved['components']:
        if saved_component['kind'] not in ('pda_extracted', 'eic_extracted'):
            continue
        is_eic = saved_component['kind'] == 'eic_extracted'
        spec = saved_component.get('eic' if is_eic else 'pda') or {}
        source = idmap.get(spec.get('source_id'), spec.get('source_id'))
        label = (f"{saved['name']} / EIC {spec.get('mz')}" if is_eic
                 else f"{saved['name']} / PDA {spec.get('wavelength_nm')} nm")
        try:
            new_id = (eic_service.add_eic_chromatogram(store, source, spec.get('mz'), spec.get('tolerance'))
                      if is_eic else pda_service.add_pda_chromatogram(store, source, spec.get('wavelength_nm')))
        except (ValueError, TypeError, KeyError) as exc:
            report.errors.append(f'{label}: could not be extracted again ({exc}).')
            report.missing_ids.append(saved_component['component_id'])
            continue
        wanted = saved_component['component_id']
        idmap[wanted] = wanted
        if new_id != wanted:
            try:
                store.rekey_bundle(bundle.bundle_id, None, {new_id: wanted})
            except (KeyError, ValueError) as exc:
                report.warnings.append(f'{label}: kept new internal id ({exc}).')
                idmap[wanted] = new_id
        component = next(c for c in store.get_bundle(bundle.bundle_id).component_list
                         if c.component_id == idmap[wanted])
        _apply_saved_component(component, saved_component, archive, report, label, remap)

    order = [idmap.get(cid, cid) for cid in saved.get('component_order', [])]
    rank = {cid: i for i, cid in enumerate(order)}
    bundle = store.get_bundle(idmap.get(saved['bundle_id'], saved['bundle_id']))
    bundle.component_list.sort(key=lambda c: rank.get(c.component_id, len(rank)))
    _rebuild_roles(bundle)
    return bundle


#: Above this many bytes of originals the previous workspace is not snapshotted before an Open (a rollback
#: would need to rebuild it); a failed Open then keeps whatever restored cleanly and reports the error.
ROLLBACK_MAX_BYTES = 100_000_000

_DICT_SECTIONS = ('visibility_state', 'collapse_state', 'file_ui_state', 'shared_plot_settings', 'group_overrides',
                  'hidden_sample_channels', 'channel_combine_modes', 'analysis_plot_settings',
                  'analysis_previous', 'peaks', 'calibrations', 'integration_settings', 'lcms_eic_overlays',
                  'instrument_methods')


def _validate_state(state: dict) -> None:
    """Dry run of everything ``_apply_state`` will do, on throwaway objects.

    Raises ``SessionFormatError`` for a state that cannot be applied, so ``restore_session`` rejects it while the
    user's workspace is still untouched.
    """
    from .calibration_service import CalibrationService
    from .integration_service import IntegrationService
    from .peak_service import PeakService

    def bad(what, exc=None):
        detail = f' ({type(exc).__name__}: {exc})' if exc is not None else ''
        return SessionFormatError(f'The session file is damaged: its saved {what} cannot be read{detail}. '
                                  f'Your current workspace was not changed.')

    for key in _DICT_SECTIONS:
        value = state.get(key)
        if value is not None and not isinstance(value, dict):
            raise bad(key.replace('_', ' '))
    history = state.get('analysis_history')
    if history is not None and not isinstance(history, list):
        raise bad('analysis history')
    bundles = state.get('bundles')
    if bundles is not None and not isinstance(bundles, list):
        raise bad('sample list')
    for saved in bundles or []:
        if (not isinstance(saved, dict) or not isinstance(saved.get('bundle_id'), str)
                or not isinstance(saved.get('components'), list)
                or not all(isinstance(c, dict) and isinstance(c.get('component_id'), str)
                           for c in saved['components'])):
            raise bad('sample list')
    for key, service, label in (('peaks', PeakService, 'peaks'), ('calibrations', CalibrationService, 'calibrations'),
                                ('integration_settings', IntegrationService, 'integration settings')):
        try:
            service().deserialize(state.get(key) or {})
        except Exception as exc:
            raise bad(label, exc) from exc
    for file_id, overlays in (state.get('lcms_eic_overlays') or {}).items():
        if not isinstance(overlays, list) or not all(isinstance(o, dict) for o in overlays):
            raise bad('LC-MS overlays')
    try:
        for value in (state.get('group_overrides') or {}).values():
            tuple(value) if isinstance(value, list) else value
    except Exception as exc:
        raise bad('group overrides', exc) from exc


def _snapshot_workspace(store) -> Optional[bytes]:
    """The current workspace as ``.gecko`` bytes (in memory) for rollback, or None when empty or too large."""
    try:
        bundles = list(store.iter_bundles())
        if not bundles:
            return None
        raw_bytes = sum(len(c.raw_bytes or b'') for b in bundles for c in b.component_list)
        if raw_bytes > ROLLBACK_MAX_BYTES:
            return None
        return build_session(store, None, embed_raw=True, raw_limit_bytes=ROLLBACK_MAX_BYTES)
    except Exception:
        log.exception('Could not snapshot the workspace before opening a session')
        return None


def restore_session(store, data_or_path, *, search_dirs: Iterable = (),
                    relocate: Optional[Callable[[dict], Any]] = None) -> SessionReport:
    """Replace the workspace of *store* with the saved session.

    The file is read and validated before anything is touched, so a bad or
    too-new file raises (``SessionFormatError`` / ``SessionVersionError``,
    messages are user-readable) and leaves the current workspace intact. That
    includes a dry run of the saved peaks, calibrations and settings.
    Afterwards ``store.reset_workspace()`` empties the workspace in place (the
    service objects callbacks hold stay the same) and every original is
    re-ingested, re-keyed to its saved id, and the saved decisions are applied.

    Nothing after the reset raises: an unexpected failure is recorded in
    ``report.errors`` (``ok=False``) and the previous workspace is put back from
    an in-memory snapshot (``report.rolled_back``) when it was small enough to
    take one; otherwise whatever restored cleanly stays.
    ``report.workspace_replaced`` tells callers that the store changed.

    Missing external originals are looked up at the stored path, in
    ``search_dirs`` (plus the session file's own folder), then via
    ``relocate(file_entry) -> path | None``; whatever stays missing is listed in
    ``SessionReport.missing_files`` and the rest is restored. Instrument peaks
    are *not* re-imported: the saved peaks are authoritative. The GUI-layer
    ``client_state`` comes back in ``report.client_state``.
    """
    return _restore_session(store, data_or_path, search_dirs=search_dirs, relocate=relocate, allow_rollback=True)


def _restore_session(store, data_or_path, *, search_dirs, relocate, allow_rollback: bool) -> SessionReport:
    with _Archive(data_or_path) as archive:
        session = _load_session(archive)
        manifest, state = session['manifest'], session['state']
        _validate_state(state)
        report = SessionReport(info=_info_from_manifest(manifest, archive))
        dirs = list(search_dirs or ())
        if archive.path is not None:
            dirs.append(archive.path.parent)
        resolver = _RawResolver(archive, manifest, dirs, relocate, report)

        # Everything that can reject the file outright (format, version, JSON, state shape) has run above.
        snapshot = _snapshot_workspace(store) if allow_rollback else None
        previous_meta = dict(getattr(store, 'session_meta', None) or {})
        store.reset_workspace()
        report.workspace_replaced = True
        try:
            _install_session(store, archive, session, report, resolver)
        except Exception as exc:
            log.exception('Restoring the session failed after the workspace was reset')
            report.ok = False
            report.client_state = {}
            report.errors.append(f'The session could not be fully restored ({type(exc).__name__}: {exc}).')
            if snapshot is not None:
                try:
                    _restore_session(store, snapshot, search_dirs=(), relocate=None, allow_rollback=False)
                    store.session_meta = previous_meta
                    report.rolled_back = True
                    report.errors.append('Your previous workspace was put back unchanged.')
                    report.restored = {}
                except Exception:
                    log.exception('Rollback of the previous workspace failed')
                    report.errors.append('Putting the previous workspace back also failed; '
                                         'what could be restored from the session is shown.')
            else:
                report.errors.append('What could be restored from the session is shown; the previous '
                                     'workspace could not be put back (too large to keep a copy).')
            if not report.rolled_back:
                report.restored = _restored_counts(store, report.restored)
        return report


def _restored_counts(store, previous: Optional[dict] = None) -> Dict[str, int]:
    counts = dict(previous or {})
    try:
        bundles = list(store.iter_bundles())
        counts['bundles'] = len(bundles)
        counts['components'] = sum(len(b.component_list) for b in bundles)
        counts['peaks'] = sum(len(p) for p in store.peak_service._peaks.values())
        counts['calibrations'] = len(store.calibration_service.get_all_models())
    except Exception:
        pass
    return counts


def _install_session(store, archive: _Archive, session: dict, report: SessionReport,
                     resolver: _RawResolver) -> None:
    manifest, state = session['manifest'], session['state']
    idmap: Dict[str, str] = {}
    remap = lambda obj: remap_ids(obj, idmap) if any(k != v for k, v in idmap.items()) else obj  # noqa: E731
    missing_ids: set = set()
    restored_bundles = restored_components = edited = 0

    for saved in state.get('bundles') or []:
        try:
            bundle = (_install_frame_bundle(store, saved, archive, resolver, report)
                      if saved.get('recipe') == 'frame'
                      else _install_ingested_bundle(store, saved, archive, resolver, report, idmap, remap))
        except Exception as exc:
            log.exception('Could not restore %s', saved.get('name'))
            report.errors.append(f"{saved.get('name')}: could not be restored ({exc}).")
            bundle = None
        saved_ids = [saved['bundle_id']] + [c['component_id'] for c in saved['components']]
        if bundle is None:
            missing_ids.update(saved_ids)
            continue
        idmap.setdefault(saved['bundle_id'], bundle.bundle_id)
        present = {c.component_id for c in bundle.component_list}
        for component_id in (c['component_id'] for c in saved['components']):
            if idmap.get(component_id, component_id) not in present:
                missing_ids.add(component_id)
        restored_bundles += 1
        restored_components += len(bundle.component_list)
        edited += sum(1 for c in saved['components'] if c.get('edited'))
    for entry in report.missing_files:
        entry['bundles'] = resolver.users.get((entry['sha256'], entry['name']), entry.get('bundles', []))
        report.warnings.append(
            f"Original file not found: {entry['name']} (used by {', '.join(entry['bundles']) or '?'}). "
            f"Locate it and restore again.")
    missing_ids.update(report.missing_ids)
    report.missing_ids = sorted(missing_ids)
    report.id_map = {k: v for k, v in idmap.items() if k != v}

    # Saved user state, with ids remapped if any id could not be kept.
    state = remap(state)
    _prune_state(state, missing_ids)
    _apply_state(store, state, report)
    _restore_method_files(store, archive)

    client_state = remap(session.get('client_state') or {})
    report.client_state = client_state
    meta = {'project_name': manifest.get('project_name') or '', 'created_at': manifest.get('created_at'),
            'saved_at': manifest.get('saved_at')}
    if archive.path is not None and archive.package is None:   # a package is a deposit, not "the project file"
        meta['path'] = str(archive.path)
    store.session_meta = meta
    for cache in getattr(store, '_render_caches', []):
        cache.prune([])
    report.restored = {
        'bundles': restored_bundles, 'components': restored_components,
        'peaks': sum(len(p) for p in store.peak_service._peaks.values()),
        'calibrations': len(store.calibration_service.get_all_models()),
        'edited_tables': edited,
    }
    report.ok = not report.errors and not report.missing_files


def _apply_state(store, state: dict, report: SessionReport) -> None:
    """Install the saved user state on a store whose bundles are already in place."""
    store.visibility_state.clear()
    store.visibility_state.update(state.get('visibility_state') or {})
    store.collapse_state.update(state.get('collapse_state') or {})
    store.file_ui_state.update(state.get('file_ui_state') or {})
    store._shared_plot_settings.update(state.get('shared_plot_settings') or {})
    overrides = {k: tuple(v) if isinstance(v, list) else v
                 for k, v in (state.get('group_overrides') or {}).items()}
    if overrides:
        store.group_overrides = overrides
    if state.get('hidden_sample_channels'):
        store._hidden_sample_channels = state['hidden_sample_channels']
    if state.get('channel_combine_modes'):
        store._channel_combine_modes = state['channel_combine_modes']
    store.analysis_history[:] = state.get('analysis_history') or []
    store.agent_clients = [dict(a) for a in (state.get('agent_clients') or []) if isinstance(a, dict)]
    store.analysis_plot_settings = state.get('analysis_plot_settings') or {}
    store._analysis_previous = state.get('analysis_previous') or {}

    store.peak_service.deserialize(state.get('peaks') or {})
    store.calibration_service.deserialize(state.get('calibrations') or {})
    store.integration_service.deserialize(state.get('integration_settings') or {})
    store.instrument_methods.clear()
    store.instrument_methods.update(state.get('instrument_methods') or {})
    from services.shimadzu_method import apply_methods
    apply_methods(store)

    for file_id, overlays in (state.get('lcms_eic_overlays') or {}).items():
        entry = store.get_data_by_id(file_id)
        for overlay in overlays:
            try:
                time_axis, intensity = store.lcms_service.extract_eic(
                    entry, float(overlay['mz']), float(overlay.get('tolerance', 0.5)))
            except Exception as exc:
                report.warnings.append(f"EIC m/z {overlay.get('mz')} could not be recomputed ({exc}).")
                continue
            store.add_lcms_eic_overlay(file_id, {**overlay, 'time': time_axis, 'intensity': intensity})
