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
    const elements = {'session-save-btn': {click: () => clicks.push('save')}};
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
        querySelector: sel => sel.includes('session-open-upload') ? picker : null,
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
    press({metaKey: true, shiftKey: true});
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
