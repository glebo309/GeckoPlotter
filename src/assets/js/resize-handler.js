// GeckoPlotter V2 — VSCode-style panel resize with snap-to-edge collapse
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
        if (!leftColumn.style.width)  leftColumn.style.width  = '30%';
        if (!rightColumn.style.width) rightColumn.style.width = '70%';
        if (topLeft  && !topLeft.style.height)  topLeft.style.height  = '50%';
        if (bottomLeft  && !bottomLeft.style.height)  bottomLeft.style.height  = '50%';
        if (topRight && !topRight.style.height) topRight.style.height = '60%';
        if (bottomRight && !bottomRight.style.height) bottomRight.style.height = '40%';

        var activeResize = null;
        var startX = 0, startY = 0;
        var start = { left: 0, top: 0, containerWidth: 0, containerHeight: 0 };

        function startDrag(e, type) {
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
                top:  topRect ? topRect.height : 0,
                containerWidth:  containerRect.width || window.innerWidth,
                containerHeight: (type === 'left-vertical' ? leftRect.height : rightRect.height) || window.innerHeight
            };

            document.body.classList.add('dragging');
            document.body.style.cursor = type === 'main' ? 'col-resize' : 'row-resize';
        }

        document.addEventListener('mousemove', function (e) {
            if (!activeResize) return;
            e.preventDefault();

            if (activeResize === 'main') {
                var deltaX = e.clientX - startX;
                var cw = start.containerWidth || container.getBoundingClientRect().width || window.innerWidth;
                var newLeft = start.left + deltaX;
                var percent = (newLeft / cw) * 100;

                // VSCode-style collapse: snap to hidden when dragged past threshold
                if (percent < 5) {
                    percent = 0;
                    leftColumn.style.display = 'none';
                } else if (percent > 95) {
                    percent = 100;
                    rightColumn.style.display = 'none';
                } else {
                    leftColumn.style.display  = 'flex';
                    rightColumn.style.display = 'flex';
                }
                leftColumn.style.width  = percent + '%';
                rightColumn.style.width = (100 - percent) + '%';

            } else if (activeResize === 'left-vertical' && topLeft && bottomLeft) {
                var deltaY = e.clientY - startY;
                var ch = start.containerHeight || leftColumn.getBoundingClientRect().height || window.innerHeight;
                var newTop = start.top + deltaY;
                var percent = (newTop / ch) * 100;

                if (percent < 5) {
                    percent = 0;
                    topLeft.style.display = 'none';
                } else if (percent > 95) {
                    percent = 100;
                    bottomLeft.style.display = 'none';
                } else {
                    topLeft.style.display    = 'flex';
                    bottomLeft.style.display = 'flex';
                }
                topLeft.style.height    = percent + '%';
                bottomLeft.style.height = (100 - percent) + '%';

            } else if (activeResize === 'right-vertical' && topRight && bottomRight) {
                var deltaY = e.clientY - startY;
                var ch = start.containerHeight || rightColumn.getBoundingClientRect().height || window.innerHeight;
                var newTop = start.top + deltaY;
                var percent = (newTop / ch) * 100;

                if (percent < 5) {
                    percent = 0;
                    topRight.style.display = 'none';
                } else if (percent > 95) {
                    percent = 100;
                    bottomRight.style.display = 'none';
                } else {
                    topRight.style.display    = 'flex';
                    bottomRight.style.display = 'flex';
                }
                topRight.style.height    = percent + '%';
                bottomRight.style.height = (100 - percent) + '%';
            }
        });

        document.addEventListener('mouseup', function () {
            if (!activeResize) return;
            activeResize = null;
            document.body.classList.remove('dragging');
            document.body.style.cursor = '';
        });

        if (leftVDivider)  leftVDivider.addEventListener('mousedown',  function (e) { startDrag(e, 'left-vertical'); });
        if (rightVDivider) rightVDivider.addEventListener('mousedown', function (e) { startDrag(e, 'right-vertical'); });
        if (mainVDivider)  mainVDivider.addEventListener('mousedown',  function (e) { startDrag(e, 'main'); });

        console.log('[GeckoPlotter] Resize handlers initialized (snap-to-edge enabled)');
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
            initializeResizeHandlers: function () {
                initResizeSystem();
                return window.dash_clientside.no_update;
            }
        }
    });
})();
