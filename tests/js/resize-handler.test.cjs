const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup(withLabels=false) {
 const elements={},listeners={},windowListeners={},frames=[];
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
 if(withLabels) for(const id of ['left-vertical-divider','right-vertical-divider','main-divider']) {
   const label=element(id+'-label'),zone=element(id+'-zone');
   elements[id].querySelector=selector=>selector==='.divider-label'?label:selector==='.divider-hover-zone'?zone:null;
   elements[id].dataset.labelAbove='Plot';elements[id].dataset.labelBelow='Analysis';
 }
 const document={readyState:'complete',querySelector:()=>null,getElementById:id=>elements[id],body:element('body'),
   addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
 const window={requestAnimationFrame:fn=>frames.push(fn),dash_clientside:{no_update:{}},addEventListener:(name,fn)=>(windowListeners[name]??=[]).push(fn)};
 vm.runInNewContext(fs.readFileSync('src/assets/js/resize-handler.js','utf8'),{window,document,setTimeout:fn=>fn(),console:{log(){}}});
 return {window,document,elements,listeners,windowListeners,paint(){while(frames.length)frames.shift()();},sync:window.__geckoSyncPlotTabLayout};
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

function wide(s,width=1200) {
 s.elements['right-column'].getBoundingClientRect=()=>({left:0,top:0,right:width,bottom:800,width,height:800});
}
function dock(s,panel,value='below',trigger='analysis-tabs',owner='raw-a',tab='raw-a') {
 s.window.dash_clientside.callback_context={triggered:[{prop_id:trigger+'.value'}]};
 return s.window.dash_clientside.resize.syncAnalysisDock(panel,value,tab,tabs,owner);
}
function dragRight(s,dx,dy=0) {
 const event={target:{classList:{contains:()=>false}},clientX:0,clientY:0,preventDefault(){},stopPropagation(){}};
 s.elements['right-vertical-divider'].events.mousedown(event);
 s.listeners.mousemove[0]({...event,clientX:dx,clientY:dy});s.listeners.mouseup[0]();
}

test('mass analysis defaults right only with room; Data and Peaks stay below',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);
 for(const panel of ['ms-scan','ms-eic','ms-peak-mass']) {
   assert.equal(dock(s,panel)[0],'right');
   assert.equal(s.elements['right-column'].style.flexDirection,'row');
   assert.equal(s.elements['right-top-panel'].style.width,'60%');
   assert.equal(s.elements['right-top-panel'].style.height,'100%');
 }
 for(const panel of ['data-overview','peak-analysis']) {
   assert.equal(dock(s,panel,'right')[0],'below');
   assert.equal(s.elements['right-column'].style.flexDirection,'column');
   assert.equal(s.elements['right-top-panel'].style.width,'100%');
 }
 wide(s,650);assert.equal(dock(s,'ms-scan')[0],'below');
});

test('right splitter uses horizontal motion and both orientations retain their own split',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);dock(s,'ms-scan');
 dragRight(s,120,500);
 assert.equal(s.elements['right-top-panel'].style.width,'70%');
 dock(s,'peak-analysis','right');
 assert.equal(s.elements['right-top-panel'].style.height,'60%');
 dragRight(s,0,80);
 assert.equal(s.elements['right-top-panel'].style.height,'70%');
 dock(s,'ms-scan');
 assert.equal(s.elements['right-top-panel'].style.width,'70%');
 dock(s,'peak-analysis','right');assert.equal(s.elements['right-top-panel'].style.height,'70%');
});

test('manual docking belongs to its plot and survives publication without leaking into new tabs',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);
 dock(s,'peak-analysis','right','analysis-dock');dragRight(s,120);
 assert.equal(dock(s,'data-overview','right')[0],'right');
 s.sync('publication-a',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 s.sync('raw-a',tabs);
 assert.equal(s.elements['right-column'].style.flexDirection,'row');
 assert.equal(s.elements['right-top-panel'].style.width,'70%');
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 s.sync('raw-b',tabs);
 assert.equal(s.elements['right-column'].style.flexDirection,'column');
 assert.equal(s.elements['right-top-panel'].style.height,'60%');
 s.sync('raw-a',tabs);
 assert.equal(s.elements['right-top-panel'].style.width,'70%');
});

