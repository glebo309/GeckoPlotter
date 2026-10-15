"""Sample names in the order a chemist expects: numbers by value (0.31 mM, 0.625 mM, 1.25 mM ... 10 mM), not as text
('10mM' before '2.5mM'). Shared by the file tree and the plot, so the subplots stack in the tree's order."""
import re

_PARTS = re.compile(r'(\d+(?:\.\d+)?)')


def natural_key(name):
    key = []
    for i, part in enumerate(_PARTS.split(str(name or '').lower())):
        if i % 2:
            key.append((0, float(part), ''))
        elif part:
            key.append((1, 0.0, part))
    return key
