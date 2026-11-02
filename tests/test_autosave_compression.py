"""Autosave trades a little disk space for lower CPU cost, without changing saved contents."""
import io
import json
import zipfile
from services import session_service as ss


def test_autosave_uses_fast_lossless_compression_including_instrument_methods(monkeypatch):
    levels = []
    real = zipfile._get_compressor
    def compressor(kind, compresslevel=None):
        levels.append(compresslevel)
        return real(kind, compresslevel)
    monkeypatch.setattr(zipfile, '_get_compressor', compressor)
    state = {'analysis_history': [{'changes': {'peaks': {'after': [1., 2., 3.]}}}]}
    raw = b'instrument method\x00\xff' * 1000
    parts = ss._Parts(manifest={'raw_cache': True}, state=state, client_state={'active-file': 'sample'},
                      tables={'tables/edited.csv': b'x,y\n1,2\n'}, raw={'methods/source.lcd': raw})
    out = io.BytesIO()
    ss._write_archive(out, parts)
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as archive:
        assert json.loads(archive.read(ss.STATE_NAME)) == state
        assert archive.read('methods/source.lcd') == raw
        assert archive.read('tables/edited.csv') == b'x,y\n1,2\n'
        assert archive.testzip() is None
    assert levels and set(levels) == {1}


def test_manual_project_saves_retain_their_compact_compression(monkeypatch):
    levels = []
    real = zipfile._get_compressor
    monkeypatch.setattr(zipfile, '_get_compressor', lambda kind, compresslevel=None:
                        levels.append(compresslevel) or real(kind, compresslevel))
    parts = ss._Parts(manifest={'raw_cache': False}, state={}, client_state={}, tables={}, raw={'source.txt': b'data'})
    ss._write_archive(io.BytesIO(), parts)
    assert levels == [6, 6, 6, 4]
