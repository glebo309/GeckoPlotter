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
HELLO, TURN = '/_gecko/agent/hello', '/_gecko/agent/turn'
LINGER = 20.0           # an agent without turn hooks counts as working this long after its last call
TURN_MAX = 30 * 60.0    # a turn whose end never arrived (agent killed) is over after this
LOOPBACK = {'127.0.0.1', '::1', '::ffff:127.0.0.1'}

# The Workspace methods an agent may call: every tool of gecko_mcp.py, nothing else.
METHODS = {'open', 'remove_samples', 'samples', 'detect_peaks', 'integrate', 'peaks', 'rename_peak', 'remove_peak', 'calibrate', 'list_calibrations',
           'remove_calibration', 'add_uv_channel', 'compare_wavelengths', 'uv_spectrum', 'add_eic_channel', 'eic', 'mass_spectrum',
           'figure', 'export_results', 'save', 'deconvolve'}
# Calls that only read: the page does not redraw after them.
READS = {'samples', 'peaks', 'list_calibrations', 'uv_spectrum', 'mass_spectrum', 'figure', 'export_results', 'save'}

# What the status bar says while the agent works ("Claude Code: integrating ...").
_DOING = {'open': 'opening {0}', 'remove_samples': 'removing samples', 'samples': 'reading the samples', 'detect_peaks': 'detecting peaks',
          'integrate': 'integrating {0}-{1} min', 'peaks': 'reading the peak table', 'rename_peak': 'renaming {1}',
          'remove_peak': 'removing {1}', 'deconvolve': 'deconvolving {0}-{1} min',
          'calibrate': 'calibrating {0}', 'compare_wavelengths': 'comparing wavelengths',
          'list_calibrations': 'reading the calibrations',
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
        self.view: Optional[dict] = None         # what the page shows after the last call (services/live_focus)
        self._workspaces: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._connections: Dict[int, tuple[str, float]] = {}
        self._parents: Dict[int, int] = {}                 # MCP process -> its agent's process (heartbeat)
        self._last_call: Dict[int, float] = {}            # MCP process -> end of its last call
        self._turns: Dict[int, float] = {}                # MCP process -> start of its agent's turn (turn hooks)
        self._hooked: set = set()                          # MCP processes whose agent sends turn hooks
        self._connections_lock = threading.Lock()          # heartbeats must not wait for a tool call

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
        with self._connections_lock:
            cutoff = time.monotonic() - 30
            self._connections = {pid: entry for pid, entry in self._connections.items() if entry[1] > cutoff}
            connected = list(dict.fromkeys(label for label, _seen in self._connections.values()))
            working = self.busy or self._working(time.monotonic())
        return {'version': self.version, 'busy': self.busy, 'agent': self.agent, 'doing': self.doing,
                'stopped': self.stopped, 'here': bool(sid and sid == self.target), 'done_at': self.done_at,
                'connected': connected, 'working': working}

    def _working(self, now: float) -> bool:
        """An agent is at work from the user's prompt to its answer: between its turn hooks (Claude Code), or
        without hooks until LINGER seconds after its last call."""
        for pid in self._connections:
            started = self._turns.get(pid)
            if started is not None and now - started < TURN_MAX:
                return True
            if pid not in self._hooked and now - self._last_call.get(pid, -1e9) < LINGER:
                return True
        return False

    def hello(self, pid: int, label: str, parent: Optional[int] = None) -> None:
        with self._connections_lock:
            self._connections[pid] = (label, time.monotonic())
            if parent:
                self._parents[pid] = parent

    def turn(self, ancestors, started: bool) -> None:
        """A turn hook of an agent (gecko_hook.py): the user sent a prompt, or the agent answered. ``ancestors`` are
        the hook's parent processes; the agent is among them, and so is the parent of its GeckoPlotter MCP server.
        A session without GeckoPlotter has no such server and is ignored."""
        ancestors = {a for a in ancestors if type(a) is int and a > 1}
        with self._connections_lock:
            for pid, parent in self._parents.items():
                if parent in ancestors:
                    self._hooked.add(pid)
                    if started:
                        self._turns[pid] = time.monotonic()
                    else:
                        self._turns.pop(pid, None)

    # -- a call ----------------------------------------------------------------------------------------------------

    def workspace(self, sid: str):
        from gecko_api import Workspace
        store = self.registry.for_session(sid)
        workspace = self._workspaces.get(sid)
        if workspace is None or workspace.store is not store:
            workspace = self._workspaces[sid] = Workspace(store)
            workspace.live = True                          # saving leaves the user's screen as it is
        return workspace

    def call(self, method: str, args=None, kwargs=None, agent: Optional[dict] = None) -> Any:
        """Run one Workspace method on the target tab's workspace. Raises LiveRefused when live mode cannot take it."""
        from gecko_api import GeckoError
        if method not in METHODS:
            raise LiveRefused(f'Unknown call {method!r}')
        if self.stopped:
            raise LiveRefused('Stopped in GeckoPlotter: click Stop again in the status bar to let the agent work.')
        if not self.target:
            raise LiveRefused(f'GeckoPlotter runs but no window is open: ask the user to open http://127.0.0.1:{self.port} '
                              'in the browser.')
        with self._lock:                                    # one agent call at a time
            workspace = self.workspace(self.target)
            agent = dict(agent or {})
            caller = agent.pop('pid', None)
            self.agent = agent.pop('client_label', None) or self.agent or 'Agent'
            workspace.agent = agent or workspace.agent
            self.doing, self.busy = describe(method, args), True
            view = None
            try:
                result = getattr(workspace, method)(*(args or []), **(kwargs or {}))
                from services.live_focus import focus
                view = focus(workspace, method, args, kwargs, result)
            except GeckoError as exc:
                result = {'error': str(exc)}
            finally:
                self.busy, self.done_at = False, time.time()
                if isinstance(caller, int):
                    with self._connections_lock:
                        self._last_call[caller] = time.monotonic()
                if method not in READS or view:
                    self.version += 1
                    self.view = dict(view, version=self.version) if view else None
        return result


CURRENT: Optional[LiveAgent] = None                   # this app's live state (install)


class LiveRefused(Exception):
    pass


def install(server, registry, port: int, folder: Optional[Path] = None) -> LiveAgent:
    """Answer agent calls and the pages' status questions; write this app's live file."""
    import atexit
    from flask import g, jsonify, request
    from services.workspaces import COOKIE, valid_session_id

    global CURRENT
    live = CURRENT = LiveAgent(registry, port, folder)
    live.write_file()
    atexit.register(live.remove_file)

    def page_sid():
        sid = request.cookies.get(COOKIE)
        return sid if valid_session_id(sid) else None

    def allowed():
        return request.remote_addr in LOOPBACK and secrets.compare_digest(
            request.headers.get('X-Gecko-Key', ''), live.key)

    @server.route(HELLO, methods=['POST'])
    def _agent_hello():
        if not allowed():
            return jsonify({'refused': 'Not allowed'}), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({'refused': 'Expected process id and agent label'}), 400
        pid, label = body.get('id'), body.get('agent', 'Agent')
        if type(pid) is not int or pid <= 0 or not isinstance(label, str):
            return jsonify({'refused': 'Expected process id and agent label'}), 400
        parent = body.get('parent')
        live.hello(pid, label.strip() or 'Agent', parent if type(parent) is int else None)
        return ('', 204)

    @server.route(TURN, methods=['POST'])
    def _agent_turn():
        if not allowed():
            return jsonify({'refused': 'Not allowed'}), 403
        body = request.get_json(silent=True) or {}
        ancestors = body.get('ancestors')
        if not isinstance(ancestors, list) or body.get('state') not in ('start', 'end'):
            return jsonify({'refused': 'Expected ancestors and state start or end'}), 400
        live.turn(ancestors, body['state'] == 'start')
        return ('', 204)

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
        if not allowed():
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
