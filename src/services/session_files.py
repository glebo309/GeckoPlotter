"""Small Dash-free helpers for the project (.gecko) GUI: names, uploads, ages, recent autosaves."""
from __future__ import annotations

import base64
import io
import os
import re
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import session_service as ss

DEFAULT_PROJECT_NAME = 'Untitled project'
AUTOSAVE_MAX_AGE_DAYS = 14
_UNSAFE = re.compile(r'[^\w\-. ()]+', re.UNICODE)


def is_session_filename(name) -> bool:
    """True for a file name that is a GeckoPlotter project (``.gecko``), whatever the case."""
    return isinstance(name, str) and name.strip().lower().endswith(ss.EXTENSION)


def is_package_filename(name) -> bool:
    """True for a ``.zip`` name (a FAIR package *may* hold a project; see :func:`is_project_upload`)."""
    return isinstance(name, str) and name.strip().lower().endswith('.zip')


def is_project_upload(contents, name) -> bool:
    """Is this uploaded file a project to open: a ``.gecko``, or a ``.zip`` that is a FAIR package with a project.

    Decided by extension for ``.gecko``; a ``.zip`` is looked into (its file list only), because ordinary zips
    are not projects. ``contents`` is the dcc.Upload data URL.
    """
    if is_session_filename(name):
        return True
    if not is_package_filename(name) or not isinstance(contents, str) or ',' not in contents:
        return False
    try:
        data = base64.b64decode(contents.split(',', 1)[1])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return ss.PACKAGE_SESSION in archive.namelist()
    except Exception:
        return False


def safe_project_filename(name: Optional[str]) -> str:
    """``'My run: 12/3'`` -> ``'My run_ 12_3.gecko'``. Never empty, never a path, always ``.gecko``."""
    text = _UNSAFE.sub('_', str(name or '').strip())
    text = re.sub(r'_{2,}', '_', text).strip(' ._')[:80].strip(' ._')
    return (text or 'project') + ss.EXTENSION


def project_title(name: Optional[str]) -> str:
    return (name or '').strip() or DEFAULT_PROJECT_NAME


def sessions_temp_dir() -> Path:
    folder = Path(tempfile.gettempdir()) / 'geckoplotter-sessions'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stash_session_upload(contents: str, filename: str) -> Dict[str, Any]:
    """Decode an uploaded ``.gecko`` (dcc.Upload data URL) into a temp file and describe it.

    The browser sends a file once; keeping it on disk lets "Retry" (after locating missing originals) restore
    again without uploading it a second time. Older stashes are removed.
    """
    _, encoded = contents.split(',', 1)
    data = base64.b64decode(encoded)
    folder = sessions_temp_dir()
    cutoff = time.time() - 24 * 3600
    for old in [*folder.glob(f'*{ss.EXTENSION}'), *folder.glob('*.zip')]:
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    suffix = '.zip' if is_package_filename(filename) else ss.EXTENSION
    fd, name = tempfile.mkstemp(suffix=suffix, dir=folder)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    return {'path': name, 'name': Path(filename or 'project').stem, 'upload': True, 'ts': int(time.time() * 1000)}


def forget_stash(source: Optional[dict]) -> None:
    """Delete a temp copy made by :func:`stash_session_upload` (no-op for other sources)."""
    if not source or not source.get('upload'):
        return
    try:
        path = Path(source['path'])
        if path.parent == sessions_temp_dir() and path.suffix in (ss.EXTENSION, '.zip'):
            path.unlink()
    except (OSError, KeyError, TypeError):
        pass


def parse_saved_at(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_seconds(info: ss.SessionInfo, path: Optional[Path] = None) -> Optional[float]:
    """Seconds since the session was saved (manifest time, else file time); None when unknown."""
    when = parse_saved_at(info.saved_at)
    if when is not None:
        return max(0.0, (datetime.now(timezone.utc) - when).total_seconds())
    if path is not None:
        try:
            return max(0.0, time.time() - path.stat().st_mtime)
        except OSError:
            return None
    return None


def humanize_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return 'a while ago'
    if seconds < 45:
        return 'just now'
    minutes = round(seconds / 60)
    if minutes < 60:
        return f'{max(minutes, 1)} min ago'
    hours = round(seconds / 3600)
    if hours < 24:
        return f'{hours} h ago'
    days = round(seconds / 86400)
    return f'{days} day{"s" if days != 1 else ""} ago'


def plural(count: int, word: str) -> str:
    return f'{count} {word}{"" if count == 1 else "s"}'


def recent_autosaves(limit: int = 5, max_age_days: Optional[float] = None) -> List[Dict[str, Any]]:
    """Newest autosaves with what the "Restore?" prompt and the Open menu show. Never creates the folder."""
    folder = ss.autosave_dir(create=False)
    try:
        files = sorted((p for p in folder.glob(f'autosave-*{ss.EXTENSION}') if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    found: List[Dict[str, Any]] = []
    for path in files:
        if len(found) >= limit:
            break
        try:
            info = ss.inspect_session(path)
        except Exception:
            continue
        if not info.compatible:
            continue
        age = age_seconds(info, path)
        if max_age_days is not None and age is not None and age > max_age_days * 86400:
            continue
        found.append({'path': str(path), 'name': info.project_name, 'samples': int(info.counts.get('bundles', 0)),
                      'age': age, 'saved_at': info.saved_at})
    return found
