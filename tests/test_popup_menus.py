"""The three right-click menus are plain HTML, never Mantine's Menu family (which slows every Dash update)."""
import subprocess
import sys


def test_layout_has_no_dash_children_update_components_and_menus_start_hidden():
    script = '''
import json
import app
from components.workspace_layout import walk
names = sorted({type(n).__name__ for n in walk(app.app.layout)})
menus = {n.id: n for n in walk(app.app.layout) if getattr(n, 'id', None) in
         ('context-menu', 'ms-plot-context-menu', 'figure-context-menu')}
print(json.dumps({'names': names, 'hidden': {k: v.hidden for k, v in menus.items()},
                  'items': {k: [c.id if isinstance(c.id, str) else c.id['action'] for c in v.children
                                if getattr(c, 'id', None)] for k, v in menus.items()}}))
'''
    import json
    out = json.loads(subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True).stdout)
    assert not {'Menu', 'MenuDropdown', 'MenuItem', 'MenuTarget', 'MenuDivider', 'Tooltip'} & set(out['names'])
    assert out['hidden'] == {'context-menu': True, 'ms-plot-context-menu': True, 'figure-context-menu': True}
    assert out['items']['context-menu'] == ['ctx-delete-item', 'ctx-rename-item', 'ctx-zero-baseline-item',
                                            'ctx-deconvolve-item', 'ctx-show-mass-item', 'ctx-integrate-item']
    assert out['items']['figure-context-menu'] == ['publication', 'export']
