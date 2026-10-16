const test = require('node:test');
const plain = value => JSON.parse(JSON.stringify(value));   // values built inside the vm have another Object prototype
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Loads session-io.js against a fake browser with a controllable clock and timers.
function load(options = {}) {
    const listeners = {window: {}, document: {}};
    const props = [], timers = [], clicks = [];
    let clock = 1000000, nextTimer = 1, triggered = [];
    const NO = {no_update: true};
    const elements = {'session-save-btn': {click: () => clicks.push('save')},
        'session-save-as-btn': {click: () => clicks.push('save-as')},
        'app-logo': {click: () => clicks.push('about')}};
    const picker = {click: () => clicks.push('picker')};
    const window = {
        dash_clientside: {
            no_update: NO,
            set_props: (id, value) => props.push([id, value]),
            callback_context: {get triggered() { return triggered; }},
        },
        addEventListener: (name, fn) => { listeners.window[name] = fn; },
        setTimeout: (fn, ms) => { const id = nextTimer++; timers.push({id, fn, ms, cancelled: false}); return id; },
        clearTimeout: id => { const t = timers.find(x => x.id === id); if (t) t.cancelled = true; },
    };
    const document = {
        title: '',
        addEventListener: (name, fn) => { listeners.document[name] = fn; },
        getElementById: id => elements[id] || null,
        querySelector: sel => sel.includes('upload-button') ? picker : null,
    };
    const FakeDate = {now: () => clock};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../src/assets/js/session-io.js'), 'utf8'),
        {window, document, Date: FakeDate});
    const io = window.dash_clientside.sessionIO;
    return {
        io, window, document, listeners, props, timers, clicks, NO,
        advance: ms => { clock += ms; },
        trigger: ids => { triggered = ids.map(id => ({prop_id: id + '.data'})); },
        pending: () => timers.filter(t => !t.cancelled),
        run: t => { t.cancelled = true; t.fn(); },
    };
}

const files = [{id: 'f1'}];
function track(env, ids, {loaded = files, settings = {}, dirty = false} = {}) {
    env.trigger(ids);
    return env.io.trackChange(loaded, 0, settings, {}, [], 0, [], 'f1', 't1', dirty);
}

test('Cmd/Ctrl+S is captured and presses Save; Cmd/Ctrl+O opens the picker', () => {
    const env = load();
    for (const mod of [{metaKey: true}, {ctrlKey: true}]) {
        let prevented = false;
        env.listeners.window.keydown({key: 's', ...mod, preventDefault: () => { prevented = true; }});
        assert.equal(prevented, true);
        prevented = false;
        env.listeners.window.keydown({key: 'O', ...mod, preventDefault: () => { prevented = true; }});
        assert.equal(prevented, true);
    }
    assert.deepEqual(env.clicks, ['save', 'picker', 'save', 'picker']);
});

test('shortcuts ignore plain keys, other modifiers, and do not repeat while held', () => {
    const env = load();
    let prevented = 0;
    const press = extra => env.listeners.window.keydown({key: 's', preventDefault: () => { prevented++; }, ...extra});
    press({});
    press({key: 'o', metaKey: true, shiftKey: true});
    press({metaKey: true, altKey: true});
    env.listeners.window.keydown({key: 'x', metaKey: true, preventDefault: () => { prevented++; }});
    assert.equal(prevented, 0);
    press({metaKey: true, repeat: true});       // browser Save is still suppressed, but nothing is clicked twice
    assert.equal(prevented, 1);
    assert.deepEqual(env.clicks, []);
});

test('a content change marks the project dirty and autosave fires 20 s after the LAST change', () => {
    const env = load();
    assert.equal(track(env, ['loaded-files']), true);
    let timers = env.pending();
    assert.equal(timers.length, 1);
    assert.equal(timers[0].ms, 20000);
    env.advance(15000);
    assert.equal(track(env, ['peak-change-trigger'], {dirty: true}), env.NO);    // already dirty: no store write
    timers = env.pending();
    assert.equal(timers.length, 1, 'the earlier timer was replaced (debounce)');
    env.run(timers[0]);
    const fired = env.props.filter(p => p[0] === 'session-autosave-fire');
    assert.equal(fired.length, 1);
    assert.equal(fired[0][1].data, 1015000);
});

