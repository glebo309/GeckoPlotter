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
