// GeckoPlotter V2 — VSCode-style panel resize with snap-to-edge collapse.
// Restore labels appear only for hidden panels and reopen that exact panel.
// Self-initializing with retry. Also exposes Dash clientside fallback.

(function () {
    'use strict';

    function initResizeSystem() {
        if (window.__geckoResizeInitialized) return;

        var container   = document.getElementById('main-container');
        var leftColumn  = document.getElementById('left-column');
        var rightColumn = document.getElementById('right-column');
        var topLeft     = document.getElementById('left-top-panel');
        var bottomLeft  = document.getElementById('left-bottom-panel');
        var topRight    = document.getElementById('right-top-panel');
        var bottomRight = document.getElementById('right-bottom-panel');

        var leftVDivider  = document.getElementById('left-vertical-divider');
        var rightVDivider = document.getElementById('right-vertical-divider');
        var mainVDivider  = document.getElementById('main-divider');

        if (!container || !leftColumn || !rightColumn ||
            !leftVDivider || !rightVDivider || !mainVDivider) {
            setTimeout(initResizeSystem, 200);
            return;
        }

        window.__geckoResizeInitialized = true;

        // Default splits (only if not already set)
        if (!leftColumn.style.width)  leftColumn.style.width  = '24%';
        if (!rightColumn.style.width) rightColumn.style.width = '76%';
        if (topLeft  && !topLeft.style.height)  topLeft.style.height  = '35%';
        if (bottomLeft  && !bottomLeft.style.height)  bottomLeft.style.height  = '65%';
        if (topRight && !topRight.style.height) topRight.style.height = '60%';
        if (bottomRight && !bottomRight.style.height) bottomRight.style.height = '40%';

        var activeResize = null;
        var startX = 0, startY = 0;
        var start = { left: 0, top: 0, containerWidth: 0, containerHeight: 0 };
        var activePlotTab = null, activePlotKind = null;
        var tabLayouts = {}, tabLayoutKinds = {};
        var applyingLayout = false;
        var analysisDock = 'below', analysisDockOverride = null, analysisPanel = 'data-overview';
        var rightSplits = {below: 60, right: 60};
        var analysisNavFramePending = false;

        function revealSelectedAnalysisTab() {
            if (analysisNavFramePending) return;
            analysisNavFramePending = true;
            var schedule = window.requestAnimationFrame || function (fn) { setTimeout(fn, 0); };
            schedule(function () {
                analysisNavFramePending = false;
                if (activePlotKind === 'publication') return;
                var nav = document.querySelector('.results-navigation');
                var scroller = nav && nav.firstElementChild;
                var selected = scroller && scroller.querySelector('[role="tab"][aria-selected="true"]');
                if (!selected) return;
                var viewport = scroller.getBoundingClientRect();
                var tab = selected.getBoundingClientRect();
                if (!viewport.width || !tab.width) return;
                // Move this tab row only; scrollIntoView would also move the
                // analysis panel or document when the dock changes size.
                if (tab.left < viewport.left) scroller.scrollLeft += tab.left - viewport.left;
                else if (tab.right > viewport.right) scroller.scrollLeft += tab.right - viewport.right;
            });
        }

        function desiredAnalysisDock() {
            if (analysisDockOverride) return analysisDockOverride;
            var mass = ['ms-scan', 'ms-eic', 'ms-peak-mass', 'pda'].indexOf(analysisPanel) !== -1;
            return mass && rightColumn.getBoundingClientRect().width >= 900 ? 'right' : 'below';
        }

        function orientAnalysis(dock) {
            analysisDock = dock;
            rightColumn.style.flexDirection = dock === 'right' ? 'row' : 'column';
            rightColumn.dataset.analysisDock = dock;
            rightVDivider.classList.remove('divider-horizontal', 'divider-vertical');
            rightVDivider.classList.add(dock === 'right' ? 'divider-horizontal' : 'divider-vertical');
            rightVDivider.dataset.labelLeft = rightVDivider.dataset.labelAbove || 'Plot';
            rightVDivider.dataset.labelRight = rightVDivider.dataset.labelBelow || 'Analysis';
            topRight.style[dock === 'right' ? 'height' : 'width'] = '100%';
            bottomRight.style[dock === 'right' ? 'height' : 'width'] = '100%';
            topRight.style.minWidth = bottomRight.style.minWidth = '0';
            topRight.style.minHeight = bottomRight.style.minHeight = '0';
            revealSelectedAnalysisTab();
        }

        function updateAnalysisDock() {
            if (activePlotKind === 'publication') return;
            revealSelectedAnalysisTab();
            var wanted = desiredAnalysisDock();
            if (wanted !== analysisDock) {
                currentLayout();
                orientAnalysis(wanted);
                applyCollapse('right-vertical', rightSplits[wanted]);
            }
        }

        // Deterministic restore positions. Collapsed panels should reopen to the
        // familiar working layout, not to the last near-edge drag position.
        var defaults = {
            leftCol: 24, rightCol: 76,
            topLeft: 35, bottomLeft: 65,
            topRight: 60, bottomRight: 40
        };

        // Collapse state: null | 'first' | 'second' (which panel of the pair is hidden)
        var collapsed = {
            main: null,           // 'first' = left col hidden, 'second' = right col hidden
            leftVertical: null,   // 'first' = top-left hidden, 'second' = bottom-left hidden
            rightVertical: null   // 'first' = top-right hidden, 'second' = bottom-right hidden
        };

        var publicationDefaultLayout = {
            main: defaults.leftCol,
            leftVertical: 0,
            rightVertical: 100
        };
        // Capture the normal workspace once, before any publication can hide
        // its Files and Results panes. Every new raw tab starts from this layout.
        var rawDefaultLayout = currentLayout();


        // ── Label management ──

        function getLabel(divider) {
            return divider.querySelector('.divider-label');
        }

        function ensureHoverZone(divider) {
            var zone = divider.querySelector('.divider-hover-zone');
            if (!zone) {
                zone = document.createElement('span');
                zone.className = 'divider-hover-zone';
                zone.setAttribute('aria-hidden', 'true');
                divider.appendChild(zone);
            }
            return zone;
        }

        function setDockGeometry(divider, collapseKey, state) {
            if (!divider || !state) {
                return;
            }

            var rect;
            var dockWidth = 0;
            var dockHeight = 0;
            var dockThickness = 46;

            if (collapseKey === 'main') {
                rect = container.getBoundingClientRect();
                dockWidth = dockThickness;
                dockHeight = rect.height;
            } else if (collapseKey === 'leftVertical') {
                rect = leftColumn.getBoundingClientRect();
                dockWidth = rect.width;
                dockHeight = dockThickness;
            } else if (collapseKey === 'rightVertical') {
                rect = rightColumn.getBoundingClientRect();
                dockWidth = analysisDock === 'right' ? dockThickness : rect.width;
                dockHeight = analysisDock === 'right' ? rect.height : dockThickness;
            }

            divider.style.setProperty('--dock-width', Math.max(1, Math.round(dockWidth)) + 'px');
            divider.style.setProperty('--dock-height', Math.max(1, Math.round(dockHeight)) + 'px');
        }

        function updateLabel(divider, collapseKey) {
            var label = getLabel(divider);
            if (!label) return;
            ensureHoverZone(divider);

            var state = collapsed[collapseKey];
            var labelAbove = divider.dataset.labelAbove || '';
            var labelBelow = divider.dataset.labelBelow || '';
            var labelLeft  = divider.dataset.labelLeft  || '';
            var labelRight = divider.dataset.labelRight || '';
            var isHorizontal = divider.classList.contains('divider-horizontal');

            // Reset direction classes
            label.classList.remove('collapse-above', 'collapse-below', 'collapse-left', 'collapse-right', 'collapsed-state');
            divider.classList.remove('has-label', 'hidden-first', 'hidden-second', 'dock-hover');

            if (!state) {
                label.textContent = '';
                label.classList.remove('visible');
                divider.style.removeProperty('--dock-width');
                divider.style.removeProperty('--dock-height');
            } else if (state === 'first') {
                // First panel hidden (top or left)
                if (isHorizontal) {
                    label.textContent = labelLeft;
                    label.classList.add('collapse-right', 'collapsed-state');
                } else {
                    label.textContent = labelAbove;
                    label.classList.add('collapse-above', 'collapsed-state');
                }
                label.classList.add('visible');
                divider.classList.add('has-label', 'hidden-first');
                setDockGeometry(divider, collapseKey, state);
            } else if (state === 'second') {
                // Second panel hidden (bottom or right)
                if (isHorizontal) {
                    label.textContent = labelRight;
                    label.classList.add('collapse-left', 'collapsed-state');
                } else {
                    label.textContent = labelBelow;
                    label.classList.add('collapse-below', 'collapsed-state');
                }
                label.classList.add('visible');
                divider.classList.add('has-label', 'hidden-second');
                setDockGeometry(divider, collapseKey, state);
            }
        }

        function ratioPercent(first, second, axis, fallback) {
            // The split model is authoritative even if an ancestor is hidden
            // or the browser has not painted the newly applied percentages yet.
            var firstStyle = first.style[axis] || '';
            var secondStyle = second.style[axis] || '';
            if (firstStyle.endsWith('%') && secondStyle.endsWith('%')) {
                var firstPercent = parseFloat(firstStyle), secondPercent = parseFloat(secondStyle);
                if (firstPercent + secondPercent > 0) return 100 * firstPercent / (firstPercent + secondPercent);
            }
            var firstRect = first.getBoundingClientRect();
            var secondRect = second.getBoundingClientRect();
            var firstSize = axis === 'height' ? firstRect.height : firstRect.width;
            var secondSize = axis === 'height' ? secondRect.height : secondRect.width;
            var total = firstSize + secondSize;
            return total > 0 ? (firstSize / total) * 100 : fallback;
        }

        function currentLayout() {
            rightSplits[analysisDock] = collapsed.rightVertical === 'first' ? 0
                : collapsed.rightVertical === 'second' ? 100
                : ratioPercent(topRight, bottomRight, analysisDock === 'right' ? 'width' : 'height', defaults.topRight);
            return {
                main: collapsed.main === 'first' ? 0
                    : collapsed.main === 'second' ? 100
                    : ratioPercent(leftColumn, rightColumn, 'width', defaults.leftCol),
                leftVertical: collapsed.leftVertical === 'first' ? 0
                    : collapsed.leftVertical === 'second' ? 100
                    : ratioPercent(topLeft, bottomLeft, 'height', defaults.topLeft),
                rightVertical: rightSplits.below,
                rightHorizontal: rightSplits.right,
                analysisDock: analysisDock,
                analysisDockOverride: analysisDockOverride,
                analysisPanel: analysisPanel
            };
        }

        function rememberActiveLayout() {
            if (!activePlotTab || applyingLayout) return;
            tabLayouts[activePlotTab] = currentLayout();
            tabLayoutKinds[activePlotTab] = activePlotKind;
        }

        function applyLayout(layout) {
            if (!layout) return;
            applyingLayout = true;
            applyCollapse('main', typeof layout.main === 'number' ? layout.main : defaults.leftCol);
            applyCollapse('left-vertical', typeof layout.leftVertical === 'number' ? layout.leftVertical : defaults.topLeft);
            rightSplits = {below: typeof layout.rightVertical === 'number' ? layout.rightVertical : defaults.topRight,
                right: typeof layout.rightHorizontal === 'number' ? layout.rightHorizontal : defaults.topRight};
            analysisDockOverride = layout.analysisDockOverride || null;
            analysisPanel = layout.analysisPanel || 'data-overview';
            orientAnalysis(activePlotKind === 'publication' ? 'below' : desiredAnalysisDock());
            applyCollapse('right-vertical', rightSplits[analysisDock]);
            applyingLayout = false;
            rememberActiveLayout();
        }

        function tabKind(activeTab, tabs) {
            if (Array.isArray(tabs)) {
                var descriptor = tabs.find(function (tab) {return tab && tab.id === activeTab;});
                if (!descriptor) return null;
                return descriptor.type === 'publication' ? 'publication' : 'raw';
            }
            return String(activeTab).indexOf('publication') === 0 ? 'publication' : 'raw';
        }

        // Apply collapse / expand for a given panel pair
        function applyCollapse(type, percent) {
            if (type === 'main') {
                if (percent < 5) {
                    leftColumn.style.display = 'none';
                    rightColumn.style.display = 'flex';
                    leftColumn.style.width = '0%';
                    rightColumn.style.width = '100%';
                    collapsed.main = 'first';
                } else if (percent > 95) {
                    rightColumn.style.display = 'none';
                    leftColumn.style.display = 'flex';
                    leftColumn.style.width = '100%';
                    rightColumn.style.width = '0%';
                    collapsed.main = 'second';
                } else {
                    leftColumn.style.display = 'flex';
                    rightColumn.style.display = 'flex';
                    leftColumn.style.width = percent + '%';
                    rightColumn.style.width = (100 - percent) + '%';
                    collapsed.main = null;
                }
                updateLabel(mainVDivider, 'main');
                rememberActiveLayout();

            } else if (type === 'left-vertical') {
                if (percent < 5) {
                    topLeft.style.display = 'none';
                    bottomLeft.style.display = 'flex';
                    topLeft.style.height = '0%';
                    bottomLeft.style.height = '100%';
                    collapsed.leftVertical = 'first';
                } else if (percent > 95) {
                    bottomLeft.style.display = 'none';
                    topLeft.style.display = 'flex';
                    topLeft.style.height = '100%';
                    bottomLeft.style.height = '0%';
                    collapsed.leftVertical = 'second';
                } else {
                    topLeft.style.display = 'flex';
                    bottomLeft.style.display = 'flex';
                    topLeft.style.height = percent + '%';
                    bottomLeft.style.height = (100 - percent) + '%';
                    collapsed.leftVertical = null;
                }
                updateLabel(leftVDivider, 'leftVertical');
                rememberActiveLayout();

            } else if (type === 'right-vertical') {
                var axis = analysisDock === 'right' ? 'width' : 'height';
                if (percent < 5) {
                    topRight.style.display = 'none';
                    bottomRight.style.display = 'flex';
                    topRight.style[axis] = '0%';
                    bottomRight.style[axis] = '100%';
                    collapsed.rightVertical = 'first';
                } else if (percent > 95) {
                    bottomRight.style.display = 'none';
                    topRight.style.display = 'flex';
                    topRight.style[axis] = '100%';
                    bottomRight.style[axis] = '0%';
                    collapsed.rightVertical = 'second';
                } else {
                    topRight.style.display = 'flex';
                    bottomRight.style.display = 'flex';
                    topRight.style[axis] = percent + '%';
                    bottomRight.style[axis] = (100 - percent) + '%';
                    collapsed.rightVertical = null;
                }
                updateLabel(rightVDivider, 'rightVertical');
                rememberActiveLayout();
            }
        }

        // Click a hidden-panel label to restore that exact panel.
        function handleLabelClick(type) {
            var collapseKey = type === 'main' ? 'main'
                : type === 'left-vertical' ? 'leftVertical' : 'rightVertical';

            if (!collapsed[collapseKey]) return;

            if (type === 'main') {
                applyCollapse('main', defaults.leftCol);
            } else if (type === 'left-vertical') {
                applyCollapse('left-vertical', defaults.topLeft);
            } else if (type === 'right-vertical') {
                applyCollapse('right-vertical', defaults.topRight);
            }
        }

        // Wire up label clicks (stop propagation so drag doesn't fire)
        [[leftVDivider, 'left-vertical'],
         [rightVDivider, 'right-vertical'],
         [mainVDivider, 'main']
        ].forEach(function (pair) {
            var divider = pair[0], type = pair[1];
            var label = getLabel(divider);
            if (label) {
                label.addEventListener('mousedown', function (e) { e.stopPropagation(); });
                label.addEventListener('click', function (e) {
                    e.stopPropagation();
                    handleLabelClick(type);
                });
            }
        });

        // Initialize labels (hidden until a panel is collapsed)
        updateLabel(leftVDivider, 'leftVertical');
        updateLabel(rightVDivider, 'rightVertical');
        updateLabel(mainVDivider, 'main');

        // ── Drag logic ──

        function isNearDividerCore(e, divider) {
            if (!divider || !divider.classList.contains('has-label')) return true;

            var rect = divider.getBoundingClientRect();
            var tolerance = 12;
            if (divider.classList.contains('divider-horizontal')) {
                return e.clientX >= rect.left - tolerance && e.clientX <= rect.right + tolerance;
            }
            return e.clientY >= rect.top - tolerance && e.clientY <= rect.bottom + tolerance;
        }

        function startDrag(e, type, divider) {
            if (e.target.classList.contains('divider-label')) return;
            if (e.target.classList.contains('divider-hover-zone')) return;
            if (!isNearDividerCore(e, divider)) return;
            e.preventDefault();
            e.stopPropagation();
            activeResize = type;
            startX = e.clientX;
            startY = e.clientY;

            var containerRect = container.getBoundingClientRect();
            var leftRect  = leftColumn.getBoundingClientRect();
            var rightRect = rightColumn.getBoundingClientRect();
            var topRect   = type === 'left-vertical'
                ? (topLeft  ? topLeft.getBoundingClientRect()  : null)
                : (topRight ? topRight.getBoundingClientRect() : null);

            start = {
                left: leftRect.width,
                top:  topRect ? (type === 'right-vertical'
                    ? ratioPercent(topRight, bottomRight, analysisDock === 'right' ? 'width' : 'height', defaults.topRight)
                      * (analysisDock === 'right' ? rightRect.width : rightRect.height) / 100 : topRect.height) : 0,
                containerWidth:  containerRect.width || window.innerWidth,
                containerHeight: (type === 'left-vertical' ? leftRect.height
                    : analysisDock === 'right' ? rightRect.width : rightRect.height) || window.innerHeight
            };

            document.body.classList.add('dragging');
            document.body.style.cursor = type === 'main' || (type === 'right-vertical' && analysisDock === 'right') ? 'col-resize' : 'row-resize';
        }

        document.addEventListener('mousemove', function (e) {
            if (!activeResize) return;
            e.preventDefault();

            if (activeResize === 'main') {
                var deltaX = e.clientX - startX;
                var cw = start.containerWidth || container.getBoundingClientRect().width || window.innerWidth;
                var newLeft = start.left + deltaX;
                var percent = (newLeft / cw) * 100;
                applyCollapse('main', percent);

            } else if (activeResize === 'left-vertical' && topLeft && bottomLeft) {
                var deltaY = e.clientY - startY;
                var ch = start.containerHeight || leftColumn.getBoundingClientRect().height || window.innerHeight;
                var newTop = start.top + deltaY;
                var percent = (newTop / ch) * 100;
                applyCollapse('left-vertical', percent);

            } else if (activeResize === 'right-vertical' && topRight && bottomRight) {
                var deltaY = analysisDock === 'right' ? e.clientX - startX : e.clientY - startY;
                var ch = start.containerHeight || rightColumn.getBoundingClientRect().height || window.innerHeight;
                var newTop = start.top + deltaY;
                var percent = (newTop / ch) * 100;
                applyCollapse('right-vertical', percent);
            }
        });

        document.addEventListener('mouseup', function () {
            if (!activeResize) return;
            var changedWidth = activeResize === 'main';
            activeResize = null;
            if (changedWidth) {
                updateAnalysisDock();
                if (window.dash_clientside.set_props) window.dash_clientside.set_props('analysis-dock', {value: analysisDock});
            }
            document.body.classList.remove('dragging');
            document.body.style.cursor = '';
        });

        if (leftVDivider)  leftVDivider.addEventListener('mousedown',  function (e) { startDrag(e, 'left-vertical', leftVDivider); });
        if (rightVDivider) rightVDivider.addEventListener('mousedown', function (e) { startDrag(e, 'right-vertical', rightVDivider); });
        if (mainVDivider)  mainVDivider.addEventListener('mousedown',  function (e) { startDrag(e, 'main', mainVDivider); });

        function pointInRect(x, y, rect) {
            return rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
        }

        function updateDockHover(e) {
            [leftVDivider, rightVDivider, mainVDivider].forEach(function (divider) {
                if (!divider || !divider.classList.contains('has-label')) return;
                var zone = divider.querySelector('.divider-hover-zone');
                var label = getLabel(divider);
                var inZone = zone && pointInRect(e.clientX, e.clientY, zone.getBoundingClientRect());
                var inLabel = label && pointInRect(e.clientX, e.clientY, label.getBoundingClientRect());
                divider.classList.toggle('dock-hover', Boolean(inZone || inLabel));
            });
        }

        function clearDockHover() {
            [leftVDivider, rightVDivider, mainVDivider].forEach(function (divider) {
                if (divider) divider.classList.remove('dock-hover');
            });
        }

        document.addEventListener('mousemove', updateDockHover);
        document.addEventListener('mouseleave', clearDockHover);

        window.addEventListener('resize', function () {
            updateAnalysisDock();
            if (window.dash_clientside.set_props) window.dash_clientside.set_props('analysis-dock', {value: analysisDock});
            updateLabel(leftVDivider, 'leftVertical');
            updateLabel(rightVDivider, 'rightVertical');
            updateLabel(mainVDivider, 'main');
        });

        window.__geckoSyncPlotTabLayout = function (activeTab, plotTabs) {
            if (!activeTab) return;
            var kind = tabKind(activeTab, plotTabs);
            if (!kind) return; // Wait for matching tab descriptors during creation/removal.

            if (activePlotTab && activePlotTab !== activeTab) rememberActiveLayout();
            activePlotTab = activeTab;
            activePlotKind = kind;
            var saved = tabLayoutKinds[activeTab] === kind && tabLayouts[activeTab];
            applyLayout(saved || (kind === 'publication' ? publicationDefaultLayout : rawDefaultLayout));

            if (Array.isArray(plotTabs)) {
                var ids = new Set(plotTabs.map(function (tab) {return tab.id;}));
                Object.keys(tabLayouts).forEach(function (id) {
                    if (!ids.has(id)) {delete tabLayouts[id]; delete tabLayoutKinds[id];}
                });
            }
        };

        window.__geckoSyncAnalysisDock = function (panel, requested, activeTab, plotTabs, owner) {
            var kind = tabKind(activeTab, plotTabs);
            if (!activeTab || !kind) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            if (activePlotTab !== activeTab || activePlotKind !== kind) window.__geckoSyncPlotTabLayout(activeTab, plotTabs);
            if (kind === 'publication') return ['below', activeTab];
            var ctx = window.dash_clientside.callback_context;
            var trigger = ctx && ctx.triggered && ctx.triggered.length ? ctx.triggered[0].prop_id.split('.')[0] : '';
            // The control is shared; its previous owner's late value cannot
            // override the newly activated figure's saved dock.
            if (trigger === 'analysis-dock' && owner === activeTab && requested !== analysisDock &&
                    (requested === 'below' || requested === 'right')) analysisDockOverride = requested;
            if (panel && (owner === activeTab || trigger === 'analysis-tabs')) analysisPanel = panel;
            updateAnalysisDock();
            rememberActiveLayout();
            return [analysisDock, activeTab];
        };

        console.log('[GeckoPlotter] Resize handlers initialized (snap-to-edge hidden-panel labels)');
    }

    // Self-init with retry
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(initResizeSystem, 0);
    } else {
        document.addEventListener('DOMContentLoaded', initResizeSystem);
    }
    window.addEventListener('load', function () { setTimeout(initResizeSystem, 100); });

    // Expose for Dash clientside callback fallback
    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        resize: {
            syncAnalysisDock: function (panel, requested, activeTab, plotTabs, owner) {
                initResizeSystem();
                return window.__geckoSyncAnalysisDock ? window.__geckoSyncAnalysisDock(panel, requested, activeTab, plotTabs, owner)
                    : [window.dash_clientside.no_update, window.dash_clientside.no_update];
            },
            initializeResizeHandlers: function () {
                initResizeSystem();
                return window.dash_clientside.no_update;
            },
            syncPlotTabLayout: function (activeTab, plotTabs) {
                initResizeSystem();
                if (window.__geckoSyncPlotTabLayout) {
                    window.__geckoSyncPlotTabLayout(activeTab, plotTabs);
                }
                return window.dash_clientside.no_update;
            }
        }
    });
})();
