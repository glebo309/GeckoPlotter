/**
 * Right-click plot customization entry points.
 *
 * Proof of concept: right-clicking the main plot X-axis publishes an
 * axis-context-menu-store event. Dash renders the actual editor so values stay
 * synchronized with current-plot-settings.
 */
(function () {
    'use strict';

    var GRAPH_ID = 'main-plot';
    var AXIS_BAND_PX = 70;

    function dashSetProps(id, props) {
        var clientside = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!clientside || typeof clientside.set_props !== 'function') return false;
        clientside.set_props(id, props);
        return true;
    }

    function getGraphDiv() {
        return document.querySelector('#' + GRAPH_ID + ' .js-plotly-plot');
    }

    function plotBounds(gd, key, subplot) {
        if (!gd || !gd._fullLayout || !subplot) return null;
        var xa = subplot.xaxis;
        var ya = subplot.yaxis;
        var svg = gd.querySelector('.main-svg');
        if (!xa || !ya || !svg) return null;
        var svgRect = svg.getBoundingClientRect();
        var left = svgRect.left + (xa._offset || 0);
        var top = svgRect.top + (ya._offset || 0);
        var width = xa._length || 0;
        var height = ya._length || 0;
        if (!width || !height) return null;
        return {
            key: key,
            left: left,
            right: left + width,
            top: top,
            bottom: top + height,
            width: width,
            height: height
        };
    }

    function xAxisAtEvent(gd, event) {
        if (!gd || !gd._fullLayout || !event) return null;
        var plots = gd._fullLayout._plots || {};
        var gdRect = gd.getBoundingClientRect();

        for (var key in plots) {
            if (!Object.prototype.hasOwnProperty.call(plots, key)) continue;
            var bounds = plotBounds(gd, key, plots[key]);
            if (!bounds) continue;

            var bandTop = bounds.bottom - 8;
            var bandBottom = Math.min(gdRect.bottom, bounds.bottom + AXIS_BAND_PX);
            var inX = event.clientX >= bounds.left && event.clientX <= bounds.right;
            var inY = event.clientY >= bandTop && event.clientY <= bandBottom;
            if (inX && inY) {
                return {axis: 'x', subplot: key};
            }
        }

        return null;
    }

    function openAxisContextMenu(gd, event) {
        var hit = xAxisAtEvent(gd, event);
        if (!hit || hit.axis !== 'x') return false;

        event.preventDefault();
        event.stopPropagation();

        dashSetProps('context-menu-close-store', {data: Date.now()});
        dashSetProps('axis-context-menu-store', {
            data: {
                axis: 'x',
                subplot: hit.subplot,
                x: event.clientX,
                y: event.clientY,
                viewport_width: window.innerWidth || document.documentElement.clientWidth,
                viewport_height: window.innerHeight || document.documentElement.clientHeight,
                ts: Date.now()
            }
        });
        return true;
    }

    function isAxisPanelOpen() {
        var panel = document.getElementById('axis-context-panel');
        return panel && panel.offsetParent !== null && panel.style.display !== 'none';
    }

    function closeAxisPanel() {
        dashSetProps('axis-context-menu-close-store', {data: Date.now()});
    }

    function install() {
        var gd = getGraphDiv();
        if (!gd) {
            window.setTimeout(install, 250);
            return;
        }
        if (gd.__geckoAxisContextMenuInstalled) return;

        gd.addEventListener('contextmenu', function (event) {
            openAxisContextMenu(gd, event);
        }, true);

        gd.__geckoAxisContextMenuInstalled = true;
    }

    document.addEventListener('mousedown', function (event) {
        if (!isAxisPanelOpen()) return;
        var panel = document.getElementById('axis-context-panel');
        if (panel && !panel.contains(event.target)) {
            closeAxisPanel();
        }
    }, true);

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && isAxisPanelOpen()) {
            closeAxisPanel();
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.setTimeout(install, 0);
    } else {
        document.addEventListener('DOMContentLoaded', install);
    }
    window.addEventListener('load', function () { window.setTimeout(install, 100); });
})();
