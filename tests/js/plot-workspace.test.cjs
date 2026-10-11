const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
    let renders = 0;
    let resizes = 0;
    let serializations = 0;
    let resizeObserver;
    const props = [];
    const elements = new Map();
    function element() {
        return {style: {}, dataset: {}, children: [], handlers: {},
            appendChild(child) { this.children.push(child); },
            remove() { this.removed = true; },
            on(name, fn) { this.handlers[name] = fn; },
            getBoundingClientRect() { return this.bounds || {width: 900, height: 500}; }};
    }
    elements.set('plot-workspace', element());
    const window = {dash_clientside: {no_update: {}, set_props(id, value) {props.push([id, value]);}},
        Plotly: {async react(gd, data, layout) {renders++; gd.data=data; gd.layout=layout;},
            purge() {}, Plots: {resize() {resizes++;}}}, addEventListener() {}};
    const document = {getElementById: id => elements.get(id), createElement: element,
        dispatchEvent() {}, addEventListener() {}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../src/assets/js/plot-workspace.js'), 'utf8'),
        {window, document, CustomEvent: function(type) {this.type=type;}, ResizeObserver: class {
            constructor(callback) {resizeObserver = callback;} observe() {}},
            requestAnimationFrame: fn => fn(), console, setTimeout, structuredClone,
            JSON: {parse: JSON.parse, stringify(value) {serializations++; return JSON.stringify(value);}}});
    return {window, document, props, host: elements.get('plot-workspace'), renders: () => renders,
        resizes: () => resizes, serializations: () => serializations, panelResize: () => resizeObserver()};
}

const figure = id => ({data: [{x:[0,1], y:[1,2]}], layout: {meta: {gecko_tab_id: id}}});
const tabs = [{id:'lcms',type:'raw'}, {id:'spectra',type:'raw'}];

test('resizing the plot panel resizes the retained graph without rebuilding it', async () => {
    const s = setup();
    await s.window.dash_clientside.plotWorkspace.update(figure('lcms'), 'lcms', tabs);
    const before = s.resizes();
    s.host.bounds = {width:900, height:600};
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

test('cached tab activation happens before awaiting an unrelated Plotly render', async () => {
 const s=setup(), update=s.window.dash_clientside.plotWorkspace.update;
 await update(figure('lcms'),'lcms',tabs); const first=s.window.geckoActivePlot();
 await update(figure('spectra'),'spectra',tabs); const second=s.window.geckoActivePlot();
 let finish;
 s.window.Plotly.react=()=>new Promise(resolve=>finish=resolve);
 const pending=update({...figure('spectra'),data:[{x:[0],y:[99]}]},'lcms',tabs);
 assert.equal(first.style.display,'block','selected cached graph appears before slow render resolves');
 assert.equal(second.style.display,'none');
 finish(); await pending;
});

test('tab click activates cached graph synchronously without figure serialization or visible rendering', async () => {
 const s=setup(), api=s.window.dash_clientside.plotWorkspace;
 await api.update(figure('lcms'),'lcms',tabs); const first=s.window.geckoActivePlot();
 await api.update(figure('spectra'),'spectra',tabs);
 first.layout.xaxis={range:[0.2,0.8]};
 const before=s.serializations();
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'{"type":"plot-tab-btn","index":"lcms"}.n_clicks'}]};
 assert.equal(api.switchTab([1,0],'spectra'),'lcms');
 assert.equal(s.window.geckoActivePlot(),first);
 assert.equal(first.style.display,'block');
 assert.equal(s.renders(),2);
 assert.equal(s.serializations(),before);
 assert.deepEqual(s.props.findLast(p=>p[0]==='main-plot' && p[1].figure)[1].figure.layout.xaxis.range,[0.2,0.8]);
 assert.ok(s.props.some(p=>p[0]==='rendered-plot-tabs' && p[1].data.includes('lcms')));
});

test('unchanged figure identity and unchanged container size skip expensive work', async () => {
 const s=setup(), f=figure('lcms'), update=s.window.dash_clientside.plotWorkspace.update;
 await update(f,'lcms',tabs);
 const before=s.serializations(), sizes=s.resizes();
 await update(f,'lcms',tabs);
 s.panelResize(); s.panelResize();
 assert.equal(s.serializations(),before);
 assert.equal(s.resizes(),sizes);
 assert.equal(s.renders(),1);
 // Explicit Dash figure events still inspect in-place patches.
 f.data[0].y=[2,3];
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'main-plot.figure'}]};
 await update(f,'lcms',tabs);
 assert.equal(s.renders(),2);
});

test('the cached figure mirrored to the hidden Dash interface is not serialized or redrawn again', async () => {
 const s=setup(), api=s.window.dash_clientside.plotWorkspace;
 await api.update(figure('lcms'),'lcms',tabs);
 await api.update(figure('spectra'),'spectra',tabs);
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'{"type":"plot-tab-btn","index":"lcms"}.n_clicks'}]};
 api.switchTab([1,0],'spectra');
 const mirrored=s.props.findLast(p=>p[0]==='main-plot' && p[1].figure)[1].figure;
 const before=s.serializations();
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'main-plot.figure'}]};
 await api.update(mirrored,'lcms',tabs);
 assert.equal(s.serializations(),before);
 assert.equal(s.renders(),2);
});

test('fast tab switching restores target panel layout before revealing the cached graph',async()=>{
 const s=setup(),api=s.window.dash_clientside.plotWorkspace;
 await api.update(figure('lcms'),'lcms',tabs);
 await api.update(figure('spectra'),'spectra',tabs);
 let calls=0;
 s.window.__geckoSyncPlotTabLayout=(id,descriptors)=>{
   calls++;assert.equal(id,'lcms');assert.equal(descriptors,tabs);
   assert.equal(s.window.geckoActivePlot().dataset.workspacePlot,'spectra','panels restore before active graph is resized');
 };
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'{"type":"plot-tab-btn","index":"lcms"}.n_clicks'}]};
 api.switchTab([1,0],'spectra');
 assert.equal(calls,1);
});


test('tab departure is announced before the old raw graph is hidden, including cold targets',async()=>{
 const s=setup(),api=s.window.dash_clientside.plotWorkspace;
 await api.update(figure('lcms'),'lcms',tabs);
 const events=[];
 s.document.dispatchEvent=event=>{events.push(event.type);if(event.type==='gecko:plot-leave') assert.equal(s.window.geckoActivePlot().dataset.workspacePlot,'lcms');};
 s.window.dash_clientside.callback_context={triggered:[{prop_id:'{"type":"plot-tab-btn","index":"spectra"}.n_clicks'}]};
 api.switchTab([0,1],'lcms');
 assert.equal(events[0],'gecko:plot-leave');
});
