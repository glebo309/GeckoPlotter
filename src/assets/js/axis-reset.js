// Axis double-clicks reset only that scale; canvas double-click keeps its normal behavior.
(function () {
    'use strict';
    function axisAtEvent(gd, event) {
        var layout = gd && gd._fullLayout;
        if (!layout) return null;
        var box = gd.getBoundingClientRect();
        var sx = layout.width ? box.width / layout.width : 1;
        var sy = layout.height ? box.height / layout.height : 1;
        var x = (event.clientX - box.left) / sx, y = (event.clientY - box.top) / sy;
        var keys = Object.keys(layout).filter(function(k){return /^[xy]axis\d*$/.test(k);});
        for (var i=0;i<keys.length;i++) {
            var key=keys[i], axis=layout[key], horizontal=key[0]==='x';
            var other=layout[(horizontal?'yaxis':'xaxis')+(axis.anchor || '').slice(1)] || layout[horizontal?'yaxis':'xaxis'];
            if (!other || !axis._length || !other._length) continue;
            var line = horizontal ? other._offset + (axis.side==='top'?0:other._length)
                                  : other._offset + (axis.side==='right'?other._length:0);
            var along = horizontal?x:y, across=horizontal?y:x;
            if (along >= axis._offset && along <= axis._offset+axis._length && Math.abs(across-line)<=50) {
                var outside = horizontal ? (axis.side==='top'? across<=line+3 : across>=line-3)
                                         : (axis.side==='right'? across>=line-3 : across<=line+3);
                if (outside) return key;
            }
        }
        return null;
    }
    function reset(gd, key) {
        var update={}, axes={};
        Object.keys(gd._fullLayout).forEach(function(other){
            if (/^[xy]axis\d*$/.test(other) && gd._fullLayout[other].range) {
                axes[other]={range:gd._fullLayout[other].range.slice(),type:gd._fullLayout[other].type || 'linear',
                    userZoom:!!(gd.__geckoInspectorZoom && gd.__geckoInspectorZoom[other])};
            }
            if (/^[xy]axis\d*$/.test(other) && other[0]!==key[0]) {
                update[other+'.range']=gd._fullLayout[other].range.slice();
                update[other+'.autorange']=false;
            }
        });
        update[key+'.range']=[null,null];
        update[key+'.autorange']=true;
        gd.__geckoAxisResetAt=Date.now();
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('axis-inspector-reset',{data:{
                tab:(gd._fullLayout.meta || {}).gecko_tab_id, axis:key, axes:axes, ts:Date.now()
            }});
        }
        return window.Plotly.relayout(gd,update);
    }
    function handle(event) {
        var gd=event.target && event.target.closest && event.target.closest('.js-plotly-plot');
        if (window.GeckoFigureLabels && window.GeckoFigureLabels.targetAtEvent(gd,event)) return;
        var key=axisAtEvent(gd,event);
        if (!key || !window.Plotly) return;
        var last=gd.__geckoAxisPointer, now=Date.now();
        var double=event.type==='dblclick' || event.detail>1 ||
            (event.type==='pointerdown' && last && last.key===key && now-last.time<360 &&
             Math.abs(last.x-event.clientX)<8 && Math.abs(last.y-event.clientY)<8);
        if(event.type==='pointerdown') gd.__geckoAxisPointer={key:key,time:now,x:event.clientX,y:event.clientY};
        if(!double) return;
        event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
        if(event.type!=='mousedown') reset(gd,key);
    }
    document.addEventListener('pointerdown',handle,true);
    document.addEventListener('mousedown',handle,true);
    document.addEventListener('dblclick',handle,true);
    window.GeckoPlotterAxisReset={axisAtEvent:axisAtEvent,reset:reset};
})();
