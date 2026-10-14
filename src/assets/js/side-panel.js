/*
 * side-panel.js
 * The Views panel to the right of the plot: drag its left edge to resize, click the arrow (or double-click the
 * edge) to hide it, click the slim bar to bring it back. Width and state are remembered per browser.
 * It also reopens itself when a tab inside it is chosen while it is hidden (for example "Show mass" on a peak).
 */
(function () {
    'use strict';
    var KEY = 'gecko.sidePanel';
    var MIN = 280;
    var state = { width: 0, collapsed: false };
    try { state = Object.assign(state, JSON.parse(window.localStorage.getItem(KEY) || '{}')); } catch (e) { /* defaults */ }

    function maxWidth() { return Math.max(MIN, Math.min(900, Math.round(window.innerWidth * 0.6))); }
    function clamp(width) { return Math.max(MIN, Math.min(maxWidth(), Math.round(width))); }
    function defaultWidth() { return Math.max(MIN, Math.min(420, Math.round(window.innerWidth * 0.26))); }

    function save() {
        try { window.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* not persisted */ }
    }

    function refreshPlots() {
        window.requestAnimationFrame(function () { window.dispatchEvent(new Event('resize')); });
    }

    function apply(panel, divider) {
        if (!state.width) state.width = defaultWidth();
        panel.style.width = state.collapsed ? '' : clamp(state.width) + 'px';
        panel.classList.toggle('collapsed', state.collapsed);
        divider.setAttribute('aria-expanded', state.collapsed ? 'false' : 'true');
        refreshPlots();
    }

    function setCollapsed(panel, divider, collapsed) {
        state.collapsed = collapsed;
        save();
        apply(panel, divider);
    }

    function install() {
        var panel = document.getElementById('side-panel');
        var divider = document.getElementById('side-divider');
        if (!panel || !divider || panel.__geckoSideInstalled) return !!panel;
        panel.__geckoSideInstalled = true;
        apply(panel, divider);

        var dragging = false;
        divider.addEventListener('mousedown', function (event) {
            if (event.button !== 0 || state.collapsed) return;
            dragging = true;
            event.preventDefault();
            document.body.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
        });
        document.addEventListener('mousemove', function (event) {
            if (!dragging) return;
            state.width = clamp(window.innerWidth - event.clientX);
            panel.style.width = state.width + 'px';
        });
        document.addEventListener('mouseup', function () {
            if (!dragging) return;
            dragging = false;
            document.body.classList.remove('dragging');
            document.body.style.cursor = '';
            save();
            refreshPlots();
        });
        divider.addEventListener('dblclick', function () { setCollapsed(panel, divider, !state.collapsed); });
        divider.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setCollapsed(panel, divider, !state.collapsed); }
            else if (!state.collapsed && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
                event.preventDefault();
                state.width = clamp((state.width || defaultWidth()) + (event.key === 'ArrowLeft' ? 24 : -24));
                save();
                apply(panel, divider);
            }
        });
        document.addEventListener('click', function (event) {
            var target = event.target && event.target.closest ? event.target : null;
            if (!target) return;
            if (target.closest('#side-panel-collapse')) setCollapsed(panel, divider, true);
            else if (target.closest('#side-panel-rail')) setCollapsed(panel, divider, false);
        });
        window.addEventListener('resize', function () {
            if (!state.collapsed && panel.style.width) panel.style.width = clamp(state.width) + 'px';
        });

        // A tab chosen while the panel is hidden (also by a button elsewhere) brings it back.
        var ready = false;
        window.setTimeout(function () { ready = true; }, 1500);
        var tabs = document.getElementById('side-tabs');
        if (tabs && window.MutationObserver) {
            new MutationObserver(function () {
                if (ready && state.collapsed) setCollapsed(panel, divider, false);
            }).observe(tabs, { attributes: true, subtree: true, attributeFilter: ['aria-selected', 'data-active'] });
        }
        return true;
    }

    window.GeckoSidePanel = { state: state, clamp: clamp, install: install };
    var tries = 0;
    var timer = window.setInterval(function () {
        tries += 1;
        if (install() || tries > 100) window.clearInterval(timer);
    }, 150);
})();
