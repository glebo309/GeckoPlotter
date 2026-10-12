(function () {
    'use strict';
    var sourcePlot = null;
    function activePlot() {
        var graphs = document.querySelectorAll('.js-plotly-plot');
        // Workspace graphs precede auxiliary result plots. Never select the hidden Dash bridge.
        var visible = Array.from(graphs).filter(function(gd) {
            var rect = gd.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && gd.data;
        });
        return visible.find(function(gd) { return gd.dataset && (gd.dataset.publicationPlot || gd.dataset.workspacePlot); }) || visible[0];
    }
    function snapshot(gd) {
        var figure = JSON.parse(JSON.stringify({data:gd.data, layout:gd.layout || {}}, function(_, value) {
            return ArrayBuffer.isView(value) ? Array.from(value) : value;
        }));
        // Plotly's resolved ranges are authoritative after zoom/pan/autoscale.
        Object.keys(gd._fullLayout || {}).forEach(function(key) {
            if (!/^[xy]axis\d*$/.test(key)) return;
            var axis = gd._fullLayout[key];
            if (axis.range) figure.layout[key] = Object.assign({}, figure.layout[key], {range:axis.range.slice(), autorange:false});
        });
        return figure;
    }
    function exportRequest(rawClicks, pubClicks, format, preset, width, height, dpi, pubFormat, pubWidth, pubHeight, pubDpi) {
        var dc = window.dash_clientside;
        var triggers = dc.callback_context && dc.callback_context.triggered;
        if (!triggers || !triggers.length || (!rawClicks && !pubClicks)) return dc.no_update;
        var gd = activePlot();
        if (!gd) return {error:'No displayed figure to export.', ts:Date.now()};
        var rect = gd.getBoundingClientRect(), layout = gd._fullLayout || {};
        var rw = layout.width || rect.width, rh = layout.height || rect.height;
        var publication = triggers[0].prop_id.indexOf('pub-export-btn.') === 0;
        if (publication) {format=pubFormat; width=pubWidth; height=pubHeight; dpi=pubDpi;}
        else if (preset === 'single-col') {width=84;height=63;}
        else if (preset === 'full-width') {width=174;height=104;}
        else if (preset === 'presentation') {width=254;height=143;}
        else if (preset === 'current' || !preset) {
            var meta = (gd.layout || {}).meta || {};
            width=meta.gecko_width_mm || 174;
            height=meta.gecko_height_mm || width * rh / rw;
        }
        return {figure:snapshot(gd), format:format, width_mm:width, height_mm:height, dpi:dpi,
            render_width:rw, label:gd.data[0] && gd.data[0].name || 'figure', origin:publication ? 'publication':'toolbox', ts:Date.now()};
    }
    function run(action, gd) {
        gd = gd || sourcePlot;
        if (!gd || !window.Plotly) return;
        var dc = window.dash_clientside;
        var label = gd.data && gd.data[0] && gd.data[0].name || 'Plot';
        if (action === 'publication') {
            var figure = snapshot(gd);
            dc.set_props('figure-action-event', {data: {action: action, figure: figure, label: label, ts: Date.now()}});
        } else if (action === 'export') {
            var rect = gd.getBoundingClientRect();
            var layout = gd._fullLayout || {}, meta = (gd.layout || {}).meta || {};
            var width = meta.gecko_width_mm || 174;
            var height = meta.gecko_height_mm || width * (layout.height || rect.height) / (layout.width || rect.width);
            dc.set_props('figure-export-request', {data:{figure:snapshot(gd),format:'svg',
                width_mm:width,height_mm:height,dpi:300,render_width:layout.width || rect.width,
                label:label,origin:'quick',ts:Date.now()}});
        }
        ['context-menu', 'ms-plot-context-menu', 'figure-context-menu'].forEach(function (id) {
            dc.set_props(id, {hidden: true});
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
    // Capture the action first, while its target and source figure still exist.
    document.addEventListener('click', function (event) {
        var current = event.target.closest && event.target.closest('[data-current-figure-action]');
        if (current) {
            event.preventDefault(); event.stopPropagation();
            var gd = activePlot();
            if (gd) run(current.getAttribute('data-current-figure-action'), gd);
            else window.dash_clientside.set_props('figure-action-status', {children:'Load or select a figure first.'});
            return;
        }
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
        dc.set_props('figure-context-menu', {hidden: false});
    });
    window.GeckoFigureActions = {run: run, snapshot:snapshot, activePlot:activePlot};
    var dc = window.dash_clientside = window.dash_clientside || {};
    dc.geckoFigureActions = {
        exportRequest: exportRequest,
        packageRequest: function(clicks,preset,width,height,dpi) {
            if (!clicks) return dc.no_update;
            var gd=activePlot();
            if (!gd) return {error:'Select a figure before exporting.',ts:Date.now()};
            var rect=gd.getBoundingClientRect(), layout=gd._fullLayout || {}, meta=(gd.layout || {}).meta || {};
            var rw=layout.width || rect.width, rh=layout.height || rect.height;
            if (preset==='single-col') {width=84;height=63;}
            else if (preset==='full-width') {width=174;height=104;}
            else if (preset==='presentation') {width=254;height=143;}
            else if (preset==='current' || !preset) {width=meta.gecko_width_mm || 174;height=meta.gecko_height_mm || width*rh/rw;}
            return {figure:snapshot(gd),width_mm:width,height_mm:height,dpi:dpi,render_width:rw,ts:Date.now()};
        },
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
