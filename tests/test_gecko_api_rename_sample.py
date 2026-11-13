import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from gecko_api import Workspace, GeckoError
from services.live_agent import METHODS, READS
from test_gecko_api_peaks import _sample
import numpy as np

@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv('GECKO_SETTINGS_DIR', str(tmp_path))
    w = Workspace()
    _sample(w, '11132026_K1_20h_001', np.linspace(0, 1, 10), np.arange(10))
    _sample(w, 'other', np.linspace(0, 1, 10), np.arange(10))
    return w

def test_rename_preserves_source_identity_and_updates_saved_project(ws, tmp_path):
    bundle = ws._sample('11132026_K1_20h_001')
    original = bundle.primary.original_filename
    identifier = bundle.bundle_id
    ws.rename_sample(bundle.name, ' K1_20h ')
    assert ws._sample('K1_20h').bundle_id == identifier
    assert bundle.primary.original_filename == original
    assert bundle.primary.metadata['sample_name'] == 'K1_20h'
    assert ws.store.analysis_history
    saved = ws.save(str(tmp_path / 'renamed.gecko'))
    restored = Workspace()
    restored.open(str(tmp_path / 'renamed.gecko'))
    assert restored._sample('K1_20h').bundle_id == identifier

@pytest.mark.parametrize('name', ['', '   ', 'other'])
def test_rejects_invalid_or_duplicate_names_without_mutation(ws, name):
    before = ws.samples()
    with pytest.raises(GeckoError):
        ws.rename_sample('11132026_K1_20h_001', name)
    assert ws.samples() == before

def test_live_bridge_allows_rename_and_redraws():
    assert 'rename_sample' in METHODS
    assert 'rename_sample' not in READS

def test_mcp_exposes_sample_rename(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import gecko_mcp
    calls = []
    monkeypatch.setattr(gecko_mcp, '_run', lambda *a, **k: calls.append((a,k)))
    gecko_mcp.rename_sample('old', 'new')
    assert calls[0][0] == ('rename_sample', 'old', 'new')
