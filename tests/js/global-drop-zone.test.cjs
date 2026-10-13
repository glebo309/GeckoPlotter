const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
    const listeners = {};
    const body = {children: [], appendChild(node) { node.parentNode = body; body.children.push(node); },
        removeChild(node) { body.children = body.children.filter(n => n !== node); node.parentNode = null; }};
    const input = {files: null, events: [], dispatchEvent(event) { this.events.push(event.type); }};
    const document = {body, createElement: () => ({className: '', setAttribute() {}, innerHTML: '', parentNode: null}),
        querySelector: selector => (selector.includes('#upload-button') ? input : null)};
    class DataTransfer {constructor() { this.list = []; this.items = {add: f => this.list.push(f)}; }
        get files() { return this.list; }}
    const window = {innerWidth: 1000, innerHeight: 800, addEventListener(name, fn) { listeners[name] = fn; },
        setTimeout: (fn) => { fn(); return 1; }, clearTimeout() {}};
    const context = {window, document, DataTransfer, Event: class {constructor(type) { this.type = type; }},
        Promise, Array, console};
    vm.runInNewContext(fs.readFileSync('src/assets/js/global-drop-zone.js', 'utf8'), context);
    return {listeners, input, body};
}

const dragEvent = (over = {}, target = {closest: () => null}) => ({
    target, types: ['Files'], defaultPrevented: false, prevented: false, stopped: false,
    preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; },
    dataTransfer: {types: ['Files'], files: [{name: 'a.lcd'}, {name: 'b.txt'}], items: [], dropEffect: ''},
    clientX: 100, clientY: 100, ...over});

test('dragging files over any part of the window allows the drop and shows the hint', () => {
    const {listeners, body} = setup();
    const event = dragEvent();
    listeners.dragover(event);
    assert.equal(event.prevented, true);
    assert.equal(event.dataTransfer.dropEffect, 'copy');
    assert.equal(body.children.length, 1);
});

test('internal drags (no files) and the zones that take files themselves are left alone', () => {
    const {listeners, body} = setup();
    const internal = dragEvent({dataTransfer: {types: ['text/plain']}});
    listeners.dragover(internal);
    assert.equal(internal.prevented, false);
    const own = dragEvent({}, {closest: selector => (selector.includes('#drop-zone') ? {} : null)});
    listeners.dragover(own);
    listeners.drop(own);
    assert.equal(own.prevented, false);
    assert.equal(body.children.length, 0);
});

test('a drop on the plot hands the files to the main upload input', async () => {
    const {listeners, input} = setup();
    const event = dragEvent();
    listeners.drop(event);
    assert.equal(event.prevented, true);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(input.files.map(f => f.name), ['a.lcd', 'b.txt']);
    assert.deepEqual(input.events, ['change']);
});

test('a drop another handler already took is not imported twice', async () => {
    const {listeners, input} = setup();
    listeners.drop(dragEvent({defaultPrevented: true}));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(input.files, null);
});
