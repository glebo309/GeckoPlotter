const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
function setup(){
 const events={};let gd;
 const document={body:{},readyState:'loading',addEventListener(n,f){events[n]=f;},getElementById(){return null;}};
 const window={geckoActivePlot:()=>gd,addEventListener(){},requestAnimationFrame(){return 1;}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/scan-line-constraint.js','utf8'),{window,document,MutationObserver:class {observe(){}},setTimeout(){}});
 gd={data:[{meta:{file_id:'negative'},xaxis:'x',yaxis:'y'},{meta:{file_id:'uv'},xaxis:'x2',yaxis:'y2'}],
 _fullLayout:{width:600,height:500,xaxis:{_offset:50,_length:500},yaxis:{_offset:20,_length:180},xaxis2:{_offset:50,_length:500},yaxis2:{_offset:250,_length:180}},
 getBoundingClientRect:()=>({left:10,top:30,width:600,height:500})};
 window.__geckoLcmsScanState={sourceFileId:'negative',subplotIdx:1};
 return {window,gd,events};
}
test('negative filter removes positive pane: cursor follows rendered negative source, not old row index',()=>{
 const {window}=setup();const rect=window.GeckoLcmsScanCursor.plotRect();assert.equal(rect.top,50);assert.equal(rect.height,180);
});
test('reordered traces and UV selection cannot move spectral cursor to UV pane',()=>{
 const {window,gd}=setup();gd.data.reverse();gd.data[1].xaxis='x2';gd.data[1].yaxis='y2';gd.data[0].xaxis='x';gd.data[0].yaxis='y';
 assert.equal(window.GeckoLcmsScanCursor.plotRect().top,280);
});
test('hidden or filtered-out spectral source hides cursor instead of clamping onto another channel',()=>{
 const {window,gd}=setup();gd.data[0].visible='legendonly';assert.equal(window.GeckoLcmsScanCursor.plotRect(),null);
 gd.data.shift();assert.equal(window.GeckoLcmsScanCursor.plotRect(),null);
});
test('overlay shares spectral source axes and geometry tracks resized figure',()=>{
 const {window,gd}=setup();gd.data[0].yaxis='y2';gd.getBoundingClientRect=()=>({left:10,top:30,width:1200,height:1000});
 const rect=window.GeckoLcmsScanCursor.plotRect();assert.equal(rect.left,110);assert.equal(rect.top,530);assert.equal(rect.height,360);
});
