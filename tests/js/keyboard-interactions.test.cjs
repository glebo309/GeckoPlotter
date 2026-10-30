const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function keyboard(options = {}) {
    const events = {}, props = [], cancelled = [];
    const window = {__geckoBaselineMode: options.mode, dash_clientside: {set_props: (id, value) => props.push([id, value])},
        GeckoPlotterManualIntegration: {cancelInteraction: id => cancelled.push(id)}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/keyboard-delete.js', 'utf8'), {
        window, document: {getElementById: id => (options.buttons || {})[id] || null, addEventListener: (name, fn) => events[name] = fn}, Date
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

test('Enter accepts and X cancels only the active deconvolution preview', () => {
    const clicked=[];
    const buttons={
        'deconv-accept-btn':{click:()=>clicked.push('accept')},
        'deconv-cancel-btn':{click:()=>clicked.push('cancel')}
    };
    const {events,props}=keyboard({mode:'deconvolve',buttons});
    const key=key=>({key,target:{tagName:'DIV'},preventDefault(){},stopPropagation(){}});
    events.keydown(key('Enter'));events.keydown(key('x'));events.keydown(key('X'));
    assert.deepEqual(clicked,['accept','cancel','cancel']);
    for (const extra of [{target:{tagName:'INPUT'}},{ctrlKey:true},{metaKey:true},{altKey:true},{repeat:true}]) {
        events.keydown({...key('Enter'),...extra});events.keydown({...key('x'),...extra});
    }
    buttons['deconv-accept-btn'].disabled=true;
    events.keydown(key('Enter'));
    assert.deepEqual(clicked,['accept','cancel','cancel']);
    assert.equal(props.length,0);
});

test('undo and redo work while a legend checkbox or slider has focus', () => {
    for (const type of ['checkbox', 'radio', 'range']) {
        const {events, props} = keyboard();
        const target = {tagName: 'INPUT', type};
        events.keydown({key: 'z', metaKey: true, target, preventDefault() {}});
        events.keydown({key: 'Z', metaKey: true, shiftKey: true, target, preventDefault() {}});
        assert.deepEqual(props.map(p => p[0]), ['undo-trigger', 'redo-trigger']);
    }
});

test('text inputs retain native text undo', () => {
    const {events, props} = keyboard();
    events.keydown({key: 'z', metaKey: true, target: {tagName: 'INPUT', type: 'text'}, preventDefault() {}});
    assert.equal(props.length, 0);
});
