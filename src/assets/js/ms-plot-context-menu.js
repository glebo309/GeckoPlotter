/**
 * Right-click on MS/EIC analysis graphs -> publish to ms-plot-context-menu-store.
 *
 * Uses document-level event delegation so it works even when the MS Analysis
 * tab is first opened (graphs aren't in DOM at page load).
 */
(function () {
    'use strict';

    var GRAPH_IDS = {
        'ms-spectrum-graph': true,
        'peak-mass-graph': true,
        'eic-graph': true
    };

    function publish(source, clientX, clientY) {
        var dc = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!dc || typeof dc.set_props !== 'function') return;
        dc.set_props('ms-plot-context-menu-store', {
            data: { source: source, x: clientX, y: clientY, ts: Date.now() }
        });
    }

    function bumpClose() {
        var dc = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!dc || typeof dc.set_props !== 'function') return;
        dc.set_props('ms-plot-context-menu', { opened: false });
        dc.set_props('ms-plot-context-menu-close-store', { data: Date.now() });
    }

    function findGraphId(target) {
        var el = target;
        while (el && el !== document.body) {
            if (el.id && GRAPH_IDS[el.id]) return el.id;
            el = el.parentElement;
        }
        return null;
    }

    document.addEventListener('contextmenu', function (event) {
        var graphId = findGraphId(event.target);
        if (!graphId) return;
        event.preventDefault();
        event.stopPropagation();
        if (typeof event.stopImmediatePropagation === 'function') {
            event.stopImmediatePropagation();
        }
        publish(graphId, event.clientX, event.clientY);
    }, true);

    // Dismiss on outside click
    document.addEventListener('mousedown', function (e) {
        var dropdown = document.getElementById('ms-plot-context-dropdown');
        if (!dropdown || dropdown.offsetParent === null) return;
        if (!dropdown.contains(e.target)) bumpClose();
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') bumpClose();
    });
    document.addEventListener('scroll', bumpClose, true);
})();
