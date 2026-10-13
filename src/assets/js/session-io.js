// Project (.gecko) save / open / autosave, browser side.
//
//  * keyboard:   Cmd/Ctrl+S saves (the browser's own "save page" is suppressed), Cmd/Ctrl+O opens the file picker
//  * dirty flag: content changes set `session-dirty`; opening or saving clears it. Selection changes, plot
//                switching and settings hydration echoes are not changes. A restore replays dozens of store
//                writes: they are ignored until the workspace has been quiet for a moment.
//  * autosave:   ~20 s after the last change one write to `session-autosave-fire` runs the server autosave
//                (debounced here, so no polling and no dcc.Interval ticking while idle)
//  * unload:     the tab asks for confirmation only while there are unsaved changes
//  * open:       dropping or picking a .gecko file (or a FAIR package .zip that holds one) shows "Opening ..." at once;
//                the server callbacks route the file
//  * guard:      opening while there are unsaved changes first asks (plain-HTML bar #session-confirm): Save first /
//                Open anyway / Cancel. Picker, drop, banner Restore and the recent menu all go through it; an empty
//                or clean workspace opens without asking. No server round trip: the bar is driven from here.
(function () {
    'use strict';

    var AUTOSAVE_DELAY = 20000;   // ms after the last change
    var SETTLE_MS = 500;          // restore: no store activity for this long = the cascade has finished
    var SETTLE_MAX = 10000;       // ... but never wait longer than this
    var QUIET_MS = 2500;          // changes this soon after a restore are the restore itself
    // Stores whose change means "the project differs from what was saved".
    var CONTENT_IDS = ['loaded-files', 'peak-change-trigger', 'current-plot-settings', 'file-order', 'plot-tabs',
                       'cal-revision', 'hidden-files'];

    var state = {dirty: false, lastChange: 0, lastActivity: 0, quietUntil: 0, timer: null, seen: {}, settle: null,
                 pending: null, lastStampTs: null, bypass: false};

    function dc() { return window.dash_clientside || {}; }
    function nu() { return dc().no_update; }
    function now() { return Date.now(); }
    function later(fn, ms) { return window.setTimeout(fn, ms); }
    function setProps(id, props) {
        if (dc().set_props) dc().set_props(id, props);
    }
    function triggeredIds() {
        var ctx = dc().callback_context || {};
        return (ctx.triggered || []).map(function (t) { return String(t.prop_id).split('.')[0]; });
    }

    // ---- file names ---------------------------------------------------------
    // A project is a .gecko, or a FAIR package (.zip) that carries one (the server looks inside the zip).
    function isSessionFile(name) {
        return typeof name === 'string' && /\.(gecko|zip)$/i.test(name.trim());
    }
    function sessionFileIn(list) {
        for (var i = 0; list && i < list.length; i++) {
            var file = list[i];
            if (file && isSessionFile(file.name)) return file;
        }
        return null;
    }
    function showOpening(file) {
        setProps('session-status', {children: 'Opening ' + file.name + '…'});
    }


    // ---- unsaved-changes guard ----------------------------------------------------
    // `pending` = {run: fn that performs the open, saving: bool, stampTs}. The bar is plain HTML (#session-confirm).
    function showConfirm(show) { setProps('session-confirm', {hidden: !show}); }
    function setConfirmText(text) { setProps('session-confirm-text', {children: text}); }
    var CONFIRM_TEXT = 'Opening replaces the current workspace. Unsaved changes will be lost.';

    // Runs `run` now when nothing would be lost; otherwise asks first. Returns true when it asked (caller must stop).
    function guardOpen(run) {
        if (state.bypass || !state.dirty) return false;
        state.pending = {run: run, saving: false, stampTs: null};
        setConfirmText(CONFIRM_TEXT);
        showConfirm(true);
        return true;
    }
    function resolvePending(proceed) {
        var pending = state.pending;
        state.pending = null;
        showConfirm(false);
        if (!pending || !proceed) return;
        state.bypass = true;
        try { pending.run(); } finally { state.bypass = false; }
    }
    function confirmAction(action) {
        var pending = state.pending;
        if (!pending) { showConfirm(false); return; }
        if (action === 'cancel') { resolvePending(false); return; }
        if (action === 'discard') { resolvePending(true); return; }
        if (action === 'save') {
            pending.saving = true;
            pending.stampTs = state.lastStampTs;
            setConfirmText('Saving… the project opens as soon as it is saved.');
            savePressed();
        }
    }
    // Called from statusText on every dirty/stamp change: a finished save continues the open, a failed one stops waiting.
    function afterStatus(dirty, stamp) {
        state.lastStampTs = stamp ? stamp.ts : null;
        var pending = state.pending;
        if (!pending || !pending.saving) return;
        if (stamp && stamp.ts !== pending.stampTs) {
            if (stamp.kind === 'saved' && !dirty) { resolvePending(true); return; }
            if (stamp.kind === 'failed') {
                pending.saving = false;
                setConfirmText('Could not save. ' + CONFIRM_TEXT);
            }
        }
    }

    function readAsDataURL(file, done) {
        var reader = new window.FileReader();
        reader.onload = function () { done(String(reader.result)); };
        reader.onerror = function () { setProps('session-status', {children: 'Could not read ' + file.name}); };
        reader.readAsDataURL(file);
    }
    // Feed a user-chosen file to the Open flow (the same input the picker fills).
    function openFile(file) {
        showOpening(file);
        readAsDataURL(file, function (contents) {
            setProps('session-open-upload', {contents: contents, filename: file.name});
        });
    }

    // ---- change tracking ------------------------------------------------------
    function stable(value) {
        if (value === null || typeof value !== 'object') return JSON.stringify(value);
        if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
        return '{' + Object.keys(value).sort().map(function (k) {
            return JSON.stringify(k) + ':' + stable(value[k]);
        }).join(',') + '}';
    }

    // current-plot-settings is rewritten whenever the user switches plots (hydration). Only a changed value of a
    // context we have already seen is an edit.
    function settingsEdited(settings) {
        var key = settings && settings._context_key;
        if (!key) return false;
        var text = stable(settings), previous = state.seen[key];
        state.seen[key] = text;
        return previous !== undefined && previous !== text;
    }

    function cancelAutosave() {
        if (state.timer) { window.clearTimeout(state.timer); state.timer = null; }
    }
    function scheduleAutosave() {
        cancelAutosave();
        state.timer = later(function () {
            state.timer = null;
            setProps('session-autosave-fire', {data: now()});
        }, AUTOSAVE_DELAY);
    }

    // Inputs: loaded-files, peak-change-trigger, current-plot-settings, file-order, plot-tabs, cal-revision,
    // hidden-files, active-file, active-plot-tab.  State: session-dirty.  Output: session-dirty.
    function trackChange(loaded, peak, settings, order, tabs, cal, hidden, activeFile, activeTab, dirty) {
        var t = now(), ids = triggeredIds();
        state.lastActivity = t;
        if (!loaded || !loaded.length) {           // nothing to lose
            cancelAutosave();
            state.dirty = false;
            return dirty ? false : nu();
        }
        var changed = ids.filter(function (id) {
            if (CONTENT_IDS.indexOf(id) < 0) return false;
            return id === 'current-plot-settings' ? settingsEdited(settings) : true;
        });
        if (!changed.length) return nu();
        if (t < state.quietUntil) {                // still replaying a restore
            state.quietUntil = Math.max(state.quietUntil, t + SETTLE_MS);
            return nu();
        }
        state.lastChange = t;
        state.dirty = true;
        scheduleAutosave();
        return dirty ? nu() : true;
    }

    // ---- restore: finish after the browser has digested the new stores --------------
    // Input: session-restore-late. Output: session-late-go (written by the timer once the cascade went quiet).
    function armRestore(payload) {
        if (!payload) return nu();
        var started = now();
        if (state.settle) window.clearTimeout(state.settle);
        state.lastActivity = started;
        state.quietUntil = started + QUIET_MS + SETTLE_MAX;   // ignore everything until finishRestore narrows it
        cancelAutosave();
        (function poll() {
            var t = now();
            if (t - state.lastActivity < SETTLE_MS && t - started < SETTLE_MAX) {
                state.settle = later(poll, 150);
                return;
            }
            state.settle = null;
            setProps('session-late-go', {data: t});
        })();
        return nu();
    }

    // Input: session-late-go. States: session-restore-late, active-plot-tab, plot-tabs, active-plot-context,
    // plot-settings-cache. Output: none that matters (session-dirty is cleared once the quiet window ends).
    function finishRestore(go, payload, activePlotTab, tabs, context, cache) {
        if (!go || !payload) return nu();
        var target = payload.active_plot_tab;
        var known = (tabs || []).some(function (tab) { return tab && tab.id === target; });
        if (payload.plot_settings_cache) {
            // What the browser rebuilt wins; the saved cache only fills the plots it does not know yet.
            setProps('plot-settings-cache', {data: Object.assign({}, payload.plot_settings_cache, cache || {})});
        }
        if (target && known && target !== activePlotTab) {
            setProps('active-plot-tab', {data: target});     // the plot context changes, controls re-hydrate by themselves
        } else if (context) {
            setProps('plot-settings-miss', {data: context}); // same plot: have the server re-read the restored settings
        }
        state.quietUntil = now() + QUIET_MS;
        later(function () {
            cancelAutosave();
            state.dirty = false;
            setProps('session-dirty', {data: false});
        }, QUIET_MS + 100);
        return nu();
    }

    // ---- text ---------------------------------------------------------------------
    // Inputs: session-dirty, session-stamp. Output: session-status.children
    function statusText(dirty, stamp) {
        state.dirty = !!dirty;
        afterStatus(state.dirty, stamp);
        var at = stamp && stamp.at ? ' ' + stamp.at : '';
        if (stamp && stamp.kind === 'failed') return stamp.message || 'Could not complete';
        if (dirty) {
            if (stamp && stamp.kind === 'autosaved' && (stamp.fired || 0) >= state.lastChange) return 'Autosaved' + at;
            return 'Unsaved changes';
        }
        if (!stamp) return '';
        if (stamp.kind === 'saved') return 'Saved' + at;
        if (stamp.kind === 'opened') return 'Opened' + at;
        if (stamp.kind === 'autosaved') return 'Autosaved' + at;
        return '';
    }

    // Input: session-name. Output: session-name-btn.children
    function nameLabel(name) {
        var text = (name || '').trim() || 'Untitled project';
        try { document.title = (name || '').trim() ? text + ' - GeckoPlotter' : 'GeckoPlotter'; } catch (e) {}
        return text;
    }

    // ---- DOM wiring (keyboard, unload, drops, menu, rename) ----------------------
    function byId(id) { return document.getElementById(id); }
    function openPicker() {
        var input = document.querySelector('#session-open-upload input[type="file"]');
        if (input) input.click();
    }
    function savePressed() {
        var button = byId('session-save-btn');
        if (button) button.click();
    }

    function onKeyDown(e) {
        if (e.key === 'Escape' && state.pending) { resolvePending(false); return; }
        if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
        var key = String(e.key || '').toLowerCase();
        if (key !== 's' && key !== 'o') return;
        e.preventDefault();                           // never the browser's own Save page / Open file
        if (e.repeat) return;
        if (key === 's') savePressed(); else openPicker();
    }

    function onBeforeUnload(e) {
        if (!state.dirty) return undefined;
        e.preventDefault();
        e.returnValue = '';
        return '';
    }

    function swallow(e) {
        if (e.preventDefault) e.preventDefault();
        if (e.stopPropagation) e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    }
    function onDrop(e) {
        var file = sessionFileIn(e.dataTransfer && e.dataTransfer.files);
        if (!file) return;
        if (guardOpen(function () { openFile(file); })) { swallow(e); return; }   // the dropzone never sees it
        showOpening(file);
    }
    function onFileInput(e) {
        var target = e.target;
        if (!target || target.type !== 'file') return;
        var file = sessionFileIn(target.files);
        if (!file) return;
        if (guardOpen(function () { openFile(file); })) {
            swallow(e);
            try { target.value = ''; } catch (err) {}      // choosing the same file again must fire again
            return;
        }
        showOpening(file);
    }

    function setMenu(open) { setProps('session-open-menu', {hidden: !open}); }
    var menuOpen = false;
    function onClick(e) {
        var target = e.target && e.target.closest ? e.target : null;
        if (!target) return;
        var choice = target.closest('[data-confirm]');
        if (choice) { confirmAction(choice.getAttribute('data-confirm')); return; }
        var toggle = target.closest('#session-open-menu-btn');
        if (toggle) { menuOpen = !menuOpen; setMenu(menuOpen); return; }
        var restore = target.closest('#session-banner-restore');
        if (restore && guardOpen(function () { restore.click(); })) { swallow(e); return; }
        var item = target.closest('[data-session-action], [data-session-recent]');
        if (item) {
            var path = item.getAttribute('data-session-recent');
            if (path) {
                var pick = function () { setProps('session-recent-pick', {data: {path: path, ts: now()}}); };
                if (!guardOpen(pick)) pick();
            } else if (item.getAttribute('data-session-action') === 'open-file') openPicker();
        }
        if (menuOpen) { menuOpen = false; setMenu(false); }
    }

    function startRename() {
        var button = byId('session-name-btn');
        if (!button || byId('session-name-edit')) return;
        var shown = button.textContent === 'Untitled project' ? '' : button.textContent;
        var input = document.createElement('input');
        input.id = 'session-name-edit';
        input.type = 'text';
        input.className = 'session-name-edit';
        input.value = shown;
        input.placeholder = 'Project name';
        input.maxLength = 80;
        input.setAttribute('aria-label', 'Project name');
        var done = false;
        function finish(commit) {
            if (done) return;
            done = true;
            var value = input.value.trim();
            if (input.parentNode) input.parentNode.removeChild(input);
            button.style.display = '';
            if (commit && value !== shown) setProps('session-name', {data: value});
        }
        input.addEventListener('keydown', function (ev) {
            ev.stopPropagation();
            if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
            else if (ev.key === 'Escape') { ev.preventDefault(); finish(false); }
        });
        input.addEventListener('blur', function () { finish(true); });
        button.style.display = 'none';
        button.parentNode.insertBefore(input, button.nextSibling);
        input.focus();
        input.select();
    }
    function onNameClick(e) {
        if (e.target && e.target.closest && e.target.closest('#session-name-btn')) startRename();
    }
    function onDocMouseDown(e) {
        if (menuOpen && !(e.target && e.target.closest && e.target.closest('#session-open-menu, #session-open-menu-btn'))) {
            menuOpen = false;
            setMenu(false);
        }
    }

    function install() {
        window.addEventListener('keydown', onKeyDown, true);
        window.addEventListener('beforeunload', onBeforeUnload);
        window.addEventListener('drop', onDrop, true);
        document.addEventListener('change', onFileInput, true);
        document.addEventListener('click', onClick, true);
        document.addEventListener('click', onNameClick, true);
        document.addEventListener('mousedown', onDocMouseDown, true);
    }
    if (typeof document !== 'undefined' && document.addEventListener && window.addEventListener) install();

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        sessionIO: {
            trackChange: trackChange, armRestore: armRestore, finishRestore: finishRestore,
            statusText: statusText, nameLabel: nameLabel,
            isSessionFile: isSessionFile, sessionFileIn: sessionFileIn, guardOpen: guardOpen, confirmAction: confirmAction,
            onClick: onClick, onKeyDown: onKeyDown, onBeforeUnload: onBeforeUnload, onDrop: onDrop, onFileInput: onFileInput,
            state: state,
            CONSTANTS: {AUTOSAVE_DELAY: AUTOSAVE_DELAY, SETTLE_MS: SETTLE_MS, QUIET_MS: QUIET_MS, CONTENT_IDS: CONTENT_IDS}
        }
    });
}());
