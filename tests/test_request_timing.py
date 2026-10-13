import logging
import time

from flask import Flask

from services import request_timing as rt


def test_output_label_is_read_from_the_start_of_the_body():
    body = b'{"output":"..file-tree.children...loaded-files.data..","inputs":[{"value":"' + b'x' * 5_000_000 + b'"}]}'
    assert rt.output_label(body) == 'file-tree.children...loaded-files.data'
    assert rt.output_label(b'{"inputs":[{"value":"' + b'x' * 5_000_000 + b'"}],"output":"a.b"}') == 'a.b'
    assert rt.output_label(b'{"inputs":[]}') == '?'


def test_only_slow_callbacks_are_logged_with_their_sizes(caplog):
    server = Flask(__name__)

    @server.route(rt.CALLBACK_PATH, methods=['POST'])
    def callback():
        time.sleep(0.05)
        return {'response': {}}

    @server.route('/asset')
    def asset():
        time.sleep(0.05)
        return 'x'

    rt.install(server, threshold_ms=20)
    client = server.test_client()
    with caplog.at_level(logging.WARNING, logger='geckoplotter.timing'):
        client.get('/asset')
        client.post(rt.CALLBACK_PATH, data=b'{"output":"main-plot.figure","inputs":[]}')
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1 and 'main-plot.figure' in messages[0] and 'ms' in messages[0]

    caplog.clear()
    server2 = Flask('quick')
    server2.add_url_rule(rt.CALLBACK_PATH, 'cb', lambda: 'ok', methods=['POST'])
    rt.install(server2, threshold_ms=5000)
    with caplog.at_level(logging.WARNING, logger='geckoplotter.timing'):
        server2.test_client().post(rt.CALLBACK_PATH, data=b'{}')
    assert not caplog.records
