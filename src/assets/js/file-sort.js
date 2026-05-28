/**
 * file-sort.js — Pointer-event drag reorder.
 * Clone follows cursor and repels siblings. Drop indicator is a thin line.
 */
(function() {
    'use strict';

    var state = null;
    var LINE_CLASS = 'drag-drop-line';

    function getSiblings(container) {
        return Array.from(container.querySelectorAll(':scope > .draggable-file-item'));
    }

    function clearLine() {
        document.querySelectorAll('.' + LINE_CLASS).forEach(function(el) {
            el.classList.remove(LINE_CLASS);
            el.style.borderTop = '';
            el.style.borderBottom = '';
        });
    }

    function onPointerDown(e) {
        if (e.button !== 0) return;
        if (e.target.tagName === 'BUTTON' || e.target.closest('button')) return;

        var el = e.target.closest('.draggable-file-item');
        if (!el) return;
        var container = el.closest('.file-group-container');
        if (!container) return;

        var siblings = getSiblings(container);
        if (siblings.length < 2) return;

        var rect = el.getBoundingClientRect();
        var idx = siblings.indexOf(el);
        var ids = siblings.map(function(s) { return s.getAttribute('data-file-id'); });

        // Floating clone
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

        // Collapse source
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
            container: container,
            siblings: siblings,
            ids: ids,
            srcIdx: idx,
            curIdx: idx,
            startY: e.clientY,
            origTop: rect.top,
            elHeight: rect.height,
        };

        e.preventDefault();
        document.addEventListener('pointermove', onPointerMove);
        document.addEventListener('pointerup', onPointerUp);
    }

    function onPointerMove(e) {
        if (!state) return;
        var dy = e.clientY - state.startY;
        state.clone.style.top = (state.origTop + dy) + 'px';

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

        // Thin line at the drop position
        if (state.srcIdx < newIdx) {
            // Dropping below: line under the target item
            state.siblings[newIdx].classList.add(LINE_CLASS);
            state.siblings[newIdx].style.borderBottom = '2px solid #ff6b35';
        } else if (state.srcIdx > newIdx) {
            // Dropping above: line above the target item
            state.siblings[newIdx].classList.add(LINE_CLASS);
            state.siblings[newIdx].style.borderTop = '2px solid #ff6b35';
        }
    }

    function onPointerUp() {
        if (!state) return;
        document.removeEventListener('pointermove', onPointerMove);
        document.removeEventListener('pointerup', onPointerUp);

        state.clone.remove();
        clearLine();

        var s = state.srcEl.style;
        s.transition = ''; s.maxHeight = ''; s.overflow = '';
        s.marginTop = ''; s.marginBottom = '';
        s.paddingTop = ''; s.paddingBottom = '';
        s.opacity = '';

        state.siblings.forEach(function(sib) {
            sib.style.transition = '';
            sib.style.transform = '';
        });

        var ids = state.ids.slice();
        if (state.curIdx !== state.srcIdx) {
            var moved = ids.splice(state.srcIdx, 1)[0];
            ids.splice(state.curIdx, 0, moved);
        }

        var groupId = null;
        try { groupId = JSON.parse(state.container.id).index; } catch(_) {}

        if (groupId && state.curIdx !== state.srcIdx &&
            window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('file-reorder-event', {
                data: { group_id: groupId, order: ids, ts: Date.now() }
            });
        }

        state = null;
    }

    document.addEventListener('pointerdown', onPointerDown);
})();
