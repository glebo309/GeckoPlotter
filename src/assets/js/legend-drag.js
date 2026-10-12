// Move legends without changing the plotting or text-edit tool.
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
            var xmin=xd[0]*size.w+8, xmax=xd[1]*size.w-8-rect.width/scale;
            var ymin=(1-yd[1])*size.h+8, ymax=(1-yd[0])*size.h-8-rect.height/scale;
            left=Math.max(xmin,Math.min(xmax,left));top=Math.max(ymin,Math.min(ymax,top));
            if (Math.abs(left-xmin)<18) left=xmin;
            if (Math.abs(left-xmax)<18) left=xmax;
            if (Math.abs(top-ymin)<18) top=ymin;
            if (Math.abs(top-ymax)<18) top=ymax;
            var pos={x:left/size.w,y:1-top/size.h,xanchor:'left',yanchor:'top'};
            var change={}; Object.keys(pos).forEach(function(k){change[key+'.'+k]=pos[k];});
            window.Plotly.relayout(gd,change);
            window.dash_clientside.set_props('legend-position-edit',{data:{legend:key,position:pos,ts:Date.now()}});
            setTimeout(function(){gd.__geckoLegendDragged=false;},350);
            e.preventDefault(); e.stopImmediatePropagation();
        }
        document.addEventListener('mousemove',move,true);
        document.addEventListener('mouseup',up,true);
    },true);
})();
