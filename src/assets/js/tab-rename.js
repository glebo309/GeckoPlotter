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

// Rename any plot tab: double-click, right-click, or a single click while the pen (edit text) tool is on. A group in
// the file tree is the same tab: double-clicking its name renames both.
(function() {
    var editor = null;

    function close() {
        if (!editor) return;
        var old = editor; editor = null;
        old.remove();
    }

    // A double-click on a group's name also clicks its expand/collapse button: the second click is stopped, and the
    // first one is undone once the name is entered, so the group stays as it was.
    var groupWas = null;
    document.addEventListener('pointerdown', function (e) {
        var label = e.target.closest && e.target.closest('.file-group-header .group-label');
        if (label && e.detail <= 1) {
            var btn = label.closest('button');
            groupWas = { id: label.getAttribute('data-group-id'), expanded: btn && btn.getAttribute('aria-expanded') };
        }
    }, true);
    document.addEventListener('click', function (e) {
        if (e.detail >= 2 && e.target.closest && e.target.closest('.file-group-header .group-label')) {
            e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
        }
    }, true);
    function restoreGroup(id) {
        if (!groupWas || groupWas.id !== id) return;
        var was = groupWas.expanded; groupWas = null;
        window.setTimeout(function () {
            var label = document.querySelector('.file-group-header .group-label[data-group-id="' + id + '"]');
            var btn = label && label.closest('button');
            if (btn && was && btn.getAttribute('aria-expanded') !== was) btn.click();
        }, 600);
    }

    function open(button, groupLabel) {
        close();
        var label = groupLabel || button.querySelector('[id*="plot-tab-label"]');
        var id;
        if (groupLabel) id = { index: groupLabel.getAttribute('data-group-id') };
        else { try { id = JSON.parse(label.id); } catch (_) { return; } }
        if (!id.index) return;
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
            if (groupLabel) restoreGroup(id.index);
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
        var group = e.type === 'dblclick' && e.target.closest && e.target.closest('.file-group-header .group-label');
        if (group) {
            e.preventDefault();
            e.stopPropagation();
            open(null, group);
            return;
        }
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
