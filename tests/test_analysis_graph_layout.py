"""Analysis graphs consume their dock's height, with controls outside the canvas."""
import json
import subprocess
import sys


def test_mass_panels_have_flexible_direct_graphs_and_controls_above_them():
    script = '''
import json
import app
from components.workspace_layout import walk
result = {}
for node in walk(app.app.layout):
    if type(node).__name__ != 'TabsPanel' or getattr(node, 'value', '') not in ('ms-scan','ms-eic','ms-peak-mass'): continue
    content = node.children[0]
    result[node.value] = {
        'panel_style':node.style,
        'class':content.className,
        'style':content.style,
        'children':[{'id':getattr(n,'id',None),'style':getattr(n,'style',{}),
                     'responsive':getattr(n,'responsive',None)} for n in content.children],
    }
print(json.dumps(result))
'''
    run = subprocess.run([sys.executable, '-B', '-c', script], text=True, capture_output=True, check=True)
    panels = json.loads(run.stdout)
    for panel, graph_id in [('ms-scan','ms-spectrum-graph'), ('ms-eic','eic-graph'), ('ms-peak-mass','peak-mass-graph')]:
        item = panels[panel]
        assert item['panel_style']['minHeight'] == 0
        assert 'analysis-graph-content' in item['class']
        assert item['style']['display'] == 'flex'
        assert item['style']['flexDirection'] == 'column'
        graph = next(n for n in item['children'] if n['id'] == graph_id)
        assert graph['style']['flex'] == '1 0 140px'
        assert graph['style']['height'] == '0px'
        assert graph['style']['minHeight'] == '140px'
        assert graph['responsive'] is True
    children = [n['id'] for n in panels['ms-peak-mass']['children']]
    assert children.index('peak-mass-selector') < children.index('peak-mass-graph') < children.index('peak-mass-info')
