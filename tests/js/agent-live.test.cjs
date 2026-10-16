const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
    function node() {
        const classes = new Set();
        return {children:[], attrs:{}, hidden:false, textContent:'', listeners:{},
            classList:{toggle(name,on) {if (on) classes.add(name); else classes.delete(name);}, contains:name=>classes.has(name)},
            appendChild(child) {this.children.push(child); this.firstChild = this.children[0];},
            setAttribute(name,value) {this.attrs[name] = String(value);},
            querySelector() {return this.group || (this.group = node());},
            addEventListener(name,fn) {this.listeners[name] = fn;}};
    }
    const el = node();
    el.hidden = true;
    let state = {version:0, connected:[], busy:false, stopped:false, here:true};
    let frame, poll, now = 0, mounted = true;
    const props = [];
    const document = {hidden:false, getElementById:()=>mounted ? el : null, createElement:node,
        createElementNS:node, addEventListener(){}};
    const window = {setInterval:fn=>poll=fn, requestAnimationFrame:fn=>frame=fn, addEventListener(){},
        dash_clientside:{set_props:(id,data)=>props.push([id,data])}};
    function fetch(url) {
        if (url.endsWith('/stop')) state.stopped = !state.stopped;
        return Promise.resolve({ok:true, json:()=>Promise.resolve({...state})});
    }
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/agent-live.js'),'utf8'),
        {window,document,fetch,Date,Math:Object.assign(Object.create(Math), {random:()=>0.42})});
    return {el, props, get who() {return el.children[1];}, get doing() {return el.children[2];},
        get stop() {return el.children[3];}, get circles() {return el.children[0].group.children;},
        tick(ms) {for (let elapsed=0; elapsed<ms; elapsed+=40) {now+=40; frame(now);}},
        async show(next) {state = {...state,...next}; poll(); await new Promise(setImmediate);},
        async settle() {await new Promise(setImmediate);}};
}

test('disconnected is visible immediately, with a static dot and connection hint', async () => {
    const h = harness();
    assert.equal(h.el.hidden,false);
    await h.settle();
    h.tick(1200);
    assert.equal(h.el.title,'No agent connected: connect one in About (click the logo)');
    assert.ok(h.who.hidden && h.doing.hidden && h.stop.hidden);
    const before = h.circles.map(c=>({...c.attrs}));
    h.tick(1200);
    assert.deepEqual(h.circles.map(c=>c.attrs),before);
    assert.equal(h.circles.filter(c=>Number(c.attrs.r)>0).length,1);
});

test('idle lists connected clients and Stop works before the first tool call', async () => {
    const h = harness();
    await h.show({connected:['Claude Code','Codex'], here:false});
    assert.equal(h.who.textContent,'Claude Code, Codex');
    assert.equal(h.doing.textContent,'connected');
    assert.equal(h.stop.textContent,'Stop');
    assert.equal(h.stop.hidden,false);
    assert.ok(h.el.classList.contains('connected'));
    h.stop.listeners.click();
    await h.settle();
    assert.equal(h.who.textContent,'Claude Code, Codex:');
    assert.equal(h.doing.textContent,'stopped');
    assert.equal(h.stop.textContent,'Let it work');
});

test('working drops split and merge within a second, and Stop wins over busy', async () => {
    const h = harness();
    await h.show({connected:['Claude Code'], agent:'Claude Code'});
    h.tick(120);
    await h.show({busy:true, doing:'reading the samples'});
    h.tick(400);
    assert.ok(h.circles.some(c=>Number(c.attrs.cx)!==22));
    assert.ok(h.el.classList.contains('busy'));
    assert.equal(h.doing.textContent,'reading the samples');
    h.tick(600);
    await h.show({busy:false, version:1});
    h.tick(400);
    assert.ok(h.circles.some(c=>Number(c.attrs.cx)!==22));
    h.tick(600);
    assert.ok(h.circles.every(c=>Number(c.attrs.cx)===22 && Number(c.attrs.cy)===8));
    assert.equal(h.circles.filter(c=>Number(c.attrs.r)>0).length,1);
    assert.equal(h.props.length,1);
    await h.show({busy:true, stopped:true});
    h.tick(1000);
    assert.ok(!h.el.classList.contains('busy') && h.el.classList.contains('stopped'));
    assert.equal(h.who.textContent,'Claude Code:');
    assert.equal(h.doing.textContent,'stopped');
    assert.equal(h.stop.textContent,'Let it work');
    assert.equal(h.circles.filter(c=>Number(c.attrs.r)>0).length,1);
    await h.show({busy:false, stopped:false, connected:[]});
    assert.ok(h.who.hidden && h.doing.hidden && h.stop.hidden);  // last caller is not a connection
});
