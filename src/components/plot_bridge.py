"""Keep Dash figure/event properties without drawing a second, hidden plot."""
from pathlib import Path

from dash.development.base_component import Component


class PlotBridge(Component):
    _namespace = 'gecko_plot_bridge'
    _type = 'PlotBridge'
    _children_props = []
    _base_nodes = ['children']

    def __init__(self, id, figure=None, clickData=None, relayoutData=None, style=None,
                 responsive=None, config=None):
        self._prop_names = ['id', 'figure', 'clickData', 'relayoutData', 'style', 'responsive', 'config']
        self._valid_wildcard_attributes = []
        self.available_properties = self._prop_names
        self.available_wildcard_properties = []
        super().__init__(id=id, figure=figure, clickData=clickData, relayoutData=relayoutData,
                         style=style, responsive=responsive, config=config)


def install(app):
    """Load the bundled Plotly runtime before the retained canvases need it.

    The removed Graph used to trigger an asynchronous runtime download. Loading
    it explicitly also lets a workspace with no other Graph components render.
    """
    import plotly
    from flask import send_file

    path = Path(plotly.__file__).parent / 'package_data' / 'plotly.min.js'
    app.config.external_scripts.append('/_gecko/plotly.js')

    @app.server.get('/_gecko/plotly.js')
    def gecko_plotly_runtime():
        return send_file(path, conditional=True)
