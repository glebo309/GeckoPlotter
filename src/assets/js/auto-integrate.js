/*
 * auto-integrate.js  (experimental, off by default; the "Auto" button next to Integrate turns it on)
 *
 * With Auto on, resting the pointer on a peak (on its flank, top or just above it) behaves as if Shift were held:
 * the cursor becomes a crosshair, the Integrate button lights up, and dragging draws an integration baseline.
 * Over flat baseline, or away from the trace, drag zooms as usual. Switch Auto off to get the old behaviour back.
 *
 * manual-integration.js asks window.__geckoAutoIntegrateNear whether to treat a press as Shift-drag.
 */
(function () {
    'use strict';
    var KEY = 'gecko.autoIntegrate';
    var enabled = false;
    try { enabled = window.localStorage.getItem(KEY) === '1'; } catch (e) { /* private mode: stays off */ }
    window.__geckoAutoIntegrateNear = false;

    var TYPED = { f8: Float64Array, f4: Float32Array, i4: Int32Array, i2: Int16Array, i1: Int8Array,
                  u4: Uint32Array, u2: Uint16Array, u1: Uint8Array };

    /** Plotly may hold numpy arrays as {dtype, bdata}; plain arrays and typed arrays pass through. */
    function asArray(values) {
        if (!values) return null;
        if (Array.isArray(values) || ArrayBuffer.isView(values)) return values;
        if (values.bdata && TYPED[values.dtype]) {
            var raw = atob(values.bdata), bytes = new Uint8Array(raw.length);
            for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
            return new TYPED[values.dtype](bytes.buffer);
        }
        return null;
    }

    function nearestIndex(xs, x) {
        var lo = 0, hi = xs.length - 1;
        while (hi - lo > 1) {
            var mid = (lo + hi) >> 1;
            if (xs[mid] < x) lo = mid; else hi = mid;
        }
        return Math.abs(xs[lo] - x) <= Math.abs(xs[hi] - x) ? lo : hi;
    }

    /**
     * True when the pointer (x, y in data units) rests on a peak of the trace (xs ascending, ys).
     * A peak is a stretch of +-window of the points whose height range is at least minProminence of the visible
     * y span; "on" it means between the local minimum and the curve, or at most tolerance above the curve.
     */
    function nearPeak(xs, ys, x, y, ySpan, tolerance, minProminence, windowFraction) {
        var n = Math.min(xs.length, ys.length);
        if (n < 8 || !(ySpan > 0)) return false;
        var i = nearestIndex(xs, x);
        var w = Math.max(3, Math.round(n * (windowFraction || 0.03)));
        var lo = Math.max(0, i - w), hi = Math.min(n - 1, i + w);
        var low = Infinity, high = -Infinity;
        for (var k = lo; k <= hi; k++) {
            var v = Number(ys[k]);
            if (!isFinite(v)) continue;
            if (v < low) low = v;
            if (v > high) high = v;
        }
        if (!(high - low >= (minProminence || 0.04) * ySpan)) return false;
        var curve = Number(ys[i]);
        return isFinite(curve) && y <= curve + tolerance && y >= low - tolerance;
    }

    function setNear(near) {
        if (window.__geckoAutoIntegrateNear === near) return;
        window.__geckoAutoIntegrateNear = near;
        var gd = window.geckoActivePlot && window.geckoActivePlot();
        if (gd) gd.classList.toggle('gecko-auto-near', near);
        var button = document.getElementById('plot-tool-integrate');
        if (button) button.classList.toggle('momentary-active', near);
    }

    function syncButton() {
        var button = document.getElementById('plot-tool-auto');
        if (!button) return;
        button.classList.toggle('active', enabled);
        button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    }

    function evaluate(event) {
        var gd = window.geckoActivePlot && window.geckoActivePlot();
        var tools = window.GeckoPlotterManualIntegration;
        if (!enabled || !gd || !gd._fullLayout || !tools) return setNear(false);
        if (window.__geckoBaselineMode && window.__geckoBaselineMode !== 'navigate') return setNear(false);
        if (gd.__geckoManualIntegrationDrawing || gd.__geckoManualIntegrationSelectedPeakId) return setNear(false);
        var sp = tools.subplotAtEvent(gd, event);
        if (!sp) return setNear(false);
        var x = sp.xaxis.p2d(event.clientX - sp.bounds.left);
        var y = sp.yaxis.p2d(event.clientY - sp.bounds.top);
        var range = sp.yaxis.range || [];
        var ySpan = Math.abs(Number(range[1]) - Number(range[0]));
        var tolerance = ySpan * 14 / Math.max(1, sp.bounds.height);        // 14 px
        var near = (gd.data || []).some(function (trace) {
            if (!trace || !trace.meta || !trace.meta.file_id || trace.fill) return false;
            if (trace.visible === false || trace.visible === 'legendonly') return false;
            if (((trace.xaxis || 'x') + (trace.yaxis || 'y')) !== sp.key) return false;
            var xs = asArray(trace.x), ys = asArray(trace.y);
            return !!(xs && ys) && nearPeak(xs, ys, Number(x), Number(y), ySpan, tolerance, 0.04, 0.03);
        });
        setNear(near);
    }

    var pending = null;
    function onMove(event) {
        if (!enabled) return;
        pending = event;
        if (onMove.scheduled) return;
        onMove.scheduled = true;
        window.requestAnimationFrame(function () {
            onMove.scheduled = false;
            try { evaluate(pending); } catch (e) { setNear(false); }
        });
    }

    function toggle() {
        enabled = !enabled;
        try { window.localStorage.setItem(KEY, enabled ? '1' : '0'); } catch (e) { /* not persisted */ }
        if (!enabled) setNear(false);
        syncButton();
    }

    if (typeof document !== 'undefined' && document.addEventListener) {
        document.addEventListener('click', function (event) {
            var target = event.target;
            if (target && target.closest && target.closest('#plot-tool-auto')) toggle();
        });
        document.addEventListener('mousemove', function (event) { syncButton(); onMove(event); }, true);
        document.addEventListener('gecko:plot-leave', function () { setNear(false); });
        document.addEventListener('DOMContentLoaded', syncButton);
        window.addEventListener('blur', function () { setNear(false); });
    }
    window.GeckoAutoIntegrate = { nearPeak: nearPeak, asArray: asArray, toggle: toggle };
})();
