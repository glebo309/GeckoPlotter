const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');

function setup() {
  const handlers = {}, taken = [], sent = [], appended = [];
  const axis = (len, off, d2p, p2d) => ({_length: len, _offset: off, d2p, p2d});
  const gd = {
    _fullLayout: {xaxis: axis(200, 40, t => t * 50, v => v / 50), yaxis: axis(100, 10, w => 100 - (w - 190) / 5.1, v => 190 + (100 - v) * 5.1)},
    getBoundingClientRect: () => ({left: 100, top: 50}),
    closest: () => view, on() {}};
  const view = {getBoundingClientRect: () => ({left: 90, top: 40}), appendChild: n => appended.push(n)};
  const host = {contains: () => true, querySelector: () => gd};
  const make = () => ({style: {}, className: '', set innerHTML(v) { this.firstChild = {style: {}}; this.lastChild = {style: {}}; }, parentNode: view});
  const document = {addEventListener: (n, f) => handlers[n] = f, getElementById: () => host, createElement: () => { const n = make(); return n; }};
  const window = {addEventListener() {}, requestAnimationFrame: f => { f(); return 1; }, dash_clientside: {set_props: (id, p) => sent.push([id, p.data])}};
  vm.runInNewContext(fs.readFileSync('src/assets/js/pda-heatmap-cursor.js', 'utf8'),
    {document, window, MutationObserver: class { observe() {} }, Date});
  // createElement returns a fresh node each time; the overlay is appended to the view as `cross`.
  return {handlers, taken, sent, appended, window, view};
}
const ev = (extra, taken) => ({button: 0, detail: 1, clientX: 160, clientY: 100, target: {},
  preventDefault: () => taken.push(1), stopPropagation() {}, ...extra});

test('pointer inside the plot maps to time and wavelength, and clamps at the edges', () => {
  const {window} = setup();
  const x = {_length: 200, p2d: v => v / 200 * 3.5}, y = {_length: 100, p2d: v => 700 - v / 100 * 510};
  const p = window.GeckoPdaHeatmapCursor.dataPoint(x, y, 100, 50);
  assert.equal(p.time_min, 1.75); assert.equal(p.wavelength_nm, 445);
  const q = window.GeckoPdaHeatmapCursor.dataPoint(x, y, -40, 999);
  assert.equal(q.time_min, 0); assert.equal(q.wavelength_nm, 190);
});

test('shift-drag is left to Plotly box zoom, plain drag is taken for the cross', () => {
  const {handlers, taken} = setup();
  handlers.mousedown(ev({shiftKey: true}, taken));
  assert.equal(taken.length, 0);
  handlers.mousedown(ev({}, taken));
  assert.equal(taken.length > 0, true);
});

