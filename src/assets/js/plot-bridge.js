// Dash owns the figure and event properties. plot-workspace draws the visible
// canvases; this bridge must never instantiate another Plotly graph.
(function () {
    'use strict';
    window.gecko_plot_bridge = {
        PlotBridge: function (props) {
            return window.React.createElement('div', {id: props.id, style: {display: 'none'}});
        }
    };
})();
