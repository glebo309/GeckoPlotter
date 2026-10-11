// Keep one live Plotly instance per tab. The hidden Dash graph remains the
// callback interface for existing integration, export and scan tools.
(function () {
    'use strict';
    var plots = new Map();
    var activeId = null;
    var config = {responsive: true, displayModeBar: false, displaylogo: false,
        doubleClick: 'reset+autosize', scrollZoom: true, edits: {shapePosition: true}};

    function setProps(props) {
        window.dash_clientside.set_props('main-plot', props);
    }

    function points(event) {
        return {points: (event.points || []).map(function (point) {
            var result = {};
            ['curveNumber', 'pointNumber', 'pointIndex', 'x', 'y', 'z', 'customdata',
                'xaxis', 'yaxis', 'bbox'].forEach(function (key) {
                // Axis objects contain circular references; callbacks need only
                // point coordinates, trace index and custom data.
                if (key !== 'xaxis' && key !== 'yaxis' && point[key] !== undefined) result[key] = point[key];
            });
            return result;
        })};
    }

    function bridge(entry) {
        if (entry.bound) return;
        var gd = entry.gd;
        gd.__geckoGraphId = 'main-plot';
        gd.on('plotly_click', function (event) { if (entry.id === activeId) setProps({clickData: points(event)}); });
        gd.on('plotly_relayout', function (event) {
            if (entry.id === activeId) setProps({relayoutData: event});
        });
        entry.bound = true;
    }

    window.geckoActivePlot = function () {
        var entry = plots.get(activeId);
        return entry ? entry.gd : null;
    };

    function resize(gd) {
        var host = document.getElementById('plot-workspace');
        if (!gd || !host || host.style.display === 'none' || gd.style.display === 'none') return;
        var rect = host.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        Promise.resolve(window.Plotly.Plots.resize(gd)).catch(function () {});
    }

    async function update(figure, tabId, tabs) {
        var host = document.getElementById('plot-workspace');
        if (!host || !window.Plotly) return window.dash_clientside.no_update;
        if (!host.__geckoResizeObserver && typeof ResizeObserver !== 'undefined') {
            host.__geckoResizeObserver = new ResizeObserver(function () {
                var gd = window.geckoActivePlot();
                if (gd) requestAnimationFrame(function () {resize(gd);});
            });
            host.__geckoResizeObserver.observe(host);
        }
        var descriptors = tabs || [];
        var allowed = new Set(descriptors.filter(function (tab) {return tab.type !== 'publication';})
            .map(function (tab) {return tab.id;}));
        if (!tabId) allowed.add('__empty__');
        plots.forEach(function (entry, id) {
            if (!allowed.has(id)) {
                window.Plotly.purge(entry.gd);
                entry.gd.remove();
                plots.delete(id);
            }
        });
        var nextId = tabId || '__empty__';
        var changed = activeId !== nextId;
        activeId = nextId;
        // A response can arrive after the user has switched away. Route it to
        // the figure's own tab rather than replacing the now-active plot.
        var figureId = figure && figure.layout && figure.layout.meta && figure.layout.meta.gecko_tab_id;
        figureId = figureId || nextId;
        if (figure && allowed.has(figureId)) {
            var entry = plots.get(figureId);
            if (!entry) {
                var gd = document.createElement('div');
                gd.dataset.workspacePlot = figureId;
                gd.style.width = '100%'; gd.style.height = '100%';
                gd.style.position = 'absolute'; gd.style.inset = '0';
                host.appendChild(gd);
                entry = {id: figureId, gd: gd};
                plots.set(figureId, entry);
            }
            var signature = JSON.stringify(figure);
            if (entry.signature !== signature) {
                entry.signature = signature;
                entry.figure = JSON.parse(signature);
                entry.gd.style.display = figureId === activeId ? 'block' : 'none';
                var layout = JSON.parse(JSON.stringify(entry.figure.layout || {}));
                // dcc.Graph mutates automatic endpoints before forwarding its figure.
                // Restore the unspecified endpoint before the retained plot consumes it.
                Object.keys(layout).forEach(function(key){
                    if (!/^[xy]axis\d*$/.test(key) || !layout[key].range) return;
                    var axis=layout[key];
                    if (axis.autorange==='max') axis.range[1]=null;
                    if (axis.autorange==='min') axis.range[0]=null;
                });
                await window.Plotly.react(entry.gd, entry.figure.data || [], layout, config);
                bridge(entry);
            }
        }
        plots.forEach(function (entry, id) {entry.gd.style.display = id === activeId ? 'block' : 'none';});
        var current = plots.get(activeId);
        if (current) {
            var rect = host.getBoundingClientRect();
            var size = rect.width + ':' + rect.height;
            if (current.size !== size) {
                current.size = size;
                resize(current.gd);
            }
            if (changed && current.figure && figureId !== activeId) {
                setProps({figure: current.figure, clickData: null, relayoutData: null});
            }
            document.dispatchEvent(new CustomEvent('gecko:plot-ready'));
        }
        return '';
    }

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        plotWorkspace: {update: update,
            switchTab: function (clicks, current) {
                var ctx = window.dash_clientside.callback_context;
                if (!(clicks || []).some(Boolean) || !ctx.triggered.length) return window.dash_clientside.no_update;
                var id = JSON.parse(ctx.triggered[0].prop_id.replace(/\.n_clicks$/, '')).index;
                return id === current ? window.dash_clientside.no_update : id;
            }}
    });
    window.addEventListener('resize', function () {
        var gd = window.geckoActivePlot();
        if (gd && window.Plotly) resize(gd);
    });
})();
