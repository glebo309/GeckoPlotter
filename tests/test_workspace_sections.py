"""Inspector controls have one visible, clearly scoped home."""
import json
import subprocess
import sys
import pytest


@pytest.fixture(scope='module')
def sections():
    # Other tests intentionally stub ingestion modules. Import the complete UI
    # in its own process so this check exercises the actual application layout.
    script = '''
import json
import app
from components.workspace_layout import walk
inspector = next(n for n in walk(app.app.layout) if getattr(n,'id',None)=='plot-tools-container')
result = {}
for section in inspector.children:
    if getattr(section,'className','') != 'inspector-section': continue
    nodes = list(walk(section.children[1]))
    result[section.children[0].children] = {
        'ids':[n.id for n in nodes if isinstance(getattr(n,'id',None),str)],
        'nested':any(getattr(n,'className','')=='inspector-section' for n in nodes),
        'texts':[n.children for n in nodes if isinstance(getattr(n,'children',None),str)]}
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_signal_controls_and_figure_defaults_have_separate_flat_sections(sections):
    assert {'Signal style','Figure style','Smoothing'} <= sections.keys()
    assert {'signal-inspector-select','signal-color','signal-width','signal-opacity'} <= set(sections['Signal style']['ids'])
    assert not {'pt-line-width','pt-trace-opacity','pt-smooth-window'} & set(sections['Signal style']['ids'])
    assert {'pt-line-width','pt-trace-opacity','pt-marker-size','pt-palette'} <= set(sections['Figure style']['ids'])
    assert {'pt-smooth-window','smooth-value'} <= set(sections['Smoothing']['ids'])
    assert not any(section['nested'] for section in sections.values())


def test_smoothing_explains_measurements_use_original_signal(sections):
    assert 'Display only. Peak areas use the original signal.' in sections['Smoothing']['texts']
