/**
 * file-sort.js — Pointer-event drag reorder.
 * Clone follows cursor and repels siblings. Drop indicator is a thin line.
 * Supports within-group reorder and cross-group moves.
 */
(function() {
    'use strict';

    var state = null;
    var pending = null;
    var DRAG_THRESHOLD = 5;
    var LINE_CLASS = 'drag-drop-line';

    function getSiblings(container) {
        return Array.from(container.querySelectorAll(':scope > .draggable-file-item'));
    }

    function getAllGroupContainers() {
        return Array.from(document.querySelectorAll('.file-group-container'));
    }

    function getGroupId(container) {
        try { return JSON.parse(container.id).index; } catch(_) { return null; }
    }

    function clearLine() {
        document.querySelectorAll('.' + LINE_CLASS).forEach(function(el) {
            el.classList.remove(LINE_CLASS);
            el.style.borderTop = '';
            el.style.borderBottom = '';
        });
    }

    function clearGroupHighlight() {
        getAllGroupContainers().forEach(function(el) {
            el.style.outline = '';
            el.style.outlineOffset = '';
        });
    }

    function containerAtPoint(x, y, excludeContainer) {
        var containers = getAllGroupContainers();
        for (var i = 0; i < containers.length; i++) {
            if (containers[i] === excludeContainer) continue;
            var r = containers[i].getBoundingClientRect();
            if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
                return containers[i];
            }
        }
        return null;
    }

    function onPointerDown(e) {
        if (e.button !== 0) return;
        if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;

        var el = e.target.closest('.draggable-file-item');
        if (!el) return;
        var container = el.closest('.file-group-container');
        if (!container) return;

        var siblings = getSiblings(container);
        var multipleGroups = getAllGroupContainers().length > 1;
        if (siblings.length < 2 && !multipleGroups) return;

        pending = {
            el: el,
            container: container,
            siblings: siblings,
            startX: e.clientX,
            startY: e.clientY,
        };

        document.addEventListener('pointermove', onPointerMove);
        document.addEventListener('pointerup', onPointerUp);
    }

    function startDrag(p) {
        var el = p.el;
        var rect = el.getBoundingClientRect();
        var idx = p.siblings.indexOf(el);
        var ids = p.siblings.map(function(s) { return s.getAttribute('data-file-id'); });

        var clone = el.cloneNode(true);
        clone.className = 'drag-clone';
        clone.style.cssText = [
            'position:fixed', 'z-index:10000',
            'width:' + rect.width + 'px',
            'left:' + rect.left + 'px',
            'top:' + rect.top + 'px',
            'opacity:0.92', 'pointer-events:none',
            'background:#fff', 'border-radius:4px',
            'box-shadow:0 4px 16px rgba(0,0,0,0.18)',
        ].join(';');
        document.body.appendChild(clone);

        el.style.transition = 'max-height 0.15s ease, margin 0.15s ease, padding 0.15s ease, opacity 0.1s ease';
        el.style.maxHeight = '0';
        el.style.overflow = 'hidden';
        el.style.marginTop = '0';
        el.style.marginBottom = '0';
        el.style.paddingTop = '0';
        el.style.paddingBottom = '0';
        el.style.opacity = '0';

        state = {
            srcEl: el,
            clone: clone,
            container: p.container,
            siblings: p.siblings,
            ids: ids,
            srcIdx: idx,
            curIdx: idx,
            startY: p.startY,
            origTop: rect.top,
            elHeight: rect.height,
            targetContainer: null,
            lastX: p.startX,
            lastY: p.startY,
        };

        pending = null;
    }

    function onPointerMove(e) {
        if (pending) {
            var dx = e.clientX - pending.startX;
            var dy = e.clientY - pending.startY;
            if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
            startDrag(pending);
        }
        if (!state) return;
        state.lastX = e.clientX;
        state.lastY = e.clientY;
        var dy = e.clientY - state.startY;
        state.clone.style.top = (state.origTop + dy) + 'px';

        var otherContainer = containerAtPoint(e.clientX, e.clientY, state.container);

        if (otherContainer) {
            if (state.targetContainer !== otherContainer) {
                clearLine();
                clearGroupHighlight();
                state.siblings.forEach(function(sib) {
                    sib.style.transition = 'transform 0.15s ease';
                    sib.style.transform = '';
                });
                state.targetContainer = otherContainer;
                otherContainer.style.outline = '2px solid #1a1a1a';
                otherContainer.style.outlineOffset = '-2px';
            }
            return;
        }

        if (state.targetContainer) {
            clearGroupHighlight();
            state.targetContainer = null;
        }

        var cloneMid = state.origTop + dy + state.elHeight / 2;
        var newIdx = state.siblings.length - 1;

        for (var i = 0; i < state.siblings.length; i++) {
            if (i === state.srcIdx) continue;
            var sib = state.siblings[i];
            var r = sib.getBoundingClientRect();
            var curShift = 0;
            var m = (sib.style.transform || '').match(/translateY\(([-\d.]+)px\)/);
            if (m) curShift = parseFloat(m[1]);
            var baseMid = (r.top - curShift) + r.height / 2;

            if (cloneMid < baseMid) {
                newIdx = i;
                break;
            }
        }

        if (newIdx === state.curIdx) return;
        state.curIdx = newIdx;

        clearLine();

        for (var j = 0; j < state.siblings.length; j++) {
            var s = state.siblings[j];
            if (j === state.srcIdx) continue;

            var shift = 0;
            if (state.srcIdx < newIdx) {
                if (j > state.srcIdx && j <= newIdx) shift = -state.elHeight;
            } else if (state.srcIdx > newIdx) {
                if (j >= newIdx && j < state.srcIdx) shift = state.elHeight;
            }

            s.style.transition = 'transform 0.15s ease';
            s.style.transform = shift ? 'translateY(' + shift + 'px)' : '';
        }

        if (state.srcIdx < newIdx) {
            state.siblings[newIdx].classList.add(LINE_CLASS);
            state.siblings[newIdx].style.borderBottom = '2px solid #1a1a1a';
        } else if (state.srcIdx > newIdx) {
            state.siblings[newIdx].classList.add(LINE_CLASS);
            state.siblings[newIdx].style.borderTop = '2px solid #1a1a1a';
        }
    }

    function onPointerUp() {
        document.removeEventListener('pointermove', onPointerMove);
        document.removeEventListener('pointerup', onPointerUp);

        if (pending) {
            pending = null;
            return;
        }
        if (!state) return;

        state.clone.remove();
        clearLine();
        clearGroupHighlight();

        var s = state.srcEl.style;
        s.transition = ''; s.maxHeight = ''; s.overflow = '';
        s.marginTop = ''; s.marginBottom = '';
        s.paddingTop = ''; s.paddingBottom = '';
        s.opacity = '';

        state.siblings.forEach(function(sib) {
            sib.style.transition = '';
            sib.style.transform = '';
        });

        var sourceGroupId = getGroupId(state.container);
        var fileId = state.ids[state.srcIdx];

        if (state.targetContainer) {
            var targetGroupId = getGroupId(state.targetContainer);
            if (targetGroupId && sourceGroupId && targetGroupId !== sourceGroupId &&
                window.dash_clientside && window.dash_clientside.set_props) {
                window.dash_clientside.set_props('group-move-event', {
                    data: {
                        file_id: fileId,
                        source_group: sourceGroupId,
                        target_group: targetGroupId,
                        ts: Date.now(),
                    }
                });
            }
            state = null;
            return;
        }

        // Check if pointer ended up outside all group containers (create new group)
        var droppedOutside = !containerAtPoint(state.lastX, state.lastY, null);

        if (droppedOutside && sourceGroupId && state.siblings.length > 1 &&
            window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('group-move-event', {
                data: {
                    file_id: fileId,
                    source_group: sourceGroupId,
                    target_group: null,
                    ts: Date.now(),
                }
            });
            state = null;
            return;
        }

        var ids = state.ids.slice();
        if (state.curIdx !== state.srcIdx) {
            var moved = ids.splice(state.srcIdx, 1)[0];
            ids.splice(state.curIdx, 0, moved);
        }

        if (sourceGroupId && state.curIdx !== state.srcIdx &&
            window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('file-reorder-event', {
                data: { group_id: sourceGroupId, order: ids, ts: Date.now() }
            });
        }

        state = null;
    }

    document.addEventListener('pointerdown', onPointerDown);
})();
