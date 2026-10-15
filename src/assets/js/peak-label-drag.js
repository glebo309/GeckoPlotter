// Drag a peak's name in the plot to where it reads best. Near its place above the peak it snaps back there; with
// Cmd (Ctrl) held a line leads from the peak's top to the name. The position is kept with the peak (peak-label-move
// -> context_menu_callbacks.move_label_from_plot -> Peak.label_offset / label_leader) and saved with the project.
(function () {
    'use strict';
    var SNAP = 14, START = 3;                 // px: back to centre within SNAP; a drag starts after START
    var drag = null;

    function overlay() {
        var svg = document.getElementById('peak-label-drag-line');
        if (!svg) {
            svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.id = 'peak-label-drag-line';
            svg.setAttribute('style', 'position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:4999');
            var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('stroke', '#666');
            line.setAttribute('stroke-width', '0.8');
            svg.appendChild(line);
            document.body.appendChild(svg);
        }
        return svg;
    }

    function place(event) {
        var dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
        var offset = [drag.base[0] + dx, drag.base[1] - dy];
        var snapped = Math.hypot(offset[0], offset[1]) < SNAP;
        if (snapped) offset = [0, 0];
        var leader = !snapped && (event.metaKey || event.ctrlKey);
        drag.offset = offset; drag.snapped = snapped; drag.leader = leader;
        var r = drag.rect;                     // the label where it was drawn, moved by the pointer (or snapped home)
        var cx = snapped && drag.home ? drag.home.x : r.left + r.width / 2 + dx;
        var bottom = snapped && drag.home ? drag.home.y - 2 : r.bottom + dy;
        drag.ghost.style.left = (cx - drag.ghost.offsetWidth / 2) + 'px';
        drag.ghost.style.top = (bottom - drag.ghost.offsetHeight) + 'px';
        drag.ghost.classList.toggle('snapped', snapped);
        var svg = overlay(), line = svg.firstChild;
        svg.style.display = leader && drag.home ? '' : 'none';
        if (leader && drag.home) {
            line.setAttribute('x1', drag.home.x); line.setAttribute('y1', drag.home.y);
            line.setAttribute('x2', cx); line.setAttribute('y2', bottom);
        }
    }

    function finish(cancelled) {
        var state = drag;
        drag = null;
        overlay().style.display = 'none';
        if (!state || !state.moved) return;
        if (cancelled) { state.ghost.remove(); state.element.style.opacity = ''; return; }
        if (window.dash_clientside) {
            window.dash_clientside.set_props('peak-label-move', {data: {
                peak_id: state.hit.peakId, offset: state.snapped ? null : state.offset,
                leader: !!state.leader, ts: Date.now()}});
        }
        // Keep the label where it was dropped until the plot is redrawn with it there.
        var done = function () { state.ghost.remove(); state.element.style.opacity = ''; };
        if (state.gd.once) state.gd.once('plotly_afterplot', function () { setTimeout(done, 30); });
        setTimeout(done, 4000);
    }

    document.addEventListener('pointerdown', function (event) {
        if (event.button !== 0 || !window.GeckoFigureLabels) return;
        if (document.body.classList.contains('gecko-text-edit-mode')) return;
        var gd = event.target.closest && event.target.closest('.js-plotly-plot');
        var hit = gd && window.GeckoFigureLabels.peakLabelAt(gd, event);
        if (!hit) return;
        drag = {gd: gd, hit: hit, element: hit.element, rect: hit.element.getBoundingClientRect(),
                startX: event.clientX, startY: event.clientY, base: (hit.offset || [0, 0]).slice(),
                home: hit.home, moved: false, offset: hit.offset, leader: hit.leader};
        event.preventDefault();               // no zoom box or integration drag from under the name
        event.stopPropagation();
        event.stopImmediatePropagation();
    }, true);

    document.addEventListener('pointermove', function (event) {
        if (!drag) return;
        if (!drag.moved) {
            if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < START) return;
            drag.moved = true;
            var ghost = document.createElement('div');
            ghost.className = 'peak-label-ghost';
            ghost.textContent = drag.hit.value;
            document.body.appendChild(ghost);
            drag.ghost = ghost;
            drag.element.style.opacity = '0';
        }
        place(event);
        event.preventDefault();
        event.stopPropagation();
    }, true);

    document.addEventListener('pointerup', function (event) {
        if (!drag) return;
        if (drag.moved) { place(event); event.stopPropagation(); }
        finish(false);
    }, true);
    document.addEventListener('pointercancel', function () { finish(true); }, true);
    document.addEventListener('keydown', function (event) {
        if (drag && event.key === 'Escape') finish(true);
        if (drag && drag.moved && (event.key === 'Meta' || event.key === 'Control')) {
            place({clientX: drag.lastX || drag.startX, clientY: drag.lastY || drag.startY, metaKey: true, ctrlKey: true});
        }
    }, true);
    document.addEventListener('pointermove', function (event) {
        if (drag) { drag.lastX = event.clientX; drag.lastY = event.clientY; }
    }, true);
})();
