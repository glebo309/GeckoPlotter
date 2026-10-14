/*
 * enter-submit.js
 * Pressing Enter in a field presses the button next to it: type an m/z and press Enter instead of clicking
 * Extract, name a peak and press Enter instead of clicking Save.
 *
 * A field opts in either through the table below or with the attribute data-enter-button="<button id>".
 * Shift/Ctrl/Cmd/Alt + Enter, text areas, table cells and disabled buttons are left alone.
 */
(function () {
    'use strict';
    var BUTTON_FOR = {
        'eic-mz-input': 'eic-extract-btn',
        'eic-tolerance-input': 'eic-extract-btn',
        'ctx-rename-input': 'ctx-rename-save',
        'session-name-input': 'session-name-confirm',
        'session-search-dir': 'session-retry-btn',
        'group-label-input': 'apply-group-btn'
    };

    function onKeyDown(e) {
        if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
        var field = e.target;
        if (!field || field.tagName !== 'INPUT') return;
        if (field.closest && field.closest('.dash-cell')) return;
        var buttonId = BUTTON_FOR[field.id] || (field.getAttribute && field.getAttribute('data-enter-button'));
        if (!buttonId) return;
        var button = document.getElementById(buttonId);
        if (!button || button.disabled || (button.hasAttribute && button.hasAttribute('data-disabled'))) return;
        e.preventDefault();
        e.stopPropagation();
        button.click();
    }

    document.addEventListener('keydown', onKeyDown, true);
    window.GeckoEnterSubmit = { buttonFor: BUTTON_FOR, onKeyDown: onKeyDown };
})();
