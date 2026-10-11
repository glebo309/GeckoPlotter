const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('layout controls preserve navigation defaults and Integrate toggles back to navigation', () => {
    const props = [], relayouts = [];
    const gd = {layout:{xaxis:{},xaxis2:{},yaxis:{},yaxis2:{}}};
    const window = {geckoActivePlot: () => gd, Plotly: {relayout: (_, value) => relayouts.push(value)},
        dash_clientside:{no_update:{},set_props:(id,value)=>props.push([id,value])}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/plot-toolbar.js'),'utf8'),
        {window,document:{getElementById:()=>null}});
    const action = window.dash_clientside.plotToolbar.action;
    action('plot-tool-separate');
    assert.ok(props.some(p=>p[0]==='pt-layout-mode' && p[1].value==='stacked'));
    action('plot-tool-overlay');
    assert.ok(props.some(p=>p[0]==='pt-layout-mode' && p[1].value==='overlay'));
    assert.ok(!props.some(p=>p[0]==='baseline-mode'));
    assert.equal(relayouts.length,0);
    action('plot-tool-integrate', 'navigate');
    assert.ok(props.some(p=>p[0]==='baseline-mode' && p[1].data==='draw'));
    props.length = 0;
    action('plot-tool-integrate', 'draw');
    assert.ok(props.some(p=>p[0]==='baseline-mode' && p[1].data==='navigate'));
});
