const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function keyboard() {
    const events = {}, props = [], cancelled = [];
    const window = {dash_clientside: {set_props: (id, value) => props.push([id, value])},
        GeckoPlotterManualIntegration: {cancelInteraction: id => cancelled.push(id)}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/keyboard-delete.js', 'utf8'), {
        window, document: {getElementById: () => null, addEventListener: (name, fn) => events[name] = fn}, Date
    });
    return {events, props, cancelled};
}

test('Escape cancels integration immediately even with numeric focus and leaves the field event intact', () => {
    const {events, props, cancelled} = keyboard();
    let prevented = false;
    events.keydown({key: 'Escape', target: {tagName: 'INPUT'}, preventDefault: () => prevented = true});
    assert.deepEqual(cancelled, ['main-plot']);
    assert.ok(props.some(([id, value]) => id === 'baseline-mode' && value.data === 'navigate'));
    assert.ok(props.some(([id, value]) => id === 'selected-peak-idx' && value.data === null));
    assert.ok(props.some(([id, value]) => id === 'baseline-mode-indicator' && value.children === 'Draw: off'));
    assert.equal(prevented, false);
});

test('focused menus and tab buttons keep their arrow keys instead of cycling peaks', () => {
    const {events, props} = keyboard();
    let prevented = false;
    events.keydown({key: 'ArrowRight', target: {tagName: 'BUTTON', closest: selector => selector.includes('button') ? {} : null},
        preventDefault: () => prevented = true});
    assert.equal(props.length, 0);
    assert.equal(prevented, false);
});

test('native selects and contenteditable fields retain typing shortcuts', () => {
    const {events, props} = keyboard();
    for (const target of [{tagName: 'SELECT'}, {isContentEditable: true}]) {
        events.keydown({key: 's', target});
    }
    assert.equal(props.length, 0);
});
