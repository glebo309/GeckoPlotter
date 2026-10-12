const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('the MS menu closes immediately on outside click and Escape', () => {
    const listeners = {}, props = [];
    const dropdown = {offsetParent: {}, hidden: false, contains: target => target === 'inside'};
    const document = {body: {}, addEventListener(name, fn) {listeners[name] = fn;},
        getElementById(id) {return id === 'ms-plot-context-menu' ? dropdown :
            {querySelector() {return null;}};}};
    const window = {dash_clientside: {set_props(id,value) {props.push([id,value]);}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../src/assets/js/ms-plot-context-menu.js'), 'utf8'),
        {document,window,Date});
    listeners.mousedown({target:'inside'});
    assert.equal(props.length, 0);
    listeners.mousedown({target:'outside'});
    assert.ok(props.some(p => p[0] === 'ms-plot-context-menu' && p[1].hidden === true));
    props.length = 0;
    listeners.keydown({key:'Escape'});
    assert.ok(props.some(p => p[0] === 'ms-plot-context-menu' && p[1].hidden === true));
});
