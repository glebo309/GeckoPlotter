/*
 * side-panel.js
 * The Views panel to the right of the plot. Drag its left edge to resize; the arrow in its tab row (or a
 * double-click on the edge) hides it. Hidden, it behaves like every other panel dragged shut: hovering the right
 * edge shows a dark "Views" label, a click brings the panel back. Width and state are remembered per browser.
 * It also reopens when one of its tabs is chosen while hidden (for example "Show mass" on a peak).
 */
(function () {
    'use strict';
    var KEY = 'gecko.sidePanel';
    var MIN = 280;
    var DOCK = 46;                       // same hover band as the other docks (resize-handler.js)
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

    function hoverZone(divider) {
        var zone = divider.querySelector('.divider-hover-zone');
        if (!zone) {
            zone = document.createElement('div');
            zone.className = 'divider-hover-zone';
            divider.appendChild(zone);
        }
        return zone;
    }

    function apply(panel, divider) {
        if (!state.width) state.width = defaultWidth();
        var label = divider.querySelector('.divider-label');
        hoverZone(divider);
        panel.style.display = state.collapsed ? 'none' : '';
        panel.style.width = state.collapsed ? '' : clamp(state.width) + 'px';
        divider.classList.toggle('has-label', state.collapsed);
        divider.classList.toggle('hidden-second', state.collapsed);
        if (!state.collapsed) divider.classList.remove('dock-hover');
        if (label) {
            label.textContent = state.collapsed ? 'Views' : '';
            ['visible', 'collapsed-state', 'collapse-left'].forEach(function (name) {
                label.classList.toggle(name, state.collapsed);
            });
        }
        if (state.collapsed) {
            divider.style.setProperty('--dock-width', DOCK + 'px');
            divider.style.setProperty('--dock-height', Math.max(1, Math.round(divider.getBoundingClientRect().height)) + 'px');
        } else {
            divider.style.removeProperty('--dock-width');
            divider.style.removeProperty('--dock-height');
        }
        divider.setAttribute('aria-expanded', state.collapsed ? 'false' : 'true');
        divider.title = state.collapsed ? 'Show Views' : 'Drag to resize. Double-click to hide.';
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

        var label = divider.querySelector('.divider-label');
        if (label) {
            label.addEventListener('mousedown', function (event) { event.stopPropagation(); });
            label.addEventListener('click', function (event) {
                event.stopPropagation();
                setCollapsed(panel, divider, false);
            });
        }

        var dragging = false;
        divider.addEventListener('mousedown', function (event) {
            if (event.button !== 0 || state.collapsed) return;
            dragging = true;
            event.preventDefault();
            document.body.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
        });
        document.addEventListener('mousemove', function (event) {
            if (dragging) {
                var wanted = window.innerWidth - event.clientX;
                if (wanted < MIN / 2) {
                    // Dragged well past its smallest width: hide it, like the other panels dragged shut.
                    dragging = false;
                    document.body.classList.remove('dragging');
                    document.body.style.cursor = '';
                    setCollapsed(panel, divider, true);
                    return;
                }
                state.width = clamp(wanted);
                panel.style.width = state.width + 'px';
                return;
            }
            if (!state.collapsed) return;
            // The soft band left of the edge lights up like the other docks.
            var rect = divider.getBoundingClientRect();
            var near = event.clientX >= rect.left - DOCK && event.clientX <= rect.right &&
                event.clientY >= rect.top && event.clientY <= rect.bottom;
            divider.classList.toggle('dock-hover', near);
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
            var target = event.target && event.target.closest ? event.target.closest('[data-hide-panel="side"]') : null;
            if (target) setCollapsed(panel, divider, true);
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