test('stale dock control from another plot cannot overwrite its automatic layout',()=>{
 const s=setup();wide(s);s.sync('raw-b',tabs);
 const result=dock(s,'peak-analysis','right','analysis-dock','raw-a','raw-b');
 assert.equal(result[0],'below');assert.equal(result[1],'raw-b');
});

test('right dock can collapse Analysis and publication roundtrip retains that collapse',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);dock(s,'ms-scan');
 dragRight(s,480);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 assert.equal(s.elements['right-top-panel'].style.width,'100%');
 s.sync('publication-a',tabs);s.sync('raw-a',tabs);
 assert.equal(s.elements['right-bottom-panel'].style.display,'none');
 assert.equal(s.elements['right-top-panel'].style.width,'100%');
});


test('collapsed right dock label restores Analysis with horizontal dock geometry',()=>{
 const s=setup(true);wide(s);s.sync('raw-a',tabs);dock(s,'ms-scan');dragRight(s,480);
 const divider=s.elements['right-vertical-divider'],label=divider.querySelector('.divider-label');
 assert.equal(label.textContent,'Analysis');assert.equal(label.classList.contains('collapse-left'),true);
 assert.equal(divider.style['--dock-width'],'46px');assert.equal(divider.style['--dock-height'],'800px');
 label.events.click({stopPropagation(){}});
 assert.equal(s.elements['right-bottom-panel'].style.display,'flex');
 assert.equal(s.elements['right-top-panel'].style.width,'60%');
 assert.equal(label.classList.contains('visible'),false);
});

test('automatic dock follows viewport width without treating control hydration as a user override',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);dock(s,'ms-scan');dragRight(s,120);
 const updates=[];s.window.dash_clientside.set_props=(id,props)=>updates.push([id,props]);
 wide(s,650);s.windowListeners.resize[0]();
 assert.equal(s.elements['right-column'].dataset.analysisDock,'below');
 assert.equal(updates.at(-1)[1].value,'below');
 dock(s,'ms-scan','below','analysis-dock');
 wide(s);s.windowListeners.resize[0]();
 assert.equal(s.elements['right-column'].dataset.analysisDock,'right');
 assert.equal(s.elements['right-top-panel'].style.width,'70%');
});

test('finishing Files divider drag adapts automatic mass dock to remaining plot space',()=>{
 const s=setup();let width=1200;wide(s,width);s.sync('raw-a',tabs);dock(s,'ms-scan');
 const event={target:{classList:{contains:()=>false}},clientX:0,clientY:0,preventDefault(){},stopPropagation(){}};
 s.elements['main-divider'].events.mousedown(event);
 s.listeners.mousemove[0]({...event,clientX:100});wide(s,650);s.listeners.mouseup[0]();
 assert.equal(s.elements['right-column'].dataset.analysisDock,'below');
});


test('docking and analysis selection reveal only the active tab inside its horizontal scroller',()=>{
 const s=setup();wide(s);s.sync('raw-a',tabs);
 let selectedBounds={left:470,right:550,width:80};
 const selected={getBoundingClientRect:()=>selectedBounds,scrollIntoView(){throw Error('must not scroll ancestors');}};
 const scroller={scrollLeft:0,querySelector:selector=>selector==='[role="tab"][aria-selected="true"]'?selected:null,
   getBoundingClientRect:()=>({left:100,right:400,width:300})};
 s.document.querySelector=selector=>selector==='.results-navigation'?{firstElementChild:scroller}:null;
 dock(s,'ms-scan');
 assert.equal(scroller.scrollLeft,0,'wait for the dock to paint');
 s.paint();assert.equal(scroller.scrollLeft,150);
 selectedBounds={left:70,right:140,width:70};
 dock(s,'ms-eic','right');s.paint();assert.equal(scroller.scrollLeft,120);
 selectedBounds={left:150,right:220,width:70};
 dock(s,'ms-peak-mass','right');s.paint();assert.equal(scroller.scrollLeft,120,'visible tab needs no scrolling');
});
