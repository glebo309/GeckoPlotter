// Channel switches above the plot (250 nm, +TIC, EIC 282.2 ...): right-click for Rename / Remove, double-click to
// rename. Both act on that channel in every run of the tab (channel-action -> file_tree_callbacks; Remove is undoable).
(function () {
    'use strict';
    var menu = null;

    function control(element) {
        var button = element.closest && element.closest('.group-channel-toggle');
        if (!button || !button.id) return null;
        try {
            var id = JSON.parse(button.id);
            return {button: button, group: id.group, channel: id.channel,
                    label: button.getAttribute('data-channel-label') || button.textContent.trim()};
        } catch (_) { return null; }
    }
    function send(target, action, extra) {
        if (!window.dash_clientside) return;
        var data = {action: action, group: target.group, channel: target.channel, ts: Date.now()};
        Object.keys(extra || {}).forEach(function (k) { data[k] = extra[k]; });
        window.dash_clientside.set_props('channel-action', {data: data});
    }
    function close() { if (menu) { menu.remove(); menu = null; } }

    function rename(target) {
        close();
        var rect = target.button.getBoundingClientRect();
        var input = document.createElement('input');
        input.type = 'text';
        input.value = target.label;
        input.className = 'figure-label-editor';
        input.setAttribute('aria-label', 'Channel name');
        input.title = 'Enter to rename in every run · Esc to cancel';
        Object.assign(input.style, {position: 'fixed', left: rect.left + 'px', top: (rect.top - 4) + 'px',
                                    width: Math.max(160, rect.width + 60) + 'px', zIndex: 5000});
        var done = false;
        function finish(apply) {
            if (done) return;
            done = true;
            var text = input.value.trim();
            input.remove();
            if (apply && text && text !== target.label) send(target, 'rename', {name: text});
        }
        input.addEventListener('keydown', function (event) {
            event.stopPropagation();
            if (event.key === 'Enter') { event.preventDefault(); finish(true); }
            else if (event.key === 'Escape') { event.preventDefault(); finish(false); }
        });
        input.addEventListener('blur', function () { finish(true); });
        document.body.appendChild(input);
        input.focus();
        input.select();
    }

    function item(label, action) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'gecko-menu-item';
        button.setAttribute('role', 'menuitem');
        button.textContent = label;
        button.addEventListener('click', function () { close(); action(); });
        return button;
    }

    document.addEventListener('contextmenu', function (event) {
        var target = control(event.target);
        if (!target) return;
        event.preventDefault();
        event.stopPropagation();
        close();
        menu = document.createElement('div');
        menu.className = 'gecko-menu peak-label-menu';
        menu.setAttribute('role', 'menu');
        var title = document.createElement('div');
        title.className = 'peak-label-menu-note';
        title.textContent = target.label + ' · in every run of this tab';
        menu.appendChild(title);
        menu.appendChild(item('Rename…', function () { rename(target); }));
        menu.appendChild(item('Remove channel', function () { send(target, 'remove'); }));
        document.body.appendChild(menu);
        menu.style.left = Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8) + 'px';
        menu.style.top = Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8) + 'px';
    }, true);
    document.addEventListener('dblclick', function (event) {
        var target = control(event.target);
        if (!target) return;
        event.preventDefault();
        rename(target);
    }, true);
    document.addEventListener('pointerdown', function (event) {
        if (menu && !menu.contains(event.target)) close();
    }, true);
    document.addEventListener('keydown', function (event) { if (menu && event.key === 'Escape') close(); }, true);
})();
