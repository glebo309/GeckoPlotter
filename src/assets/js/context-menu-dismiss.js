/**
 * Close the peak context menu on outside click or Escape.
 *
 * When the user clicks anywhere outside a .gecko-menu popup,
 * or presses Escape, bump context-menu-close-store so the Dash
 * callback closes the menu.
 */
(function () {
    'use strict';

    var menus = [
        {id: 'context-menu', close: 'context-menu-close-store'},
        {id: 'ms-plot-context-menu', close: 'ms-plot-context-menu-close-store'},
        {id: 'figure-context-menu', close: 'figure-context-close'}
    ];
    function dismiss(event) {
        if (document.querySelectorAll) {
            document.querySelectorAll('details.gesture-help[open]').forEach(function (details) {
                if (!event || !details.contains(event.target)) details.removeAttribute('open');
            });
        }
        var dc = window.dash_clientside;
        if (!dc || !dc.set_props) return;
        menus.forEach(function (menu) {
            var dropdown = document.getElementById(menu.id);
            if (!dropdown || dropdown.hidden || dropdown.offsetParent === null) return;
            if (event && dropdown.contains(event.target)) return;
            dc.set_props(menu.id, {hidden: true});
            dc.set_props(menu.close, {data: Date.now()});
        });
    }
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') dismiss();
    });
    document.addEventListener('scroll', function () {dismiss();}, true);
})();
