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


def test_largest_values_names_the_stored_values_that_made_a_request_big():
    body = ('{"output":"a.b","inputs":[{"id":"x","property":"data","value":1}],"state":['
            '{"id":"main-plot","property":"figure","value":{"data":"' + 'y' * 300_000 + '"}},'
            '{"id":"loaded-files","property":"data","value":[1,2]}]}').encode()
    text = rt.largest_values(body)
    assert 'main-plot.figure' in text and 'loaded-files' not in text and 'KB' in text
    assert rt.largest_values(b'not json') == ''
    assert rt.largest_values(b'{"inputs":[],"state":[]}') == ''


def test_a_multi_output_callback_still_gets_a_name():
    outputs = '...'.join(f'component-{i}.children' for i in range(40))
    label = rt.output_label(('{"output":"..' + outputs + '..","inputs":[]}').encode())
    assert label.startswith('component-0.children') and len(label) <= 90
