// Drag a peak's name in the plot to where it reads best. A name moved away from its peak is joined to the peak's top
// by a thin line; near its place above the peak it snaps back there. Right-click a name for its menu: connecting line
// on/off, reset position, rename. The position is kept with the peak (peak-label-move ->
// context_menu_callbacks.move_label_from_plot -> Peak.label_offset / label_leader) and saved with the project.
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
        // A name leaving its place gets the connecting line; one already moved keeps its own setting (menu).
        var leader = !snapped && (drag.wasHome || drag.hit.leader);
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
        if (!state || !state.moved) { overlay().style.display = 'none'; return; }
        var restore = function () { state.ghost.remove(); state.hidden.style.opacity = ''; overlay().style.display = 'none'; };
        if (cancelled) { restore(); return; }
        if (window.dash_clientside) {
            window.dash_clientside.set_props('peak-label-move', {data: {
                peak_id: state.hit.peakId, offset: state.snapped ? null : state.offset,
                leader: !!state.leader, ts: Date.now()}});
        }
        // The name (and its line) stay where they were dropped until the plot is redrawn with them there.
        var finished = false;
        var done = function () { if (!finished) { finished = true; restore(); } };
        var arrived = function () {                       // the redraw that carries the new position
            var a = ((state.gd._fullLayout || {}).annotations || []).find(function (x) {
                return String(x.name || '') === 'peak-label:' + state.hit.peakId; });
            if (state.snapped) return !a;
            if (!a) return false;
            var dx = a.showarrow ? a.ax : a.xshift, dy = a.showarrow ? -a.ay : a.yshift;
            return Math.abs(dx - state.offset[0]) < 1 && Math.abs(dy - state.offset[1]) < 1;
        };
        var wait = function () {
            if (finished || !state.gd.once) return;
            state.gd.once('plotly_afterplot', function () { if (arrived()) setTimeout(done, 30); else wait(); });
        };
        wait();
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
                home: hit.home, moved: false, offset: hit.offset, leader: hit.leader,
                wasHome: !(hit.offset && (hit.offset[0] || hit.offset[1]))};
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
            // A moved name is an annotation: its line goes with it (hidden while the preview line is drawn).
            drag.hidden = drag.element.closest('.annotation') || drag.element;
            drag.hidden.style.opacity = '0';
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
        if (menu && event.key === 'Escape') closeMenu();
    }, true);

    // ---- right-click menu of a name ----------------------------------------------------------------------------
    var menu = null;
    function closeMenu() { if (menu) { menu.remove(); menu = null; } }
    function send(hit, offset, leader) {
        if (window.dash_clientside) window.dash_clientside.set_props('peak-label-move', {data: {
            peak_id: hit.peakId, offset: offset, leader: !!leader, ts: Date.now()}});
    }
    function item(label, enabled, action, checked) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'gecko-menu-item' + (checked ? ' checked' : '');
        button.setAttribute('role', checked === undefined ? 'menuitem' : 'menuitemcheckbox');
        if (checked !== undefined) button.setAttribute('aria-checked', String(!!checked));
        button.textContent = label;
        button.disabled = !enabled;
        button.addEventListener('click', function () { closeMenu(); action(); });
        return button;
    }
    function openMenu(gd, hit, event) {
        closeMenu();
        var moved = !!(hit.offset && (hit.offset[0] || hit.offset[1]));
        menu = document.createElement('div');
        menu.className = 'gecko-menu peak-label-menu';
        menu.setAttribute('role', 'menu');
        menu.appendChild(item('Connecting line', moved, function () { send(hit, hit.offset, !hit.leader); }, moved && hit.leader));
        menu.appendChild(item('Reset position', moved, function () { send(hit, null, false); }));
        var divider = document.createElement('div');
        divider.className = 'gecko-menu-divider';
        menu.appendChild(divider);
        menu.appendChild(item('Rename…', true, function () { window.GeckoFigureLabels.begin(gd, hit); }));
        if (!moved) {
            var note = document.createElement('div');
            note.className = 'peak-label-menu-note';
            note.textContent = 'Drag the name to move it';
            menu.insertBefore(note, menu.firstChild);
        }
        document.body.appendChild(menu);
        menu.style.left = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8) + 'px';
    }
    document.addEventListener('contextmenu', function (event) {
        var gd = event.target.closest && event.target.closest('.js-plotly-plot');
        var hit = gd && window.GeckoFigureLabels && window.GeckoFigureLabels.peakLabelAt(gd, event);
        if (!hit) return;
        event.preventDefault();               // the name's own menu, not the plot's
        event.stopPropagation();
        event.stopImmediatePropagation();
        openMenu(gd, hit, event);
    }, true);
    document.addEventListener('pointerdown', function (event) {
        if (menu && !menu.contains(event.target)) closeMenu();
    }, true);
})();
