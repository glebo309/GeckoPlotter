const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
test('double-clicking one axis resets that axis and freezes the perpendicular zoom',()=>{
 const handlers={},updates=[];
 const window={Plotly:{relayout(g,u){updates.push(u);return Promise.resolve();}}};
 const document={addEventListener(n,f){handlers[n]=f;}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/axis-reset.js','utf8'),{window,document,Date});
 const gd={_fullLayout:{xaxis:{_offset:100,_length:400,range:[5,9]},yaxis:{_offset:30,_length:200,range:[0,600]}},
  getBoundingClientRect:()=>({left:0,top:0,width:550,height:300})};
 assert.equal(window.GeckoPlotterAxisReset.axisAtEvent(gd,{clientX:90,clientY:130}),'yaxis');
 window.GeckoPlotterAxisReset.reset(gd,'yaxis');
 assert.equal(updates[0]['yaxis.autorange'],true);
 assert.deepEqual(Array.from(updates[0]['xaxis.range']),[5,9]);
 assert.equal(updates[0]['xaxis.autorange'],false);
 assert.equal(window.GeckoPlotterAxisReset.axisAtEvent(gd,{clientX:300,clientY:240}),'xaxis');
 assert.equal(window.GeckoPlotterAxisReset.axisAtEvent(gd,{clientX:300,clientY:130}),null);
});

test('axis double-click events are consumed while canvas double-clicks pass through',()=>{
 const handlers={},updates=[];
 const window={Plotly:{relayout(g,u){updates.push(u);return Promise.resolve();}}};
 const document={addEventListener(n,f){handlers[n]=f;}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/axis-reset.js','utf8'),{window,document,Date});
 const gd={_fullLayout:{width:550,height:300,xaxis:{_offset:100,_length:400,range:[5,9]},yaxis:{_offset:30,_length:200,range:[0,600]}},
  getBoundingClientRect:()=>({left:20,top:10,width:1100,height:600})};
 let stopped=false;
 const e={type:'dblclick',detail:2,clientX:200,clientY:270,target:{closest:()=>gd},
  preventDefault(){},stopPropagation(){},stopImmediatePropagation(){stopped=true;}};
 handlers.dblclick(e);
 assert.equal(stopped,true);
 assert.equal(updates[0]['yaxis.autorange'],true);
 assert.deepEqual(Array.from(updates[0]['xaxis.range']),[5,9]);
 stopped=false; e.clientX=620;
 handlers.dblclick(e);
 assert.equal(stopped,false);
 assert.equal(updates.length,1);
 e.clientY=490;
 handlers.dblclick(e);
 assert.equal(updates[1]['xaxis.autorange'],true);
 assert.deepEqual(Array.from(updates[1]['yaxis.range']),[0,600]);
});

test('axis reset publishes owner and current scales for inspector persistence',()=>{
 const events=[];
 const window={Plotly:{relayout(){return Promise.resolve();}},dash_clientside:{set_props(id,props){events.push([id,props]);}}};
 const document={addEventListener(){}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/axis-reset.js','utf8'),{window,document,Date});
 const gd={_fullLayout:{meta:{gecko_tab_id:'plot-a'},xaxis:{range:[5,9],type:'linear'},yaxis:{range:[0,600],type:'linear'}}};
 window.GeckoPlotterAxisReset.reset(gd,'yaxis');
 assert.equal(events[0][0],'axis-inspector-reset');
 assert.equal(events[0][1].data.tab,'plot-a');
 assert.equal(events[0][1].data.axis,'yaxis');
 assert.deepEqual(Array.from(events[0][1].data.axes.xaxis.range),[5,9]);
});
