"""Shared helpers for the session tests: load files the way the upload callback does."""
import io
import json
import os
import tempfile
import zipfile

import numpy as np

from src.ingestion import ingest_file
from services.bundling_service import assign_bundles
from services.channel_visibility import initialize_imported_channels


def load_files(store, files, skip_unparsable=False):
    """files: [(name, bytes)]. Same steps as callbacks.upload_callbacks.handle_file_upload."""
    parsed = []
    for name, data in files:
        fd, tmp = tempfile.mkstemp(suffix='_' + name.replace('/', '_'))
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
            result = ingest_file(tmp, name)
        finally:
            os.unlink(tmp)
        if result is None and skip_unparsable:
            continue  # the upload callback skips these too
        assert result is not None, name
        parsed.append((name, data, result))
    bundles = assign_bundles(parsed)
    for bundle in bundles:
        store.add_bundle(bundle)
    initialize_imported_channels(store, bundles)
    return bundles


def chromatogram_csv(centres, amplitude=100.0, width=0.15, offset=0.0):
    t = np.linspace(0, 10, 501)
    y = np.full_like(t, offset)
    for c in centres:
        y = y + amplitude * np.exp(-((t - c) / width) ** 2)
    text = 'Time (min),Signal (mAU)\n' + ''.join(f'{a:.4f},{b:.6f}\n' for a, b in zip(t, y))
    return text.encode()


def rewrite_zip(data, change):
    """Return a copy of a .gecko with change(name, bytes) -> bytes | None applied (None drops the entry)."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = change(info.filename, source.read(info.filename))
            if content is not None:
                target.writestr(info.filename, content)
    return out.getvalue()


def edit_json(data, name, edit):
    def change(entry, content):
        if entry != name:
            return content
        value = json.loads(content)
        edit(value)
        return json.dumps(value).encode()
    return rewrite_zip(data, change)
