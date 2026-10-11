const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    let renders = 0;
    let resizes = 0;
    let resizeObserver;
    const props = [];
    const elements = new Map();
    function element() {
        return {style: {}, dataset: {}, children: [], handlers: {},
            appendChild(child) { this.children.push(child); },
            remove() { this.removed = true; },
            on(name, fn) { this.handlers[name] = fn; },
            getBoundingClientRect() { return {width: 900, height: 500}; }};
    }
    elements.set('plot-workspace', element());
    const window = {dash_clientside: {no_update: {}, set_props(id, value) {props.push([id, value]);}},
        Plotly: {async react(gd, data, layout) {renders++; gd.data=data; gd.layout=layout;},
            purge() {}, Plots: {resize() {resizes++;}}}, addEventListener() {}};
    const document = {getElementById: id => elements.get(id), createElement: element,
        dispatchEvent() {}, addEventListener() {}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../src/assets/js/plot-workspace.js'), 'utf8'),
        {window, document, CustomEvent: function() {}, ResizeObserver: class {
            constructor(callback) {resizeObserver = callback;} observe() {}},
            requestAnimationFrame: fn => fn(), console, setTimeout});
    return {window, props, host: elements.get('plot-workspace'), renders: () => renders,
        resizes: () => resizes, panelResize: () => resizeObserver()};
}

const figure = id => ({data: [{x:[0,1], y:[1,2]}], layout: {meta: {gecko_tab_id: id}}});
const tabs = [{id:'lcms',type:'raw'}, {id:'spectra',type:'raw'}];

test('resizing the plot panel resizes the retained graph without rebuilding it', async () => {
    const s = setup();
    await s.window.dash_clientside.plotWorkspace.update(figure('lcms'), 'lcms', tabs);
    const before = s.resizes();
    s.panelResize();
    assert.ok(s.resizes() > before);
    assert.equal(s.renders(), 1);
});

test('switching tabs preserves both plot instances and does not redraw cached plots', async () => {
    const s = setup();
    const update = s.window.dash_clientside.plotWorkspace.update;
    await update(figure('lcms'), 'lcms', tabs);
    const first = s.window.geckoActivePlot();
    first.layout.xaxis = {range:[.2,.8]};
    await update(figure('spectra'), 'spectra', tabs);
    const second = s.window.geckoActivePlot();
    await update(figure('spectra'), 'lcms', tabs);
    assert.equal(s.window.geckoActivePlot(), first);
    assert.equal(first.style.display, 'block');
    assert.equal(second.style.display, 'none');
    assert.deepEqual(first.layout.xaxis.range, [.2,.8]);
    assert.equal(s.renders(), 2);
    await update(figure('lcms'), 'lcms', tabs);
    assert.equal(s.renders(), 2);
});

test('late responses update their own tab and interaction events reach existing callbacks', async () => {
    const s = setup();
    const update = s.window.dash_clientside.plotWorkspace.update;
    await update(figure('lcms'), 'lcms', tabs);
    await update(figure('spectra'), 'spectra', tabs);
    const active = s.window.geckoActivePlot();
    await update({...figure('lcms'), data:[{x:[0], y:[5]}]}, 'spectra', tabs);
    assert.equal(s.window.geckoActivePlot(), active);
    active.handlers.plotly_click({points:[{curveNumber:0,pointNumber:1,x:1,y:2,data:{large:true}}]});
    const click = s.props.findLast(p => p[1].clickData)[1].clickData;
    assert.equal(click.points[0].curveNumber, 0);
    assert.equal(click.points[0].data, undefined);
    await update(figure('spectra'), 'spectra', [tabs[1]]);
    assert.equal(s.host.children[0].removed, true);
});

test('hiding the raw workspace for publication never resizes a hidden plot', async () => {
    const s = setup();
    await s.window.dash_clientside.plotWorkspace.update(figure('lcms'), 'lcms', tabs);
    s.host.style.display = 'none';
    const before=s.resizes();
    s.panelResize();
    assert.equal(s.resizes(),before);
});

test('partial manual bounds survive the hidden Dash graph filling the automatic endpoint', async () => {
 const s=setup(), f=figure('lcms');
 f.layout.xaxis={range:[6,10],autorange:'max'};
 await s.window.dash_clientside.plotWorkspace.update(f,'lcms',tabs);
 assert.deepEqual(Array.from(s.window.geckoActivePlot().layout.xaxis.range),[6,null]);
 assert.deepEqual(f.layout.xaxis.range,[6,10]);
});
