/**
 * file-sort.js: pointer-event drag & drop for the file tree.
 *
 * While dragging, the rows stay in place (dimmed). A small pill with the file
 * name ("N files" for a multi-selection) follows the pointer, offset so it does
 * not sit on top of the row being targeted. The drop target is shown in place:
 *   - another figure's header/body: outline + "Move to <figure>" label
 *   - between rows of the same figure: a thin insertion line (reorder)
 *   - the "New figure" zone at the bottom of the list: creates a new figure
 * Escape / pointercancel / window blur cancel the drag; dropping anywhere else
 * does nothing.
 *
 * Server events (unchanged shapes; multi-file moves add a backwards-compatible
 * `file_ids` list next to the legacy `file_id`):
 *   file-reorder-event  {group_id, order, ts}
 *   group-move-event    {file_id, source_group, target_group|null, [file_ids], ts}
 *
 * The pure logic (resolveDragIds, computeDropTarget, buildEvents) is exported on
 * window._geckoFileDrag for tests/js/file-drag.test.cjs.
 */
(function() {
    'use strict';

    var DRAG_THRESHOLD = 5;
    var PILL_OFFSET_X = 16;
    var PILL_OFFSET_Y = 18;

    // ---------------------------------------------------------------------
    // Pure logic
    // ---------------------------------------------------------------------

    function inRect(x, y, r) {
        return !!r && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    }

    /**
     * Which rows travel with the grabbed one. `items` are all draggable rows in
     * DOM order: {id, keys:[ids that may appear in the multi-selection]}.
     * Grabbing a row that belongs to a multi-selection (2+ rows) drags the whole
     * selection; grabbing any other row drags just that row.
     */
    function resolveDragIds(clickedId, items, selection) {
        var sel = {};
        (selection || []).forEach(function(k) { sel[k] = true; });
        var isSel = function(it) { return it.keys.some(function(k) { return sel[k]; }); };
        var clicked = items.filter(function(it) { return it.id === clickedId; })[0];
        var picked = items.filter(isSel);
        if ((selection || []).length > 1 && picked.length > 1 && clicked && isSel(clicked)) {
            return picked.map(function(it) { return it.id; });
        }
        return [clickedId];
    }

    /**
     * layout: {zone: rect|null, groups: [{id, header: rect|null, container: rect|null,
     *          rows: [{id, rect}]}]}   (rect = {left, top, right, bottom})
     * drag:   {ids: [rowId...] in DOM order, groupOf: {rowId: groupId}}
     * Returns null (no valid drop here) or one of
     *   {kind:'new'}
     *   {kind:'group', group}
     *   {kind:'reorder', group, index, lineY, left, right, order, changed}
     */
    function computeDropTarget(pt, layout, drag) {
        var ids = drag.ids;
        if (!ids.length) return null;

        if (inRect(pt.x, pt.y, layout.zone)) {
            // Moving every file of the only figure into a "new" one is a no-op.
            var srcGroups = {};
            ids.forEach(function(id) { srcGroups[drag.groupOf[id]] = true; });
            var srcList = Object.keys(srcGroups);
            if (srcList.length === 1) {
                var only = layout.groups.filter(function(g) { return g.id === srcList[0]; })[0];
                if (only && only.rows.length === ids.length) return null;
            }
            return {kind: 'new'};
        }

        for (var i = 0; i < layout.groups.length; i++) {
            var g = layout.groups[i];
            var allFromHere = ids.every(function(id) { return drag.groupOf[id] === g.id; });

            if (inRect(pt.x, pt.y, g.header)) {
                return allFromHere ? null : {kind: 'group', group: g.id};
            }
            if (!inRect(pt.x, pt.y, g.container)) continue;
            if (!allFromHere) return {kind: 'group', group: g.id};

            var dragged = {};
            ids.forEach(function(id) { dragged[id] = true; });
            var rest = g.rows.filter(function(r) { return !dragged[r.id]; });
            if (!rest.length) return null;

            var index = rest.length;
            for (var j = 0; j < rest.length; j++) {
                var mid = (rest[j].rect.top + rest[j].rect.bottom) / 2;
                if (pt.y < mid) { index = j; break; }
            }
            var lineY = index < rest.length ? rest[index].rect.top : rest[rest.length - 1].rect.bottom;
            var order = rest.map(function(r) { return r.id; });
            // Dragged rows keep their relative DOM order.
            var block = g.rows.filter(function(r) { return dragged[r.id]; }).map(function(r) { return r.id; });
            Array.prototype.splice.apply(order, [index, 0].concat(block));
            var original = g.rows.map(function(r) { return r.id; });
            return {
                kind: 'reorder', group: g.id, index: index, lineY: lineY,
                left: g.container.left, right: g.container.right,
                order: order, changed: order.join('\u0000') !== original.join('\u0000'),
            };
        }
        return null;
    }

    /** Server events for a drop: [{target: storeId, data}] (empty when nothing changes). */
    function buildEvents(drop, drag, ts) {
        if (!drop) return [];
        if (drop.kind === 'reorder') {
            return drop.changed
                ? [{target: 'file-reorder-event', data: {group_id: drop.group, order: drop.order, ts: ts}}]
                : [];
        }
        var ids = drag.ids.filter(function(id) {
            return drop.kind === 'new' || drag.groupOf[id] !== drop.group;
        });
        if (!ids.length) return [];
        var data = {
            file_id: ids[0],
            source_group: drag.groupOf[ids[0]],
            target_group: drop.kind === 'new' ? null : drop.group,
            ts: ts,
        };
        if (ids.length > 1) data.file_ids = ids.slice();
        return [{target: 'group-move-event', data: data}];
    }

    if (typeof window !== 'undefined') {
        window._geckoFileDrag = {
            resolveDragIds: resolveDragIds,
            computeDropTarget: computeDropTarget,
            buildEvents: buildEvents,
        };
    }

    // ---------------------------------------------------------------------
    // DOM layer
    // ---------------------------------------------------------------------

    var pending = null;
    var state = null;
    var suppressClickUntil = 0;

    function rectOf(el) {
        if (!el) return null;
        var r = el.getBoundingClientRect();
        if (!r.width && !r.height) return null;   // display:none (collapsed)
        return {left: r.left, top: r.top, right: r.right, bottom: r.bottom};
    }

    function groupIdOf(container) {
        try { return JSON.parse(container.id).index; } catch (_) { return null; }
    }

    function groupLabel(container) {
        var header = container.previousElementSibling;
        if (!header || !header.classList.contains('file-group-header')) return '';
        var spans = header.querySelectorAll('.group-disclosure-btn span');
        var last = spans.length ? spans[spans.length - 1] : null;
        return last ? last.textContent.trim() : '';
    }

    function rowName(row) {
        var n = row.querySelector('.dataset-name');
        return (n ? n.textContent : row.textContent || '').trim();
    }

    function rowKeys(row) {
        var keys = [row.getAttribute('data-file-id')];
        row.querySelectorAll('[data-file-key]').forEach(function(k) { keys.push(k.getAttribute('data-file-key')); });
        return keys.filter(Boolean);
    }

    function allRows() {
        return Array.from(document.querySelectorAll('.draggable-file-item'));
    }

    function readLayout(withZone) {
        var groups = Array.from(document.querySelectorAll('.file-group-container')).map(function(c) {
            var header = c.previousElementSibling;
            if (header && !header.classList.contains('file-group-header')) header = null;
            return {
                id: groupIdOf(c),
                el: c,
                headerEl: header,
                header: rectOf(header),
                container: rectOf(c),
                rows: Array.from(c.querySelectorAll(':scope > .draggable-file-item')).map(function(r) {
                    return {id: r.getAttribute('data-file-id'), rect: rectOf(r)};
                }),
            };
        });
        return {
            zone: withZone && state && state.zoneEl ? rectOf(state.zoneEl) : null,
            groups: groups,
        };
    }

    function ensureLine() {
        if (!state.lineEl) {
            state.lineEl = document.createElement('div');
            state.lineEl.className = 'file-drag-line';
            document.body.appendChild(state.lineEl);
        }
        return state.lineEl;
    }

    function clearIndicators() {
        document.querySelectorAll('.file-drag-target, .file-drag-target-body').forEach(function(el) {
            el.classList.remove('file-drag-target', 'file-drag-target-body');
            el.removeAttribute('data-drop-label');
        });
        if (state && state.zoneEl) state.zoneEl.classList.remove('file-drag-zone-hot');
        if (state && state.lineEl) state.lineEl.style.display = 'none';
    }

    function showIndicator(drop, layout) {
        clearIndicators();
        if (!drop) return;
        if (drop.kind === 'new') {
            state.zoneEl.classList.add('file-drag-zone-hot');
        } else if (drop.kind === 'group') {
            var g = layout.groups.filter(function(x) { return x.id === drop.group; })[0];
            if (!g) return;
            var label = 'Move to ' + groupLabel(g.el);
            var host = g.headerEl || g.el;
            host.classList.add('file-drag-target');
            host.setAttribute('data-drop-label', label);
            g.el.classList.add('file-drag-target-body');
        } else if (drop.kind === 'reorder') {
            var line = ensureLine();
            line.style.display = 'block';
            line.style.left = drop.left + 'px';
            line.style.width = (drop.right - drop.left) + 'px';
            line.style.top = (drop.lineY - 1) + 'px';
            line.classList.toggle('file-drag-line-noop', !drop.changed);
        }
    }

    function movePill(x, y) {
        var pill = state.pillEl;
        var w = pill.offsetWidth || 120, h = pill.offsetHeight || 22;
        var left = x + PILL_OFFSET_X, top = y + PILL_OFFSET_Y;
        var vw = window.innerWidth || 0, vh = window.innerHeight || 0;
        if (vw && left + w > vw - 4) left = x - PILL_OFFSET_X - w;   // flip left near the edge
        if (vh && top + h > vh - 4) top = y - PILL_OFFSET_Y - h;      // flip above near the bottom
        pill.style.transform = 'translate(' + Math.round(left) + 'px,' + Math.round(top) + 'px)';
    }

    function update(x, y) {
        movePill(x, y);
        var layout = readLayout(true);
        state.drop = computeDropTarget({x: x, y: y}, layout, state.drag);
        showIndicator(state.drop, layout);
    }

    function onPointerDown(e) {
        if (e.button !== 0) return;
        if (e.target.tagName === 'BUTTON' || (e.target.closest && e.target.closest('button'))) return;
        var el = e.target.closest && e.target.closest('.draggable-file-item');
        if (!el) return;
        var container = el.closest('.file-group-container');
        if (!container) return;

        var multipleGroups = document.querySelectorAll('.file-group-container').length > 1;
        if (container.querySelectorAll(':scope > .draggable-file-item').length < 2 && !multipleGroups) return;

        pending = {el: el, startX: e.clientX, startY: e.clientY};
        document.addEventListener('pointermove', onPointerMove);
        document.addEventListener('pointerup', onPointerUp);
        document.addEventListener('pointercancel', cancelDrag);
        document.addEventListener('keydown', onKeyDown, true);
    }

    function startDrag(p) {
        var rows = allRows();
        var items = rows.map(function(r) { return {id: r.getAttribute('data-file-id'), keys: rowKeys(r), el: r}; });
        var selection = window._geckoGetFileSelection ? window._geckoGetFileSelection() : [];
        var clickedId = p.el.getAttribute('data-file-id');
        var ids = resolveDragIds(clickedId, items, selection);
        // DOM order, for a stable event payload and block-move order.
        ids = items.filter(function(it) { return ids.indexOf(it.id) >= 0; }).map(function(it) { return it.id; });

        var groupOf = {};
        var dragEls = [];
        items.forEach(function(it) {
            var c = it.el.closest('.file-group-container');
            groupOf[it.id] = c ? groupIdOf(c) : null;
            if (ids.indexOf(it.id) >= 0) dragEls.push(it.el);
        });

        var pill = document.createElement('div');
        pill.className = 'file-drag-pill';
        pill.textContent = ids.length > 1 ? ids.length + ' files' : rowName(p.el);
        document.body.appendChild(pill);

        dragEls.forEach(function(el) { el.classList.add('file-drag-source'); });
        document.body.classList.add('file-drag-active');

        var zoneEl = null;
        var tree = document.getElementById('file-tree');
        if (tree) {
            zoneEl = document.createElement('div');
            zoneEl.className = 'file-drag-zone';
            zoneEl.textContent = 'New figure';
            tree.appendChild(zoneEl);
        }

        state = {drag: {ids: ids, groupOf: groupOf}, dragEls: dragEls, pillEl: pill, zoneEl: zoneEl,
                 lineEl: null, drop: null, lastX: p.startX, lastY: p.startY};
        pending = null;
    }

    function onPointerMove(e) {
        if (pending) {
            if (Math.abs(e.clientX - pending.startX) < DRAG_THRESHOLD &&
                Math.abs(e.clientY - pending.startY) < DRAG_THRESHOLD) return;
            startDrag(pending);
        }
        if (!state) return;
        state.lastX = e.clientX;
        state.lastY = e.clientY;
        update(e.clientX, e.clientY);
    }

    function onScroll() {
        if (state) update(state.lastX, state.lastY);
    }

    function teardown() {
        document.removeEventListener('pointermove', onPointerMove);
        document.removeEventListener('pointerup', onPointerUp);
        document.removeEventListener('pointercancel', cancelDrag);
        document.removeEventListener('keydown', onKeyDown, true);
        pending = null;
        if (!state) return;
        clearIndicators();
        state.dragEls.forEach(function(el) { el.classList.remove('file-drag-source'); });
        if (state.pillEl) state.pillEl.remove();
        if (state.lineEl) state.lineEl.remove();
        if (state.zoneEl) state.zoneEl.remove();
        document.body.classList.remove('file-drag-active');
        state = null;
        suppressClickUntil = Date.now() + 120;
    }

    function cancelDrag() { teardown(); }

    function onKeyDown(e) {
        if (e.key === 'Escape') {
            if (state) { e.preventDefault(); e.stopPropagation(); }
            teardown();
        }
    }

    function onPointerUp() {
        if (!state) { teardown(); return; }
        var events = buildEvents(state.drop, state.drag, Date.now());
        teardown();
        if (window.dash_clientside && window.dash_clientside.set_props) {
            events.forEach(function(ev) { window.dash_clientside.set_props(ev.target, {data: ev.data}); });
        }
    }

    document.addEventListener('pointerdown', onPointerDown);
    // The click that follows a drag must not select/toggle a row.
    document.addEventListener('click', function(e) {
        if (Date.now() < suppressClickUntil) { e.stopPropagation(); e.preventDefault(); }
    }, true);
    document.addEventListener('scroll', onScroll, true);
    if (window.addEventListener) window.addEventListener('blur', cancelDrag);
})();
