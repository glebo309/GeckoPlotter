"""A GeckoPlotter started from the icon stops on its own once no page is open; sleep does not count."""
import time

from flask import Flask

from services import idle_exit


def test_pages_report_they_are_open_and_sleep_does_not_count():
    server = Flask(__name__)
    idle_exit.install(server, exit_after=0)                   # 0: route only, no watcher
    idle_exit.tick(30, 5)
    assert idle_exit.idle_seconds() == 7.5                    # a 30 s gap between 5 s checks is sleep: capped
    assert server.test_client().post(idle_exit.ROUTE).status_code == 204
    assert idle_exit.idle_seconds() == 0


def test_the_app_stops_after_the_last_page_is_gone():
    stopped = []
    server = Flask('watched')
    idle_exit.install(server, exit_after=0.3, step=0.05, exit_fn=lambda: stopped.append(True))
    deadline = time.time() + 5
    while not stopped and time.time() < deadline:
        time.sleep(0.05)
    assert stopped


def test_nothing_is_stopped_without_the_setting(monkeypatch):
    import threading
    monkeypatch.delenv('GECKO_EXIT_WHEN_IDLE', raising=False)
    before = sum(t.name == 'gecko-idle-exit' for t in threading.enumerate())
    server = Flask('plain')
    idle_exit.install(server)
    assert sum(t.name == 'gecko-idle-exit' for t in threading.enumerate()) == before
    assert server.test_client().get(idle_exit.ROUTE).status_code == 204