test('dragging moves the overlay with transforms and sends the selection once released', () => {
  const {handlers, taken, sent, appended} = setup();
  handlers.mousedown(ev({}, taken));
  handlers.mousemove(ev({clientX: 190}, taken));
  handlers.mouseup({});
  const cross = appended[0];
  assert.match(cross.firstChild.style.transform, /^translateX\(/);
  assert.match(cross.lastChild.style.transform, /^translateY\(/);
  const last = sent.at(-1);
  assert.equal(last[0], 'pda-heatmap-event');
  assert.equal(Math.round(last[1].time_min * 1000) / 1000, 1.0);   // (190 - 100 - 40) / 50
});

test('shift + double-click resets the heatmap zoom; a single shift click, a shift drag and a plain click do not', () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const handlers = {}, relayouts = [];
  const view = {getBoundingClientRect: () => ({left: 0, top: 0}), appendChild() {}};
  const gd = {_fullLayout: {xaxis: {_length: 200, _offset: 0, p2d: v => v, d2p: v => v}, yaxis: {_length: 100, _offset: 0, p2d: v => v, d2p: v => v}},
              getBoundingClientRect: () => ({left: 0, top: 0}), closest: () => view, on() {}, layout: {}};
  const host = {contains: () => true, querySelector: () => gd};
  vm.runInNewContext(fs.readFileSync('src/assets/js/pda-heatmap-cursor.js', 'utf8'), {
    document: {addEventListener: (n, f) => handlers[n] = f, getElementById: () => host, createElement: () => ({style: {}, set innerHTML(v) { this.firstChild = {style: {}}; this.lastChild = {style: {}}; }, parentNode: view})},
    window: {addEventListener() {}, requestAnimationFrame: f => { f(); return 1; }, Plotly: {relayout: (g, u) => relayouts.push(u)},
             dash_clientside: {set_props() {}}}, MutationObserver: class { observe() {} }, Date});
  const ev = (x, extra) => ({button: 0, detail: 1, clientX: x, clientY: 20, target: {}, preventDefault() {}, stopPropagation() {}, ...extra});
  handlers.mousedown(ev(50, {shiftKey: true})); handlers.mouseup(ev(50, {shiftKey: true}));      // single shift click
  assert.equal(relayouts.length, 0);
  handlers.mousedown(ev(50, {shiftKey: true})); handlers.mouseup(ev(120, {shiftKey: true}));     // a box zoom drag
  assert.equal(relayouts.length, 0);
  handlers.mousedown(ev(50, {})); handlers.mouseup(ev(50, {}));                                   // plain click selects only
  assert.equal(relayouts.length, 0);
  handlers.mousedown(ev(50, {shiftKey: true, detail: 2}));                                        // shift + double-click
  assert.equal(relayouts.length, 1);
  assert.equal(relayouts[0]['xaxis.autorange'], true);
  assert.equal(relayouts[0]['yaxis.autorange'], true);
});

// ---- live preview: every sample of the plot follows the cross -------------------------------------------------
function previewSetup({samples, traces, owner = 'a-uv', sid = 'a-uv'}) {
  const handlers = {}, restyles = [], fetched = [], pending = [];
  const axis = (len, off, d2p, p2d) => ({_length: len, _offset: off, d2p, p2d});
  const heat = {
    _fullLayout: {xaxis: axis(200, 40, t => t * 50, v => v / 50), yaxis: axis(100, 10, w => 100 - (w - 190) / 5.1, v => 190 + (100 - v) * 5.1)},
    _fullData: [{x: [0, 1, 2], y: [190, 250, 300, 400], z: [[1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4]]}],
    getBoundingClientRect: () => ({left: 100, top: 50}), closest: () => view, on() {}};
  const spectrum = {data: [{y: []}]};
  const view = {getBoundingClientRect: () => ({left: 90, top: 40}), appendChild() {}};
  const hostOf = gd => ({contains: () => true, querySelector: () => gd});
  const main = {data: traces};
  const document = {addEventListener: (n, f) => handlers[n] = f,
    getElementById: id => id === 'pda-spectrum' ? hostOf(spectrum) : hostOf(heat),
    createElement: () => ({style: {}, set innerHTML(v) { this.firstChild = {style: {}}; this.lastChild = {style: {}}; }, parentNode: view})};
  const Plotly = {restyle: (gd, update, indices) => restyles.push({update, indices}), update() {}};
  const window = {addEventListener() {}, requestAnimationFrame: f => { f(); return 1; }, Plotly,
    geckoActivePlot: () => main, GeckoPdaScanCursor: {sourceId: () => sid, ownerId: () => owner, preview() {}},
    dash_clientside: {set_props() {}}};
  const fetch = url => { fetched.push(url); return new Promise(resolve => pending.push(() => resolve({json: () => Promise.resolve({samples})}))); };
  vm.runInNewContext(fs.readFileSync('src/assets/js/pda-heatmap-cursor.js', 'utf8'),
    {document, window, fetch, encodeURIComponent, Math, Array, String, Number, Object, Promise, MutationObserver: class { observe() {} }, Date});
  const drag = () => {
    handlers.mousedown({button: 0, detail: 1, clientX: 160, clientY: 100, target: {}, preventDefault() {}, stopPropagation() {}});
    handlers.mousemove({button: 0, clientX: 170, clientY: 100, target: {}, preventDefault() {}});
  };
  const settle = async () => { while (pending.length) { pending.shift()(); await new Promise(r => setImmediate(r)); } };
  return {drag, settle, restyles, fetched, main, handlers};
}
const previewTrace = (id, name = 'PDA 263 nm · preview') => ({name, meta: {pda_preview: true, pda_source_id: id}, x: [0], y: [0]});

test('every matching preview trace follows the cross in one restyle call; others are left alone', async () => {
  const ids = ['a-uv', 'b-uv', 'c-uv', 'd-uv', 'e-uv'];
  const traces = [...ids.map(id => previewTrace(id)),
                  {name: 'other', meta: {file_id: 'x'}, x: [0], y: [0]}, {name: 'ms', meta: {file_id: 'tic'}, x: [0], y: [0]}];
  const samples = ids.map((id, n) => ({source_id: id, wavelength_nm: 250, x: [0, 1], y: [n, n + 1]}));
  const t = previewSetup({samples, traces});
  t.drag();
  assert.equal(t.fetched.length, 1);
  assert.match(t.fetched[0], /owner=a-uv&wavelength=\d+$/);
  const before = t.restyles.length;                      // the selected trace already moved from the heatmap column
  await t.settle();
  const series = t.restyles.slice(before);
  assert.equal(series.length, 1);                        // one redraw for every sample
  assert.deepEqual(Array.from(series[0].indices), [0, 1, 2, 3, 4]);
  assert.deepEqual(JSON.parse(JSON.stringify(series[0].update.y)), samples.map(s => s.y));
  assert.equal(series[0].update.name.every(n => n === 'PDA 250 nm · preview'), true);
});

test('hidden or absent samples neither break matching nor get traces', async () => {
  const traces = [previewTrace('a-uv'), previewTrace('c-uv'), {name: 'plain', meta: 'text', x: [0], y: [0]}, {name: 'none', x: [0], y: [0]}];
  const samples = ['a-uv', 'b-uv', 'c-uv'].map(id => ({source_id: id, wavelength_nm: 250, x: [0], y: [1]}));
  const t = previewSetup({samples, traces});
  t.drag();
  const before = t.restyles.length;
  await t.settle();
  assert.deepEqual(Array.from(t.restyles.slice(before)[0].indices), [0, 1]);      // b-uv is hidden: no trace, no error
});

test('a wavelength requested while a fetch is in flight is fetched next, even after the button is released', async () => {
  const ids = ['a-uv', 'b-uv'];
  const samples = ids.map(id => ({source_id: id, wavelength_nm: 300, x: [0], y: [1]}));
  const t = previewSetup({samples, traces: ids.map(id => previewTrace(id))});
  t.drag();                                              // first request in flight (wavelength column 1)
  t.handlers.mousemove({button: 0, clientX: 170, clientY: 140, target: {}, preventDefault() {}});   // another wavelength, still in flight
  t.handlers.mouseup({});
  await t.settle();
  assert.equal(t.fetched.length, 2);
  assert.notEqual(t.fetched[0], t.fetched[1]);
});
