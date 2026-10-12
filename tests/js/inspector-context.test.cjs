const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
test('inspector context preserves scientific labels and styles without measurement arrays',()=>{
 const noUpdate={unchanged:true},context={window:{dash_clientside:{no_update:noUpdate}}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/inspector-context.js','utf8'),context);
 const summarize=context.window.dash_clientside.inspectorContext.summarize;
 const figure={data:[{type:'scatter',name:'Sample · 250 nm',meta:{file_id:'channel',pda_preview:true,pda_source_id:'primary'},
 x:Array(3000).fill(1),y:Array(3000).fill(2),customdata:Array(3000).fill('long'),
 line:{color:'#112233',width:2,dash:'dot'},marker:{color:'#445566',size:Array(3000).fill(6)},opacity:.5},
 {name:'peak:one',fill:'toself',x:[1,2],y:[1,2]}],layout:{xaxis:{title:{text:'Time (min)'}},
 yaxis:{title:{text:'Absorbance (mAU)'}},meta:{gecko_tab_id:'raw',gecko_axis_units:{xaxis:'Time (min)'}},
 shapes:[{path:'large geometry'}],template:{data:{}}}};
 const result=summarize(figure,null);
 assert.equal(result.data[0].meta.file_id,'channel');
 assert.equal(result.data[0].meta.pda_preview,true);
 assert.equal(result.data[0].meta.pda_source_id,'primary');
 assert.equal(result.data[0].line.dash,'dot');
 assert.equal(result.data[1].fill,'toself');
 assert.equal(result.layout.xaxis.title.text,'Time (min)');
 assert.equal(result.layout.meta.gecko_tab_id,'raw');
 assert.equal(result.data[0].x,undefined);assert.equal(result.data[0].customdata,undefined);
 assert.equal(result.data[0].marker.size,undefined);assert.equal(result.layout.shapes,undefined);
 assert.ok(JSON.stringify(result).length<1000);
 figure.data[0].y[0]=4;
 assert.equal(summarize(figure,result),noUpdate);
 figure.data[0].name='Renamed · 250 nm';
 assert.equal(summarize(figure,result).data[0].name,'Renamed · 250 nm');
});
