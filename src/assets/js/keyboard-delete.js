/**
 * keyboard-delete.js
 * Listen for Backspace / Delete / X and bump the keyboard-delete-trigger
 * dcc.Store so Dash can react server-side (delete the selected peak).
 *
 * Uses capture phase (third arg = true) so the event is caught before
 * Plotly's own keydown handlers can swallow it.
 */
(function () {
    'use strict';

    var DELETE_KEYS = { Backspace: 1, Delete: 1, x: 1, X: 1 };

    function isTypingTarget(el) {
        if (!el) return false;
        var tag = el.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return true;
        if (el.isContentEditable) return true;
        if (el.closest && el.closest('.dash-cell')) return true;
        return false;
    }

    document.addEventListener('keydown', function (e) {
        if (!DELETE_KEYS[e.key]) return;
        if (isTypingTarget(e.target)) return;
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('keyboard-delete-trigger', { data: Date.now() });
        }

        if (e.key === 'Backspace') e.preventDefault();
    }, true);
})();
