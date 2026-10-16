// The plot tools are one choice: Auto (the default), Integrate, Inspect or Edit text. Choosing one switches the
// others off; switching a tool off returns to Auto. Each tool keeps its own script (auto-integrate.js,
// plot-toolbar.js, plot-cursor.js, figure-label-edit.js); this only clicks the others off, after they have updated.
(function () {
    'use strict';
    var TOOLS = ['plot-tool-auto', 'plot-tool-integrate', 'plot-tool-inspect', 'plot-tool-edit-text'];
    var settling = false;

    function button(id) { return document.getElementById(id); }
    function on(id) { var b = button(id); return !!(b && b.classList.contains('active')); }
    function off(id) {
        if (!on(id)) return;
        if (id === 'plot-tool-auto' && window.GeckoAutoIntegrate) window.GeckoAutoIntegrate.toggle();
        else button(id).click();
    }

    function settle(chosen) {
        settling = true;
        try {
            if (on(chosen)) TOOLS.forEach(function (id) { if (id !== chosen) off(id); });
            else if (!TOOLS.some(on)) {
                var auto = button('plot-tool-auto');
                if (auto && window.GeckoAutoIntegrate) window.GeckoAutoIntegrate.toggle();
            }
        } finally {
            settling = false;
        }
    }

    document.addEventListener('click', function (event) {
        if (settling) return;
        var hit = event.target && event.target.closest && event.target.closest(TOOLS.map(function (id) {
            return '#' + id; }).join(','));
        if (!hit) return;
        // Integrate's state comes back through a Dash callback: wait for it before deciding.
        window.setTimeout(function () { settle(hit.id); }, 250);
    });
    // Esc leaves Edit text: back to Auto.
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') window.setTimeout(function () { if (!TOOLS.some(on)) settle('plot-tool-auto'); }, 250);
    });
    // Tools remembered from the last visit (Auto and Inspect are kept in the browser): one wins, the last chosen.
    var tries = 0, wait = window.setInterval(function () {
        if (!button('plot-tool-auto') && ++tries < 40) return;
        window.clearInterval(wait);
        var chosen = TOOLS.slice(1).filter(on)[0];
        if (chosen) settle(chosen);
    }, 250);
})();
