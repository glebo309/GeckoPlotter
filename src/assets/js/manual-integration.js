// Manual integration helpers that need direct Plotly DOM access.
(function () {
    'use strict';

    function getGraphDiv(graphId) {
        var root = document.getElementById(graphId);
        if (!root) return null;
        return root.querySelector('.js-plotly-plot') || root;
    }

    function graphDivFromEvent(event) {
        if (!event || !event.target || typeof event.target.closest !== 'function') return null;
        var gd = event.target.closest('.js-plotly-plot');
        if (gd && gd.id === 'main-plot') return gd;
        var root = event.target.closest('#main-plot');
        if (!root) return null;
        return root.querySelector('.js-plotly-plot') || root;
    }

    function clearTransientShapes(graphId) {
        var gd = getGraphDiv(graphId);
        if (!gd || !window.Plotly || !gd.layout) return;

        var shapes = gd.layout.shapes || [];
        var kept = shapes.filter(function (shape) {
            return shape && typeof shape.name === 'string' && shape.name.indexOf('baseline:') === 0;
        });

        if (kept.length !== shapes.length) {
            window.Plotly.relayout(gd, { shapes: kept });
        }
    }

    function syncSelectedShape(graphId, selectedPeakId) {
        var gd = getGraphDiv(graphId);
        if (!gd || !window.Plotly || !gd.layout) return;
        gd.__geckoManualIntegrationSelectedPeakId = selectedPeakId || null;

        var shapes = gd.layout.shapes || [];
        var kept = [];

        if (selectedPeakId) {
            var wantedName = 'baseline:' + selectedPeakId;
            kept = shapes.filter(function (shape) {
                return shape && shape.name === wantedName;
            });
            kept = kept.length ? [kept[kept.length - 1]] : [];
        }

        if (kept.length !== shapes.length || (kept[0] && shapes[0] && kept[0].name !== shapes[0].name)) {
            window.Plotly.relayout(gd, { shapes: kept });
        }
        syncInteractionDragmode(gd);
    }

    function syncInteractionDragmode(gd) {
        if (!gd || !window.Plotly) return;
        var dragmode = 'zoom';
        if (
            gd.__geckoManualIntegrationSelectedPeakId ||
            gd.__geckoManualIntegrationSuspendDrawUntilMouseUp ||
            gd.__geckoManualIntegrationDrawing
        ) {
            dragmode = false;
        }
        var update = {
            dragmode: dragmode
        };
        window.Plotly.relayout(gd, update);
    }

    function syncDrawMode(graphId, mode) {
        var gd = getGraphDiv(graphId);
        if (!gd || !window.Plotly) return;
        gd.__geckoManualIntegrationMode = mode;
        syncInteractionDragmode(gd);
    }

    function pointPeakId(point) {
        if (!point) return null;
        var custom = point.customdata;
        if (Array.isArray(custom)) {
            if (custom[0] === '__deselect__') return null;
            return custom[0] || null;
        }
        return custom && custom !== '__deselect__' ? custom : null;
    }

    function eventPeakId(eventData) {
        if (!eventData || !eventData.points || !eventData.points.length) return null;
        return pointPeakId(eventData.points[0]);
    }

    function axisPixelToData(axis, pixel, span, reversed) {
        if (!axis) return null;
        if (typeof axis.p2d === 'function') return axis.p2d(pixel);
        if (typeof axis.p2c === 'function' && typeof axis.c2d === 'function') return axis.c2d(axis.p2c(pixel));
        var range = axis.range || [];
        if (range.length !== 2 || !isFinite(range[0]) || !isFinite(range[1]) || !span) return null;
        var t = pixel / span;
        if (reversed) t = 1 - t;
        return range[0] + (range[1] - range[0]) * t;
    }

    function pointInPolygon(x, y, polyX, polyY) {
        var inside = false;
        for (var i = 0, j = polyX.length - 1; i < polyX.length; j = i++) {
            var xi = Number(polyX[i]);
            var yi = Number(polyY[i]);
            var xj = Number(polyX[j]);
            var yj = Number(polyY[j]);
            if (!isFinite(xi) || !isFinite(yi) || !isFinite(xj) || !isFinite(yj)) continue;
            var intersects = ((yi > y) !== (yj > y)) &&
                (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
            if (intersects) inside = !inside;
        }
        return inside;
    }

    function peakIdAtEvent(gd, event) {
        if (!gd || !gd.data) return null;
        var sp = subplotAtEvent(gd, event);
        if (!sp) return null;
        var x = axisPixelToData(sp.xaxis, event.clientX - sp.bounds.left, sp.bounds.width, false);
        var y = axisPixelToData(sp.yaxis, event.clientY - sp.bounds.top, sp.bounds.height, true);
        if (x === null || y === null || !isFinite(Number(x)) || !isFinite(Number(y))) return null;

        for (var i = gd.data.length - 1; i >= 0; i--) {
            var trace = gd.data[i];
            if (!trace || trace.meta !== 'peak_overlay' || trace.fill !== 'toself' || !trace.x || !trace.y) continue;
            var peakId = null;
            if (Array.isArray(trace.customdata) && trace.customdata.length) {
                peakId = Array.isArray(trace.customdata[0]) ? trace.customdata[0][0] : trace.customdata[0];
            }
            if (!peakId || peakId === '__deselect__') continue;
            if (pointInPolygon(Number(x), Number(y), trace.x, trace.y)) return peakId;
        }
        return null;
    }

    function publishAction(type, payload) {
        var dashClientside = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!dashClientside || typeof dashClientside.set_props !== 'function') return;
        dashClientside.set_props('interaction-action-store', {
            data: { type: type, payload: payload || {}, ts: Date.now() }
        });
    }

    function publishPeakClick(peakId) {
        var dashClientside = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!peakId || !dashClientside || typeof dashClientside.set_props !== 'function') {
            return false;
        }
        dashClientside.set_props('plot-peak-click-store', {
            data: { peakId: peakId, ts: Date.now() }
        });
        publishAction('select', { peakId: peakId });
        return true;
    }

    function publishDrawLine(line) {
        var dashClientside = window.dash_clientside ||
            (window.parent && window.parent !== window ? window.parent.dash_clientside : null);
        if (!line || !dashClientside || typeof dashClientside.set_props !== 'function') {
            return false;
        }
        var lineData = {
            x0: line.x0,
            y0: line.y0,
            x1: line.x1,
            y1: line.y1,
            subplot: line.subplot || 'xy',
            momentary: !!line.momentary,
            ts: Date.now()
        };
        dashClientside.set_props('manual-draw-line-store', { data: lineData });
        publishAction('draw', { x0: line.x0, y0: line.y0, x1: line.x1, y1: line.y1, subplot: lineData.subplot });
        return true;
    }

    function resetAxes(gd) {
        if (!window.Plotly || !gd || !gd._fullLayout) return;
        var reset = {};
        Object.keys(gd._fullLayout).forEach(function (key) {
            if (/^[xy]axis[0-9]*$/.test(key)) {
                reset[key + '.autorange'] = true;
            }
        });
        window.Plotly.relayout(gd, reset);
        publishAction('reset-axes', {});
    }

    function clearEmptyClickTimer(gd) {
        if (gd.__geckoManualIntegrationEmptyClickTimer) {
            window.clearTimeout(gd.__geckoManualIntegrationEmptyClickTimer);
            gd.__geckoManualIntegrationEmptyClickTimer = null;
        }
    }

    function isInsidePlotArea(gd, event) {
        return subplotAtEvent(gd, event) !== null;
    }

    function dataPointAtEvent(gd, event) {
        var sp = subplotAtEvent(gd, event);
        if (!sp) return null;
        var x = axisPixelToData(sp.xaxis, event.clientX - sp.bounds.left, sp.bounds.width, false);
        var y = axisPixelToData(sp.yaxis, event.clientY - sp.bounds.top, sp.bounds.height, true);
        if (x === null || y === null || !isFinite(Number(x)) || !isFinite(Number(y))) return null;
        return { x: Number(x), y: Number(y), subplot: sp.key };
    }

    function axisRange(axis) {
        if (!axis || !axis.range || axis.range.length !== 2) return null;
        var start = Number(axis.range[0]);
        var end = Number(axis.range[1]);
        if (!isFinite(start) || !isFinite(end)) return null;
        return [start, end];
    }

    function subplotAtEvent(gd, event) {
        if (!gd || !gd._fullLayout || !event) return null;

        // Collect all .nsewdrag rects and match the one under the pointer
        var allDrags = gd.querySelectorAll('.nsewdrag');
        var hitDrag = null;
        var hitBounds = null;
        for (var d = 0; d < allDrags.length; d++) {
            var b = allDrags[d].getBoundingClientRect();
            if (event.clientX >= b.left && event.clientX <= b.right &&
                event.clientY >= b.top && event.clientY <= b.bottom) {
                hitDrag = allDrags[d];
                hitBounds = b;
                break;
            }
        }
        if (!hitDrag) return null;

        // Try to find which subplot owns this drag rect
        var plots = gd._fullLayout._plots;
        if (plots) {
            for (var key in plots) {
                if (!plots.hasOwnProperty(key)) continue;
                var subplot = plots[key];
                // plotgroup may be a D3 selection or DOM node
                var groupNode = subplot.plotgroup;
                if (groupNode && typeof groupNode.node === 'function') groupNode = groupNode.node();
                if (groupNode && groupNode.contains && groupNode.contains(hitDrag)) {
                    return {
                        key: key,
                        xaxis: subplot.xaxis,
                        yaxis: subplot.yaxis,
                        plotArea: hitDrag,
                        bounds: hitBounds
                    };
                }
            }
        }

        // Fallback: single-subplot layout
        return {
            key: 'xy',
            xaxis: gd._fullLayout.xaxis,
            yaxis: gd._fullLayout.yaxis,
            plotArea: hitDrag,
            bounds: hitBounds
        };
    }

    function isPanModifier(event) {
        return !!(event && (event.metaKey || event.ctrlKey));
    }

    function isDrawModifier(event) {
        return !!(event && event.shiftKey);
    }

    function setMomentaryDrawActive(active) {
        var button = document.getElementById('baseline-draw-btn');
        if (!button) return;
        button.classList.toggle('momentary-active', active);
    }

    function syncMomentaryDrawButton(event) {
        var gd = getGraphDiv('main-plot');
        var active = !!(
            event &&
            event.shiftKey &&
            gd &&
            gd.__geckoManualIntegrationMode !== 'draw' &&
            !gd.__geckoManualIntegrationSelectedPeakId
        );
        setMomentaryDrawActive(active);
    }

    function isOverlayTarget(event) {
        return !!(event && event.target && event.target.closest('.scatterlayer, .shapelayer, .hoverlayer'));
    }

    function triggerEmptyClick() {
        var trigger = document.getElementById('plot-empty-click-trigger');
        if (trigger) {
            trigger.click();
        }
        publishAction('deselect', {});
    }

    function stopPlotlyGesture(event) {
        event.preventDefault();
        event.stopPropagation();
        event.__geckoManualIntegrationHandled = true;
        if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();
    }

    function setDragBoxSuppressed(gd, suppressed) {
        if (gd && gd.classList) {
            gd.classList.toggle('gecko-suppress-plotly-dragbox', suppressed);
        }
        if (document.documentElement && document.documentElement.classList) {
            document.documentElement.classList.toggle('gecko-suppress-plotly-dragbox', suppressed);
        }
    }

    function suspendDrawUntilMouseUp(gd) {
        if (!gd || gd.__geckoManualIntegrationSuspendDrawUntilMouseUp) return;
        gd.__geckoManualIntegrationSuspendDrawUntilMouseUp = true;
        setDragBoxSuppressed(gd, true);
        syncInteractionDragmode(gd);

        var release = function () {
            window.removeEventListener('pointerup', release, true);
            window.removeEventListener('mouseup', release, true);
            window.clearTimeout(gd.__geckoManualIntegrationSuspendReleaseTimer);
            window.setTimeout(function () {
                gd.__geckoManualIntegrationSuspendDrawUntilMouseUp = false;
                setDragBoxSuppressed(gd, false);
                syncInteractionDragmode(gd);
            }, 0);
        };

        window.addEventListener('pointerup', release, true);
        window.addEventListener('mouseup', release, true);
        gd.__geckoManualIntegrationSuspendReleaseTimer = window.setTimeout(release, 900);
    }

    function consumeSelectedBlankClick(gd, event) {
        if (
            !gd.__geckoManualIntegrationSelectedPeakId ||
            !isInsidePlotArea(gd, event) ||
            isOverlayTarget(event)
        ) {
            return false;
        }

        suspendDrawUntilMouseUp(gd);
        stopPlotlyGesture(event);
        clearTransientShapes('main-plot');
        gd.__geckoManualIntegrationLastPlotlyClickAt = Date.now();
        clearEmptyClickTimer(gd);

        var now = Date.now();
        if (!gd.__geckoManualIntegrationLastBlankDeselectAt ||
            now - gd.__geckoManualIntegrationLastBlankDeselectAt > 120) {
            gd.__geckoManualIntegrationLastBlankDeselectAt = now;
            triggerEmptyClick();
        }
        return true;
    }

    function previewLineElement() {
        var existing = document.getElementById('gecko-manual-draw-preview');
        if (existing) return existing;

        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('id', 'gecko-manual-draw-preview');
        svg.style.position = 'fixed';
        svg.style.left = '0';
        svg.style.top = '0';
        svg.style.width = '100vw';
        svg.style.height = '100vh';
        svg.style.pointerEvents = 'none';
        svg.style.zIndex = '2147483647';

        var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('stroke', 'rgba(80,80,80,0.75)');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('stroke-dasharray', '4 4');
        line.setAttribute('stroke-linecap', 'round');
        svg.appendChild(line);
        document.body.appendChild(svg);
        return svg;
    }

    function updatePreviewLine(x0, y0, x1, y1) {
        var svg = previewLineElement();
        var line = svg.querySelector('line');
        line.setAttribute('x1', x0);
        line.setAttribute('y1', y0);
        line.setAttribute('x2', x1);
        line.setAttribute('y2', y1);
    }

    function removePreviewLine() {
        var svg = document.getElementById('gecko-manual-draw-preview');
        if (svg && svg.parentNode) svg.parentNode.removeChild(svg);
    }

    function beginCustomDraw(gd, event) {
        if (
            !gd ||
            (gd.__geckoManualIntegrationMode !== 'draw' && !isDrawModifier(event)) ||
            gd.__geckoManualIntegrationSelectedPeakId ||
            !isInsidePlotArea(gd, event) ||
            isOverlayTarget(event)
        ) {
            return false;
        }

        var startData = dataPointAtEvent(gd, event);
        if (!startData) return false;

        stopPlotlyGesture(event);
        gd.__geckoManualIntegrationDrawing = {
            startClientX: event.clientX,
            startClientY: event.clientY,
            startData: startData,
            momentary: isDrawModifier(event) && gd.__geckoManualIntegrationMode !== 'draw'
        };
        if (gd.__geckoManualIntegrationDrawing.momentary) {
            setMomentaryDrawActive(true);
        }
        setDragBoxSuppressed(gd, true);
        syncInteractionDragmode(gd);
        updatePreviewLine(event.clientX, event.clientY, event.clientX, event.clientY);

        var move = function (moveEvent) {
            if (!gd.__geckoManualIntegrationDrawing) return;
            stopPlotlyGesture(moveEvent);
            updatePreviewLine(
                gd.__geckoManualIntegrationDrawing.startClientX,
                gd.__geckoManualIntegrationDrawing.startClientY,
                moveEvent.clientX,
                moveEvent.clientY
            );
        };

        var finish = function (upEvent) {
            if (!gd.__geckoManualIntegrationDrawing) return;
            stopPlotlyGesture(upEvent);

            window.removeEventListener('pointermove', move, true);
            window.removeEventListener('pointerup', finish, true);
            window.removeEventListener('pointercancel', finish, true);

            var drawing = gd.__geckoManualIntegrationDrawing;
            gd.__geckoManualIntegrationDrawing = null;
            removePreviewLine();
            setDragBoxSuppressed(gd, false);
            if (drawing.momentary) {
                setMomentaryDrawActive(false);
            }
            syncInteractionDragmode(gd);

            var distance = Math.hypot(upEvent.clientX - drawing.startClientX, upEvent.clientY - drawing.startClientY);
            var endData = dataPointAtEvent(gd, upEvent);
            if (distance < 4 || !endData) return;

            publishDrawLine({
                x0: drawing.startData.x,
                y0: drawing.startData.y,
                x1: endData.x,
                y1: endData.y,
                subplot: drawing.startData.subplot,
                momentary: drawing.momentary
            });
        };

        window.addEventListener('pointermove', move, true);
        window.addEventListener('pointerup', finish, true);
        window.addEventListener('pointercancel', finish, true);
        return true;
    }

    function beginModifierPan(gd, event) {
        if (!gd || !window.Plotly || !isPanModifier(event) || event.button !== 0) return false;

        var sp = subplotAtEvent(gd, event);
        if (!sp) return false;

        var xAxisKey = (sp.xaxis && sp.xaxis._name) || 'xaxis';
        var yAxisKey = (sp.yaxis && sp.yaxis._name) || 'yaxis';
        var xRange = axisRange(sp.xaxis);
        var yRange = axisRange(sp.yaxis);
        if (!xRange && !yRange) return false;

        stopPlotlyGesture(event);
        clearEmptyClickTimer(gd);
        gd.__geckoManualIntegrationPanning = {
            startClientX: event.clientX,
            startClientY: event.clientY,
            xRange: xRange,
            yRange: yRange,
            xAxisKey: xAxisKey,
            yAxisKey: yAxisKey,
            plotWidth: sp.bounds.width,
            plotHeight: sp.bounds.height,
            lastEvent: event,
            raf: null
        };

        var applyPan = function () {
            var pan = gd.__geckoManualIntegrationPanning;
            if (!pan || !pan.lastEvent) return;
            pan.raf = null;
            var update = {};
            if (pan.xRange && pan.plotWidth) {
                var dxPixels = pan.lastEvent.clientX - pan.startClientX;
                var dx = dxPixels * (pan.xRange[1] - pan.xRange[0]) / pan.plotWidth;
                update[pan.xAxisKey + '.range'] = [pan.xRange[0] - dx, pan.xRange[1] - dx];
            }
            if (pan.yRange && pan.plotHeight) {
                var dyPixels = pan.lastEvent.clientY - pan.startClientY;
                var dy = dyPixels * (pan.yRange[1] - pan.yRange[0]) / pan.plotHeight;
                update[pan.yAxisKey + '.range'] = [pan.yRange[0] + dy, pan.yRange[1] + dy];
            }
            if (Object.keys(update).length) {
                window.Plotly.relayout(gd, update);
            }
        };

        var move = function (moveEvent) {
            if (!gd.__geckoManualIntegrationPanning) return;
            stopPlotlyGesture(moveEvent);
            gd.__geckoManualIntegrationPanning.lastEvent = moveEvent;
            if (!gd.__geckoManualIntegrationPanning.raf) {
                gd.__geckoManualIntegrationPanning.raf = window.requestAnimationFrame(applyPan);
            }
        };

        var finish = function (upEvent) {
            if (!gd.__geckoManualIntegrationPanning) return;
            stopPlotlyGesture(upEvent);
            window.removeEventListener('pointermove', move, true);
            window.removeEventListener('pointerup', finish, true);
            window.removeEventListener('pointercancel', finish, true);
            if (gd.__geckoManualIntegrationPanning.raf) {
                window.cancelAnimationFrame(gd.__geckoManualIntegrationPanning.raf);
            }
            gd.__geckoManualIntegrationPanning = null;
            gd.__geckoManualIntegrationLastPlotlyClickAt = Date.now();
        };

        window.addEventListener('pointermove', move, true);
        window.addEventListener('pointerup', finish, true);
        window.addEventListener('pointercancel', finish, true);
        return true;
    }

    function handleGraphPointerDown(gd, event) {
        if (!gd || event.__geckoManualIntegrationHandled || event.__geckoManualIntegrationSeen) return;
        event.__geckoManualIntegrationSeen = true;
        if (beginModifierPan(gd, event)) return;
        if (isDoublePointer(gd, event)) {
            stopPlotlyGesture(event);
            gd.__geckoManualIntegrationLastDoubleClickAt = Date.now();
            clearEmptyClickTimer(gd);
            resetAxes(gd);
            return;
        }

        var peakId = peakIdAtEvent(gd, event);
        if (peakId && publishPeakClick(peakId)) {
            stopPlotlyGesture(event);
            gd.__geckoManualIntegrationLastPlotlyClickAt = Date.now();
            clearEmptyClickTimer(gd);
            clearTransientShapes('main-plot');
            return;
        }

        if (consumeSelectedBlankClick(gd, event)) return;
        beginCustomDraw(gd, event);
    }

    function isDoublePointer(gd, event) {
        var now = Date.now();
        var last = gd.__geckoManualIntegrationLastPointerDown;
        gd.__geckoManualIntegrationLastPointerDown = {
            time: now,
            x: event.clientX,
            y: event.clientY
        };
        if (event.detail && event.detail > 1) return true;
        if (!last) return false;
        return now - last.time < 360 &&
            Math.abs(event.clientX - last.x) < 8 &&
            Math.abs(event.clientY - last.y) < 8;
    }

    function installEmptyClickHandler() {
        var gd = getGraphDiv('main-plot');
        if (!gd) {
            window.setTimeout(installEmptyClickHandler, 250);
            return;
        }
        if (!document.__geckoManualIntegrationGlobalBlankClickInstalled) {
            var consumeBlankBeforePlotly = function (event) {
                if (event.detail && event.detail > 1) return;
                var eventGd = graphDivFromEvent(event);
                if (!eventGd) return;
                handleGraphPointerDown(eventGd, event);
            };
            var consumeMouseBeforePlotly = function (event) {
                var eventGd = graphDivFromEvent(event);
                if (!eventGd) return;
                if (eventGd.__geckoManualIntegrationDrawing || eventGd.__geckoManualIntegrationPanning) {
                    stopPlotlyGesture(event);
                    return;
                }
                if (event.detail && event.detail > 1) return;
                consumeSelectedBlankClick(eventGd, event);
            };
            document.addEventListener('pointerdown', consumeBlankBeforePlotly, true);
            document.addEventListener('mousedown', consumeMouseBeforePlotly, true);
            document.addEventListener('keydown', syncMomentaryDrawButton, true);
            document.addEventListener('keyup', syncMomentaryDrawButton, true);
            window.addEventListener('blur', function () {
                setMomentaryDrawActive(false);
            });
            document.__geckoManualIntegrationGlobalBlankClickInstalled = true;
        }

        if (gd.__geckoManualIntegrationClickInstalled) return;

        if (typeof gd.on === 'function') {
            gd.on('plotly_click', function (eventData) {
                gd.__geckoManualIntegrationLastPlotlyClickAt = Date.now();
                clearEmptyClickTimer(gd);
                if (eventPeakId(eventData)) {
                    clearTransientShapes('main-plot');
                }
            });
            gd.on('plotly_doubleclick', function () {
                gd.__geckoManualIntegrationLastDoubleClickAt = Date.now();
                clearEmptyClickTimer(gd);
                resetAxes(gd);
            });
        }

        gd.addEventListener('pointerdown', function (event) {
            handleGraphPointerDown(gd, event);
        }, true);

        gd.addEventListener('mousedown', function (event) {
            if (gd.__geckoManualIntegrationDrawing || gd.__geckoManualIntegrationPanning) {
                stopPlotlyGesture(event);
                return;
            }
            if (event.detail && event.detail > 1) return;
            consumeSelectedBlankClick(gd, event);
        }, true);

        gd.addEventListener('dblclick', function () {
            gd.__geckoManualIntegrationLastDoubleClickAt = Date.now();
            clearEmptyClickTimer(gd);
            resetAxes(gd);
        });

        gd.addEventListener('click', function (event) {
            if (!event || event.defaultPrevented) return;
            if (event.detail && event.detail > 1) return;
            if (event.target && event.target.closest('.scatterlayer, .shapelayer, .modebar, .hoverlayer')) {
                return;
            }

            var plotArea = gd.querySelector('.nsewdrag');
            if (plotArea) {
                var bounds = plotArea.getBoundingClientRect();
                if (
                    event.clientX < bounds.left ||
                    event.clientX > bounds.right ||
                    event.clientY < bounds.top ||
                    event.clientY > bounds.bottom
                ) {
                    return;
                }
            }

            if (gd.__geckoManualIntegrationEmptyClickTimer) {
                window.clearTimeout(gd.__geckoManualIntegrationEmptyClickTimer);
            }
            gd.__geckoManualIntegrationEmptyClickTimer = window.setTimeout(function () {
                gd.__geckoManualIntegrationEmptyClickTimer = null;
                var lastPlotlyClick = gd.__geckoManualIntegrationLastPlotlyClickAt || 0;
                var lastDoubleClick = gd.__geckoManualIntegrationLastDoubleClickAt || 0;
                if (Date.now() - lastPlotlyClick < 500) return;
                if (Date.now() - lastDoubleClick < 350) return;

                triggerEmptyClick();
            }, 240);
        });

        gd.__geckoManualIntegrationClickInstalled = true;
    }

    window.GeckoPlotterManualIntegration = {
        clearTransientShapes: clearTransientShapes,
        syncSelectedShape: syncSelectedShape,
        syncDrawMode: syncDrawMode,
        installEmptyClickHandler: installEmptyClickHandler
    };

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.setTimeout(installEmptyClickHandler, 0);
    } else {
        document.addEventListener('DOMContentLoaded', installEmptyClickHandler);
    }
    window.addEventListener('load', function () {
        window.setTimeout(installEmptyClickHandler, 100);
    });
})();
