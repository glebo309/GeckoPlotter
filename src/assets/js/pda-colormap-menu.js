// Right-click the PDA heatmap to choose its colour map (remembered in the pda-colormap store).
(function () {
    'use strict';
    var menu = null;
    function options() {
        var el = document.getElementById('pda-colormap-options');
        try { return JSON.parse(el.getAttribute('data-options')); } catch (e) { return []; }
    }
    function current() {
        try { return JSON.parse(localStorage.getItem('pda-colormap')) || 'Viridis'; } catch (e) { return 'Viridis'; }
    }
    function close() { if (menu) { menu.remove(); menu = null; } }
    function choose(name) {
        window.dash_clientside.set_props('pda-colormap', {data: name});
        try { localStorage.setItem('pda-colormap', JSON.stringify(name)); } catch (e) {}
        close();
    }
    function open(e) {
        var host = document.getElementById('pda-heatmap');
        if (!host || !host.contains(e.target)) return;
        // Registered on window (capture), so this is the only menu opened for a right-click on the heatmap.
        e.preventDefault(); e.stopImmediatePropagation(); close();
        var now = current();
        menu = document.createElement('div');
        menu.className = 'pda-colormap-menu'; menu.setAttribute('role', 'menu');
        var title = document.createElement('div'); title.className = 'pda-colormap-title'; title.textContent = 'Colour map';
        menu.appendChild(title);
        options().forEach(function (name) {
            var item = document.createElement('button');
            item.type = 'button'; item.setAttribute('role', 'menuitemradio');
            item.setAttribute('aria-checked', String(name === now));
            item.textContent = (name === now ? '✓ ' : '') + name;
            item.addEventListener('click', function () { choose(name); });
            menu.appendChild(item);
        });
        document.body.appendChild(menu);
        var w = menu.offsetWidth, h = menu.offsetHeight;
        menu.style.left = Math.max(4, Math.min(e.clientX, window.innerWidth - w - 4)) + 'px';
        menu.style.top = Math.max(4, Math.min(e.clientY, window.innerHeight - h - 4)) + 'px';
    }
    window.addEventListener('contextmenu', open, true);
    document.addEventListener('mousedown', function (e) { if (menu && !menu.contains(e.target)) close(); }, true);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); }, true);
    window.addEventListener('blur', close);
})();
