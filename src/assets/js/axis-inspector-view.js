// Capture displayed zoom before inspector edits reach Dash's debounced controls.
(function () {
    'use strict';
    function track(gd) {
        if (!gd || !gd.on || gd.__geckoInspectorZoomBound) return;
        gd.__geckoInspectorZoomBound=true;
        gd.__geckoInspectorZoom={};
        gd.on('plotly_relayout',function(update){
            if (Date.now()-(gd.__geckoAxisResetAt || 0)<500) return;
            Object.keys(update || {}).forEach(function(key){
                var match=key.match(/^([xy]axis\d*)\.(range(?:\[[01]\])?|autorange)$/);
                if (!match) return;
                if (match[2]==='autorange') {
                    if (update[key]===true) gd.__geckoInspectorZoom[match[1]]=false;
                } else gd.__geckoInspectorZoom[match[1]]=true;
            });
        });
    }
    function capture(event) {
        if (!event.target.closest) return;
        track(event.target.closest('.js-plotly-plot'));
        if (!event.target.closest('.axis-inspector')) return;
        var candidates = Array.from(document.querySelectorAll('.js-plotly-plot'));
        var gd = candidates.find(function(plot) {
            var box=plot.getBoundingClientRect();
            return box.width && box.height && plot._fullLayout && plot.dataset &&
                (plot.dataset.workspacePlot || plot.dataset.publicationPlot);
        });
        if (!gd || !window.dash_clientside || !window.dash_clientside.set_props) return;
        var full=gd._fullLayout, layout={meta:full.meta || {}}, axes={};
        Object.keys(full).forEach(function(key) {
            if (!/^[xy]axis\d*$/.test(key) || !full[key].range) return;
            var axis=full[key];
            axes[key]={range:axis.range.slice(),type:axis.type || 'linear',autorange:axis.autorange,
                userZoom:!!(gd.__geckoInspectorZoom && gd.__geckoInspectorZoom[key])};
            layout[key]={title:{text:axis.title && axis.title.text || ''},visible:axis.visible};
        });
        window.dash_clientside.set_props('axis-inspector-view',{data:{
            tab:(full.meta || {}).gecko_tab_id, layout:layout, axes:axes, ts:Date.now()
        }});
    }
    ['pointerdown','wheel','focusin','keydown'].forEach(function(name){document.addEventListener(name,capture,true);});
})();
