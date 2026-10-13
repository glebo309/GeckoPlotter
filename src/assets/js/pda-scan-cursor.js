// PDA time scrubber: the same source-owned DOM overlay as the MS scan cursor,
// using real axis transforms rather than a scan-index fraction of the viewport.
(function () {
    'use strict';
    var state = null, dragging = false, dragTime = null, raf = 0, suppressClick = false, lastSentAt = 0;
    function root() { return window.geckoActivePlot ? window.geckoActivePlot() : null; }
    function overlay() { return document.getElementById('pda-scan-cursor-overlay'); }
    function plotRect() {
        var gd = root();
        if (!state || !gd || !gd._fullLayout) return null;
        var trace = (gd.data || []).find(function (t) {
            return t.meta && (t.meta.file_id === state.owner_id || t.meta.pda_owner_id === state.owner_id) &&
                t.visible !== false && t.visible !== 'legendonly' && !t.meta.peak_id;
        });
        if (!trace) return null;
        var l = gd._fullLayout, x = l['xaxis' + (trace.xaxis || 'x').slice(1)], y = l['yaxis' + (trace.yaxis || 'y').slice(1)];
        if (!x || !y || !x.d2p || !x.p2d || !(x._length > 0) || !(y._length > 0)) return null;
        var b = gd.getBoundingClientRect(), sx = b.width / l.width, sy = b.height / l.height;
        var left = b.left + x._offset * sx, top = b.top + y._offset * sy;
        return {left:left, top:top, right:left+x._length*sx, bottom:top+y._length*sy,
                width:x._length*sx, height:y._length*sy, axis:x, scale:sx};
    }
    function timeToX(time) {
        var r = plotRect();
        return r && Number.isFinite(Number(time)) ? r.left + r.axis.d2p(Number(time)) * r.scale : null;
    }
    function xToTime(x) {
        var r = plotRect();
        if (!r) return null;
        var t = Number(r.axis.p2d((Math.max(r.left, Math.min(r.right, x))-r.left)/r.scale));
        if (!Number.isFinite(t)) return null;
        return Math.max(state.time_minimum, Math.min(state.time_maximum, t));
    }
    function px(v) { return (Math.round(v*100)/100)+'px'; }
    function place(time) {
        var c = overlay(), r = plotRect(), x = timeToX(time);
        if (!c) return;
        if (!r || x === null || x < r.left || x > r.right) { c.style.display='none'; return; }
        var host = c.parentElement.getBoundingClientRect();
        Object.assign(c.style, {display:'block', left:px(x-host.left), top:px(r.top-host.top),
            height:px(r.height), pointerEvents:'none'});
    }
    // The PDA heatmap shows the same time window as the main figure.
    function heatmap() {
        var host = document.getElementById('pda-heatmap');
        return host && host.querySelector ? host.querySelector('.js-plotly-plot') : null;
    }
    var followed = null;
    // Only a change of the main figure's range moves the heatmap, so zooming the heatmap itself sticks.
    function followMainZoom() {
        var r = plotRect(), h = heatmap(), range = r && r.axis.range;
        if (!range || !h || !h._fullLayout || !h._fullLayout.xaxis || !window.Plotly) return;
        var key = range[0] + ':' + range[1];
        if (key === followed) return;
        followed = key;
        var now = h._fullLayout.xaxis.range;
        if (now && Math.abs(now[0] - range[0]) < 1e-9 && Math.abs(now[1] - range[1]) < 1e-9) return;
        window.Plotly.relayout(h, {'xaxis.range': [range[0], range[1]]});
    }
    // While the heatmap cross is dragged, its time is shown here until the server confirms a new state (setState);
    // otherwise the redraws caused by the live preview would snap the line back to the last saved time.
    var previewTime = null, followPending = false;
    function sync() {
        place(dragging ? dragTime : previewTime !== null ? previewTime : state && state.time_min);
        // Only a zoom of the main figure (or opening a new PDA source) moves the heatmap's range. A redraw caused by
        // clicking in the heatmap must never change its zoom.
        if (followPending) { followPending = false; followMainZoom(); }
    }
    function onMainRelayout(event) {
        if (event && Object.keys(event).some(function (k) { return /^xaxis\d*\.(range|autorange)/.test(k); })) followPending = true;
        schedule();
    }
    function schedule() {
        if (raf) return;
        raf = window.requestAnimationFrame(function () { raf=0; sync(); });
    }
    function point(e) { return e.touches && e.touches.length ? e.touches[0] : e; }
    function scrub(e) {
        var t = xToTime(point(e).clientX);
        if (t === null) return;
        dragTime = t; place(t);
        send(false);
    }
    function send(force) {
        var now=Date.now();
        if (!state || dragTime===null || (!force && now-lastSentAt<50)) return;
        lastSentAt=now;
        window.dash_clientside.set_props('pda-cursor-event', {data:{
            source_id:state.source_id, owner_id:state.owner_id, time_min:dragTime, at:now}});
    }
    function near(e) {
        var p=point(e), r=plotRect(), x=timeToX(dragging ? dragTime : state && state.time_min);
        return r && x !== null && p.clientY>=r.top && p.clientY<=r.bottom && Math.abs(p.clientX-x)<=18;
    }
    function down(e) {
        if (e.button===2 || e.detail>1 || e.shiftKey || e.altKey || e.metaKey || e.ctrlKey || !near(e)) return;
        e.preventDefault(); e.stopImmediatePropagation(); dragging=true; suppressClick=true;
        document.body.style.cursor='col-resize'; lastSentAt=0; scrub(e);
    }
    function move(e) {
        if (!dragging) {
            var gd=root();
            if (gd && near(e)) gd.style.cursor='col-resize';
            else if (gd && gd.style.cursor==='col-resize') gd.style.cursor='';
            return;
        }
        e.preventDefault(); e.stopImmediatePropagation(); scrub(e);
    }
    function up() {
        if (!dragging) return;
        send(true); dragging=false; document.body.style.cursor='';
        setTimeout(function () { suppressClick=false; }, 0);
    }
    // Cheap on purpose: the MutationObserver below fires for every DOM change on the page. Without PDA state there is
    // nothing to track; once the plot and the heatmap are bound their own plotly events (and resize/scroll) drive
    // redraws, so a mutation reads no layout and schedules nothing.
    function install() {
        if (!state) return;
        var gd=root();
        var bound = gd && gd.__geckoPdaScrub;
        if (gd && !gd.__geckoPdaScrub) {
            gd.__geckoPdaScrub=true;
            gd.addEventListener('mousedown', down, true);
            gd.addEventListener('touchstart', down, {capture:true, passive:false});
            gd.addEventListener('click', function(e) {
                if (suppressClick && !(e.detail>1)) { suppressClick=false; e.preventDefault(); e.stopImmediatePropagation(); }
            }, true);
            if (gd.on) { gd.on('plotly_afterplot', schedule); gd.on('plotly_relayout', onMainRelayout); }
        }
        var h = heatmap();
        var heatBound = !h || h.__geckoPdaFollow || !h.on;
        if (h && !h.__geckoPdaFollow && h.on) { h.__geckoPdaFollow = true; h.on('plotly_afterplot', schedule); }
        if (bound && heatBound) return;     // nothing new to attach: no redraw needed
        schedule();
    }
    var mutationFrame = 0;
    // At most one install() per animation frame, however many mutations arrive.
    function onMutation() {
        if (mutationFrame) return;
        mutationFrame = window.requestAnimationFrame(function () { mutationFrame = 0; install(); }) || 1;
    }
    window.GeckoPdaScanCursor={install:install, sourceId:function(){return state&&state.source_id;}, ownerId:function(){return state&&state.owner_id;}, preview:function(time){previewTime=time;place(time);}, plotRect:plotRect, timeToX:timeToX, xToTime:xToTime, sync:schedule, followMainZoom:followMainZoom,
        setState:function (value) {
            if (!value || !state || value.owner_id!==state.owner_id || value.source_id!==state.source_id) up();
            if (!state || !value || value.owner_id!==state.owner_id || value.source_id!==state.source_id) followPending = true;
            state=value; previewTime=null; install(); schedule();
        }};
    document.addEventListener('gecko:plot-ready', function () { install(); schedule(); });
    document.addEventListener('gecko:plot-leave', function () { up(); var c=overlay(); if(c)c.style.display='none'; });
    document.addEventListener('mousemove', move, true);
    document.addEventListener('touchmove', move, {capture:true, passive:false});
    document.addEventListener('mouseup', up, true);
    document.addEventListener('touchend', up, true);
    document.addEventListener('touchcancel', up, true);
    window.addEventListener('resize', schedule, true);
    window.addEventListener('scroll', schedule, true);
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install);
    else setTimeout(install,250);
    new MutationObserver(onMutation).observe(document.body,{childList:true,subtree:true});
})();
