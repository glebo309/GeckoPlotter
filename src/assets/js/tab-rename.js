// Push contentEditable tab renames into the tab-rename-event store via set_props
(function() {
    document.addEventListener('focusout', function(e) {
        var el = e.target;
        if (!el || el.contentEditable !== 'true') return;
        var id;
        try { id = JSON.parse(el.id); } catch(_) { return; }
        if (!id || id.type !== 'plot-tab-label') return;
        var text = (el.textContent || '').trim();
        if (!text) return;
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('tab-rename-event', {
                data: { tab_id: id.index, new_label: text, ts: Date.now() }
            });
        }
    });

    document.addEventListener('keydown', function(e) {
        var el = e.target;
        if (!el || el.contentEditable !== 'true') return;
        if (e.key === 'Enter') { e.preventDefault(); el.blur(); }
    });
})();

// Rename any plot tab: double-click, right-click, or a single click while the pen (edit text) tool is on.
(function() {
    var editor = null;

    function close() {
        if (!editor) return;
        var old = editor; editor = null;
        old.remove();
    }

    function open(button) {
        close();
        var label = button.querySelector('[id*="plot-tab-label"]');
        var id;
        try { id = JSON.parse(label.id); } catch (_) { return; }
        var rect = label.getBoundingClientRect();
        var input = document.createElement('input');
        input.type = 'text';
        input.value = (label.textContent || '').trim();
        input.className = 'figure-label-editor';
        input.setAttribute('aria-label', 'Rename plot tab');
        input.title = 'Enter to apply · Esc to cancel';
        var width = Math.max(160, rect.width + 40);
        Object.assign(input.style, {
            position: 'fixed', zIndex: 5000, width: width + 'px',
            left: Math.max(8, Math.min(rect.left - 8, window.innerWidth - width - 8)) + 'px',
            top: Math.max(4, rect.top - 4) + 'px'
        });
        var done = false;
        function commit(apply) {
            if (done) return;
            done = true;
            var text = input.value.trim();
            close();
            if (apply && text && text !== (label.textContent || '').trim() &&
                window.dash_clientside && window.dash_clientside.set_props) {
                window.dash_clientside.set_props('tab-rename-event', {
                    data: { tab_id: id.index, new_label: text, ts: Date.now() }
                });
            }
        }
        input.addEventListener('keydown', function(e) {
            e.stopPropagation();
            if (e.key === 'Enter') { e.preventDefault(); commit(true); }
            else if (e.key === 'Escape') { e.preventDefault(); commit(false); }
        });
        input.addEventListener('blur', function() { commit(true); });
        document.body.appendChild(input);
        editor = input;
        input.focus();
        input.select();
    }

    function onEvent(e) {
        if (e.target.closest && e.target.closest('.figure-label-editor')) return;
        var button = e.target.closest && e.target.closest('.plot-tab-btn');
        if (!button || (e.target.closest && e.target.closest('[id*="plot-tab-close"]'))) return;
        var editing = document.body.classList.contains('gecko-text-edit-mode');
        if (e.type === 'click' && !editing) return;
        if (!button.querySelector('[id*="plot-tab-label"]')) return;
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (e.type === 'click' || e.type === 'dblclick' || e.type === 'contextmenu') open(button);
    }

    ['click', 'dblclick', 'contextmenu'].forEach(function(name) {
        document.addEventListener(name, onEvent, true);
    });
})();
