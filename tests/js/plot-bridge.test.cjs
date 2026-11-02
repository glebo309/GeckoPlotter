const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
test('the callback bridge never draws or copies the figure',()=>{
 const window={React:{createElement:(type,props)=>({type,props})},Plotly:new Proxy({}, {get(){throw Error('Hidden graph rendered');}})};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/plot-bridge.js'),'utf8'),{window});
 const figure=new Proxy({}, {get(){throw Error('Traversed the figure');}});
 const result=window.gecko_plot_bridge.PlotBridge({id:'main-plot',figure,clickData:{},relayoutData:{}});
 assert.equal(result.type,'div');assert.equal(result.props.id,'main-plot');assert.equal(result.props.style.display,'none');
});
