// The peak Area header offers display units without changing the stored integration.
(function () {
    'use strict';
    var menu = null, anchor = null, queued = false;
    var units = ['mAU·min', 'mAU·s', 'µAU·s'];

    function current(header) {
        return units.find(function (unit) { return header.textContent.includes('(' + unit + ')'); });
    }
    function headerFor(target) {
        var header = target.closest && target.closest('th[data-dash-column="Area"]');
        return header && header.closest('#peak-table') && current(header) ? header : null;
    }
    function close(restoreFocus) {
        if (menu) { menu.remove(); menu = null; }
        if (restoreFocus && anchor) anchor.focus();
    }
    function open(header, x, y) {
        close(false);
        anchor = header.querySelector('.area-units-button');
        menu = document.createElement('div');
        menu.className = 'gecko-menu peak-label-menu area-units-menu';
        menu.setAttribute('role', 'menu');
        menu.setAttribute('aria-label', 'Area units');
        var title = document.createElement('div');
        title.className = 'peak-label-menu-note';
        title.textContent = 'Area units';
        menu.appendChild(title);
        units.forEach(function (unit) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'gecko-menu-item';
            button.setAttribute('role', 'menuitemradio');
            button.setAttribute('aria-checked', String(unit === current(header)));
            button.textContent = unit + (unit === 'mAU·min' ? ' (default)' : unit === 'µAU·s' ? ' (Shimadzu scale)' : '');
            button.addEventListener('click', function () {
                close(true);
                window.dash_clientside.set_props('area-display-unit', {data: unit});
            });
            menu.appendChild(button);
        });
        var note = document.createElement('div');
        note.className = 'peak-label-menu-note';
        note.textContent = 'Display units only. Integration stays unchanged.';
        menu.appendChild(note);
        document.body.appendChild(menu);
        menu.style.left = Math.max(8, Math.min(x, window.innerWidth - menu.offsetWidth - 8)) + 'px';
        menu.style.top = Math.max(8, Math.min(y, window.innerHeight - menu.offsetHeight - 8)) + 'px';
        menu.children[1].focus();
    }
    function decorate() {
        queued = false;
        document.querySelectorAll('#peak-table th[data-dash-column="Area"]').forEach(function (header) {
            var existing = header.querySelector('.area-units-button');
            if (!current(header)) { if (existing) existing.remove(); return; }
            if (existing) return;
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'area-units-button';
            button.textContent = '⋮';
            button.setAttribute('aria-label', 'Area units');
            button.setAttribute('aria-haspopup', 'menu');
            button.title = 'Area units (also available by right-click)';
            ['pointerdown', 'mousedown'].forEach(function (name) {
                button.addEventListener(name, function (event) { event.stopPropagation(); });
            });
            button.addEventListener('click', function (event) {
                event.preventDefault(); event.stopPropagation();
                var rect = button.getBoundingClientRect();
                open(header, rect.left, rect.bottom + 4);
            });
            header.appendChild(button);
        });
    }
    document.addEventListener('contextmenu', function (event) {
        var header = headerFor(event.target);
        if (!header) return;
        event.preventDefault(); event.stopPropagation();
        open(header, event.clientX, event.clientY);
    }, true);
    document.addEventListener('pointerdown', function (event) {
        if (menu && !menu.contains(event.target)) close(false);
    }, true);
    document.addEventListener('keydown', function (event) {
        if (!menu) return;
        if (event.key === 'Escape') { event.preventDefault(); close(true); }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            var choices = Array.from(menu.children).filter(function (item) { return item.getAttribute('role') === 'menuitemradio'; });
            var index = choices.indexOf(document.activeElement);
            choices[(index + (event.key === 'ArrowDown' ? 1 : choices.length - 1)) % choices.length].focus();
        }
    }, true);
    new MutationObserver(function () {
        if (!queued) { queued = true; window.requestAnimationFrame(decorate); }
    }).observe(document.body, {childList: true, subtree: true});
    decorate();
})();
