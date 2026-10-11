const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('publication tabs retain their own graphs and move the same graph between paper and slide', async () => {
  let renders=0, disconnected=0;
  function el(){return {style:{},dataset:{},children:[],appendChild(c){c.parentElement=this;this.children.push(c)},remove(){this.removed=true},getBoundingClientRect(){return {width:600,height:400}}};}
  const paper=el(),slide=el(); const nodes={'pub-plot-workspace':paper,'pub-slide-workspace':slide};
  const document={getElementById:id=>nodes[id],createElement:el};
  const window={dash_clientside:{no_update:{}},Plotly:{async react(g,d,l){renders++;g.data=d;g.layout=l},purge(){},Plots:{resize(){return Promise.resolve()}}}};
  vm.runInNewContext(fs.readFileSync('src/assets/js/publication-workspace.js','utf8'),{window,document,ResizeObserver:class{observe(){} disconnect(){disconnected++;}},requestAnimationFrame:fn=>fn()});
  const update=window.dash_clientside.publicationWorkspace.update;
  const tabs=[{id:'a',type:'publication'},{id:'b',type:'publication'}];
  const fig=id=>({data:[{x:[0,1],y:[0,2]}],layout:{meta:{gecko_tab_id:id}}});
  await update(fig('a'),'a',tabs,'single-col');
  const a=paper.children[0]; a.layout.xaxis={range:[.2,.8]};
  await update(fig('b'),'b',tabs,'single-col');
  await update(fig('b'),'a',tabs,'single-col');
  assert.equal(a.style.display,'block');
  assert.equal(renders,2);
  assert.deepEqual(a.layout.xaxis.range,[.2,.8]);
  await update(fig('a'),'a',tabs,'presentation');
  assert.equal(a.parentElement,slide);
  assert.equal(renders,2);
  await update(fig('b'),'b',[tabs[1]],'single-col');
  assert.equal(a.removed,true);
  assert.equal(disconnected,1);
});

test('figure/page preview moves the retained plot and scales the figure to the editing space', async () => {
  let renders=0;
  function el(){return {style:{},dataset:{},children:[],clientWidth:1000,clientHeight:700,appendChild(c){c.parentElement=this;this.children.push(c)},getBoundingClientRect(){return {width:2000,height:1400}}};}
  const paper=el(),editor=el(); const nodes={'pub-plot-workspace':paper,'pub-figure-workspace':editor};
  const document={getElementById:id=>nodes[id],createElement:el};
  const window={dash_clientside:{no_update:{}},Plotly:{async react(g,d,l){renders++;g.data=d;g.layout=l},purge(){},Plots:{resize(){return Promise.resolve()}}}};
  vm.runInNewContext(fs.readFileSync('src/assets/js/publication-workspace.js','utf8'),{window,document,ResizeObserver:class{observe(){} disconnect(){}},requestAnimationFrame:fn=>fn()});
  const update=window.dash_clientside.publicationWorkspace.update;
  const tabs=[{id:'a',type:'publication'}];
  const figure={data:[{x:[0,1],y:[0,2]}],layout:{meta:{gecko_tab_id:'a',gecko_width_mm:84,gecko_height_mm:63}}};
  await update(figure,'a',tabs,'single-col','figure');
  const gd=editor.children[0];
  assert.ok(gd,'figure is mounted in the editing canvas');
  assert.match(gd.style.transform,/scale\(/);
  assert.ok(Math.abs(parseFloat(gd.style.left)-100/3)<.01, 'fit uses unscaled container size even if page/browser is magnified');
  await update(figure,'a',tabs,'single-col','page');
  assert.equal(gd.parentElement,paper);
  assert.equal(renders,1,'changing the preview frame does not recreate or redraw the figure');
});

test('CSS preview magnification never lets Plotly resize against the transformed bounds', async () => {
  let resizeCalls=0, config;
  function el(){return {style:{},dataset:{},children:[],clientWidth:272,clientHeight:204,
    appendChild(c){c.parentElement=this;this.children.push(c)},
    getBoundingClientRect(){return {width:544,height:408}}};}
  const host=el(),document={getElementById:id=>id==='pub-plot-workspace'?host:null,createElement:el};
  const window={dash_clientside:{no_update:{}},Plotly:{async react(g,d,l,c){g.data=d;g.layout=l;config=c;},
    purge(){},Plots:{resize(){resizeCalls++;return Promise.resolve();}}}};
  vm.runInNewContext(fs.readFileSync('src/assets/js/publication-workspace.js','utf8'),{window,document,
    ResizeObserver:class{observe(){}disconnect(){}},requestAnimationFrame:fn=>fn()});
  await window.dash_clientside.publicationWorkspace.update({data:[{x:[0,1],y:[0,1]}],
    layout:{meta:{gecko_tab_id:'p',gecko_width_mm:84,gecko_height_mm:63}}},'p',[{id:'p',type:'publication'}],'single-col','page');
  const gd=host.children[0];
  assert.equal(gd.layout.width,307);
  assert.equal(gd.layout.height,307*63/84);
  assert.equal(gd.layout.autosize,false);
  assert.equal(config.responsive,false);
  assert.equal(resizeCalls,0,'Plotly resize would measure the already transformed canvas and shrink it twice');
});
