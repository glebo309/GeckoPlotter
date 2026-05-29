#!/usr/bin/env python3
"""Validate that every callback Input/Output/State references a prop the
target component actually exposes.

Catches the silent-failure class introduced when a control's prop name
changes (e.g. dcc.Checklist '.value' -> dmc.Switch '.checked') but a
callback still references the old prop. Run after any layout refactor.

Usage:  GP_DEBUG=1 PYTHONPATH=. python3 scripts/validate_callback_props.py
Exit 0 = all good, 1 = mismatches found.
"""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location('gpapp', 'app.py')
m = importlib.util.module_from_spec(spec)
sys.modules['gpapp'] = m
spec.loader.exec_module(m)
app = m.app

# 1. Map every id'd component in the layout to its valid prop names.
id_props = {}        # id -> set(available_properties)
id_kind = {}         # id -> component class name (for reporting)

def walk(node):
    cid = getattr(node, 'id', None)
    if cid is not None and not isinstance(cid, dict):  # skip pattern-matching ids
        props = getattr(node, 'available_properties', None)
        if props:
            id_props[cid] = set(props)
            id_kind[cid] = type(node).__name__
    children = getattr(node, 'children', None)
    if children is None:
        return
    for c in (children if isinstance(children, (list, tuple)) else [children]):
        if hasattr(c, 'children') or getattr(c, 'id', None) is not None:
            walk(c)

walk(app.layout)

# 2. Parse every callback's dependencies.
def parse_output_spec(spec_str):
    s = spec_str.strip()
    parts = s[2:-2].split('...') if s.startswith('..') and s.endswith('..') else [s]
    out = []
    for p in parts:
        p = p.split('@')[0]
        if not p:
            continue
        cid, prop = p.rsplit('.', 1)
        out.append((cid, prop))
    return out

problems = []
checked = 0
for cb in app._callback_list:
    deps = []
    for kind in ('inputs', 'state'):
        for d in cb.get(kind, []):
            deps.append((d['id'], d['property'], kind))
    for cid, prop in parse_output_spec(cb['output']):
        deps.append((cid, prop, 'output'))
    for cid, prop, kind in deps:
        if isinstance(cid, dict):
            continue
        if cid not in id_props:
            continue  # component built dynamically / not in initial layout
        checked += 1
        if prop not in id_props[cid]:
            problems.append(
                f"  {kind:6} {cid}.{prop}  -- {id_kind[cid]} has no '{prop}' "
                f"(valid e.g.: {sorted(p for p in id_props[cid] if not p.startswith('_'))[:8]})"
            )

print(f"components with ids in layout: {len(id_props)}")
print(f"callback dependencies checked against layout: {checked}")
if problems:
    print(f"\nFAIL: {len(problems)} prop mismatch(es):")
    for p in problems:
        print(p)
    sys.exit(1)
print("PASS: all callback props match their components")
