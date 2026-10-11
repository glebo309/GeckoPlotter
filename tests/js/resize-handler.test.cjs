const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup() {
 const elements={},listeners={};
 const style=()=>({setProperty(k,v){this[k]=v;},removeProperty(k){delete this[k];}});
 function element(id) {
   const classes=new Set();
   return {id,style:style(),dataset:{},events:{},classList:{contains:k=>classes.has(k),add:(...ks)=>ks.forEach(k=>classes.add(k)),remove:(...ks)=>ks.forEach(k=>classes.delete(k)),toggle(){}},
     querySelector:()=>null,appendChild(){},addEventListener(name,fn){this.events[name]=fn;},
     getBoundingClientRect(){const hidden=this.style.display==='none';return {left:0,top:0,right:1000,bottom:1000,
       width:hidden?0:parseFloat(this.style.width||100)*10,height:hidden?0:parseFloat(this.style.height||100)*10};}};
 }
 ['main-container','left-column','right-column','left-top-panel','left-bottom-panel','right-top-panel','right-bottom-panel',
  'left-vertical-divider','right-vertical-divider','main-divider'].forEach(id=>elements[id]=element(id));
 elements['left-top-panel'].style.height='38%';elements['left-bottom-panel'].style.height='62%';
 const document={readyState:'complete',getElementById:id=>elements[id],body:element('body'),
   addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
 const window={dash_clientside:{no_update:{}},addEventListener(){}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/resize-handler.js','utf8'),{window,document,setTimeout:fn=>fn(),console:{log(){}}});
 return {window,elements,listeners,sync:window.__geckoSyncPlotTabLayout};
}
const tabs=[{id:'raw-a',type:'raw'},{id:'publication-a',type:'publication'},{id:'raw-b',type:'raw'}];

test('first visit to a raw tab restores the results pane after publication',()=>{
 const s=setup();s.sync('raw-a',tabs);s.sync('publication-a',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 s.sync('raw-b',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 assert.equal(s.elements['right-bottom-panel'].style.height,'40%');
 assert.equal(s.elements['left-top-panel'].style.display,'flex');
 assert.equal(s.elements['left-top-panel'].style.height,'38%');
});

test('raw custom split survives publication and repeated tab synchronizations',()=>{
 const s=setup();s.sync('raw-a',tabs);
 const target={classList:{contains:()=>false}},event={target,clientX:0,clientY:600,preventDefault(){},stopPropagation(){}};
 s.elements['right-vertical-divider'].events.mousedown(event);
 s.listeners.mousemove[0]({...event,clientY:730});s.listeners.mouseup[0]();
 assert.equal(s.elements['right-bottom-panel'].style.height,'27%');
 s.sync('publication-a',tabs);s.sync('raw-a',tabs);s.sync('raw-a',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 assert.equal(s.elements['right-bottom-panel'].style.height,'27%');
 s.sync('publication-a',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
});

test('tab descriptors decide publication mode instead of ambiguous ID prefixes',()=>{
 const s=setup();s.sync('publication-data',[{id:'publication-data',type:'raw'}]);
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 assert.equal(s.elements['right-bottom-panel'].style.height,'40%');
});

test('publication-first startup and rapid switching cannot leak hidden Results into an unseen raw tab',()=>{
 const s=setup();
 s.sync('publication-a',tabs);
 for(let i=0;i<50;i++) {
   s.sync(i%2?'raw-a':'raw-b',tabs);
   assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
   assert.equal(s.elements['right-bottom-panel'].style.height,'40%');
   s.sync('publication-a',tabs);
   assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 }
 s.sync('raw-b',tabs);
 assert.equal(s.elements['right-top-panel'].style.height,'60%');
});

test('a recycled tab id cannot restore a layout belonging to the other tab kind',()=>{
 const s=setup();
 s.sync('same',[{id:'same',type:'publication'}]);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 s.sync('same',[{id:'same',type:'raw'}]);
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 assert.equal(s.elements['right-bottom-panel'].style.height,'40%');
});
