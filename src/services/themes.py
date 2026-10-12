"""Figure themes registered as Plotly templates, plus the PDA heatmap colour maps."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from services.crameri_colors import SEQUENTIAL

# name -> (label, paper, plot area, text/axes, grid)
THEMES = {  # kept for saved settings; only the default is offered in the UI
    'gecko_clean': ('Clean', '#ffffff', '#ffffff', '#1f2328', '#e6e8eb'),
    'gecko_paper': ('Paper', '#faf7f0', '#faf7f0', '#2b2926', '#e5dfd2'),
    'gecko_soft': ('Soft grey', '#ffffff', '#f3f5f7', '#2a3036', '#dde2e7'),
    'gecko_slate': ('Slate', '#1b222a', '#1b222a', '#e6ebf0', '#34404c'),
    'gecko_night': ('Night', '#0f1318', '#0f1318', '#dfe5ea', '#27303a'),
}
DARK_THEMES = {'gecko_slate', 'gecko_night', 'plotly_dark'}
DEFAULT_THEME = 'gecko_clean'


def register_themes():
    for name, (_, paper, plot, ink, grid) in THEMES.items():
        axis = dict(gridcolor=grid, linecolor=ink, zerolinecolor=grid, tickcolor=ink)
        pio.templates[name] = go.layout.Template(layout=go.Layout(
            paper_bgcolor=paper, plot_bgcolor=plot,
            font=dict(family='Arial, sans-serif', color=ink), xaxis=axis, yaxis=axis))


def theme_options():
    return [{'label': label, 'value': name} for name, (label, *_) in THEMES.items()]


# Heatmap colour maps: Plotly's own, plus two Crameri maps. Viridis is Plotly's usual default.
HEATMAP_COLORMAPS = ['Viridis', 'Plasma', 'Inferno', 'Magma', 'Cividis', 'Turbo', 'Greys', 'Batlow', 'Oslo']
DEFAULT_COLORMAP = 'Viridis'


def colorscale(name):
    """Colorscale for a heatmap colour map name (a Plotly name, or a Crameri list)."""
    if name in ('Batlow', 'Oslo'):
        colors = SEQUENTIAL[name.lower()]
        last = len(colors) - 1
        return [[i / last, c] for i, c in enumerate(colors)]
    return name if name in HEATMAP_COLORMAPS else DEFAULT_COLORMAP


register_themes()
