// Retain a live publication figure per tab; the paper/slide is a shared frame.
(function () {
    'use strict';
    var plots = new Map(), activeId = null;
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
        // Keep print typography and geometry constant; magnify the entire canvas.
        var scale = Math.min(availableWidth / width, availableHeight / height);
        Object.assign(gd.style, {width:width+'px',height:height+'px',inset:'auto',
            left:(availableWidth-width*scale)/2+'px',top:(availableHeight-height*scale)/2+'px',
            transform:'scale('+scale+')',transformOrigin:'top left',background:'white'});
        // Do not call Plotly.resize here: it measures the transformed DOM bounds
        // and would apply this magnification a second time to the SVG geometry.
    }
    async function update(figure, tabId, tabs, preset, viewMode) {
        if (!window.Plotly) return window.dash_clientside.no_update;
        activeId = tabId;
        var host = document.getElementById(viewMode === 'figure' ? 'pub-figure-workspace' : (preset === 'presentation' ? 'pub-slide-workspace' : 'pub-plot-workspace'));
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
                    ['pub-figure-workspace','pub-plot-workspace','pub-slide-workspace'].forEach(function(id){
                        var node=document.getElementById(id); if(node) entry.observer.observe(node);
                    });
                }
            }
            var signature = JSON.stringify(figure);
            if (entry.signature !== signature) {
                entry.signature = signature;
                var copy = JSON.parse(signature);
                var meta = copy.layout && copy.layout.meta || {};
                var width = (meta.gecko_width_mm || 84) > 90 ? 624 : 307;
                var height = width*(meta.gecko_height_mm || 63)/(meta.gecko_width_mm || 84);
                copy.layout = Object.assign({},copy.layout,{width:width,height:height,autosize:false});
                Object.assign(entry.gd.style, {width:width+'px',height:height+'px'});
                entry.gd.style.display = figureId === activeId ? 'block' : 'none';
                await window.Plotly.react(entry.gd,copy.data || [],copy.layout || {},
                    {responsive:false,displayModeBar:false,displaylogo:false,scrollZoom:false,doubleClick:'reset+autosize'});
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
