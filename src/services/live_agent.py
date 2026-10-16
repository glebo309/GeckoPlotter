"""Live mode: an agent (gecko_mcp.py) works in the GeckoPlotter that is open, and the screen redraws after each step.

The running app answers agent calls at ``/_gecko/agent/call``: only from this computer (loopback) and only with the key
in its live file, ``<settings folder>/live/<port>.json`` (readable by this user only). The call runs a ``gecko_api``
Workspace method on the workspace of the browser tab used last. Every open page asks ``/_gecko/agent/state`` once a
second (assets/js/agent-live.js): what the agent is doing, for the status bar, and a counter that tells the page to
redraw. Stop in the status bar makes the app refuse agent calls until it is clicked again.

When several GeckoPlotters run (an installed one and a development copy), the agent works in the one whose window was
used last: a page that is clicked or focused touches its live file, and gecko_mcp picks the newest file.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

CALL, STATE, HERE, STOP = '/_gecko/agent/call', '/_gecko/agent/state', '/_gecko/agent/here', '/_gecko/agent/stop'
LOOPBACK = {'127.0.0.1', '::1', '::ffff:127.0.0.1'}

# The Workspace methods an agent may call: every tool of gecko_mcp.py, nothing else.
METHODS = {'open', 'samples', 'detect_peaks', 'integrate', 'peaks', 'rename_peak', 'calibrate', 'list_calibrations',
           'remove_calibration', 'add_uv_channel', 'uv_spectrum', 'add_eic_channel', 'eic', 'mass_spectrum',
           'figure', 'export_results', 'save'}
# Calls that only read: the page does not redraw after them.
READS = {'samples', 'peaks', 'list_calibrations', 'uv_spectrum', 'mass_spectrum', 'figure', 'export_results', 'save'}

# What the status bar says while the agent works ("Claude Code: integrating ...").
_DOING = {'open': 'opening {0}', 'samples': 'reading the samples', 'detect_peaks': 'detecting peaks',
          'integrate': 'integrating {0}-{1} min', 'peaks': 'reading the peak table', 'rename_peak': 'renaming {1}',
          'calibrate': 'calibrating {0}', 'list_calibrations': 'reading the calibrations',
          'remove_calibration': 'removing calibration {0}', 'add_uv_channel': 'adding {0} nm',
          'uv_spectrum': 'reading the UV spectrum at {1} min', 'add_eic_channel': 'adding EIC {0}',
          'eic': 'extracting EIC {0}', 'mass_spectrum': 'reading the mass spectrum', 'figure': 'drawing a figure',
          'export_results': 'exporting to Excel', 'save': 'saving the project'}


def settings_dir() -> Path:
    return Path(os.environ.get('GECKO_SETTINGS_DIR') or Path.home() / 'Documents' / 'GeckoPlotter')


def live_dir() -> Path:
    return settings_dir() / 'live'


def describe(method: str, args) -> str:
    text = _DOING.get(method, method)
    names = [Path(str(a)).name if method == 'open' else a for a in (args or [])]
    try:
        return text.format(*names)
    except (IndexError, KeyError):
        return text.split(' {')[0]


class LiveAgent:
    """The live state of one app process: its key, the browser tab the agent works in and what the agent does."""

    def __init__(self, registry, port: int, folder: Optional[Path] = None):
        self.registry = registry
        self.port = port
        self.folder = folder or live_dir()
        self.key = secrets.token_hex(24)
        self.target: Optional[str] = None        # session id of the tab used last
        self.stopped = False
        self.version = 0                         # bumped after every change: the page redraws
        self.busy = False
        self.agent = ''                          # 'Claude Code'
        self.doing = ''                          # 'integrating 10.4-11.2 min'
        self.done_at = 0.0
        self._workspaces: Dict[str, Any] = {}
        self._lock = threading.Lock()

    # -- the live file ---------------------------------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self.folder / f'{self.port}.json'

    def write_file(self) -> None:
        """Write (or touch) this app's live file: newest file = the GeckoPlotter whose window was used last."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            body = json.dumps({'port': self.port, 'pid': os.getpid(), 'key': self.key, 'used': time.time()})
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as handle:
                handle.write(body)
        except OSError as exc:                              # read-only settings: live mode is off, nothing else
            log.warning('Live mode is off (%s)', exc)

    def remove_file(self) -> None:
        try:
            if json.loads(self.path.read_text()).get('pid') == os.getpid():
                self.path.unlink()
        except (OSError, ValueError):
            pass

    # -- the tab the agent works in --------------------------------------------------------------------------------

    def here(self, sid: Optional[str]) -> None:
        if sid and sid != self.target:
            self.target = sid
        self.write_file()

    def state(self, sid: Optional[str]) -> dict:
        return {'version': self.version, 'busy': self.busy, 'agent': self.agent, 'doing': self.doing,
                'stopped': self.stopped, 'here': bool(sid and sid == self.target), 'done_at': self.done_at}

    # -- a call ----------------------------------------------------------------------------------------------------

    def workspace(self, sid: str):
        from gecko_api import Workspace
        store = self.registry.for_session(sid)
        workspace = self._workspaces.get(sid)
        if workspace is None or workspace.store is not store:
            workspace = self._workspaces[sid] = Workspace(store)
        return workspace

    def call(self, method: str, args=None, kwargs=None, agent: Optional[dict] = None) -> Any:
        """Run one Workspace method on the target tab's workspace. Raises LiveRefused when live mode cannot take it."""
        from gecko_api import GeckoError
        if method not in METHODS:
            raise LiveRefused(f'Unknown call {method!r}')
        if self.stopped:
            raise LiveRefused('Stopped in GeckoPlotter: click Stop again in the status bar to let the agent work.')
        if not self.target:
            raise LiveRefused('No GeckoPlotter window has been used yet.')
        with self._lock:                                    # one agent call at a time
            workspace = self.workspace(self.target)
            agent = dict(agent or {})
            self.agent = agent.pop('client_label', None) or self.agent or 'Agent'
            workspace.agent = agent or workspace.agent
            self.doing, self.busy = describe(method, args), True
            try:
                result = getattr(workspace, method)(*(args or []), **(kwargs or {}))
            except GeckoError as exc:
                result = {'error': str(exc)}
            finally:
                self.busy, self.done_at = False, time.time()
                if method not in READS:
                    self.version += 1
        return result