test('every change input of the spec counts; selection-only changes and an empty workspace do not', () => {
    for (const id of ['loaded-files', 'peak-change-trigger', 'file-order', 'plot-tabs', 'cal-revision', 'hidden-files']) {
        assert.equal(track(load(), [id]), true, id);
    }
    const env = load();
    assert.equal(track(env, ['active-file']), env.NO);
    assert.equal(track(env, ['active-plot-tab']), env.NO);
    assert.equal(env.pending().length, 0);
    assert.equal(track(env, ['loaded-files'], {loaded: [], dirty: true}), false);   // everything removed: nothing to save
    assert.equal(track(env, ['loaded-files'], {loaded: []}), env.NO);
});

test('plot-settings hydration echoes are not edits; a real edit of a known context is', () => {
    const env = load();
    const a = {_context_key: 'shared:raw:tab-a', line_width: 1.5, title: 'x'};
    assert.equal(track(env, ['current-plot-settings'], {settings: a}), env.NO);          // first sight = hydration
    const sameDifferentOrder = {title: 'x', line_width: 1.5, _context_key: 'shared:raw:tab-a'};
    assert.equal(track(env, ['current-plot-settings'], {settings: sameDifferentOrder}), env.NO);
    const other = {_context_key: 'shared:raw:tab-b', line_width: 3};
    assert.equal(track(env, ['current-plot-settings'], {settings: other}), env.NO);       // switched plot
    assert.equal(track(env, ['current-plot-settings'], {settings: {...a, line_width: 2}}), true);
    assert.equal(env.pending().length, 1);
});

test('a restore replays store writes: they are ignored until it has settled, then dirty is cleared', () => {
    const env = load();
    assert.equal(track(env, ['loaded-files']), true);                           // an early echo wins the race
    assert.equal(env.pending().length, 1);
    assert.equal(env.io.armRestore({active_plot_tab: 'tab-b'}), env.NO);
    assert.equal(env.pending().some(t => t.ms === 20000), false, 'pending autosave cancelled');
    env.advance(100);
    assert.equal(track(env, ['plot-tabs']), env.NO);                            // part of the replay
    assert.equal(env.pending().some(t => t.ms === 20000), false);
    // poll until quiet (500 ms without activity)
    let poll = env.pending()[0];
    env.advance(200); env.run(poll);                                            // still within the settle window
    assert.equal(env.props.some(p => p[0] === 'session-late-go'), false);
    env.advance(600);
    env.run(env.pending()[0]);
    assert.equal(env.props.filter(p => p[0] === 'session-late-go').length, 1);
    // finish: the saved tab is applied, the cache is merged with the browser's winning, dirty is cleared later
    const result = env.io.finishRestore(1, {active_plot_tab: 'tab-b', plot_settings_cache: {old: 1, shared: 'saved'}},
        'tab-a', [{id: 'tab-a'}, {id: 'tab-b'}], 'shared:raw:tab-a', {shared: 'browser'});
    assert.equal(result, env.NO);
    const set = Object.fromEntries(env.props.map(p => [p[0], p[1]]));
    assert.deepEqual(plain(set['plot-settings-cache'].data), {old: 1, shared: 'browser'});
    assert.equal(set['active-plot-tab'].data, 'tab-b');
    assert.equal(set['plot-settings-miss'], undefined, 'a tab change re-hydrates by itself');
    env.advance(50);
    assert.equal(track(env, ['hidden-files']), env.NO);                         // still in the quiet window
    const clear = env.pending().find(t => t.ms > 2000);
    env.run(clear);
    assert.deepEqual(plain(env.props.filter(p => p[0] === 'session-dirty').pop()), ['session-dirty', {data: false}]);
    env.advance(5000);
    assert.equal(track(env, ['loaded-files']), true, 'real edits after the quiet window count again');
});

test('restoring onto the plot that is already shown asks the server to re-read its settings', () => {
    const env = load();
    env.io.finishRestore(1, {active_plot_tab: 'tab-a'}, 'tab-a', [{id: 'tab-a'}], 'shared:raw:tab-a', {});
    assert.deepEqual(plain(env.props.find(p => p[0] === 'plot-settings-miss')), ['plot-settings-miss', {data: 'shared:raw:tab-a'}]);
    assert.equal(env.props.some(p => p[0] === 'active-plot-tab'), false);
});

