"""Fast file upload: raw (optionally gzip) bytes instead of base64 text inside a Dash callback.

Dash's own upload turns a file into a base64 data URL, which is a third larger and has to be read, sent as JSON and
parsed again. The browser now posts the file itself to ``/_gecko/upload`` (compressed on the way when the browser can),
the server keeps the bytes for a few minutes and hands the callbacks a short ``gecko-upload:<token>`` string where they
used to receive the data URL. ``read_contents`` accepts both, so older paths keep working.
"""
from __future__ import annotations

import threading
import time
import urllib.parse
import uuid
import zlib
from typing import Dict, Optional, Tuple

PREFIX = 'gecko-upload:'
ROUTE = '/_gecko/upload'
MAX_FILE_BYTES = 1_500_000_000          # after decompression
MAX_STAGED_BYTES = 2_500_000_000        # everything waiting to be used
TTL_SECONDS = 15 * 60

_lock = threading.Lock()
_staged: Dict[str, Tuple[str, bytes, float]] = {}


class UploadError(ValueError):
    """The uploaded bytes were refused."""


def _expire(now: float) -> None:
    for token in [t for t, (_, _, stamp) in _staged.items() if now - stamp > TTL_SECONDS]:
        del _staged[token]


def stage(name: str, data: bytes) -> str:
    """Keep ``data`` for the callbacks and return its token."""
    if len(data) > MAX_FILE_BYTES:
        raise UploadError('This file is too large.')
    now = time.time()
    with _lock:
        _expire(now)
        if sum(len(d) for _, d, _ in _staged.values()) + len(data) > MAX_STAGED_BYTES:
            raise UploadError('Too many uploads are waiting; try again in a moment.')
        token = uuid.uuid4().hex
        _staged[token] = (name, data, now)
    return token


def decode_body(body: bytes, encoding: str) -> bytes:
    """The file bytes of an upload request body (``gzip`` is decompressed with a size limit)."""
    if encoding == 'gzip':
        inflater = zlib.decompressobj(wbits=31)
        try:
            data = inflater.decompress(body, MAX_FILE_BYTES + 1)
            if inflater.unconsumed_tail or len(data) > MAX_FILE_BYTES:
                raise UploadError('This file is too large.')
            data += inflater.flush()
        except zlib.error as exc:
            raise UploadError('The compressed upload is damaged.') from exc
        return data
    if encoding not in ('', 'identity'):
        raise UploadError('Unknown upload encoding.')
    return body


def is_token(contents) -> bool:
    return isinstance(contents, str) and contents.startswith(PREFIX)


def read_contents(contents: str) -> bytes:
    """The bytes behind an upload value: a staged token, or a classic base64 data URL."""
    if is_token(contents):
        with _lock:
            item = _staged.get(contents[len(PREFIX):])
        if item is None:
            raise UploadError('The upload expired; add the file again.')
        return item[1]
    import base64
    _, encoded = contents.split(',', 1)
    return base64.b64decode(encoded)


def release(contents) -> None:
    """Forget a staged upload once its bytes are in the workspace (they would otherwise be held twice)."""
    if is_token(contents):
        with _lock:
            _staged.pop(contents[len(PREFIX):], None)


def install(server) -> None:
    from flask import jsonify, request

    @server.route(ROUTE, methods=['POST'])
    def _gecko_upload():
        name = urllib.parse.unquote(request.headers.get('X-Gecko-Name', '')) or 'upload'
        try:
            data = decode_body(request.get_data(), request.headers.get('X-Gecko-Encoding', 'identity'))
            token = stage(name, data)
        except UploadError as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(token=token, name=name, size=len(data))
