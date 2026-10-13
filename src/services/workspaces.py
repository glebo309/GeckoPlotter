"""One workspace per browser.

The app used to keep a single global workspace, so everyone who opened a shared copy saw, changed and wiped everyone
else's files. Now every browser gets a random id in a cookie (``gecko_sid``), and ``WorkspaceProxy`` -- which stands in
for the old global store -- hands each request the store of its own browser. Code written against the global keeps
working unchanged; code that kept a *service* of the store from registration time uses ``scoped`` instead.

Workspaces live in memory. One that was idle for hours, or the oldest when too many exist, is dropped (its autosave
stays on disk, in a folder of its own).
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

COOKIE = 'gecko_sid'
COOKIE_MAX_AGE = 365 * 24 * 3600
_VALID = re.compile(r'^[0-9a-f]{32}$')


def new_session_id() -> str:
    return uuid.uuid4().hex


def valid_session_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_VALID.match(value))


class WorkspaceRegistry:
    """The stores of all browsers currently known, plus one default store for code running outside any request."""

    def __init__(self, factory: Callable[[], Any], *, max_idle_seconds: float = 8 * 3600, max_workspaces: int = 12,
                 session_id: Optional[Callable[[], Optional[str]]] = None):
        self._factory = factory
        self._stores: Dict[str, Any] = {}
        self._seen: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._default = None
        self.max_idle_seconds = max_idle_seconds
        self.max_workspaces = max_workspaces
        self._session_id = session_id or current_session_id
        self.proxy = WorkspaceProxy(self)

    def default(self):
        with self._lock:
            if self._default is None:
                self._default = self._factory()
            return self._default

    def current(self):
        sid = self._session_id()
        return self.for_session(sid) if sid else self.default()

    def for_session(self, sid: str):
        now = time.time()
        with self._lock:
            store = self._stores.get(sid)
            if store is None:
                self._evict(now)
                store = self._stores[sid] = self._factory()
            self._seen[sid] = now
            return store

    def _evict(self, now: float) -> None:
        for sid in [s for s, seen in self._seen.items() if now - seen > self.max_idle_seconds]:
            self._stores.pop(sid, None)
            self._seen.pop(sid, None)
        while len(self._stores) >= self.max_workspaces:
            oldest = min(self._seen, key=self._seen.get)
            self._stores.pop(oldest, None)
            self._seen.pop(oldest, None)

    def count(self) -> int:
        with self._lock:
            return len(self._stores)


class WorkspaceProxy:
    """Looks like one workspace store; every attribute access goes to the store of the current browser."""

    def __init__(self, registry: WorkspaceRegistry):
        object.__setattr__(self, '_registry', registry)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, '_registry').current(), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(object.__getattribute__(self, '_registry').current(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(object.__getattribute__(self, '_registry').current(), name)

    def __repr__(self) -> str:
        return f'<WorkspaceProxy of {object.__getattribute__(self, "_registry").count()} workspaces>'


class ScopedProxy:
    """A helper object (a service, a cache) that exists once per workspace instead of once per process.

    ``factory`` is called the first time the current workspace needs it. A store without ``scoped`` (a test double)
    keeps a single shared object, which is the behaviour before workspaces existed.
    """

    def __init__(self, data_manager, key: str, factory: Callable[[], Any]):
        object.__setattr__(self, '_dm', data_manager)
        object.__setattr__(self, '_key', key)
        object.__setattr__(self, '_factory', factory)
        object.__setattr__(self, '_fallback', None)

    def _target(self):
        dm = object.__getattribute__(self, '_dm')
        key, factory = object.__getattribute__(self, '_key'), object.__getattribute__(self, '_factory')
        scoped = getattr(dm, 'scoped', None)
        if callable(scoped):
            return scoped(key, factory)
        if object.__getattribute__(self, '_fallback') is None:
            object.__setattr__(self, '_fallback', factory())
        return object.__getattribute__(self, '_fallback')

    def __getattr__(self, name: str):
        return getattr(self._target(), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._target(), name, value)

    # Dunder methods are looked up on the type, so the container protocol is forwarded explicitly.
    def __getitem__(self, key): return self._target()[key]
    def __setitem__(self, key, value): self._target()[key] = value
    def __delitem__(self, key): del self._target()[key]
    def __contains__(self, key): return key in self._target()
    def __iter__(self): return iter(self._target())
    def __len__(self): return len(self._target())
    def __bool__(self): return bool(self._target())


def scoped(data_manager, key: str, factory: Callable[[], Any]) -> ScopedProxy:
    return ScopedProxy(data_manager, key, factory)


def service_of(data_manager, name: str) -> ScopedProxy:
    """The named service (``'peak_service'``...) of whichever workspace is current, looked up at every use."""
    class _Service:
        def __getattr__(self, attribute):
            return getattr(getattr(data_manager, name), attribute)
    return _Service()


# -- the browser's id ----------------------------------------------------------------------------------------------

def current_session_id() -> Optional[str]:
    try:
        from flask import g, has_request_context
    except ImportError:                                  # pragma: no cover
        return None
    if not has_request_context():
        return None
    return getattr(g, 'gecko_sid', None)


def current_session_key() -> Optional[str]:
    """A short folder-safe form of the id, for per-browser autosave folders."""
    sid = current_session_id()
    return sid[:16] if sid else None


def install(server) -> None:
    """Give every browser an id (cookie) before any other request code runs."""
    from flask import g, request

    @server.before_request
    def _identify():
        sid = request.cookies.get(COOKIE)
        g.gecko_new_sid = None
        if not valid_session_id(sid):
            sid = g.gecko_new_sid = new_session_id()
        g.gecko_sid = sid

    @server.after_request
    def _remember(response):
        if getattr(g, 'gecko_new_sid', None):
            response.set_cookie(COOKIE, g.gecko_new_sid, max_age=COOKIE_MAX_AGE, httponly=True, samesite='Lax')
        return response
