const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const eq = (actual, expected) => assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);

function load() {
    const window = {};
    const context = {window, JSON, Date, Math, Array, Object, document: {addEventListener() {}}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/file-sort.js', 'utf8'), context);
    return window._geckoFileDrag;
}
const drag = load();

const rect = (top, bottom, left = 0, right = 200) => ({left, top, right, bottom});
// Figure G1: header 0-20, rows a b c (20-110, 30px each). Figure G2: header 120-140, rows d e (140-200).
function layout(withZone = true) {
    const row = (id, top) => ({id, rect: rect(top, top + 30)});
    return {
        zone: withZone ? rect(220, 260) : null,
        groups: [
            {id: 'G1', header: rect(0, 20), container: rect(20, 110), rows: [row('a', 20), row('b', 50), row('c', 80)]},
            {id: 'G2', header: rect(120, 140), container: rect(140, 200), rows: [row('d', 140), row('e', 170)]},
        ],
    };
}
const groupOf = {a: 'G1', b: 'G1', c: 'G1', d: 'G2', e: 'G2'};
const dragOf = (...ids) => ({ids, groupOf});

test('dragging a row of the multi-selection drags the whole selection', () => {
    const items = ['a', 'b', 'c', 'd'].map(id => ({id, keys: [id]}));
    eq(drag.resolveDragIds('b', items, ['a', 'b', 'd']), ['a', 'b', 'd']);
});

test('dragging an unselected row, or a single-row selection, drags just that row', () => {
    const items = ['a', 'b', 'c'].map(id => ({id, keys: [id]}));
    eq(drag.resolveDragIds('c', items, ['a', 'b']), ['c']);
    eq(drag.resolveDragIds('a', items, ['a']), ['a']);
    eq(drag.resolveDragIds('a', items, []), ['a']);
});

test('a selected child inside a bundle row selects that row', () => {
    const items = [{id: 'bundle', keys: ['bundle', 'child1']}, {id: 'x', keys: ['x']}];
    eq(drag.resolveDragIds('x', items, ['child1', 'x']), ['bundle', 'x']);
});

test('pointer over another figure header or body targets that figure', () => {
    eq(drag.computeDropTarget({x: 50, y: 130}, layout(), dragOf('a')), {kind: 'group', group: 'G2'});
    eq(drag.computeDropTarget({x: 50, y: 160}, layout(), dragOf('a')), {kind: 'group', group: 'G2'});
});

test('own header is not a target; outside every region is no target', () => {
    assert.equal(drag.computeDropTarget({x: 50, y: 10}, layout(), dragOf('a')), null);
    assert.equal(drag.computeDropTarget({x: 50, y: 112}, layout(), dragOf('a')), null);
    assert.equal(drag.computeDropTarget({x: 500, y: 50}, layout(), dragOf('a')), null);
});

test('within the same figure the insertion gap follows the pointer', () => {
    // Drag a; pointer in the upper half of c => insert before c (index 1 among b,c)
    const t = drag.computeDropTarget({x: 50, y: 85}, layout(), dragOf('a'));
    assert.equal(t.kind, 'reorder');
    eq(t.order, ['b', 'a', 'c']);
    assert.equal(t.lineY, 80);
    assert.equal(t.changed, true);
    // lower half of c => end of list, line under the last remaining row
    const end = drag.computeDropTarget({x: 50, y: 105}, layout(), dragOf('a'));
    eq(end.order, ['b', 'c', 'a']);
    assert.equal(end.lineY, 110);
});

test('dropping back at the original position is flagged unchanged', () => {
    const t = drag.computeDropTarget({x: 50, y: 40}, layout(), dragOf('a'));
    assert.equal(t.kind, 'reorder');
    assert.equal(t.changed, false);
    eq(drag.buildEvents(t, dragOf('a'), 1), []);
});

test('multi-row reorder moves the block, keeping its internal order', () => {
    const t = drag.computeDropTarget({x: 50, y: 22}, layout(), dragOf('b', 'c'));
    eq(t.order, ['b', 'c', 'a']);
    assert.equal(t.lineY, 20);
    const events = drag.buildEvents(t, dragOf('b', 'c'), 7);
    eq(events, [{target: 'file-reorder-event', data: {group_id: 'G1', order: ['b', 'c', 'a'], ts: 7}}]);
});

test('a selection spanning figures never shows a reorder line, it moves into the figure', () => {
    eq(drag.computeDropTarget({x: 50, y: 40}, layout(), dragOf('a', 'd')), {kind: 'group', group: 'G1'});
});

test('New figure zone: hit test, and no-op when the only figure would be emptied', () => {
    eq(drag.computeDropTarget({x: 50, y: 230}, layout(), dragOf('a')), {kind: 'new'});
    assert.equal(drag.computeDropTarget({x: 50, y: 230}, layout(false), dragOf('a')), null);
    const single = {zone: rect(220, 260), groups: [layout().groups[0]]};
    assert.equal(drag.computeDropTarget({x: 50, y: 230}, single, dragOf('a', 'b', 'c')), null);
    eq(drag.computeDropTarget({x: 50, y: 230}, single, dragOf('a', 'b')), {kind: 'new'});
});

test('single-file group move keeps the legacy payload exactly', () => {
    const events = drag.buildEvents({kind: 'group', group: 'G2'}, dragOf('a'), 5);
    eq(events, [{target: 'group-move-event', data: {file_id: 'a', source_group: 'G1', target_group: 'G2', ts: 5}}]);
    const nw = drag.buildEvents({kind: 'new'}, dragOf('a'), 5);
    eq(nw, [{target: 'group-move-event', data: {file_id: 'a', source_group: 'G1', target_group: null, ts: 5}}]);
});

test('multi-file move adds file_ids, skipping files already in the target figure', () => {
    const events = drag.buildEvents({kind: 'group', group: 'G2'}, dragOf('a', 'b', 'd'), 9);
    eq(events, [{target: 'group-move-event',
        data: {file_id: 'a', source_group: 'G1', target_group: 'G2', ts: 9, file_ids: ['a', 'b']}}]);
    eq(drag.buildEvents({kind: 'group', group: 'G2'}, dragOf('d'), 9), []);
    eq(drag.buildEvents(null, dragOf('a'), 9), []);
});
