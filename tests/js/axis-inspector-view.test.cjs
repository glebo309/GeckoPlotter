const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
test('inspector captures actual visible zoom before keyboard and pointer edits',()=>{
 const handlers={},events=[];
 const hidden={getBoundingClientRect:()=>({width:0,height:0})};
 const gd={getBoundingClientRect:()=>({width:500,height:300}),dataset:{publicationPlot:'publication-1'},
  _fullLayout:{meta:{gecko_tab_id:'publication-1'},xaxis:{range:[5,9],type:'linear',autorange:false,title:{text:'Time (min)'}}}};
 const document={querySelectorAll:()=>[hidden,gd],addEventListener(n,f){handlers[n]=f;}};
 const window={dash_clientside:{set_props(id,p){events.push([id,p]);}}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/axis-inspector-view.js','utf8'),{window,document,Date});
 handlers.focusin({target:{closest:()=>true}});
 assert.equal(events[0][0],'axis-inspector-view');
 assert.equal(events[0][1].data.tab,'publication-1');
 assert.deepEqual(Array.from(events[0][1].data.axes.xaxis.range),[5,9]);
 assert.equal(events[0][1].data.axes.xaxis.autorange,false);
 handlers.keydown({target:{closest:()=>null}});
 assert.equal(events.length,1);
 assert.equal(typeof handlers.pointerdown,'function');
});

test('fixed publication snapshot ranges count as zoom only after a graph interaction',()=>{
 const handlers={},events=[],listeners={};
 const gd={on(n,f){listeners[n]=f;},getBoundingClientRect:()=>({width:500,height:300}),dataset:{publicationPlot:'publication-1'},
  _fullLayout:{meta:{gecko_tab_id:'publication-1'},xaxis:{range:[0,10],type:'linear',autorange:false,title:{text:'Time (min)'}}}};
 const document={querySelectorAll:()=>[gd],addEventListener(n,f){handlers[n]=f;}};
 const window={dash_clientside:{set_props(id,p){events.push(p.data);}}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/axis-inspector-view.js','utf8'),{window,document,Date});
 handlers.focusin({target:{closest:s=>s==='.axis-inspector'?{}:null}});
 assert.equal(events.at(-1).axes.xaxis.userZoom,false);
 handlers.pointerdown({target:{closest:s=>s==='.js-plotly-plot'?gd:null}});
 listeners.plotly_relayout({'xaxis.range[0]':5,'xaxis.range[1]':9});
 gd._fullLayout.xaxis.range=[5,9];
 handlers.focusin({target:{closest:s=>s==='.axis-inspector'?{}:null}});
 assert.equal(events.at(-1).axes.xaxis.userZoom,true);
 listeners.plotly_relayout({'xaxis.autorange':true});
 handlers.focusin({target:{closest:s=>s==='.axis-inspector'?{}:null}});
 assert.equal(events.at(-1).axes.xaxis.userZoom,false);
});
