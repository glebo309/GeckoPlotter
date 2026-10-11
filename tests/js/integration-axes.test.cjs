const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('drawing on overlaid UV data uses its own Y scale', () => {
    const window = {__geckoActiveFile:'uv1',addEventListener(){},setTimeout(){}};
    const document = {readyState:'loading',addEventListener(){}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/manual-integration.js'),'utf8'),
        {window,document});
    const bounds = {left:0,right:100,top:0,bottom:100,width:100,height:100};
    const drag = {getBoundingClientRect:()=>bounds,parentNode:{getAttribute:()=> 'xy'}};
    const xaxis = {}, count = {}, uv = {overlaying:'y'};
    const gd = {data:[{meta:{file_id:'uv1'},xaxis:'x',yaxis:'y3'}],
        querySelectorAll:()=>[drag],_fullLayout:{_plots:{xy:{xaxis,yaxis:count},xy3:{xaxis,yaxis:uv}}}};
    const sp = window.GeckoPlotterManualIntegration.subplotAtEvent(gd,{clientX:50,clientY:50});
    assert.equal(sp.yaxis,uv);
    assert.equal(sp.key,'xy3');
});

test('Escape aborts an in-progress baseline, removes preview and never commits on later pointerup', () => {
    const events = {}, graphEvents = {}, props = [], relayouts = [];
    const bounds = {left:0,right:100,top:0,bottom:100,width:100,height:100};
    const axis = {range:[0,10]};
    const drag = {getBoundingClientRect: () => bounds, parentNode:{getAttribute: () => 'xy'}};
    let preview = null;
    const gd = {data: [], layout:{}, classList:{toggle(){}},
        _fullLayout:{_plots:{xy:{xaxis:axis,yaxis:axis}},xaxis:axis,yaxis:axis},
        querySelectorAll: () => [drag], addEventListener: (name, fn) => graphEvents[name] = fn};
    const window = {geckoActivePlot: () => gd, __geckoBaselineMode:'draw',
        Plotly:{relayout:(_,v)=>relayouts.push(v)},
        dash_clientside:{set_props:(id,v)=>props.push([id,v])},
        addEventListener:(name,fn)=>events[name]=fn,
        removeEventListener:(name,fn)=>{if(events[name]===fn)delete events[name];}, setTimeout(){}};
    const document = {readyState:'loading',addEventListener(){},
        getElementById:id=>id==='gecko-manual-draw-preview'?preview:null,
        createElementNS:()=>({style:{},setAttribute(){},appendChild(){},querySelector:()=>({setAttribute(){}})}),
        body:{appendChild(node){preview=node;node.parentNode={removeChild(){preview=null;}};}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/manual-integration.js'),'utf8'),
        {window,document,Date});
    window.GeckoPlotterManualIntegration.installEmptyClickHandler();
    const event = {clientX:20,clientY:20,button:0,target:{closest:()=>null},preventDefault(){},stopPropagation(){}};
    graphEvents.pointerdown(event);
    assert.ok(gd.__geckoManualIntegrationDrawing);
    assert.ok(preview);
    const stalePointerUp = events.pointerup;
    window.GeckoPlotterManualIntegration.cancelInteraction('main-plot');
    assert.equal(gd.__geckoManualIntegrationDrawing,null);
    assert.equal(gd.__geckoManualIntegrationMode,'navigate');
    assert.equal(preview,null);
    assert.equal(events.pointermove,undefined);
    assert.equal(events.pointerup,undefined);
    stalePointerUp({...event,clientX:80,clientY:30});
    assert.equal(props.length,0);
    assert.equal(relayouts.at(-1).dragmode,'zoom');
});
