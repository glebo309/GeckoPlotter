/**
 * Right-click plot customization entry points.
 *
 * Proof of concept: right-clicking the main plot axes publishes an
 * axis-context-menu-store event. Dash renders the actual editor so values stay
 * synchronized with current-plot-settings.
 */
(function () {
    'use strict';

    var GRAPH_ID = 'main-plot';
    var AXIS_BAND_PX = 70;
    var lastCloseAt = 0;

    function dashSetProps(id, props) {
        var clientside = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!clientside || typeof clientside.set_props !== 'function') return false;
        clientside.set_props(id, props);
        return true;
    }

    function getGraphDiv() {
        if (window.geckoActivePlot) return window.geckoActivePlot();
        return document.querySelector('#' + GRAPH_ID + ' .js-plotly-plot');
    }

    function panelIsOpen(id) {
        var panel = document.getElementById(id);
        if (!panel) return false;
        var style = window.getComputedStyle ? window.getComputedStyle(panel) : panel.style;
        return style.display !== 'none' && style.visibility !== 'hidden';
    }

    function closeContextPanel(panelId, storeId, now) {
        var panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'none';
        dashSetProps(storeId, {data: now});
    }

    function withCloseGuard(callback) {
        var now = Date.now ? Date.now() : new Date().getTime();
        if (now - lastCloseAt < 40) return;
        lastCloseAt = now;
        callback(now);
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

    function axisAtEvent(gd, event) {
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

            var bandLeft = Math.max(gdRect.left, bounds.left - AXIS_BAND_PX);
            var bandRight = bounds.left + 8;
            var inYBand = event.clientY >= bounds.top && event.clientY <= bounds.bottom;
            var inYAxis = event.clientX >= bandLeft && event.clientX <= bandRight;
            if (inYBand && inYAxis) {
                return {axis: 'y', subplot: key};
            }
        }

        return null;
    }

    function openAxisContextMenu(gd, event) {
        var hit = axisAtEvent(gd, event);
        if (!hit || (hit.axis !== 'x' && hit.axis !== 'y')) return false;

        event.preventDefault();
        event.stopPropagation();

        dashSetProps('context-menu-close-store', {data: Date.now()});
        dashSetProps('axis-context-menu-store', {
            data: {
                axis: hit.axis,
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

    // Separate subplots each have a legend of their own: g.legend, g.legend2, g.legend3 ...
    function legendOf(element) {
        for (var node = element; node && node.getAttribute; node = node.parentNode) {
            if (/^legend\d*$/.test(node.getAttribute('class') || '')) return node;
        }
        return null;
    }

    function openLegendContextMenu(gd, event) {
        if (!gd || !event || !event.target || !event.target.closest) return false;
        var legend = legendOf(event.target);
        if (!legend || !gd.contains(legend)) return false;

        event.preventDefault();
        event.stopPropagation();

        dashSetProps('context-menu-close-store', {data: Date.now()});
        dashSetProps('axis-context-menu-close-store', {data: Date.now()});
        dashSetProps('legend-context-menu-store', {
            data: {
                target: 'legend',
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
        return panelIsOpen('axis-context-panel');
    }

    function isAnyContextPanelOpen() {
        return panelIsOpen('axis-context-panel') ||
            panelIsOpen('legend-context-panel') ||
            panelIsOpen('trace-context-panel') ||
            panelIsOpen('title-context-panel') ||
            panelIsOpen('label-context-panel');
    }

    function closeAxisPanel() {
        withCloseGuard(function (now) {
            closeContextPanel('axis-context-panel', 'axis-context-menu-close-store', now);
        });
    }

    function closeLegendPanel() {
        withCloseGuard(function (now) {
            closeContextPanel('legend-context-panel', 'legend-context-menu-close-store', now);
        });
    }

    function closeTracePanel() {
        withCloseGuard(function (now) {
            closeContextPanel('trace-context-panel', 'trace-context-menu-close-store', now);
        });
    }

    function closeOpenContextPanels() {
        withCloseGuard(function (now) {
            if (panelIsOpen('axis-context-panel')) {
                closeContextPanel('axis-context-panel', 'axis-context-menu-close-store', now);
            }
            if (panelIsOpen('legend-context-panel')) {
                closeContextPanel('legend-context-panel', 'legend-context-menu-close-store', now);
            }
            if (panelIsOpen('trace-context-panel')) {
                closeContextPanel('trace-context-panel', 'trace-context-menu-close-store', now);
            }
            if (panelIsOpen('title-context-panel')) {
                closeContextPanel('title-context-panel', 'title-context-menu-close-store', now);
            }
            if (panelIsOpen('label-context-panel')) {
                closeContextPanel('label-context-panel', 'label-context-menu-close-store', now);
            }
        });
    }

    function isEditableTarget(target) {
        if (!target) return false;
        var tag = (target.tagName || '').toLowerCase();
        return tag === 'input' ||
            tag === 'textarea' ||
            tag === 'select' ||
            target.isContentEditable;
    }

    function blockLegendRightClick(event) {
        if (event.button !== 2) return;
        if (!event.target || !event.target.closest) return;
        var gd = getGraphDiv();
        if (!gd) return;
        var legend = legendOf(event.target);
        if (legend && gd.contains(legend)) {
            event.stopImmediatePropagation();
        }
    }

    function _isPeakOverlay(traceObj) {
        var name = traceObj.name || '';
        var meta = traceObj.meta;
        return traceObj.fill || meta === 'peak_overlay' || meta === 'deconv_overlay' ||
            name.indexOf('peak:') === 0 || name === '__deselect__' ||
            name.toLowerCase().indexOf('baseline') !== -1;
    }

    function _clickInsidePeakPolygon(gd, event) {
        if (!gd || !gd.data || !gd._fullLayout) return false;
        var rect = gd.getBoundingClientRect();
        var cx = event.clientX - rect.left;
        var cy = event.clientY - rect.top;
        var plots = gd._fullLayout._plots || {};
        for (var k in plots) {
            var pa = plots[k].xaxis;
            var ya = plots[k].yaxis;
            if (!pa || !ya) continue;
            var dataX = pa.p2d(cx - pa._offset);
            for (var i = 0; i < gd.data.length; i++) {
                var t = gd.data[i];
                if (t.meta !== 'peak_overlay' || t.fill !== 'toself') continue;
                var xs = t.x;
                if (!xs || xs.length < 3) continue;
                var xMin = Infinity, xMax = -Infinity;
                for (var j = 0; j < xs.length; j++) {
                    if (xs[j] != null) { xMin = Math.min(xMin, xs[j]); xMax = Math.max(xMax, xs[j]); }
                }
                if (dataX >= xMin && dataX <= xMax) return true;
            }
            break;
        }
        return false;
    }

    function traceAtEvent(gd, event) {
        if (!gd || !gd.data) return null;
        if (_clickInsidePeakPolygon(gd, event)) return null;
        // Use Plotly's hover data -- set whenever the cursor is near a trace.
        // Plotly's closest-mode hover has generous proximity, so this fires
        // even when the cursor isn't pixel-perfect on the thin line.
        var hoverData = gd._hoverdata;
        if (!hoverData || !hoverData.length) return null;
        var point = hoverData[0];
        var curveNumber = point.curveNumber;
        if (curveNumber == null || curveNumber < 0 || curveNumber >= gd.data.length) return null;
        var name = gd.data[curveNumber].name || '';
        var traceObj = gd.data[curveNumber];
        // Skip peak overlay traces
        if (_isPeakOverlay(traceObj)) {
            return null;
        }
        // Count data-trace index (skipping peak traces) for palette color lookup
        var dataIdx = 0;
        for (var i = 0; i < curveNumber; i++) {
            if (_isPeakOverlay(gd.data[i])) continue;
            dataIdx++;
        }
        return {curve_number: dataIdx, trace_name: name};
    }

    function titleAtEvent(gd, event) {
        if (!event || !event.target) return null;
        var el = event.target;
        // Check if clicking directly on an existing title text element
        var tag = (el.tagName || '').toLowerCase();
        if (tag === 'text' || tag === 'tspan') {
            var textEl = tag === 'tspan' ? el.parentElement : el;
            if (textEl && gd.contains(textEl)) {
                var cls = textEl.getAttribute('class') || '';
                if (cls.indexOf('gtitle') !== -1) return {target: 'title'};
            }
        }
        // If no title text exists, detect click in the top margin area
        // (above the plot area, where the title would appear)
        var plots = gd._fullLayout ? gd._fullLayout._plots || {} : {};
        var svg = gd.querySelector('.main-svg');
        if (!svg) return null;
        var svgRect = svg.getBoundingClientRect();
        var topOfPlot = svgRect.bottom;
        for (var key in plots) {
            if (!Object.prototype.hasOwnProperty.call(plots, key)) continue;
            var sp = plots[key];
            if (sp.yaxis && sp.yaxis._offset != null) {
                var plotTop = svgRect.top + sp.yaxis._offset;
                if (plotTop < topOfPlot) topOfPlot = plotTop;
            }
        }
        // Title area: from top of SVG to top of plot area
        if (event.clientY >= svgRect.top && event.clientY < topOfPlot &&
            event.clientX >= svgRect.left && event.clientX <= svgRect.right) {
            return {target: 'title'};
        }
        return null;
    }

    function labelAtEvent(gd, event) {
        if (!event || !event.target) return null;
        var el = event.target;
        var tag = (el.tagName || '').toLowerCase();
        if (tag !== 'text' && tag !== 'tspan') return null;
        var textEl = tag === 'tspan' ? el.parentElement : el;
        if (!textEl || !gd.contains(textEl)) return null;
        var cls = textEl.getAttribute('class') || '';
        if (cls.indexOf('xtitle') !== -1) return {axis: 'x'};
        if (cls.indexOf('ytitle') !== -1) return {axis: 'y'};
        return null;
    }

    function openLabelContextMenu(gd, event) {
        var hit = labelAtEvent(gd, event);
        if (!hit) return false;

        event.preventDefault();
        event.stopPropagation();

        var allClose = Date.now();
        dashSetProps('context-menu-close-store', {data: allClose});
        dashSetProps('axis-context-menu-close-store', {data: allClose});
        dashSetProps('legend-context-menu-close-store', {data: allClose});
        dashSetProps('trace-context-menu-close-store', {data: allClose});
        dashSetProps('title-context-menu-close-store', {data: allClose});
        dashSetProps('label-context-menu-store', {
            data: {
                axis: hit.axis,
                x: event.clientX,
                y: event.clientY,
                viewport_width: window.innerWidth || document.documentElement.clientWidth,
                viewport_height: window.innerHeight || document.documentElement.clientHeight,
                ts: Date.now()
            }
        });
        return true;
    }

    function openTitleContextMenu(gd, event) {
        var hit = titleAtEvent(gd, event);
        if (!hit) return false;

        event.preventDefault();
        event.stopPropagation();

        var allClose = Date.now();
        dashSetProps('context-menu-close-store', {data: allClose});
        dashSetProps('axis-context-menu-close-store', {data: allClose});
        dashSetProps('legend-context-menu-close-store', {data: allClose});
        dashSetProps('trace-context-menu-close-store', {data: allClose});
        dashSetProps('label-context-menu-close-store', {data: allClose});
        dashSetProps('title-context-menu-store', {
            data: {
                target: hit.target,
                x: event.clientX,
                y: event.clientY,
                viewport_width: window.innerWidth || document.documentElement.clientWidth,
                viewport_height: window.innerHeight || document.documentElement.clientHeight,
                ts: Date.now()
            }
        });
        return true;
    }

    function openTraceContextMenu(gd, event) {
        var hit = traceAtEvent(gd, event);
        if (!hit) return false;

        event.preventDefault();
        event.stopPropagation();

        dashSetProps('context-menu-close-store', {data: Date.now()});
        dashSetProps('axis-context-menu-close-store', {data: Date.now()});
        dashSetProps('legend-context-menu-close-store', {data: Date.now()});
        dashSetProps('trace-context-menu-store', {
            data: {
                curve_number: hit.curve_number,
                trace_name: hit.trace_name,
                x: event.clientX,
                y: event.clientY,
                viewport_width: window.innerWidth || document.documentElement.clientWidth,
                viewport_height: window.innerHeight || document.documentElement.clientHeight,
                ts: Date.now()
            }
        });
        return true;
    }

    function install() {
        var gd = getGraphDiv();
        if (!gd) {
            window.setTimeout(install, 250);
            return;
        }
        if (gd.__geckoAxisContextMenuInstalled) return;

        gd.addEventListener('contextmenu', function (event) {
            if (openLabelContextMenu(gd, event)) return;
            if (openTitleContextMenu(gd, event)) return;
            if (openLegendContextMenu(gd, event)) return;
            if (openAxisContextMenu(gd, event)) return;
            openTraceContextMenu(gd, event);
        }, true);

        gd.__geckoAxisContextMenuInstalled = true;
    }

    // Block Plotly legend-click on right-click at document level so it fires
    // before any handler Plotly attaches to SVG legend elements.
    document.addEventListener('pointerdown', blockLegendRightClick, true);
    document.addEventListener('mousedown', blockLegendRightClick, true);

    function handleOutsidePanelPointer(event) {
        if (!isAnyContextPanelOpen()) return;
        var axisPanel = document.getElementById('axis-context-panel');
        var legendPanel = document.getElementById('legend-context-panel');
        var tracePanel = document.getElementById('trace-context-panel');
        var titlePanel = document.getElementById('title-context-panel');
        var labelPanel = document.getElementById('label-context-panel');
        var insideAxis = axisPanel && axisPanel.contains(event.target);
        var insideLegend = legendPanel && legendPanel.contains(event.target);
        var insideTrace = tracePanel && tracePanel.contains(event.target);
        var insideTitle = titlePanel && titlePanel.contains(event.target);
        var insideLabel = labelPanel && labelPanel.contains(event.target);
        // Mantine Select/ColorInput dropdowns portal to body — detect via ARIA
        // roles and data attributes (Mantine v7 uses hashed class names, not BEM).
        var t = event.target;
        var inPortaledDropdown = t && t.closest && (
            t.closest('[role="listbox"]') ||
            t.closest('[data-combobox-option]') ||
            t.closest('[data-combobox-dropdown]') ||
            t.closest('.mantine-ColorPicker-wrapper') ||
            t.closest('[data-floating-ui-portal]')
        );
        if (!insideAxis && !insideLegend && !insideTrace && !insideTitle && !insideLabel && !inPortaledDropdown) {
            closeOpenContextPanels();
        }
    }

    document.addEventListener('pointerdown', handleOutsidePanelPointer, true);
    document.addEventListener('mousedown', handleOutsidePanelPointer, true);
    document.addEventListener('click', handleOutsidePanelPointer, true);

    document.addEventListener('keydown', function (event) {
        if (!isAnyContextPanelOpen()) return;
        var key = event.key || '';
        var shortcutClose = key === 'Escape' ||
            (!isEditableTarget(event.target) && key.toLowerCase() === 'x');
        if (shortcutClose) {
            closeOpenContextPanels();
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.setTimeout(install, 0);
    } else {
        document.addEventListener('DOMContentLoaded', install);
    }
    window.addEventListener('load', function () { window.setTimeout(install, 100); });
    document.addEventListener('gecko:plot-ready', install);
})();
