import plotly.express as px

# Valid color palettes for Plotly
_PALETTES = {
    'viridis': px.colors.sequential.Viridis,
    'plasma': px.colors.sequential.Plasma,
    'inferno': px.colors.sequential.Inferno,
    'magma': px.colors.sequential.Magma,
    'cividis': px.colors.sequential.Cividis,
    'rainbow': px.colors.sequential.Rainbow,
    'ylgnbu': px.colors.sequential.YlGnBu,
    'hydrophobicity': [  # custom hydrophobicity scale
        '#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6',
        '#4292c6', '#2171b5', '#08519c', '#08306b'
    ]
}

def list_palettes() -> list[str]:
    return list(_PALETTES.keys())

def get_palette(name: str) -> list[str]:
    key = name.lower()
    if key not in _PALETTES:
        raise KeyError(f"Palette '{name}' not found. Available: {', '.join(list_palettes())}")
    return _PALETTES[key]

def apply_palette(fig, palette: str, attr: str = 'color'):
    colors = get_palette(palette)
    for i, trace in enumerate(fig.data):
        color = colors[i % len(colors)]
        if hasattr(trace, 'marker') and attr.startswith('marker'):
            trace.marker.color = color
        elif hasattr(trace, 'line') and attr.startswith('line'):
            trace.line.color = color
        else:
            if hasattr(trace, 'marker'):
                trace.marker.color = color
    return fig