class LiveRefused(Exception):
    pass


def install(server, registry, port: int, folder: Optional[Path] = None) -> LiveAgent:
    """Answer agent calls and the pages' status questions; write this app's live file."""
    import atexit
    from flask import g, jsonify, request
    from services.workspaces import COOKIE, valid_session_id

    live = LiveAgent(registry, port, folder)
    live.write_file()
    atexit.register(live.remove_file)

    def page_sid():
        sid = request.cookies.get(COOKIE)
        return sid if valid_session_id(sid) else None

    @server.route(STATE, methods=['GET'])
    def _agent_state():
        return jsonify(live.state(page_sid()))

    @server.route(HERE, methods=['POST'])
    def _agent_here():
        live.here(page_sid())
        return ('', 204)

    @server.route(STOP, methods=['POST'])
    def _agent_stop():
        live.stopped = not live.stopped
        return jsonify(live.state(page_sid()))

    @server.route(CALL, methods=['POST'])
    def _agent_call():
        if request.remote_addr not in LOOPBACK or not secrets.compare_digest(
                request.headers.get('X-Gecko-Key', ''), live.key):
            return jsonify({'refused': 'Not allowed'}), 403
        body = request.get_json(silent=True) or {}
        g.gecko_sid = live.target                           # services that use the app's store see the target tab's
        try:
            result = live.call(body.get('method', ''), body.get('args'), body.get('kwargs'), body.get('agent'))
        except LiveRefused as exc:
            return jsonify({'refused': str(exc)}), 409
        except Exception as exc:                            # noqa: BLE001  the agent gets the error, the app goes on
            log.exception('Agent call %s failed', body.get('method'))
            return jsonify({'result': {'error': f'{type(exc).__name__}: {exc}'}})
        return server.response_class(json.dumps({'result': result}, default=_plain), mimetype='application/json')

    return live


def _plain(value):
    """numpy numbers, paths and the like in a result, as JSON."""
    item = getattr(value, 'item', None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, 'tolist', None)
    return tolist() if callable(tolist) else str(value)