test('status text: unsaved, autosaved only if it covers the last change, saved, opened, failed', () => {
    const env = load();
    const s = env.io.statusText;
    assert.equal(s(false, null), '');
    assert.equal(s(false, {kind: 'saved', at: '12:03'}), 'Saved 12:03');
    assert.equal(s(false, {kind: 'opened', at: '09:00'}), 'Opened 09:00');
    track(env, ['loaded-files']);                                              // lastChange = 1000000
    assert.equal(s(true, {kind: 'saved', at: '12:03'}), 'Unsaved changes');
    assert.equal(s(true, {kind: 'autosaved', at: '12:04', fired: 1000000}), 'Autosaved 12:04');
    env.advance(10);
    track(env, ['loaded-files'], {dirty: true});
    assert.equal(s(true, {kind: 'autosaved', at: '12:04', fired: 1000000}), 'Unsaved changes');
    assert.equal(s(true, {kind: 'failed', message: 'Autosave failed'}), 'Autosave failed');
});

test('closing the tab is only blocked while there are unsaved changes', () => {
    const env = load();
    env.io.statusText(false, null);
    const quiet = {preventDefault() { throw new Error('should not prevent'); }};
    assert.equal(env.listeners.window.beforeunload(quiet), undefined);
    env.io.statusText(true, null);
    let prevented = false;
    const event = {preventDefault: () => { prevented = true; }};
    env.listeners.window.beforeunload(event);
    assert.equal(prevented, true);
    assert.equal(event.returnValue, '');
});

test('a dropped or picked .gecko file is recognised by extension and announced at once', () => {
    const env = load();
    const {isSessionFile, sessionFileIn} = env.io;
    assert.ok(isSessionFile('Run 1.gecko') && isSessionFile('RUN.GECKO') && isSessionFile(' a.gecko '));
    assert.ok(!isSessionFile('data.csv') && !isSessionFile('gecko') && !isSessionFile('a.gecko.csv') && !isSessionFile(null));
    assert.equal(sessionFileIn([{name: 'a.csv'}, {name: 'p.gecko'}]).name, 'p.gecko');
    assert.equal(sessionFileIn([{name: 'a.csv'}]), null);
    env.listeners.window.drop({dataTransfer: {files: [{name: 'a.csv'}]}});
    assert.equal(env.props.length, 0);
    env.listeners.window.drop({dataTransfer: {files: [{name: 'a.csv'}, {name: 'p.gecko'}]}});
    assert.deepEqual(plain(env.props), [['session-status', {children: 'Opening p.gecko…'}]]);
    env.props.length = 0;
    env.listeners.document.change({target: {type: 'file', files: [{name: 'q.gecko'}]}});
    env.listeners.document.change({target: {type: 'text', files: [{name: 'z.gecko'}]}});
    assert.deepEqual(plain(env.props), [['session-status', {children: 'Opening q.gecko…'}]]);
});

test('project name label falls back to Untitled project and updates the window title', () => {
    const env = load();
    assert.equal(env.io.nameLabel(''), 'Untitled project');
    assert.equal(env.document.title, 'GeckoPlotter');
    assert.equal(env.io.nameLabel('  Ala 5 mM '), 'Ala 5 mM');
    assert.equal(env.document.title, 'Ala 5 mM - GeckoPlotter');
});

// ---- unsaved-changes guard ---------------------------------------------------------------
function makeDirty(env) {
    track(env, ['loaded-files']);                // dirty flag set by a content change
    env.io.statusText(true, null);
    assert.equal(env.io.state.dirty, true);
    env.props.length = 0;
}
function fakeEvent(extra) {
    const e = {prevented: 0, stopped: 0, preventDefault() { e.prevented++; }, stopPropagation() { e.stopped++; }, ...extra};
    return e;
}
function fakeReader(env) {
    env.window.FileReader = function () {
        this.readAsDataURL = () => { this.result = 'data:application/zip;base64,QUJD'; this.onload(); };
    };
}
const hidden = env => env.props.filter(p => p[0] === 'session-confirm').map(p => p[1].hidden);

test('a clean or empty workspace opens without asking', () => {
    const env = load();
    const e = fakeEvent({dataTransfer: {files: [{name: 'p.gecko'}]}});
    env.listeners.window.drop(e);
    assert.equal(e.prevented + e.stopped, 0);                    // the dropzone gets the file untouched
    assert.deepEqual(plain(env.props), [['session-status', {children: 'Opening p.gecko…'}]]);
    assert.equal(env.io.guardOpen(() => { throw new Error('must not run here'); }), false);
});

