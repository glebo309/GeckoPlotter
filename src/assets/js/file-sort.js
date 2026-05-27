(function() {
    var dragSrcEl = null;

    function handleDragStart(e) {
        dragSrcEl = this;
        this.style.opacity = '0.4';
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', this.getAttribute('data-file-id'));
    }

    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var target = findDraggable(e.target);
        if (target && target !== dragSrcEl) {
            target.classList.add('drag-over');
        }
        return false;
    }

    function handleDragEnter(e) {
        var target = findDraggable(e.target);
        if (target) target.classList.add('drag-over');
    }

    function handleDragLeave(e) {
        var target = findDraggable(e.target);
        if (target) target.classList.remove('drag-over');
    }

    function handleDrop(e) {
        e.stopPropagation();
        e.preventDefault();
        var target = findDraggable(e.target);
        if (!target || !dragSrcEl || target === dragSrcEl) return;
        target.classList.remove('drag-over');

        var container = dragSrcEl.parentNode;
        var items = Array.from(container.querySelectorAll('.draggable-file-item'));
        var srcIdx = items.indexOf(dragSrcEl);
        var tgtIdx = items.indexOf(target);

        if (srcIdx < tgtIdx) {
            container.insertBefore(dragSrcEl, target.nextSibling);
        } else {
            container.insertBefore(dragSrcEl, target);
        }

        var newOrder = Array.from(container.querySelectorAll('.draggable-file-item'))
            .map(function(el) { return el.getAttribute('data-file-id'); })
            .filter(Boolean);

        var groupId = null;
        try {
            var parsed = JSON.parse(container.id);
            groupId = parsed.index;
        } catch(_) {}

        if (groupId && newOrder.length && window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('file-reorder-event', {
                data: { group_id: groupId, order: newOrder, ts: Date.now() }
            });
        }

        return false;
    }

    function handleDragEnd() {
        this.style.opacity = '1';
        document.querySelectorAll('.draggable-file-item').forEach(function(el) {
            el.classList.remove('drag-over');
        });
    }

    function findDraggable(el) {
        while (el && !el.classList.contains('draggable-file-item')) {
            el = el.parentElement;
        }
        return el;
    }

    function initDraggables() {
        document.querySelectorAll('.draggable-file-item').forEach(function(el) {
            if (el._dragInit) return;
            el._dragInit = true;
            el.draggable = true;
            el.addEventListener('dragstart', handleDragStart);
            el.addEventListener('dragover', handleDragOver);
            el.addEventListener('dragenter', handleDragEnter);
            el.addEventListener('dragleave', handleDragLeave);
            el.addEventListener('drop', handleDrop);
            el.addEventListener('dragend', handleDragEnd);
        });
    }

    var observer = new MutationObserver(function() { initDraggables(); });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', initDraggables);
})();
