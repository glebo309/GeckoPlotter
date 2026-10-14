const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');

function load(buttons){
  const listeners={};
  const document={addEventListener(type,fn){listeners[type]=fn;},getElementById(id){return buttons[id]||null;}};
  const window={};
  vm.runInNewContext(fs.readFileSync('src/assets/js/enter-submit.js','utf8'),{document,window});
  return {press:(target,extra)=>{const e=Object.assign({key:'Enter',target,prevented:false,stopped:false,
    preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}},extra||{});listeners.keydown(e);return e;},window};
}
const field=(id,attrs)=>({tagName:'INPUT',id,closest:()=>null,getAttribute:n=>(attrs||{})[n]||null});
const button=()=>({disabled:false,clicks:0,click(){this.clicks++;},hasAttribute:()=>false});

test('Enter in the m/z or tolerance field presses Extract',()=>{
  const extract=button();const {press}=load({'eic-extract-btn':extract});
  assert.equal(press(field('eic-mz-input')).prevented,true);
  press(field('eic-tolerance-input'));
  assert.equal(extract.clicks,2);
});

test('the rename, project name, folder and group label fields press their own button',()=>{
  const save=button(),name=button(),retry=button(),apply=button();
  const {press}=load({'ctx-rename-save':save,'session-name-confirm':name,'session-retry-btn':retry,'apply-group-btn':apply});
  press(field('ctx-rename-input'));press(field('session-name-input'));press(field('session-search-dir'));press(field('group-label-input'));
  assert.deepEqual([save.clicks,name.clicks,retry.clicks,apply.clicks],[1,1,1,1]);
});

test('any field can opt in with data-enter-button',()=>{
  const go=button();const {press}=load({go});
  press(field('anything',{'data-enter-button':'go'}));
  assert.equal(go.clicks,1);
});

test('modifier keys, other keys, other fields, table cells and disabled buttons do nothing',()=>{
  const extract=button();const {press}=load({'eic-extract-btn':extract});
  press(field('eic-mz-input'),{shiftKey:true});press(field('eic-mz-input'),{metaKey:true});
  press(field('eic-mz-input'),{key:'a'});press(field('other-input'));
  press(Object.assign(field('eic-mz-input'),{closest:()=>({})}));
  extract.disabled=true;press(field('eic-mz-input'));
  assert.equal(extract.clicks,0);
  assert.equal(press({tagName:'TEXTAREA',id:'eic-mz-input'}).prevented,false);
});
