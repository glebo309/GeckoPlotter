"""Bounded local diagnostics and optional PostHog delivery. Research contents never enter reports."""
import json
import os
import platform
import queue
import re
import threading
import traceback
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / 'diagnostics.json'
HOSTS = {'https://eu.i.posthog.com', 'https://us.i.posthog.com'}
FIELDS = {'control', 'action', 'operation', 'outcome', 'http_status', 'duration_ms', 'browser', 'error_type'}


def basename(value):
    return str(value).replace('\\', '/').rsplit('/', 1)[-1][:200]


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


class Reporter:
    def __init__(self, directory, config=None, sender=None, background=True):
        self.directory = Path(directory)
        self.config = config if config is not None else read_json(CONFIG)
        self.key = os.environ.get('GECKO_POSTHOG_KEY') or self.config.get('project_key', '')
        host = os.environ.get('GECKO_POSTHOG_HOST') or self.config.get('host', 'https://eu.i.posthog.com')
        self.host = host.rstrip('/') if host.rstrip('/') in HOSTS else ''
        self.preferences = read_json(self.directory / 'diagnostics-preferences.json')
        self.installation_id = self.preferences.get('installation_id') or str(uuid.uuid4())
        self.enabled = bool(self.preferences.get('enabled', False))
        self.pending = queue.Queue(maxsize=200)
        self.lock = threading.RLock()
        self.sender = sender or self._send
        self.last_error = False
        self.delivered = 0
        self._persist_preferences()
        if background and self.configured:
            threading.Thread(target=self._worker, daemon=True, name='gecko-diagnostics').start()

    @property
    def configured(self):
        return bool(self.host and re.fullmatch(r'phc_[A-Za-z0-9_-]+', self.key or ''))

    def _persist_preferences(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / 'diagnostics-preferences.json'
            path.write_text(json.dumps({'enabled': self.enabled, 'installation_id': self.installation_id}), encoding='utf-8')
        except OSError:
            pass

    def set_enabled(self, enabled):
        with self.lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                while not self.pending.empty():
                    try:
                        self.pending.get_nowait()
                    except queue.Empty:
                        break
            self._persist_preferences()

    def record(self, event, **properties):
        safe = {key: value for key, value in properties.items() if key in FIELDS and isinstance(value, (str, int, float, bool))}
        safe = {key: value[:160] if isinstance(value, str) else value for key, value in safe.items()}
        names = properties.get('filenames') or []
        safe['filenames'] = list(dict.fromkeys(basename(n) for n in names if isinstance(n, str)))[:30]
        sid = properties.get('session_id')
        if isinstance(sid, str) and re.fullmatch(r'[0-9a-f]{32}', sid):
            safe['$session_id'] = str(uuid.UUID(sid))
        return self._emit(event, safe)

    def exception(self, exc, **context):
        frames = [{'filename': basename(frame.filename), 'function': frame.name, 'lineno': frame.lineno,
                   'in_app': True} for frame in traceback.extract_tb(exc.__traceback__)[-20:]]
        properties = {'$exception_list': [{'type': type(exc).__name__, 'value': 'Operation failed',
                       'mechanism': {'handled': True, 'type': 'generic'}, 'stacktrace': {'frames': frames, 'type': 'raw'}}],
                      '$exception_level': 'error', 'filenames': [basename(n) for n in context.get('filenames', [])][:30]}
        sid = context.get('session_id')
        if isinstance(sid, str) and re.fullmatch(r'[0-9a-f]{32}', sid):
            properties['$session_id'] = str(uuid.UUID(sid))
        return self._emit('$exception', properties)

    def _emit(self, event, properties):
        from services.about import VERSION
        properties.update({'app_version': VERSION.get('sha', '')[:12], 'os': platform.system(),
                           'architecture': platform.machine(), 'python_version': platform.python_version(),
                           '$geoip_disable': True, '$process_person_profile': False})
        item = {'event': event, 'distinct_id': self.installation_id, 'properties': properties,
                'timestamp': datetime.now(timezone.utc).isoformat()}
        with self.lock:
            try:
                path = self.directory / 'diagnostics.jsonl'
                if path.exists() and path.stat().st_size > 1_000_000:
                    path.replace(self.directory / 'diagnostics.previous.jsonl')
                with path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(item, ensure_ascii=False) + '\n')
            except OSError:
                pass
            if self.enabled and self.configured:
                try:
                    self.pending.put_nowait(item)
                except queue.Full:
                    pass
        return item

    def flush(self):
        with self.lock:
            if not self.enabled or not self.configured:
                return
            batch = []
            while len(batch) < 20:
                try:
                    batch.append(self.pending.get_nowait())
                except queue.Empty:
                    break
        if not batch:
            return
        try:
            self.sender(self.host + '/batch/', {'api_key': self.key, 'batch': batch})
            self.last_error = False
            self.delivered += len(batch)
        except Exception:
            self.last_error = True

    @staticmethod
    def _send(url, payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status >= 300:
                raise OSError('Report was not accepted')

    def _worker(self):
        import time
        while True:
            time.sleep(3)
            self.flush()

    def status(self):
        if not self.configured:
            return 'Local reports only. PostHog is not connected yet.'
        if not self.enabled:
            return 'Sharing is off. Reports stay on this computer.'
        if self.last_error:
            return 'PostHog is offline or unreachable. A local report is available below.'
        return 'Sharing with PostHog (' + ('EU' if '.eu.' in self.host or '//eu.' in self.host else 'US') + ').'

    def log_text(self):
        try:
            return (self.directory / 'diagnostics.jsonl').read_text(encoding='utf-8')
        except OSError:
            return ''


_reporter = None

def reporter():
    global _reporter
    if _reporter is None:
        folder = Path(os.environ.get('GECKO_SETTINGS_DIR') or Path.home() / 'Documents' / 'GeckoPlotter')
        _reporter = Reporter(folder)
    return _reporter
