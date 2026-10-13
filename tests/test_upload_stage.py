import base64
import gzip

import pytest
from flask import Flask

from services import upload_stage as us


@pytest.fixture(autouse=True)
def clean():
    us._staged.clear()
    yield
    us._staged.clear()


def test_gzip_and_plain_bodies_decode_to_the_file_bytes():
    data = b'0.0\t1\n' * 5000
    assert us.decode_body(gzip.compress(data), 'gzip') == data
    assert us.decode_body(data, 'identity') == data
    with pytest.raises(us.UploadError):
        us.decode_body(b'not gzip', 'gzip')
    with pytest.raises(us.UploadError):
        us.decode_body(data, 'brotli')


def test_a_decompression_bomb_is_refused(monkeypatch):
    monkeypatch.setattr(us, 'MAX_FILE_BYTES', 1000)
    with pytest.raises(us.UploadError):
        us.decode_body(gzip.compress(b'\0' * 100_000), 'gzip')


def test_staged_bytes_are_read_by_token_and_released():
    token = us.stage('a.lcd', b'payload')
    contents = us.PREFIX + token
    assert us.is_token(contents) and us.read_contents(contents) == b'payload'
    us.release(contents)
    with pytest.raises(us.UploadError):
        us.read_contents(contents)


def test_classic_data_urls_still_work():
    url = 'data:text/csv;base64,' + base64.b64encode(b'x,y\n1,2\n').decode()
    assert us.read_contents(url) == b'x,y\n1,2\n'
    assert not us.is_token(url)


def test_old_uploads_expire_and_the_staging_area_is_capped(monkeypatch):
    token = us.stage('old.txt', b'1')
    name, data, _ = us._staged[token]
    us._staged[token] = (name, data, 0.0)
    us.stage('new.txt', b'2')
    assert token not in us._staged
    monkeypatch.setattr(us, 'MAX_STAGED_BYTES', 10)
    with pytest.raises(us.UploadError):
        us.stage('big.bin', b'x' * 11)


def test_the_upload_route_stages_the_file_and_returns_a_token():
    server = Flask(__name__)
    us.install(server)
    client = server.test_client()
    payload = b'Time\tSignal\n' * 1000
    response = client.post(us.ROUTE, data=gzip.compress(payload),
                           headers={'X-Gecko-Name': 'run%201.txt', 'X-Gecko-Encoding': 'gzip'})
    body = response.get_json()
    assert response.status_code == 200 and body['name'] == 'run 1.txt' and body['size'] == len(payload)
    assert us.read_contents(us.PREFIX + body['token']) == payload
    bad = client.post(us.ROUTE, data=b'junk', headers={'X-Gecko-Encoding': 'gzip'})
    assert bad.status_code == 400 and 'error' in bad.get_json()
