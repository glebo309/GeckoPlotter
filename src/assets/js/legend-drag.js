// Move legends without changing the plotting or text-edit tool. Near an edge of its plot a legend snaps to it (3 px
// clear of the frame). With subplots, the other subplots' legends move to the same place in theirs, unless "Move subplot
// legends together" is off in the legend's right-click menu (layout.meta.gecko_legends_linked).
(function () {
    'use strict';
    document.addEventListener('mousedown', function (event) {
        if (event.button !== 0 || document.body.classList.contains('gecko-text-edit-mode')) return;
        var node = event.target.closest && event.target.closest('g.legend, g[class^="legend"]');
        if (!node) return;
        var key = Array.from(node.classList).find(function (c) {return /^legend\d*$/.test(c);});
        var gd = node.closest('.js-plotly-plot');
        if (!key || !gd || (!gd.dataset.workspacePlot && !gd.dataset.publicationPlot)) return;
        var rect = node.getBoundingClientRect(), graphRect = gd.getBoundingClientRect();
        var size = gd._fullLayout._size, startX = event.clientX, startY = event.clientY;
        var scale = graphRect.width / gd._fullLayout.width || 1;
        var oldTransform = node.getAttribute('transform'), moved = false;
        event.stopImmediatePropagation();
        function move(e) {
            var dx = e.clientX-startX, dy=e.clientY-startY;
            if (!moved && Math.hypot(dx,dy)<5) return;
            moved=true; gd.__geckoLegendDragged=true;
            node.setAttribute('transform', (oldTransform || '')+' translate('+(dx/scale)+','+(dy/scale)+')');
            e.preventDefault();
        }
        function up(e) {
            document.removeEventListener('mousemove',move,true);
            document.removeEventListener('mouseup',up,true);
            if (!moved) return;
            node.setAttribute('transform',oldTransform);
            var left=(rect.left+e.clientX-startX-graphRect.left)/scale-size.l;
            var top=(rect.top+e.clientY-startY-graphRect.top)/scale-size.t;
            var suffix=key.slice(6), xa=gd._fullLayout['xaxis'+suffix], ya=gd._fullLayout['yaxis'+suffix];
            var xd=xa && xa.domain || [0,1], yd=ya && ya.domain || [0,1];
            var GAP=3, SNAP=10;
            var xmin=xd[0]*size.w+GAP, xmax=xd[1]*size.w-GAP-rect.width/scale;
            var ymin=(1-yd[1])*size.h+GAP, ymax=(1-yd[0])*size.h-GAP-rect.height/scale;
            left=Math.max(xmin,Math.min(xmax,left));top=Math.max(ymin,Math.min(ymax,top));
            if (Math.abs(left-xmin)<SNAP) left=xmin;
            if (Math.abs(left-xmax)<SNAP) left=xmax;
            if (Math.abs(top-ymin)<SNAP) top=ymin;
            if (Math.abs(top-ymax)<SNAP) top=ymax;
            var pos={x:left/size.w,y:1-top/size.h,xanchor:'left',yanchor:'top'};
            var change={}; Object.keys(pos).forEach(function(k){change[key+'.'+k]=pos[k];});
            // Saved as a place inside its own subplot, so it stays there when subplots are added or removed.
            var fx=(pos.x-xd[0])/((xd[1]-xd[0])||1), fy=(pos.y-yd[0])/((yd[1]-yd[0])||1);
            pos.in_subplot=[fx,fy];
            var linked={}, meta=gd.layout.meta||{};
            if (meta.gecko_legends_linked!==false) {
                // The same place inside every other subplot.
                Object.keys(gd._fullLayout).filter(function(k){return /^legend\d*$/.test(k) && k!==key;}).forEach(function(k){
                    var sfx=k.slice(6), oxa=gd._fullLayout['xaxis'+sfx], oya=gd._fullLayout['yaxis'+sfx];
                    if (!oxa || !oya) return;
                    var ox=oxa.domain||[0,1], oy=oya.domain||[0,1];
                    linked[k]={x:ox[0]+fx*(ox[1]-ox[0]), y:oy[0]+fy*(oy[1]-oy[0]), xanchor:'left', yanchor:'top'};
                    Object.keys(linked[k]).forEach(function(p){change[k+'.'+p]=linked[k][p];});
                    linked[k].in_subplot=[fx,fy];
                });
            }
            window.Plotly.relayout(gd,change);
            window.dash_clientside.set_props('legend-position-edit',{data:{legend:key,position:pos,linked:linked,ts:Date.now()}});
            setTimeout(function(){gd.__geckoLegendDragged=false;},350);
            e.preventDefault(); e.stopImmediatePropagation();
        }
        document.addEventListener('mousemove',move,true);
        document.addEventListener('mouseup',up,true);
    },true);
})();
