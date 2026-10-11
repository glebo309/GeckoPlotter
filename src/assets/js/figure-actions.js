(function () {
    'use strict';
    var sourcePlot = null;
    function run(action, gd) {
        gd = gd || sourcePlot;
        if (!gd || !window.Plotly) return;
        var dc = window.dash_clientside;
        var label = gd.data && gd.data[0] && gd.data[0].name || 'Plot';
        if (action === 'publication') {
            var figure = JSON.parse(JSON.stringify({data: gd.data, layout: gd.layout}, function (_, value) {
                return ArrayBuffer.isView(value) ? Array.from(value) : value;
            }));
            dc.set_props('figure-action-event', {data: {action: action, figure: figure, label: label, ts: Date.now()}});
        } else if (action === 'export') {
            var rect = gd.getBoundingClientRect();
            window.Plotly.downloadImage(gd, {format: 'svg', filename: 'GeckoPlotter',
                width: Math.round(rect.width), height: Math.round(rect.height)});
        }
        ['context-menu', 'ms-plot-context-menu', 'figure-context-menu'].forEach(function (id) {
            dc.set_props(id, {opened: false});
        });
        ['axis', 'legend', 'trace', 'title', 'label'].forEach(function (name) {
            var panel = document.getElementById(name + '-context-panel');
            if (panel) panel.style.display = 'none';
            dc.set_props(name + '-context-menu-close-store', {data: Date.now()});
        });
    }
    // Capture the actual figure before a specialized peak/MS/axis menu handles
    // the event. All menus and editors then act on this same figure.
    document.addEventListener('contextmenu', function (event) {
        var gd = event.target.closest && event.target.closest('.js-plotly-plot');
        if (gd) sourcePlot = gd;
    }, true);
    // Mantine closes and unmounts MenuItems during their React click handler.
    // Capture the action first, while its target and source figure still exist.
    document.addEventListener('click', function (event) {
        var button = event.target.closest && event.target.closest('[data-figure-action]');
        if (!button) return;
        var action = button.getAttribute('data-figure-action');
        if (action !== 'publication' && action !== 'export') return;
        event.preventDefault();
        event.stopPropagation();
        run(action);
    }, true);
    document.addEventListener('contextmenu', function (event) {
        // The integration handler prevents the browser menu for every plot
        // right-click. Specialized plot menus stop propagation themselves.
        if (!event.target.closest) return;
        var gd = event.target.closest('.js-plotly-plot');
        if (!gd) return;
        event.preventDefault();
        var dc = window.dash_clientside;
        dc.set_props('figure-context-anchor', {style: {position: 'fixed',
            left: Math.min(event.clientX, window.innerWidth - 240) + 'px',
            top: Math.min(event.clientY, window.innerHeight - 100) + 'px',
            width: '1px', height: '1px', zIndex: 4000, pointerEvents: 'none'}});
        dc.set_props('figure-context-menu', {opened: true});
    });
    window.GeckoFigureActions = {run: run};
    var dc = window.dash_clientside = window.dash_clientside || {};
    dc.geckoFigureActions = {
        dispatch: function (clicks) {
            var triggered = dc.callback_context && dc.callback_context.triggered;
            if (!clicks || !clicks.some(function (value) { return value > 0; }) || !triggered || !triggered.length) {
                return dc.no_update;
            }
            var prop = triggered[0].prop_id;
            var id = JSON.parse(prop.substring(0, prop.lastIndexOf('.')));
            if (id.action === 'publication' || id.action === 'export') run(id.action);
            return dc.no_update;
        }
    };
})();
