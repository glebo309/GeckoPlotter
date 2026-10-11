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

function integrationHarness() {
    const events={}, docEvents={}, props=[];
    const axis={range:[0,10]};
    const bounds={left:0,right:100,top:0,bottom:100,width:100,height:100};
    function graph(id,file) {
        const handlers={};
        return {handlers,dataset:{workspacePlot:id},data:[{meta:{file_id:file},x:[0,1],y:[0,1]}],layout:{},classList:{toggle(){}},
            _fullLayout:{_plots:{xy:{xaxis:axis,yaxis:axis}},xaxis:axis,yaxis:axis},
            querySelectorAll:()=>[{getBoundingClientRect:()=>bounds,parentNode:{getAttribute:()=> 'xy'}}],
            addEventListener:(name,fn)=>handlers[name]=fn};
    }
    let active=graph('chrom','control');
    const first=active,second=graph('spectra','blue');
    const window={geckoActivePlot:()=>active,__geckoActiveFile:'control',__geckoBaselineMode:'navigate',
        Plotly:{relayout(){}},dash_clientside:{set_props:(id,v)=>props.push([id,v])},
        addEventListener:(name,fn)=>events[name]=fn,removeEventListener:(name,fn)=>{if(events[name]===fn)delete events[name];},setTimeout(){}};
    const document={readyState:'loading',addEventListener:(name,fn)=>docEvents[name]=fn,
        getElementById:()=>null,createElementNS:()=>({style:{},setAttribute(){},appendChild(){},querySelector:()=>({setAttribute(){}})}),body:{appendChild(){}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/manual-integration.js'),'utf8'),{window,document,Date});
    const api=window.GeckoPlotterManualIntegration;
    api.installEmptyClickHandler();
    const event={clientX:20,clientY:90,button:0,target:{closest:()=>null},preventDefault(){},stopPropagation(){}};
    return {window,api,first,second,events,docEvents,props,event,activate(gd){active=gd;docEvents['gecko:plot-ready']();}};
}

test('revisiting an installed tab reapplies Integrate and removes stale selected peak',()=>{
    const h=integrationHarness();
    h.first.__geckoManualIntegrationSelectedPeakId='oldpeak';
    h.activate(h.second);h.api.syncDrawMode('main-plot','draw');h.activate(h.first);
    assert.equal(h.first.__geckoManualIntegrationMode,'draw');
    assert.equal(h.first.__geckoManualIntegrationSelectedPeakId,null);
    h.first.handlers.pointerdown(h.event);
    assert.ok(h.first.__geckoManualIntegrationDrawing);
});

test('integration owns the visible trace even while active-file still belongs to previous tab',()=>{
    const h=integrationHarness();h.activate(h.second);h.api.syncDrawMode('main-plot','draw');
    h.second.handlers.pointerdown(h.event);h.events.pointerup({...h.event,clientX:80});
    const payload=h.props.find(p=>p[0]==='manual-draw-line-store')[1].data;
    assert.equal(payload.file_id,'blue');assert.equal(payload.tab_id,'spectra');
});

test('leaving a tab cancels in-progress drawing without turning off Integrate',()=>{
    const h=integrationHarness();h.api.syncDrawMode('main-plot','draw');
    h.first.handlers.pointerdown(h.event);const staleFinish=h.events.pointerup;
    h.docEvents['gecko:plot-leave']();h.activate(h.second);staleFinish({...h.event,clientX:80});
    assert.equal(h.first.__geckoManualIntegrationDrawing,null);
    assert.equal(h.window.__geckoBaselineMode,'draw');assert.equal(h.second.__geckoManualIntegrationMode,'draw');
    assert.ok(!h.props.some(p=>p[0]==='manual-draw-line-store'));
});

test('a delayed peak selection from the old tab cannot block drawing on the new graph',()=>{
    const h=integrationHarness();h.activate(h.second);h.api.syncDrawMode('main-plot','draw');
    h.api.syncSelectedShape('main-plot','chrom-peak');
    assert.equal(h.second.__geckoManualIntegrationSelectedPeakId,null);
    h.second.handlers.pointerdown(h.event);
    assert.ok(h.second.__geckoManualIntegrationDrawing);
});

test('a selected peak present in the visible graph remains editable',()=>{
    const h=integrationHarness();
    h.first.data.push({meta:'peak_overlay',customdata:['peak-one','peak-one']});
    h.api.syncSelectedShape('main-plot','peak-one');
    assert.equal(h.first.__geckoManualIntegrationSelectedPeakId,'peak-one');
});
