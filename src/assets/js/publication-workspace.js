// Retain a live publication figure per tab; the paper/slide is a shared frame.
(function () {
    'use strict';
    var plots = new Map(), activeId = null;
    function resize(gd) {
        if (!gd || gd.style.display === 'none') return;
        var rect = gd.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        Promise.resolve(window.Plotly.Plots.resize(gd)).catch(function () {});
    }
    async function update(figure, tabId, tabs, preset) {
        if (!window.Plotly) return window.dash_clientside.no_update;
        activeId = tabId;
        var host = document.getElementById(preset === 'presentation' ? 'pub-slide-workspace' : 'pub-plot-workspace');
        if (!host) return window.dash_clientside.no_update;
        var allowed = new Set((tabs || []).filter(function(t){return t.type === 'publication';}).map(function(t){return t.id;}));
        plots.forEach(function(entry,id){
            if (!allowed.has(id)) {if (entry.observer) entry.observer.disconnect();window.Plotly.purge(entry.gd);entry.gd.remove();plots.delete(id);}
            else entry.gd.style.display = id === activeId ? 'block' : 'none';
        });
        var figureId = figure && figure.layout && figure.layout.meta && figure.layout.meta.gecko_tab_id;
        if (figure && allowed.has(figureId)) {
            var entry = plots.get(figureId);
            if (!entry) {
                var gd = document.createElement('div');
                gd.dataset.publicationPlot = figureId;
                Object.assign(gd.style,{width:'100%',height:'100%',position:'absolute',inset:'0'});
                host.appendChild(gd);
                entry = {gd:gd}; plots.set(figureId,entry);
                if (typeof ResizeObserver !== 'undefined') {
                    entry.observer = new ResizeObserver(function(){requestAnimationFrame(function(){resize(gd);});});
                    entry.observer.observe(gd);
                }
            }
            var signature = JSON.stringify(figure);
            if (entry.signature !== signature) {
                entry.signature = signature;
                var copy = JSON.parse(signature);
                entry.gd.style.display = figureId === activeId ? 'block' : 'none';
                await window.Plotly.react(entry.gd,copy.data || [],copy.layout || {},
                    {responsive:true,displayModeBar:false,displaylogo:false,scrollZoom:false,doubleClick:'reset+autosize'});
            }
        }
        var current = plots.get(activeId);
        if (current) {
            if (current.gd.parentElement !== host) host.appendChild(current.gd);
            current.gd.style.display='block';
            requestAnimationFrame(function(){resize(current.gd);});
        }
        return '';
    }
    window.dash_clientside = Object.assign({},window.dash_clientside,{publicationWorkspace:{update:update}});
})();
