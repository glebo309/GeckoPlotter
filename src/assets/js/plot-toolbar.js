(function () {
    'use strict';
    function action(id, mode) {
        var dc = window.dash_clientside;
        if (id === 'plot-tool-overlay' || id === 'plot-tool-separate') {
            dc.set_props('pt-layout-mode', {value: id === 'plot-tool-overlay' ? 'overlay' : 'stacked'});
        } else if (id === 'plot-tool-integrate') {
            var next = mode === 'draw' ? 'navigate' : 'draw';
            if (window.GeckoPlotterManualIntegration) {
                window.GeckoPlotterManualIntegration.syncSelectedShape('main-plot', null);
                window.GeckoPlotterManualIntegration.syncDrawMode('main-plot', next);
            }
            dc.set_props('selected-peak-idx', {data: null});
            dc.set_props('baseline-mode', {data: next});
            dc.set_props('baseline-mode-indicator', {children: next === 'draw' ? 'Draw: on' : 'Draw: off'});
        }
    }
    function update() {
        var args = Array.prototype.slice.call(arguments);
        var mode = args[args.length - 1];
        var settings = args[args.length - 2] || {};
        var ctx = window.dash_clientside.callback_context;
        var trigger = ctx && ctx.triggered.length ? ctx.triggered[0].prop_id.split('.')[0] : '';
        if (trigger.indexOf('plot-tool-') === 0 && args.slice(0, -2).some(Boolean)) action(trigger, mode);
        var textTool = document.getElementById('plot-tool-edit-text');
        if (textTool) textTool.disabled = mode === 'deconvolve';
        ['overlay', 'separate', 'integrate'].forEach(function (tool) {
            var button = document.getElementById('plot-tool-' + tool);
            if (!button) return;
            var selected = tool === 'integrate' ? mode === 'draw' :
                (settings.layout_mode || 'overlay') === (tool === 'overlay' ? 'overlay' : 'stacked');
            button.classList.toggle('active', selected);
            button.setAttribute('aria-pressed', selected ? 'true' : 'false');
        });
        return '';
    }
    window.dash_clientside = Object.assign({}, window.dash_clientside, {plotToolbar: {action: action, update: update}});
})();
