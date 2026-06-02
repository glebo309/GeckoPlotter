// LC-MS scan scrubber.
//
// Uses only public DOM signals:
// - the plot's .nsewdrag rectangle for the visible plot bounds
// - the Dash-rendered slider handle aria-valuenow for the current scan index
// - a hidden Dash input for click/drag -> Python/slider sync
(function () {
    'use strict';

    var GRAB_PX = 18;
    var dragging = false;
    var currentIdx = null;
    var sliderObserver = null;
    var raf = 0;
    var suppressNextClick = false;

    function graphRoot() {
        return document.getElementById('main-plot');
    }

    function plotRect() {
        var root = graphRoot();
        if (!root) return null;
        var drags = root.querySelectorAll('.nsewdrag');
        if (!drags.length) return null;
        // Use the subplot index from the cursor overlay state if available
        var state = window.__geckoLcmsScanState;
        var idx = (state && typeof state.subplotIdx === 'number') ? state.subplotIdx : 0;
        var rectNode = drags[Math.min(idx, drags.length - 1)];
        var r = rectNode.getBoundingClientRect();
        return r.width > 0 && r.height > 0 ? r : null;
    }

    function overlay() {
        return document.getElementById('lcms-scan-cursor-overlay');
    }

    function overlayHost() {
        var c = overlay();
        return c ? c.parentElement : null;
    }

    function sliderRoot() {
        return document.getElementById('ms-scan-slider');
    }

    function sliderHandle() {
        var root = sliderRoot();
        return root ? root.querySelector('[role="slider"]') : null;
    }

    function msViewerActive() {
        var root = sliderRoot();
        if (!root || !root.getClientRects || !root.getClientRects().length) return false;
        return window.getComputedStyle(root).display !== 'none';
    }

    function sliderIndex() {
        var handle = sliderHandle();
        if (!handle) return null;
        var value = Number(handle.getAttribute('aria-valuenow'));
        return Number.isFinite(value) ? Math.round(value) : null;
    }

    function sliderMax() {
        var handle = sliderHandle();
        if (!handle) return null;
        var value = Number(handle.getAttribute('aria-valuemax'));
        return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
    }

    function setHiddenInput(idx) {
        var input = document.getElementById('ms-scan-client-input');
        if (!input || idx === null || idx === undefined) return;
        var valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
        if (valueSetter && valueSetter.set) {
            valueSetter.set.call(input, String(Math.round(idx)));
        } else {
            input.value = String(Math.round(idx));
        }
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function pushSlider(idx) {
        idx = clampIdx(idx);
        if (idx === null) return;
        setHiddenInput(idx);
    }

    function clampIdx(idx) {
        var max = sliderMax();
        idx = Number(idx);
        if (!Number.isFinite(idx) || max === null) return null;
        return Math.max(0, Math.min(Math.round(idx), max));
    }

    function idxToX(idx) {
        var r = plotRect();
        var max = sliderMax();
        idx = clampIdx(idx);
        if (!r || max === null || idx === null) return null;
        return r.left + (max === 0 ? 0 : (idx / max) * r.width);
    }

    function xToIdx(clientX) {
        var r = plotRect();
        var max = sliderMax();
        if (!r || max === null) return null;
        var frac = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
        return clampIdx(frac * max);
    }

    function placeOverlay(idx) {
        var c = overlay();
        var host = overlayHost();
        var r = plotRect();
        var x = idxToX(idx);
        if (!msViewerActive() || !c || !host || !r || x === null) {
            if (c) c.style.display = 'none';
            return null;
        }
        var hr = host.getBoundingClientRect();
        c.style.display = 'block';
        c.style.left = (x - hr.left) + 'px';
        c.style.top = (r.top - hr.top) + 'px';
        c.style.height = r.height + 'px';
        c.style.width = '18px';
        c.style.pointerEvents = 'auto';
        c.style.cursor = 'col-resize';
        currentIdx = clampIdx(idx);
        return currentIdx;
    }

    function syncFromSlider() {
        raf = 0;
        if (!msViewerActive()) {
            var c = overlay();
            if (c) c.style.display = 'none';
            return;
        }
        placeOverlay(sliderIndex());
    }

    function scheduleSync() {
        if (raf) return;
        raf = window.requestAnimationFrame(syncFromSlider);
    }

    function clientX(evt) {
        if (evt.touches && evt.touches.length) return evt.touches[0].clientX;
        if (evt.changedTouches && evt.changedTouches.length) return evt.changedTouches[0].clientX;
        return evt.clientX;
    }

    function clientY(evt) {
        if (evt.touches && evt.touches.length) return evt.touches[0].clientY;
        if (evt.changedTouches && evt.changedTouches.length) return evt.changedTouches[0].clientY;
        return evt.clientY;
    }

    function inPlot(evt) {
        if (!msViewerActive()) return false;
        var r = plotRect();
        if (!r) return false;
        var x = clientX(evt);
        var y = clientY(evt);
        return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    }

    function nearLine(evt) {
        var x = idxToX(currentIdx === null ? sliderIndex() : currentIdx);
        return x !== null && inPlot(evt) && Math.abs(clientX(evt) - x) <= GRAB_PX;
    }

    function scrubAt(evt) {
        var idx = xToIdx(clientX(evt));
        idx = placeOverlay(idx);
        pushSlider(idx);
    }

    function onDown(evt) {
        if (evt.button === 2 || !inPlot(evt)) return;
        if (evt.currentTarget === graphRoot() && !nearLine(evt)) return;
        evt.preventDefault();
        evt.stopImmediatePropagation();
        dragging = true;
        suppressNextClick = true;
        document.body.style.cursor = 'col-resize';
        scrubAt(evt);
    }

    function onClick(evt) {
        if (suppressNextClick) {
            suppressNextClick = false;
            return;
        }
        if (evt.button === 2 || !inPlot(evt) || nearLine(evt)) return;
        scrubAt(evt);
    }

    function onMove(evt) {
        if (dragging) {
            evt.preventDefault();
            evt.stopImmediatePropagation();
            scrubAt(evt);
            return;
        }
        var root = graphRoot();
        if (root) root.style.cursor = nearLine(evt) ? 'col-resize' : '';
    }

    function onUp() {
        if (!dragging) return;
        dragging = false;
        document.body.style.cursor = '';
    }

    function install() {
        var root = graphRoot();
        if (root && !root.__geckoScanScrubV5) {
            root.__geckoScanScrubV5 = true;
            root.addEventListener('mousedown', onDown, true);
            root.addEventListener('touchstart', onDown, true);
            root.addEventListener('click', onClick, true);
        }
        var c = overlay();
        if (c && !c.__geckoScanScrubV5) {
            c.__geckoScanScrubV5 = true;
            c.addEventListener('mousedown', onDown, true);
            c.addEventListener('touchstart', onDown, true);
        }

        var handle = sliderHandle();
        var sroot = sliderRoot();
        if (sroot && handle && sroot.__geckoScanHandleV5 !== handle) {
            sroot.__geckoScanHandleV5 = handle;
            if (sliderObserver) sliderObserver.disconnect();
            sliderObserver = new MutationObserver(scheduleSync);
            sliderObserver.observe(handle, {
                attributes: true,
                attributeFilter: ['aria-valuenow', 'style']
            });
            if (!sroot.__geckoScanSliderEventsV5) {
                sroot.__geckoScanSliderEventsV5 = true;
                ['input', 'change', 'mousedown', 'mousemove', 'mouseup',
                 'touchstart', 'touchmove', 'touchend', 'keydown', 'keyup'].forEach(function (name) {
                    sroot.addEventListener(name, scheduleSync, true);
                });
            }
        }
        scheduleSync();
    }

    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('touchmove', onMove, true);
    document.addEventListener('mouseup', onUp, true);
    document.addEventListener('touchend', onUp, true);
    document.addEventListener('touchcancel', onUp, true);
    window.addEventListener('resize', scheduleSync, true);
    window.addEventListener('scroll', scheduleSync, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { setTimeout(install, 250); });
    } else {
        setTimeout(install, 250);
    }
    new MutationObserver(install).observe(document.body, { childList: true, subtree: true });
})();
