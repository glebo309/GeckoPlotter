// Retain a live publication figure per tab; the paper/slide is a shared frame.
(function () {
    'use strict';
    var plots = new Map(), activeId = null, updateVersion = 0;
    var lastView = 'page', lastPreset = 'single-col';
    function display(node, value) {
        if (node && node.style.display !== value) node.style.display = value;
    }
    function hostFor(preset, view) {
        return document.getElementById(view === 'figure' ? 'pub-figure-workspace' :
            (preset === 'presentation' ? 'pub-slide-workspace' : 'pub-plot-workspace'));
    }
    function resize(gd) {
        if (!gd || gd.style.display === 'none') return;
        var host = gd.parentElement;
        if (!host) return;
        var bounds = host.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        var availableWidth = host.clientWidth || bounds.width;
        var availableHeight = host.clientHeight || bounds.height;
        var meta = gd.layout && gd.layout.meta || {};
        var width = (meta.gecko_width_mm || 84) > 90 ? 624 : 307;
        var height = width * (meta.gecko_height_mm || 63) / (meta.gecko_width_mm || 84);
        var size = [availableWidth, availableHeight, width, height].join(':');
        if (gd.__geckoPublicationSize === size) return;
        gd.__geckoPublicationSize = size;
        // Magnify the complete canvas, keeping print typography and geometry.
        var scale = Math.min(availableWidth / width, availableHeight / height);
        Object.assign(gd.style, {width:width+'px',height:height+'px',inset:'auto',
            left:(availableWidth-width*scale)/2+'px',top:(availableHeight-height*scale)/2+'px',
            transform:'scale('+scale+')',transformOrigin:'top left',background:'white'});
        // Plotly.resize measures transformed bounds and would scale twice.
    }
    function activate(tabId, host, reveal) {
        if (activeId !== tabId && window.GeckoFigureLabels) window.GeckoFigureLabels.cancel();
        activeId = tabId;
        var current = plots.get(tabId);
        var preset = current && current.preset || lastPreset;
        host = host || hostFor(preset, lastView);
        plots.forEach(function (entry, id) {display(entry.gd, id === activeId ? 'block' : 'none');});
        if (reveal !== false) {
            display(document.getElementById('pub-preview-wrapper'), 'flex');
            display(document.getElementById('plot-workspace'), 'none');
            display(document.getElementById('pub-figure-container'), lastView === 'figure' ? 'flex' : 'none');
            display(document.getElementById('pub-paper-container'), lastView !== 'figure' && preset !== 'presentation' ? 'flex' : 'none');
            display(document.getElementById('pub-slide-container'), lastView !== 'figure' && preset === 'presentation' ? 'flex' : 'none');
        }
        if (current && host) {
            if (current.gd.parentElement !== host) host.appendChild(current.gd);
            resize(current.gd);
        }
        return !!current;
    }
    async function update(figure, tabId, tabs, preset, viewMode) {
        if (!window.Plotly) return window.dash_clientside.no_update;
        var version = ++updateVersion;
        lastView = viewMode || 'page'; lastPreset = preset || 'single-col';
        var host = hostFor(lastPreset, lastView);
        if (!host) return window.dash_clientside.no_update;
        var allowed = new Set((tabs || []).filter(function(t){return t.type === 'publication';}).map(function(t){return t.id;}));
        plots.forEach(function(entry,id){
            if (!allowed.has(id)) {
                if (entry.observer) entry.observer.disconnect();
                window.Plotly.purge(entry.gd);entry.gd.remove();plots.delete(id);
            }
        });
        // Move/show the cached canvas before any data work or asynchronous render.
        activate(tabId, host, false);
        var current = plots.get(tabId);
        if (current) current.preset = lastPreset;
        var figureId = figure && figure.layout && figure.layout.meta && figure.layout.meta.gecko_tab_id;
        if (figure && allowed.has(figureId)) {
            var entry = plots.get(figureId);
            if (!entry) {
                var gd = document.createElement('div');
                gd.dataset.publicationPlot = figureId;
                Object.assign(gd.style,{width:'100%',height:'100%',position:'absolute',inset:'0'});
                display(gd, figureId === activeId ? 'block' : 'none');
                host.appendChild(gd);
                entry = {id:figureId,gd:gd,preset:lastPreset}; plots.set(figureId,entry);
                if (typeof ResizeObserver !== 'undefined') {
                    var queued = false;
                    entry.observer = new ResizeObserver(function(){
                        if (entry.id !== activeId || queued) return;
                        queued = true;
                        requestAnimationFrame(function(){queued=false;resize(gd);});
                    });
                    ['pub-figure-workspace','pub-plot-workspace','pub-slide-workspace'].forEach(function(id){
                        var node=document.getElementById(id); if(node) entry.observer.observe(node);
                    });
                }
            }
            var ctx = window.dash_clientside.callback_context;
            var figureTriggered = ctx && (ctx.triggered || []).some(function(t){return t.prop_id === 'pub-preview-graph.data';});
            var signature = entry.source === figure && !figureTriggered ? entry.signature : JSON.stringify(figure);
            entry.source = figure;
            if (entry.signature !== signature) {
                entry.signature = signature;
                var copy = JSON.parse(signature);
                var meta = copy.layout && copy.layout.meta || {};
                var width = (meta.gecko_width_mm || 84) > 90 ? 624 : 307;
                var height = width*(meta.gecko_height_mm || 63)/(meta.gecko_width_mm || 84);
                copy.layout = Object.assign({},copy.layout,{width:width,height:height,autosize:false});
                Object.assign(entry.gd.style, {width:width+'px',height:height+'px'});
                entry.gd.__geckoPublicationSize = null;
                await window.Plotly.react(entry.gd,copy.data || [],copy.layout || {},
                    {responsive:false,staticPlot:false,displayModeBar:false,displaylogo:false,scrollZoom:false,doubleClick:'reset+autosize'});
                if (window.GeckoLegendVisibility) window.GeckoLegendVisibility.bind(entry.gd);
                if (version !== updateVersion) return '';
            }
        }
        if (version !== updateVersion) return '';
        current = plots.get(activeId);
        if (current) {
            if (current.gd.parentElement !== host) host.appendChild(current.gd);
            display(current.gd,'block');
            resize(current.gd);
        }
        return '';
    }
    window.dash_clientside = Object.assign({},window.dash_clientside,{publicationWorkspace:{update:update,activate:activate}});
})();
