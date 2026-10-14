"""Stop the app on its own once nobody has it open.

When the launcher starts GeckoPlotter without a window (from the desktop icon), there is no window to close. Every open
GeckoPlotter page calls ``/_gecko/alive`` every 20 s (assets/js/heartbeat.js); if no page has called for
``GECKO_EXIT_WHEN_IDLE`` seconds the process exits, and the launcher with it. Time the computer spends asleep does not
count, so a laptop opened the next morning finds GeckoPlotter still running. Without the setting nothing happens.
"""
from __future__ import annotations

import logging
import os
import threading
import time

ROUTE = '/_gecko/alive'
log = logging.getLogger(__name__)

_lock = threading.Lock()
_awake_since_last_call = 0.0          # seconds the computer was awake since a page last called


def seen() -> None:
    global _awake_since_last_call
    with _lock:
        _awake_since_last_call = 0.0


def idle_seconds() -> float:
    with _lock:
        return _awake_since_last_call


def tick(elapsed: float, step: float) -> None:
    """Add one check interval of awake time; a longer gap means the computer slept, which does not count."""
    global _awake_since_last_call
    with _lock:
        _awake_since_last_call += min(elapsed, step * 1.5)


def install(server, exit_after: float | None = None, step: float = 5.0, exit_fn=None) -> None:
    @server.route(ROUTE, methods=['GET', 'POST'])
    def _alive():
        seen()
        return ('', 204)

    if exit_after is None:
        value = os.environ.get('GECKO_EXIT_WHEN_IDLE')
        exit_after = float(value) if value else None
    if not exit_after:
        return
    seen()                                 # the first page gets the full allowance to open
    exit_fn = exit_fn or (lambda: os._exit(0))

    def watch():
        last = time.monotonic()
        while True:
            time.sleep(step)
            now = time.monotonic()
            tick(now - last, step)
            last = now
            if idle_seconds() >= exit_after:
                log.info('No GeckoPlotter page open for %.0f s: stopping.', idle_seconds())
                exit_fn()
                return

    threading.Thread(target=watch, name='gecko-idle-exit', daemon=True).start()
