// Keep one live Plotly instance per tab. The hidden Dash graph remains the
// callback interface for existing integration, export and scan tools.
(function () {
    'use strict';
    var plots = new Map();
    var activeId = null, lastTabs = [], updateVersion = 0, publishedTabs = '';
    var pendingId = null;
    // A new file's tab drawn straight from the upload response (preview), before the tab list and the active tab
    // arrive. Kept on screen and out of the clean-up below until the tab list has it, or for 15 s at most.
    var previewId = null, previewAt = 0;
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
        if (window.GeckoLegendVisibility) window.GeckoLegendVisibility.bind(gd);
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
        var size = rect.width + ':' + rect.height;
        if (gd.__geckoWorkspaceSize === size) return;
        gd.__geckoWorkspaceSize = size;
        Promise.resolve(window.Plotly.Plots.resize(gd)).catch(function () {gd.__geckoWorkspaceSize = null;});
    }

    function publishRetainedTabs() {
        var ids = [];
        plots.forEach(function (entry, id) {if (entry.bound) ids.push(id);});
        var key = ids.join('|');
        if (key !== publishedTabs) {
            publishedTabs = key;
            window.dash_clientside.set_props('rendered-plot-tabs', {data: ids});
        }
    }

    function activate(id, mirror, reveal) {
        var changed = activeId !== id;
        if (changed) document.dispatchEvent(new CustomEvent('gecko:plot-leave'));
        activeId = id;
        plots.forEach(function (entry, key) {entry.gd.style.display = key === id ? 'block' : 'none';});
        if (reveal) {
            var raw = document.getElementById('plot-workspace');
            var pub = document.getElementById('pub-preview-wrapper');
            if (raw) raw.style.display = 'block';
            if (pub) pub.style.display = 'none';
        }
        var current = plots.get(id);
        if (current) {
            resize(current.gd);
            if (mirror && (changed || current.needsMirror) && current.figure) {
                current.needsMirror = false;
                // Legacy callbacks still consume main-plot.figure. Mirror once;
                // the visible graph itself is already on screen and untouched.
                var layout = current.gd.layout || current.figure.layout || {};
                layout = typeof structuredClone === 'function' ? structuredClone(layout) : JSON.parse(JSON.stringify(layout));
                current.mirroredFigure = {data: current.figure.data, layout: layout};
                setProps({figure: current.mirroredFigure, clickData: null, relayoutData: null});
            }
            if (changed) document.dispatchEvent(new CustomEvent('gecko:plot-ready'));
        }
        return !!current;
    }

    async function update(figure, tabId, tabs) {
        var host = document.getElementById('plot-workspace');
        if (!host || !window.Plotly) return window.dash_clientside.no_update;
        var version = ++updateVersion;
        if (!host.__geckoResizeObserver && typeof ResizeObserver !== 'undefined') {
            var queued = false;
            host.__geckoResizeObserver = new ResizeObserver(function () {
                if (queued) return;
                queued = true;
                requestAnimationFrame(function () {
                    queued = false;
                    resize(window.geckoActivePlot());
                });
            });
            host.__geckoResizeObserver.observe(host);
        }
        lastTabs = tabs || [];
        var allowed = new Set(lastTabs.filter(function (tab) {return tab.type !== 'publication';})
            .map(function (tab) {return tab.id;}));
        if (previewId && (tabId === previewId || Date.now() - previewAt > 15000)) previewId = null;
        if (previewId) allowed.add(previewId);
        if (!tabId) allowed.add('__empty__');
        plots.forEach(function (entry, id) {
            if (!allowed.has(id)) {
                window.Plotly.purge(entry.gd);
                entry.gd.remove();
                plots.delete(id);
            }
        });
        publishRetainedTabs();
        if (pendingId && (!lastTabs.some(function (t) {return t.id === pendingId;}) || tabId === pendingId)) pendingId = null;
        var nextId = pendingId || previewId || tabId || '__empty__';
        var changed = activeId !== nextId;
        // Show the cached target before serializing data or awaiting any render.
        activate(nextId, false, false);
        var figureId = figure && figure.layout && figure.layout.meta && figure.layout.meta.gecko_tab_id;
        figureId = figureId || nextId;
        if (figure && allowed.has(figureId)) {
            var entry = plots.get(figureId);
            if (!entry) {
                var gd = document.createElement('div');
                gd.dataset.workspacePlot = figureId;
                gd.style.width = '100%'; gd.style.height = '100%';
                gd.style.position = 'absolute'; gd.style.inset = '0';
                gd.style.display = figureId === activeId ? 'block' : 'none';
                host.appendChild(gd);
                entry = {id: figureId, gd: gd};
                plots.set(figureId, entry);
            }
            var ctx = window.dash_clientside.callback_context;
            var figureTriggered = ctx && (ctx.triggered || []).some(function (t) {return t.prop_id === 'main-plot.figure';});
            // Dash tab/settings callbacks reuse the figure object. Explicit
            // figure events still inspect it so in-place Patch updates are safe.
            var isMirror = entry.mirroredFigure === figure;
            var signature = isMirror || (entry.source === figure && !figureTriggered) ? entry.signature : JSON.stringify(figure);
            if (isMirror) entry.mirroredFigure = null;
            entry.source = figure;
            if (entry.previewSignature && !(figure.data || []).length) {
                // An empty placeholder for the new tab (sent while its file is still being selected) must not blank
                // the plot drawn from the upload; the full render follows.
                signature = entry.signature;
            } else if (entry.previewSignature && entry.signature !== signature) {
                // The full render of a tab drawn from the upload: when only its render stamp differs, keep the canvas.
                var same = entry.previewSignature === withoutRevision(figure);
                entry.previewSignature = null;
                if (same) { entry.signature = signature; entry.figure = JSON.parse(signature); }
            }
            if (entry.signature !== signature) {
                entry.signature = signature;
                entry.figure = JSON.parse(signature);
                var layout = JSON.parse(JSON.stringify(entry.figure.layout || {}));
                Object.keys(layout).forEach(function(key){
                    if (!/^[xy]axis\d*$/.test(key) || !layout[key].range) return;
                    var axis=layout[key];
                    if (axis.autorange==='max') axis.range[1]=null;
                    if (axis.autorange==='min') axis.range[0]=null;
                });
                await window.Plotly.react(entry.gd, entry.figure.data || [], layout, config);
                if (!plots.has(figureId)) return '';
                bridge(entry);
                // Plotly.react already laid this canvas out at its current size.
                if (figureId === activeId && host.style.display !== 'none') {
                    var bounds = host.getBoundingClientRect();
                    if (bounds.width && bounds.height) entry.gd.__geckoWorkspaceSize = bounds.width + ':' + bounds.height;
                }
                publishRetainedTabs();
                if (version !== updateVersion) return '';
                if (figureId === activeId) document.dispatchEvent(new CustomEvent('gecko:plot-ready'));
            }
        }
        if (version !== updateVersion) return '';
        var current = plots.get(activeId);
        if (current) {
            resize(current.gd);
            if ((changed || current.needsMirror) && current.figure && figureId !== activeId && !pendingId) {
                current.needsMirror = false;
                var liveLayout = current.gd.layout || current.figure.layout || {};
                liveLayout = typeof structuredClone === 'function' ? structuredClone(liveLayout) : JSON.parse(JSON.stringify(liveLayout));
                current.mirroredFigure = {data: current.figure.data, layout: liveLayout};
                setProps({figure: current.mirroredFigure, clickData: null, relayoutData: null});
            }
        }
        return '';
    }

    function withoutRevision(figure) {
        return JSON.stringify(figure, function (key, value) {return key === 'gecko_render_revision' ? undefined : value;});
    }

    // Draw a new file's tab from the upload response (upload_callbacks._first_paint), ahead of the tab list.
    async function preview(data) {
        var none = window.dash_clientside.no_update;
        var host = document.getElementById('plot-workspace');
        if (!data || !data.tab || !data.figure || !host || !window.Plotly) return none;
        var current = lastTabs.find(function (t) {return t.id === activeId;});
        if (current && current.type === 'publication') return null;        // stay on the publication page
        var entry = plots.get(data.tab);
        if (!entry) {
            var gd = document.createElement('div');
            gd.dataset.workspacePlot = data.tab;
            gd.style.width = '100%'; gd.style.height = '100%';
            gd.style.position = 'absolute'; gd.style.inset = '0';
            host.appendChild(gd);
            entry = {id: data.tab, gd: gd};
            plots.set(data.tab, entry);
        }
        previewId = data.tab; previewAt = Date.now();
        activate(data.tab, false, true);
        var signature = JSON.stringify(data.figure);
        entry.signature = signature;
        entry.figure = JSON.parse(signature);
        entry.source = null;
        entry.previewSignature = withoutRevision(data.figure);
        await window.Plotly.react(entry.gd, entry.figure.data || [], entry.figure.layout || {}, config);
        bridge(entry);
        var bounds = host.getBoundingClientRect();
        if (bounds.width && bounds.height) entry.gd.__geckoWorkspaceSize = bounds.width + ':' + bounds.height;
        document.dispatchEvent(new CustomEvent('gecko:plot-ready'));
        return null;                                                        // the figure is drawn; free the store
    }

    function revealTab(id, mirror) {
        // Both the direct click and Dash reconciliation share the same layout.
        if (window.__geckoSyncPlotTabLayout) window.__geckoSyncPlotTabLayout(id, lastTabs);
        if (document.querySelectorAll) document.querySelectorAll('.plot-tab-btn').forEach(function (button) {
            try {
                var selected = JSON.parse(button.id).index === id;
                button.classList.toggle('active', selected);
                button.setAttribute('aria-pressed', selected ? 'true' : 'false');
            } catch (_) {}
        });
        var tab = lastTabs.find(function (t) {return t.id === id;});
        if (tab && tab.type === 'publication') {
            activate(id, false, false);
            var publication = window.dash_clientside.publicationWorkspace;
            if (publication && publication.activate) publication.activate(id);
        } else {
            activate(id, mirror, true);
        }
    }

    // Capture the actual click before Dash's dependency queue. Retained canvases
    // can be revealed immediately; Python still owns data/settings selection.
    document.addEventListener('click', function (event) {
        if (!event.target || !event.target.closest) return;
        var button = event.target.closest('.plot-tab-btn');
        var id;
        if (button) {
            if (event.target.closest('[id*="plot-tab-close"]')) return;
            try {id = JSON.parse(button.id).index;} catch (_) {return;}
        } else {
            var row = event.target.closest('.file-tree-item');
            if (!row) return;
            // Preserve the publication inspector's existing source-selection behavior.
            var current = lastTabs.find(function (t) {return t.id === activeId;});
            if (current && current.type === 'publication') return;
            var group = row.closest('.file-group-container');
            if (!group) return;
            try {id = JSON.parse(group.id).index;} catch (_) {return;}
        }
        if (!id || id === activeId || !lastTabs.some(function (t) {return t.id === id;})) return;
        pendingId = id;
        var entry = plots.get(id);
        if (entry) entry.needsMirror = true;
        revealTab(id, false);
    }, true);

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        plotWorkspace: {update: update, activate: activate, preview: preview,
            switchTab: function (clicks, current) {
                var ctx = window.dash_clientside.callback_context;
                if (!(clicks || []).some(Boolean) || !ctx.triggered.length) return window.dash_clientside.no_update;
                var id = JSON.parse(ctx.triggered[0].prop_id.replace(/\.n_clicks$/, '')).index;
                if (id === current) return window.dash_clientside.no_update;
                revealTab(id, true);
                return id;
            }}
    });
    window.addEventListener('resize', function () {
        if (window.Plotly) resize(window.geckoActivePlot());
    });
})();