test('.zip (FAIR package) counts as a project file by name', () => {
    const env = load();
    assert.ok(env.io.isSessionFile('Study.zip') && env.io.isSessionFile('A.ZIP'));
    assert.ok(!env.io.isSessionFile('a.zip.csv'));
});

test('dropping a project over unsaved changes asks first and swallows the drop', () => {
    const env = load();
    makeDirty(env);
    const e = fakeEvent({dataTransfer: {files: [{name: 'old.gecko'}]}});
    env.listeners.window.drop(e);
    assert.ok(e.prevented >= 1 && e.stopped >= 1);
    assert.deepEqual(hidden(env), [false]);
    assert.ok(env.props.some(p => p[0] === 'session-confirm-text' && /Unsaved changes will be lost/.test(p[1].children)));
    assert.ok(!env.props.some(p => p[0] === 'session-open-upload'));      // nothing opened yet
});

test('Open anyway feeds the file to the Open flow; Cancel drops it', () => {
    const env = load();
    fakeReader(env);
    makeDirty(env);
    env.listeners.window.drop(fakeEvent({dataTransfer: {files: [{name: 'old.gecko'}]}}));
    env.io.confirmAction('discard');
    assert.deepEqual(plain(env.props.filter(p => p[0] === 'session-open-upload')),
        [['session-open-upload', {contents: 'data:application/zip;base64,QUJD', filename: 'old.gecko'}]]);
    assert.equal(hidden(env).pop(), true);

    env.props.length = 0;
    env.listeners.window.drop(fakeEvent({dataTransfer: {files: [{name: 'x.zip'}]}}));
    env.io.confirmAction('cancel');
    assert.ok(!env.props.some(p => p[0] === 'session-open-upload'));
    assert.equal(hidden(env).pop(), true);
    env.io.confirmAction('discard');                                       // nothing pending: harmless
    assert.ok(!env.props.some(p => p[0] === 'session-open-upload'));
});

test('picker: a chosen project is held back and the input reset; other files are untouched', () => {
    const env = load();
    makeDirty(env);
    const input = {type: 'file', value: 'C:\\fakepath\\p.gecko', files: [{name: 'p.gecko'}]};
    const e = fakeEvent({target: input});
    env.listeners.document.change(e);
    assert.ok(e.stopped >= 1);
    assert.equal(input.value, '');
    assert.deepEqual(hidden(env), [false]);
    env.io.confirmAction('cancel');
    const csv = fakeEvent({target: {type: 'file', files: [{name: 'a.csv'}]}});
    env.listeners.document.change(csv);
    assert.equal(csv.stopped, 0);
});

test('Save first runs the save flow, then opens once the saved stamp arrives', () => {
    const env = load();
    fakeReader(env);
    makeDirty(env);
    env.io.statusText(true, {kind: 'autosaved', ts: 5, at: '10:00', fired: 1});   // an older stamp is already showing
    env.listeners.window.drop(fakeEvent({dataTransfer: {files: [{name: 'old.gecko'}]}}));
    env.io.confirmAction('save');
    assert.deepEqual(env.clicks, ['save']);
    env.io.statusText(true, {kind: 'autosaved', ts: 5, at: '10:00', fired: 1});   // same stamp: keep waiting
    assert.ok(!env.props.some(p => p[0] === 'session-open-upload'));
    env.io.statusText(false, {kind: 'saved', ts: 9, at: '10:01'});                 // the save finished
    assert.equal(env.props.filter(p => p[0] === 'session-open-upload').length, 1);
    assert.equal(hidden(env).pop(), true);
});

test('a failed Save keeps the bar so the user can still choose', () => {
    const env = load();
    fakeReader(env);
    makeDirty(env);
    env.listeners.window.drop(fakeEvent({dataTransfer: {files: [{name: 'old.gecko'}]}}));
    env.io.confirmAction('save');
    env.io.statusText(true, {kind: 'failed', ts: 11, message: 'Save failed'});
    assert.ok(!env.props.some(p => p[0] === 'session-open-upload'));
    assert.ok(env.props.some(p => p[0] === 'session-confirm-text' && /Could not save/.test(p[1].children)));
    env.io.confirmAction('discard');
    assert.equal(env.props.filter(p => p[0] === 'session-open-upload').length, 1);
});

