const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(heat){
 const events={},sent=[],overlay={style:{},parentElement:{getBoundingClientRect:()=>({left:10,top:30})}};
 const axis={_offset:50,_length:500,d2p:t=>(t-4)*250,p2d:p=>4+p/250};
 const gd={data:[{meta:{file_id:'other'}},{meta:{file_id:'owner'},xaxis:'x2',yaxis:'y2'}],style:{},
  _fullLayout:{width:600,height:500,xaxis:axis,yaxis:{_offset:20,_length:180},xaxis2:axis,yaxis2:{_offset:250,_length:180}},
  getBoundingClientRect:()=>({left:10,top:30,width:600,height:500}),addEventListener:(n,f)=>events[n]=f,on(n,f){(this.handlers=this.handlers||{})[n]=f;}};
 const document={body:{style:{}},readyState:'complete',addEventListener:(n,f)=>events['doc-'+n]=f,getElementById:id=>id==='pda-scan-cursor-overlay'?overlay:id==='pda-heatmap'&&heat?{querySelector:()=>heat}:null};
 const window={Plotly:{relayout:(g,u)=>g.relayouts.push(u)},geckoActivePlot:()=>gd,addEventListener(){},requestAnimationFrame:f=>{f();return 0;},dash_clientside:{set_props:(id,p)=>sent.push([id,p])}};
 vm.runInNewContext(fs.readFileSync('src/assets/js/pda-scan-cursor.js','utf8'),{window,document,MutationObserver:class{observe(){}},setTimeout:f=>f()});
 window.GeckoPdaScanCursor.setState({owner_id:'owner',source_id:'source',time_min:5,time_minimum:0,time_maximum:10});
 return {window,gd,events,overlay,sent};
}
test('PDA cursor maps measured time through zoomed source axes and source subplot',()=>{
 const {window,overlay}=setup();const c=window.GeckoPdaScanCursor;
 assert.equal(c.timeToX(5),310);assert.equal(c.xToTime(185),4.5);
 assert.equal(overlay.style.top,'250px');assert.equal(overlay.style.height,'180px');
 assert.equal(c.xToTime(-500),4);assert.equal(c.xToTime(900),6);
});
test('PDA drag stays horizontal, clamps visible/time bounds and sends source identity',()=>{
 const {events,sent,overlay}=setup();const event=(x,y)=>({clientX:x,clientY:y,button:0,detail:1,preventDefault(){},stopImmediatePropagation(){}});
 events.mousedown(event(310,300));events['doc-mousemove'](event(999,-800));events['doc-mouseup']({});
 const last=sent.at(-1);assert.equal(last[0],'pda-cursor-event');assert.equal(last[1].data.time_min,6);assert.equal(last[1].data.source_id,'source');
 assert.equal(overlay.style.top,'250px');assert.equal(overlay.style.height,'180px');
});
test('ordinary zoom gestures and double click pass through unchanged',()=>{
 const {events,sent}=setup();let prevented=false;const e={clientX:100,clientY:300,button:0,detail:1,preventDefault(){prevented=true;},stopImmediatePropagation(){}};
 events.mousedown(e);assert.equal(prevented,false);assert.equal(sent.length,0);
 events.mousedown({...e,clientX:310,detail:2});assert.equal(prevented,false);assert.equal(sent.length,0);
 assert.equal(events.dblclick,undefined);
});
test('hidden source cannot attach cursor to another trace, preview retains its owner',()=>{
 const {window,gd}=setup();gd.data[1].visible='legendonly';assert.equal(window.GeckoPdaScanCursor.plotRect(),null);
 delete gd.data[1].visible;gd.data[1].meta={pda_preview:true,pda_owner_id:'owner'};
 assert.equal(window.GeckoPdaScanCursor.plotRect().top,280);
});

test('rapid drag moves line immediately but throttles callback requests and flushes release',()=>{
 const {events,sent,overlay}=setup();const e=x=>({clientX:x,clientY:300,button:0,detail:1,preventDefault(){},stopImmediatePropagation(){}});
 events.mousedown(e(310));
 for(let x=311;x<400;x++)events['doc-mousemove'](e(x));
 assert.equal(sent.length,1);assert.equal(overlay.style.left,'389px');
 events['doc-mouseup']({});assert.equal(sent.length,2);assert.equal(sent[1][1].data.time_min,5.356);
});

test('heatmap time axis follows the main figure zoom without redundant relayouts',()=>{
 const heat={relayouts:[],on(){},_fullLayout:{xaxis:{range:[0,10]}}},{gd,window}=setup(heat);
 gd._fullLayout.xaxis2.range=[4.5,6];window.GeckoPdaScanCursor.followMainZoom();
 assert.equal(JSON.stringify(heat.relayouts),JSON.stringify([{'xaxis.range':[4.5,6]}]));
 heat._fullLayout.xaxis.range=[4.5,6];window.GeckoPdaScanCursor.followMainZoom();
 assert.equal(heat.relayouts.length,1);
 heat._fullLayout.xaxis.range=[5,5.5];window.GeckoPdaScanCursor.followMainZoom();
 assert.equal(heat.relayouts.length,1);
});

test('a heatmap preview time survives redraws until the server state arrives',()=>{
 const {window,overlay,gd}=setup();const c=window.GeckoPdaScanCursor;
 c.preview(4.5);
 const placed=overlay.style.left;
 c.sync();                         // a redraw (afterplot/relayout) re-places the cursor
 assert.equal(overlay.style.left,placed);
 c.setState({owner_id:'owner',source_id:'source',time_min:6,time_minimum:0,time_maximum:10});
 c.sync();
 assert.notEqual(overlay.style.left,placed);   // server state wins again
});

test('a redraw never changes the heatmap zoom; only a zoom of the main figure does',()=>{
 const heat={relayouts:[],on(){},_fullLayout:{xaxis:{range:[0,10]}}},{gd,window}=setup(heat);
 gd._fullLayout.xaxis2.range=[4.5,6];
 window.GeckoPdaScanCursor.sync();                       // afterplot-style redraw
 assert.equal(heat.relayouts.length,0);
 gd.handlers.plotly_relayout({'yaxis2.range[0]':1});      // y-only relayout: still no follow
 window.GeckoPdaScanCursor.sync();
 assert.equal(heat.relayouts.length,0);
 gd.handlers.plotly_relayout({'xaxis2.range[0]':4.5,'xaxis2.range[1]':6});   // the user zoomed the main plot
 window.GeckoPdaScanCursor.sync();
 assert.equal(heat.relayouts.length,1);
});

test('install() is a no-op once the plot and heatmap are bound, and without PDA state',()=>{
 const heat={on(){},_fullLayout:{xaxis:{range:[0,10]}}},{window,gd}=setup(heat);
 let frames=0,rects=0;const raf=window.requestAnimationFrame;
 window.requestAnimationFrame=f=>{frames++;return raf(f);};
 const rect=gd.getBoundingClientRect;gd.getBoundingClientRect=()=>{rects++;return rect();};
 window.GeckoPdaScanCursor.install();window.GeckoPdaScanCursor.install();
 assert.equal(frames,0);assert.equal(rects,0);
 window.GeckoPdaScanCursor.setState(null);                 // no state: nothing to track
 frames=0;rects=0;window.GeckoPdaScanCursor.install();
 assert.equal(frames,0);assert.equal(rects,0);
});
