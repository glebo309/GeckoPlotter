// PDA heatmap selector. The dashed cross is a light DOM overlay (not Plotly shapes), so moving it never
// redraws the heatmap. Plain drag moves the cross; Shift + drag passes through to Plotly's box zoom.
(function () {
    'use strict';
    var dragging = false, lastSentAt = 0, latest = null, cross = null, selected = null, raf = 0, geom = null, lastWi = -1;
    function dataPoint(x, y, px, py) {
        var cx = Math.max(0, Math.min(x._length, px)), cy = Math.max(0, Math.min(y._length, py));
        return {time_min: Number(x.p2d(cx)), wavelength_nm: Number(y.p2d(cy))};
    }
    function plot() {
        var host = document.getElementById('pda-heatmap');
        return host && host.querySelector('.js-plotly-plot');
    }
    function locate(e, gd) {
        var l = gd && gd._fullLayout;
        if (!l || !l.xaxis || !l.yaxis || !l.xaxis._length || !l.yaxis._length) return null;
        var box = geom || gd.getBoundingClientRect(), left = geom ? geom.boxLeft : box.left, top = geom ? geom.boxTop : box.top;
        return {x: l.xaxis, y: l.yaxis, px: e.clientX - left - l.xaxis._offset, py: e.clientY - top - l.yaxis._offset};
    }
    function overlay(gd) {
        var view = gd.closest ? gd.closest('.pda-heatmap-view') : null;
        if (!view) return null;
        if (cross && cross.parentNode === view) return cross;
        cross = document.createElement('div');
        cross.className = 'pda-cross';
        cross.innerHTML = '<div class="pda-cross-v"></div><div class="pda-cross-h"></div>';
        view.appendChild(cross);
        return cross;
    }
    // Rectangles are read once (at mousedown, or when the plot changes); moves then only write transforms.
    function measure() {
        var gd = plot(), l = gd && gd._fullLayout;
        if (!gd || !l || !l.xaxis || !l.yaxis || !l.xaxis._length) return null;
        var c = overlay(gd);
        if (!c) return null;
        var view = c.parentNode.getBoundingClientRect(), box = gd.getBoundingClientRect();
        return {c: c, x: l.xaxis, y: l.yaxis, boxLeft: box.left, boxTop: box.top,
                left: box.left - view.left + l.xaxis._offset, top: box.top - view.top + l.yaxis._offset};
    }
    function place(t, w) {
        var g = geom || measure();
        if (!g) return;
        var x = g.left + g.x.d2p(t), y = g.top + g.y.d2p(w);
        var v = g.c.firstChild, h = g.c.lastChild;
        var inX = x >= g.left && x <= g.left + g.x._length, inY = y >= g.top && y <= g.top + g.y._length;
        v.style.display = inX ? 'block' : 'none'; h.style.display = inY ? 'block' : 'none';
        v.style.transform = 'translateX(' + x + 'px)'; v.style.top = g.top + 'px'; v.style.height = g.y._length + 'px';
        h.style.transform = 'translateY(' + y + 'px)'; h.style.left = g.left + 'px'; h.style.width = g.x._length + 'px';
    }
    function refresh() {
        raf = 0;
        var p = dragging && latest ? latest : selected;
        if (p) place(p.time_min, p.wavelength_nm);
    }
    function schedule() { if (!raf) raf = window.requestAnimationFrame(refresh); }
    function send(final) {
        var now = Date.now();
        if (!latest || (!final && now - lastSentAt < 100)) return;
        lastSentAt = now;
        window.dash_clientside.set_props('pda-heatmap-event', {data: Object.assign({at: now}, latest)});
    }
    function nearest(values, target) {
        var lo = 0, hi = values.length - 1;
        while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (values[mid] < target) lo = mid; else hi = mid; }
        return Math.abs(values[lo] - target) <= Math.abs(values[hi] - target) ? lo : hi;
    }
    // While dragging, the spectrum and main-plot cursor follow from data already in the browser (the heatmap's own
    // matrix), so no server round trip happens until release, when the exact measured slice replaces this preview.
    // Live preview on the main figure: the selected sample's preview trace is swapped for the heatmap column at the
    // new wavelength (already downsampled for display, keeping each bin's strongest sample so peaks survive).
    // Other samples and the exact full-resolution trace follow from the server on release.
    var previewSeq = 0, previewBusy = false, previewWanted = null;
    // Every sample in the plot follows the cross: a small endpoint returns each one's downsampled chromatogram at
    // this wavelength (latest request wins; one in flight at a time).
    function fetchSeries(owner, wl) {
        previewWanted = {owner: owner, wl: wl};
        if (previewBusy) return;
        previewBusy = true;
        var want = previewWanted; previewWanted = null; var seq = ++previewSeq;
        fetch('/_pda/chromatograms?owner=' + encodeURIComponent(want.owner) + '&wavelength=' + want.wl)
            .then(function (r) { return r.json(); })
            .then(function (data) { if (seq === previewSeq) applySeries(data.samples || [], want.wl); })
            .catch(function () {})
            .then(function () { previewBusy = false; if (previewWanted) fetchSeries(previewWanted.owner, previewWanted.wl); });   // the last wavelength is never dropped, even if the button was released meanwhile
    }
    function applySeries(samples, wl) {
        var main = window.geckoActivePlot && window.geckoActivePlot();
        if (!main || !main.data || !window.Plotly) return;
        var update = {x: [], y: [], name: []}, indices = [];
        samples.forEach(function (s) {
            main.data.forEach(function (tr, i) {
                if (!tr.meta || !tr.meta.pda_preview || tr.meta.pda_source_id !== s.source_id) return;
                update.x.push(s.x); update.y.push(s.y); indices.push(i);
                update.name.push(String(tr.name || '').replace(/PDA \d+ nm/, 'PDA ' + Math.round(s.wavelength_nm) + ' nm'));
            });
        });
        if (indices.length) window.Plotly.restyle(main, update, indices);   // one redraw for all samples
    }
    function previewMain(t, wi) {
        var main = window.geckoActivePlot && window.geckoActivePlot(), api = window.GeckoPdaScanCursor;
        var sid = api && api.sourceId && api.sourceId();
        if (!main || !main.data || !sid || !window.Plotly) return;
        var xs = Array.prototype.slice.call(t.x), ys = Array.prototype.slice.call(t.z[wi]), wl = Math.round(t.y[wi]);
        var api2 = window.GeckoPdaScanCursor, owner = api2 && api2.ownerId && api2.ownerId();
        if (owner) fetchSeries(owner, wl);
        main.data.forEach(function (tr, i) {
            if (!tr.meta || !tr.meta.pda_preview || tr.meta.pda_source_id !== sid) return;
            window.Plotly.restyle(main, {x: [xs], y: [ys],
                name: [String(tr.name || '').replace(/PDA \d+ nm/, 'PDA ' + wl + ' nm')]}, [i]);
        });
    }
    function preview(gd, point) {
        var t = gd._fullData && gd._fullData[0];
        if (!t || !t.z || !t.x || !window.Plotly) return;
        if (window.GeckoPdaScanCursor && window.GeckoPdaScanCursor.preview) window.GeckoPdaScanCursor.preview(point.time_min);
        var host = document.getElementById('pda-spectrum'), s = host && host.querySelector('.js-plotly-plot');
        if (!s || !s.data || !s.data.length) return;
        var wi = nearest(t.y, point.wavelength_nm);
        if (wi !== lastWi) { lastWi = wi; previewMain(t, wi); }
        var ti = nearest(t.x, point.time_min), ys = new Array(t.z.length);
        for (var i = 0; i < ys.length; i++) ys[i] = t.z[i][ti];
        var wl = Math.round(point.wavelength_nm);
        window.Plotly.update(s, {y: [ys]}, {'shapes[0].x0': wl, 'shapes[0].x1': wl,
            'title.text': (Math.round(t.x[ti] * 1000) / 1000) + ' min'});
    }
    function update(e) {
        var gd = plot(), a = locate(e, gd);
        if (!a) return;
        latest = dataPoint(a.x, a.y, a.px, a.py);
        place(latest.time_min, latest.wavelength_nm);
        preview(gd, latest);
    }
    // Shift + double-click resets the heatmap zoom; nothing else ever does.
    function shiftDoubleClickReset() {
        var gd = plot();
        if (!gd || !window.Plotly) return;
        window.Plotly.relayout(gd, {'xaxis.autorange': true, 'yaxis.autorange': true});
    }
    function down(e) {
        if (e.button === 0 && e.shiftKey && e.detail > 1) {
            var host0 = document.getElementById('pda-heatmap');
            if (host0 && host0.contains(e.target)) { shiftDoubleClickReset(); e.preventDefault(); e.stopPropagation(); }
            return;
        }
        if (e.button !== 0 || e.detail > 1 || e.shiftKey) return;
        var host = document.getElementById('pda-heatmap'), gd = plot();
        if (!host || !host.contains(e.target)) return;
        geom = null;
        var a = locate(e, gd);
        if (!a || a.px < 0 || a.py < 0 || a.px > a.x._length || a.py > a.y._length) return;
        geom = measure();
        lastWi = -1;
        dragging = true;
        e.preventDefault(); e.stopPropagation();
        update(e);
    }
    // Hover readout: plain DOM, so moving over the heatmap never goes through Dash.
    var readoutAt = 0;
    function readout(e) {
        var now = Date.now();
        if (now - readoutAt < 40) return;
        readoutAt = now;
        var out = document.getElementById('pda-hover-info');
        if (!out) return;
        var host = document.getElementById('pda-heatmap'), gd = plot(), t = gd && gd._fullData && gd._fullData[0];
        var a = host && host.contains(e.target) && t && t.z ? locate(e, gd) : null;
        if (!a || a.px < 0 || a.py < 0 || a.px > a.x._length || a.py > a.y._length) { out.textContent = ''; return; }
        var p = dataPoint(a.x, a.y, a.px, a.py), ti = nearest(t.x, p.time_min), wi = nearest(t.y, p.wavelength_nm);
        out.textContent = t.x[ti].toFixed(3) + ' min · ' + Math.round(t.y[wi]) + ' nm · ' + Number(t.z[wi][ti]).toPrecision(4) + ' mAU';
    }
    function move(e) {
        if (!dragging) { readout(e); return; }
        e.preventDefault(); update(e); readout(e);
    }
    function up() {
        if (!dragging) return;
        dragging = false; geom = null; send(true); selected = latest; latest = null;
    }
    // Cheap on purpose: the MutationObserver below fires for every DOM change on the page (Plotly hover layers
    // mutate constantly). Nothing to do without a heatmap; once a heatmap is bound its own plotly_afterplot /
    // plotly_relayout events (and resize) drive redraws, so a mutation only matters when the plot or the overlay
    // is new. No layout is read here.
    function install() {
        var gd = plot();
        if (!gd) return;
        if (gd.__geckoPdaCross && (!selected || (cross && cross.parentNode))) return;
        if (!gd.__geckoPdaCross && gd.on) {
            gd.__geckoPdaCross = true;
            gd.on('plotly_afterplot', schedule); gd.on('plotly_relayout', schedule);
        }
        schedule();
    }
    // Called with the selected {time_min, wavelength_nm} from the server (peak click, fields, main-plot cursor).
    function setSelection(value) {
        if (!value || dragging) return;
        selected = {time_min: Number(value.time_min), wavelength_nm: Number(value.wavelength_nm)};
        install();
        schedule();     // the selection moved: place the cross even when the plot was already bound
    }
    // At most one install() per animation frame, however many mutations arrive.
    var mutationFrame = 0;
    function onMutation() {
        if (mutationFrame) return;
        mutationFrame = window.requestAnimationFrame(function () { mutationFrame = 0; install(); }) || 1;
    }
    document.addEventListener('mousedown', down, true);
    document.addEventListener('mousemove', move, true);
    document.addEventListener('mouseup', up, true);
    window.addEventListener('resize', schedule, true);
    new MutationObserver(onMutation).observe(document.body, {childList: true, subtree: true});
    window.GeckoPdaHeatmapCursor = {setSelection: setSelection, dataPoint: dataPoint, install: install};
    if (typeof module !== 'undefined') module.exports = {dataPoint: dataPoint};
})();
