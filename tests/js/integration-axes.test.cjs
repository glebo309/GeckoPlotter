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
