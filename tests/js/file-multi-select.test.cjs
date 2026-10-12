const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Arrays built inside the vm context have another prototype; compare by value.
const eq = (actual, expected) => assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);

// A tree of rows a..e (c sits in a collapsed group, so it is not visible).
function setup(keys = ['a', 'b', 'c', 'd', 'e'], collapsed = ['c']) {
    const events = {}, published = [], applied = [];
    const rows = keys.map(key => {
        const classes = new Set();
        const row = {
            id: JSON.stringify({type: 'file-tree-item', index: key}),
            offsetParent: collapsed.includes(key) ? null : {},
            classes,
            classList: {add: c => classes.add(c), remove: c => classes.delete(c)},
            getAttribute: name => name === 'data-file-key' ? key : null,
        };
        row.closest = selector => selector === '.file-tree-item' ? row : null;
        return row;
    });
    const window = {dash_clientside: {set_props: (id, props) => published.push([id, props.data])}};
    const context = {window, Set, JSON, document: {
        body: {}, getElementById: () => null,
        querySelectorAll: selector => selector === '.file-tree-item' ? rows : [],
        addEventListener: (event, listener) => events[event] = listener,
    }, MutationObserver: class {observe() {}}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/file-tree-ui.js', 'utf8'), context);
    const realApply = window._geckoApplyActiveFile;
    window._geckoApplyActiveFile = id => { applied.push(id); realApply(id); };
    const clickTarget = (target, mods = {}) => events.click({target, ...mods, preventDefault() {}, stopPropagation() {}});
    const click = (key, mods = {}) => {
        const row = rows.find(r => r.getAttribute('data-file-key') === key);
        const log = {prevented: 0, stopped: 0};
        const target = {closest: sel => sel === '.file-tree-item' ? row : null};
        events.click({target, ...mods, preventDefault: () => log.prevented++, stopPropagation: () => log.stopped++});
        return log;
    };
    const marked = () => rows.filter(r => r.classes.has('multi-selected')).map(r => r.getAttribute('data-file-key'));
    return {window, rows, click, clickTarget, marked, published, applied};
}

const cmp = window => window._geckoComputeSelection;

test('cmd/ctrl-click toggles a file in and out of the selection', () => {
    const {window} = setup();
    const compute = cmp(window), order = ['a', 'b', 'd', 'e'];
    let s = compute({keys: ['a'], anchor: 'a'}, order, 'd', {toggle: true});
    eq(s.keys, ['a', 'd']);
    s = compute(s, order, 'b', {toggle: true});
    eq(s.keys, ['a', 'd', 'b']);
    s = compute(s, order, 'd', {toggle: true});
    eq(s.keys, ['a', 'b']);
});

test('shift-click selects the range from the anchor in visible row order', () => {
    const {window} = setup();
    const compute = cmp(window), order = ['a', 'b', 'd', 'e'];
    let s = compute({keys: ['b'], anchor: 'b'}, order, 'e', {range: true});
    eq(s.keys, ['b', 'd', 'e']);
    // Pivots around the anchor in either direction and replaces the previous range.
    s = compute(s, order, 'a', {range: true});
    eq(s.keys, ['a', 'b']);
    assert.equal(s.anchor, 'b');
    // Without an anchor the first selected file is used.
    s = compute({keys: ['d'], anchor: null}, order, 'a', {range: true});
    eq(s.keys, ['a', 'b', 'd']);
});

test('cmd+shift adds the range to the existing selection', () => {
    const compute = cmp(setup().window);
    const s = compute({keys: ['a', 'e'], anchor: 'a'}, ['a', 'b', 'd', 'e'], 'd', {range: true, toggle: true});
    eq([...s.keys].sort(), ['a', 'b', 'd', 'e']);
});

test('plain click resets the selection to the clicked file', () => {
    const compute = cmp(setup().window);
    const s = compute({keys: ['a', 'b', 'd'], anchor: 'a'}, ['a', 'b', 'd', 'e'], 'e', {});
    eq(s, {keys: ['e'], anchor: 'e'});
});

test('click handler: cmd-click marks rows, publishes the store and does not reach Dash', () => {
    const t = setup();
    t.window.__geckoActiveFile = 'a';
    let log = t.click('d', {metaKey: true});
    // The active file 'a' is the implicit first selection.
    eq(t.marked(), ['a', 'd']);
    eq(t.published.at(-1), ['file-multi-selection', ['a', 'd']]);
    assert.equal(log.stopped, 1);
    assert.equal(t.applied.length, 0, 'a modifier click must not change the active file');
    t.click('d', {ctrlKey: true});
    eq(t.marked(), ['a']);
});

test('click handler: shift-click skips rows hidden in collapsed groups', () => {
    const t = setup();
    t.click('a');
    t.click('e', {shiftKey: true});
    eq(t.marked(), ['a', 'b', 'd', 'e']);
    eq(t.published.at(-1)[1], ['a', 'b', 'd', 'e']);
});

test('click handler: plain click keeps today\'s behaviour and collapses the selection', () => {
    const t = setup();
    t.click('a');
    t.click('b', {metaKey: true});
    eq(t.marked(), ['a', 'b']);
    const log = t.click('d');
    assert.equal(log.stopped, 0, 'plain clicks still reach Dash');
    assert.equal(log.prevented, 0);
    eq(t.applied.at(-1), 'd');
    eq(t.marked(), ['d']);
    eq(t.published.at(-1), ['file-multi-selection', ['d']]);
});

test('eye and delete buttons never alter the selection', () => {
    const t = setup();
    t.click('a'); t.click('b', {metaKey: true});
    const before = t.published.length;
    // Clicking a button inside a selected row (even with Cmd held) is left to Dash.
    t.clickTarget({closest: sel => sel === '.file-tree-item' ? t.rows[0] : (/button/.test(sel) ? {} : null)}, {metaKey: true});
    assert.equal(t.published.length, before);
    eq(t.marked(), ['a', 'b']);
});

test('selection forgets rows that disappear after a tree re-render', () => {
    const t = setup();
    t.click('a'); t.click('b', {metaKey: true});
    t.rows.pop(); t.rows.splice(1, 1);  // b and e vanish
    t.window._geckoApplyMultiSelection();
    eq(t.window._geckoGetFileSelection(), ['a']);
    eq(t.published.at(-1), ['file-multi-selection', ['a']]);
});

test('a changed active file outside the selection ends the multi-selection', () => {
    const t = setup();
    t.click('a'); t.click('b', {metaKey: true});
    t.window._geckoApplyActiveFile('b');
    eq(t.window._geckoGetFileSelection(), ['a', 'b']);
    t.window._geckoApplyActiveFile('d');
    eq(t.window._geckoGetFileSelection(), []);
    eq(t.marked(), []);
});
