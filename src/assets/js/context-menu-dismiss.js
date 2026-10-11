/**
 * Close the peak context menu on outside click or Escape.
 *
 * When the user clicks anywhere outside the .mantine-Menu-dropdown,
 * or presses Escape, bump context-menu-close-store so the Dash
 * callback closes the menu.
 */
(function () {
    'use strict';

    var menus = [
        {id: 'context-menu', dropdown: 'context-menu-dropdown', close: 'context-menu-close-store'},
        {id: 'ms-plot-context-menu', dropdown: 'ms-plot-context-dropdown', close: 'ms-plot-context-menu-close-store'},
        {id: 'figure-context-menu', dropdown: 'figure-context-dropdown', close: 'figure-context-close'}
    ];
    function dismiss(event) {
        var dc = window.dash_clientside;
        if (!dc || !dc.set_props) return;
        menus.forEach(function (menu) {
            var dropdown = document.getElementById(menu.dropdown);
            if (!dropdown || dropdown.offsetParent === null) return;
            if (event && dropdown.contains(event.target)) return;
            dc.set_props(menu.id, {opened: false});
            dc.set_props(menu.close, {data: Date.now()});
        });
    }
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') dismiss();
    });
    document.addEventListener('scroll', function () {dismiss();}, true);
})();
