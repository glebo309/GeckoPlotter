const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');
const window={localStorage:{getItem:()=>null,setItem(){}},addEventListener(){}};
vm.runInNewContext(fs.readFileSync('src/assets/js/auto-integrate.js','utf8'),{window,document:{},atob:s=>Buffer.from(s,'base64').toString('binary'),
  Float64Array,Float32Array,Int32Array,Int16Array,Int8Array,Uint32Array,Uint16Array,Uint8Array,ArrayBuffer,Math,Number,Infinity,isFinite});
const {nearPeak,asArray}=window.GeckoAutoIntegrate;

function chromatogram(){
  const xs=[],ys=[];
  for(let i=0;i<2000;i++){const x=i*0.005;xs.push(x);ys.push(100*Math.exp(-(((x-5)/0.08)**2))+0.3*Math.sin(i));}
  return {xs,ys};
}
const {xs,ys}=chromatogram();   // one peak at 5 min, height 100, noise 0.3; visible y span 110
const span=110, tol=span*14/400;

test('on the flank and the top of a peak counts as near',()=>{
  assert.equal(nearPeak(xs,ys,5.0,60,span,tol,0.04,0.03),true);       // inside the peak
  assert.equal(nearPeak(xs,ys,5.1,15,span,tol,0.04,0.03),true);       // under the flank (curve is ~21 there)
  assert.equal(nearPeak(xs,ys,5.1,40,span,tol,0.04,0.03),false);      // well above the flank
  assert.equal(nearPeak(xs,ys,5.0,100+tol*0.5,span,tol,0.04,0.03),true); // just above the apex
});
test('flat baseline and far above the peak are not near',()=>{
  assert.equal(nearPeak(xs,ys,2.0,0.2,span,tol,0.04,0.03),false);     // baseline far from the peak
  assert.equal(nearPeak(xs,ys,5.0,100+tol*3,span,tol,0.04,0.03),false); // well above the apex
  assert.equal(nearPeak(xs,ys,8.0,50,span,tol,0.04,0.03),false);      // empty space on a quiet stretch
});
test('tiny bumps below the prominence limit do not trigger',()=>{
  const flat=xs.map((x,i)=>0.4*Math.sin(i));
  assert.equal(nearPeak(xs,flat,5.0,0.1,span,tol,0.04,0.03),false);
});
test('too few points or a zero span never trigger',()=>{
  assert.equal(nearPeak([1,2,3],[1,5,1],2,3,10,1,0.04,0.03),false);
  assert.equal(nearPeak(xs,ys,5,50,0,tol,0.04,0.03),false);
});
test('numpy style {dtype,bdata} arrays are decoded',()=>{
  const buf=Buffer.from(new Float64Array([1.5,2.5,3.5]).buffer).toString('base64');
  assert.deepEqual(Array.from(asArray({dtype:'f8',bdata:buf})),[1.5,2.5,3.5]);
  assert.deepEqual(Array.from(asArray([1,2])),[1,2]);
  assert.equal(asArray(null),null);
});
