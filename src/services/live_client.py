"""The agent's side of live mode (services/live_agent): find the GeckoPlotter that is open and run a call in it.

``find()`` reads the live files: the newest one whose app still runs. ``call()`` returns the result, raises Refused
when the app said no (Stop, unknown call) and NotRunning when no app answers, so gecko_mcp works on its own then.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from services.live_agent import CALL, live_dir


class NotRunning(Exception):
    pass


class Refused(Exception):
    pass


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def find() -> Optional[dict]:
    """The live file of the GeckoPlotter used last: {port, pid, key}, or None when none runs."""
    best = None
    try:
        files = list(live_dir().glob('*.json'))
    except OSError:
        return None
    for path in files:
        try:
            info = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not _alive(info.get('pid')):
            continue
        if best is None or info.get('used', 0) > best.get('used', 0):
            best = info
    return best


def call(method: str, args=None, kwargs=None, agent: Optional[dict] = None, timeout: float = 900) -> Any:
    info = find()
    if not info:
        raise NotRunning()
    body = json.dumps({'method': method, 'args': list(args or []), 'kwargs': kwargs or {}, 'agent': agent}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{info['port']}{CALL}", data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'X-Gecko-Key': info['key']})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())['result']
    except TimeoutError:                                # it is working on it: do not run the call a second time here
        raise Refused(f'GeckoPlotter did not answer within {timeout:.0f} s.') from None
    except urllib.error.HTTPError as exc:
        try:
            reason = json.loads(exc.read()).get('refused') or str(exc)
        except ValueError:
            reason = str(exc)
        if exc.code in (403, 409):
            raise Refused(reason) from None
        raise NotRunning() from None
    except (urllib.error.URLError, ConnectionError, OSError):
        raise NotRunning() from None
