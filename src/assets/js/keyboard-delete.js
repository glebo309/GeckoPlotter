/**
 * keyboard-delete.js
 * Keyboard shortcuts for GeckoPlotter.
 *
 * Uses capture phase (third arg = true) so the event is caught before
 * Plotly's own keydown handlers can swallow it.
 *
 * Shortcuts:
 *   Backspace / Delete / X / x  — delete selected peak
 *   Ctrl+Z / Cmd+Z             — undo
 *   Ctrl+Shift+Z / Cmd+Shift+Z — redo
 *   Escape                      — deselect peak / exit mode
 *   ArrowLeft / ArrowRight      — cycle through peaks
 *   S / s                       — toggle superposed / subplots
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

    function setProps(id, data) {
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props(id, { data: data });
        }
    }

    document.addEventListener('keydown', function (e) {
        if (isTypingTarget(e.target)) return;

        var mod = e.ctrlKey || e.metaKey;

        // Undo: Ctrl/Cmd + Z (no shift)
        if (mod && !e.shiftKey && e.key === 'z') {
            e.preventDefault();
            setProps('undo-trigger', Date.now());
            return;
        }

        // Redo: Ctrl/Cmd + Shift + Z
        if (mod && e.shiftKey && (e.key === 'Z' || e.key === 'z')) {
            e.preventDefault();
            setProps('redo-trigger', Date.now());
            return;
        }

        // Skip modifier combos for remaining shortcuts
        if (mod || e.altKey) return;

        // Delete peak
        if (DELETE_KEYS[e.key]) {
            setProps('keyboard-delete-trigger', Date.now());
            if (e.key === 'Backspace') e.preventDefault();
            return;
        }

        // Escape — deselect
        if (e.key === 'Escape') {
            setProps('keyboard-action-trigger', { action: 'escape', ts: Date.now() });
            return;
        }

        // Arrow keys — cycle peaks
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            setProps('keyboard-action-trigger', { action: 'prev_peak', ts: Date.now() });
            return;
        }
        if (e.key === 'ArrowRight') {
            e.preventDefault();
            setProps('keyboard-action-trigger', { action: 'next_peak', ts: Date.now() });
            return;
        }

        // S — toggle layout mode
        if (e.key === 's' || e.key === 'S') {
            setProps('keyboard-action-trigger', { action: 'toggle_layout', ts: Date.now() });
            return;
        }
    }, true);
})();
