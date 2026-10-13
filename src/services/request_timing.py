"""Log the Dash callbacks that take long, with how much data they moved.

On a shared or slower computer the question is always "which step is slow": a heavy calculation, or a large upload
travelling through a callback. Every callback slower than ``threshold_ms`` is written to the log with its duration,
request and response size and the output it updates. Set ``GECKO_SLOW_MS`` to change the threshold (default 500).
"""
from __future__ import annotations

import logging
import re
import time

log = logging.getLogger('geckoplotter.timing')
CALLBACK_PATH = '/_dash-update-component'
_OUTPUT = re.compile(r'"output"\s*:\s*"([^"]{1,300})"')


def output_label(raw: bytes) -> str:
    """The output id a callback request is for, read from the ends of its body without parsing all of it."""
    for part in (raw[:2000], raw[-2000:]):          # Dash puts "output" first or last depending on the version
        match = _OUTPUT.search(part.decode('utf-8', errors='ignore'))
        if match:
            return match.group(1).strip('.')
    return '?'


def _size(n: int) -> str:
    return f'{n / 1e6:.1f} MB' if n >= 1e6 else f'{n / 1e3:.0f} KB'


def install(server, threshold_ms: float = 500.0) -> None:
    from flask import g, request

    @server.before_request
    def _start():
        g._gecko_started = time.perf_counter()

    @server.after_request
    def _finish(response):
        started = getattr(g, '_gecko_started', None)
        if started is not None and request.path == CALLBACK_PATH:
            elapsed = (time.perf_counter() - started) * 1000.0
            if elapsed >= threshold_ms:
                raw = request.get_data(cache=True)
                log.warning('slow callback %5.0f ms  in %s  out %s  %s', elapsed, _size(len(raw)),
                            _size(response.calculate_content_length() or 0), output_label(raw))
        return response
