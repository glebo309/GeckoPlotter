const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
function setup(){
 const handlers={},events=[],updates=[];
 const input=()=>({style:{},handlers:{},setAttribute(){},addEventListener(n,f){this.handlers[n]=f;},
   remove(){this.removed=true},focus(){},select(){}});
 const document={addEventListener(n,f){handlers[n]=f;},createElement:input,body:{appendChild(){}}};
 const window={innerWidth:1200,innerHeight:800,dash_clientside:{set_props(id,props){events.push([id,props]);}},
   Plotly:{relayout(g,update){updates.push(update);return Promise.resolve();}}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/figure-label-edit.js','utf8'),{window,document,Date,requestAnimationFrame:f=>f()});
 return {api:window.GeckoFigureLabels,handlers,events,updates};
}
function graph(){return {layout:{title:{text:'Original'},meta:{gecko_tab_id:'publication-1'},
 yaxis2:{title:{text:'Absorbance (mAU)'}},xaxis:{title:{text:'Time (min)'}}},contains:()=>true,
 getBoundingClientRect:()=>({width:400,height:300}),style:{display:'block'}};}
function text(cls){return {tagName:'text',textContent:'Original',getAttribute:()=>cls,
 getBoundingClientRect:()=>({left:100,top:140,width:80,height:15})};}
test('direct hit distinguishes text editing from axis tick zoom reset',()=>{
 const {api}=setup(),gd=graph();
 assert.equal(api.targetAtEvent(gd,{target:text('gtitle')}).field,'title');
 assert.equal(api.targetAtEvent(gd,{target:text('y2title')}).field,'yaxis2');
 assert.equal(api.targetAtEvent(gd,{target:text('xtitle')}).field,'xaxis');
 assert.equal(api.targetAtEvent(gd,{target:text('ytick')}),null);
});
test('publication inline edit sends owned settings event and updates live paper figure',()=>{
 const {api,events,updates}=setup(),gd=graph();
 const editor=api.begin(gd,{field:'yaxis2',element:text('y2title')});
 assert.equal(editor.value,'Absorbance (mAU)');
 editor.value='UV response';
 editor.handlers.keydown({key:'Enter',preventDefault(){},stopPropagation(){}});
 assert.equal(events[0][0],'figure-label-edit');
 assert.equal(events[0][1].data.tab,'publication-1');
 assert.equal(events[0][1].data.field,'yaxis2');
 assert.equal(events[0][1].data.text,'UV response');
 assert.equal(updates[0]['yaxis2.title.text'],'UV response');
 assert.equal(editor.removed,true);
});
test('escape or leaving figure cancels without changing settings',()=>{
 const {api,events,handlers}=setup(),gd=graph();
 let editor=api.begin(gd,{field:'title',element:text('gtitle')});
 editor.value='Discard';editor.handlers.keydown({key:'Escape',preventDefault(){},stopPropagation(){}});
 assert.equal(events.length,0);
 editor=api.begin(gd,{field:'title',element:text('gtitle')});
 handlers['gecko:plot-leave']();
 assert.equal(editor.removed,true);assert.equal(events.length,0);
});
test('automatic title bold formatting is not exposed as markup in the editor',()=>{
 const {api}=setup(),gd=graph();gd.layout.title.text='<b>My publication</b>';
 const editor=api.begin(gd,{field:'title',element:text('gtitle')});
 assert.equal(editor.value,'My publication');
});
test('shared publication axis annotations edit their matching measurement axis',()=>{
 const {api,events,updates}=setup(),gd=graph();
 gd.layout.yaxis={title:{text:''}};gd.layout.yaxis2.title.text='';
 gd.layout.meta.gecko_axis_identities={yaxis:{id:'y:ioncount',label:'Ion Count'},yaxis2:{id:'y:mau',label:'Absorbance (mAU)'}};
 gd.layout.annotations=[{name:'gecko-shared-y',text:'Absorbance (mAU)',xref:'paper',yref:'paper',y:.2}];
 const label=text('annotation-text');label.closest=()=>({getAttribute:()=> '0'});
 const hit=api.targetAtEvent(gd,{target:label});
 assert.equal(hit.field,'yaxis2');
 const editor=api.begin(gd,hit);assert.equal(editor.value,'Absorbance (mAU)');
 editor.value='UV';editor.handlers.keydown({key:'Enter',preventDefault(){},stopPropagation(){}});
 assert.equal(events[0][1].data.field,'yaxis2');assert.equal(updates[0]['annotations[0].text'],'UV');
});
