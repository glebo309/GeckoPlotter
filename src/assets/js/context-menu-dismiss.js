/**
 * Close the peak context menu on outside click or Escape.
 *
 * When the user clicks anywhere outside the .mantine-Menu-dropdown,
 * or presses Escape, bump context-menu-close-store so the Dash
 * callback closes the menu.
 */
(function () {
    'use strict';

    function isMenuOpen() {
        var dropdown = document.querySelector('.mantine-Menu-dropdown');
        return dropdown && dropdown.offsetParent !== null;
    }

    document.addEventListener('mousedown', function (e) {
        if (!isMenuOpen()) return;
        var dropdown = document.querySelector('.mantine-Menu-dropdown');
        if (dropdown && !dropdown.contains(e.target)) {
            var store = document.getElementById('context-menu-close-store');
            if (store) {
                var cur = parseInt(store._dashprivate_value || '0', 10) || 0;
                window.dash_clientside && window.dash_clientside.set_props
                    ? window.dash_clientside.set_props('context-menu-close-store', {data: cur + 1})
                    : null;
            }
        }
    }, true);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && isMenuOpen()) {
            window.dash_clientside && window.dash_clientside.set_props
                ? window.dash_clientside.set_props('context-menu-close-store',
                    {data: (Date.now ? Date.now() : 0)})
                : null;
        }
    });
})();