test('recent menu and banner Restore are guarded too; Escape cancels', () => {
    const env = load();
    makeDirty(env);
    const recentEl = {getAttribute: n => n === 'data-session-recent' ? '/tmp/a.gecko' : null};
    const target = {closest: sel => sel.includes('data-session-recent') ? recentEl : null};
    env.io.onClick(fakeEvent({target}));
    assert.ok(!env.props.some(p => p[0] === 'session-recent-pick'));
    env.io.confirmAction('discard');
    assert.deepEqual(plain(env.props.filter(p => p[0] === 'session-recent-pick')).map(p => p[1].data.path), ['/tmp/a.gecko']);

    env.props.length = 0;
    let restored = 0;
    const restoreEl = {click: () => { restored++; env.io.onClick(fakeEvent({target: restoreTarget})); }};
    const restoreTarget = {closest: sel => sel.includes('session-banner-restore') ? restoreEl : null};
    const e = fakeEvent({target: restoreTarget});
    env.io.onClick(e);
    assert.ok(e.stopped >= 1 && restored === 0);
    env.listeners.window.keydown({key: 'Escape'});
    assert.equal(hidden(env).pop(), true);
    assert.equal(env.io.state.pending, null);

    env.io.onClick(fakeEvent({target: restoreTarget}));
    env.io.confirmAction('discard');
    assert.equal(restored, 1);                       // re-clicked once, and let through the guard this time
});

test('data-confirm buttons are routed by the click handler', () => {
    const env = load();
    makeDirty(env);
    env.listeners.window.drop(fakeEvent({dataTransfer: {files: [{name: 'p.gecko'}]}}));
    const btn = {getAttribute: () => 'cancel'};
    env.io.onClick(fakeEvent({target: {closest: sel => sel.includes('data-confirm') ? btn : null}}));
    assert.equal(env.io.state.pending, null);
});


test('Shift+Cmd/Ctrl+S presses Save as', () => {
    const env = load();
    for (const mod of [{metaKey: true}, {ctrlKey: true}]) {
        const e = fakeEvent({key: 'S', shiftKey: true, ...mod});
        env.io.onKeyDown(e);
        assert.equal(e.prevented, 1);
    }
    assert.deepEqual(env.clicks, ['save-as', 'save-as']);
});

function menuAction(env, action) {
    const item = {getAttribute: name => name === 'data-session-action' ? action : null};
    env.io.onClick(fakeEvent({target: {closest: sel => sel.includes('data-session-action') ? item : null}}));
}

test('File Open uses the Files upload picker and About clicks the logo', () => {
    const env = load();
    menuAction(env, 'open-file');
    menuAction(env, 'about');
    assert.deepEqual(env.clicks, ['picker', 'about']);
});

test('New project guards dirty work: Cancel, discard, and Save first', () => {
    for (const action of ['cancel', 'discard', 'save']) {
        const env = load();
        makeDirty(env);
        menuAction(env, 'new-project');
        assert.deepEqual(hidden(env), [false]);
        assert.ok(!env.props.some(p => p[0] === 'session-new-request'));
        env.io.confirmAction(action);
        if (action === 'save') {
            assert.deepEqual(env.clicks, ['save']);
            assert.ok(!env.props.some(p => p[0] === 'session-new-request'));
            env.io.statusText(false, {kind: 'saved', ts: 42});
        }
        assert.equal(env.props.filter(p => p[0] === 'session-new-request').length, action === 'cancel' ? 0 : 1);
    }
});

test('New project in a clean workspace runs immediately and cancels stale restore timers', () => {
    const env = load();
    env.io.armRestore({active_plot_tab: 'old'});
    menuAction(env, 'new-project');
    assert.equal(env.props.filter(p => p[0] === 'session-new-request').length, 1);
    assert.equal(env.pending().length, 0);
    assert.equal(env.io.state.dirty, false);
});

test('data added immediately after New project is dirty, even following a restore', () => {
    const env = load();
    env.io.armRestore({active_plot_tab: 'old'});
    menuAction(env, 'new-project');
    assert.equal(track(env, ['loaded-files']), true);
});

test('New project cancels the final restore cleanup so it cannot clear subsequent edits', () => {
    const env = load();
    env.io.finishRestore(1, {active_plot_tab: 'old'}, 'old', [], null, {});
    menuAction(env, 'new-project');
    assert.equal(env.pending().length, 0);
});
