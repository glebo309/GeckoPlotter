const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function setup(label='Area (mAU·min)') {
    const events={}, sent=[];
    class Element {
        constructor(tag) {this.tag=tag;this.children=[];this.style={};this.attrs={};this.listeners={};this.textContent='';}
        appendChild(c){this.children.push(c);c.parent=this;return c;}
        setAttribute(k,v){this.attrs[k]=v;}
        getAttribute(k){return this.attrs[k];}
        addEventListener(k,f){this.listeners[k]=f;}
        remove(){if(this.parent)this.parent.children=this.parent.children.filter(c=>c!==this);}
        contains(c){return c===this || this.children.some(x=>x.contains(c));}
        querySelector(){return this.children.find(c=>c.className==='area-units-button') || null;}
        focus(){this.focused=true;}
        getBoundingClientRect(){return {left:100,bottom:130};}
        get offsetWidth(){return 230;}
        get offsetHeight(){return 180;}
    }
    const body=new Element('body'), header=new Element('th');header.textContent=label;
    header.closest=selector=>selector==='#peak-table' ? {} : header;
    const document={body,addEventListener(k,f){events[k]=f;},
        querySelectorAll(){return [header];},createElement(tag){return new Element(tag);}};
    const window={innerWidth:1000,innerHeight:800,requestAnimationFrame:f=>f(),
        dash_clientside:{set_props(id,value){sent.push([id,value]);}}};
    class MutationObserver {constructor(f){this.fn=f;}observe(){}}
    vm.runInNewContext(fs.readFileSync('src/assets/js/area-units-menu.js','utf8'),{document,window,MutationObserver});
    const open=()=>events.contextmenu({target:header,clientX:100,clientY:100,preventDefault(){},stopPropagation(){}});
    return {body,header,events,sent,open};
}

test('right-click exposes units and choosing Shimadzu units updates the display preference',()=>{
    const s=setup();s.open();
    const menu=s.body.children[0];
    const choices=menu.children.filter(c=>c.attrs.role==='menuitemradio');
    assert.equal(choices.length,3);
    assert.equal(choices[0].attrs['aria-checked'],'true');
    choices.find(c=>c.textContent.includes('µAU·s')).listeners.click();
    assert.deepEqual(JSON.parse(JSON.stringify(s.sent)),[['area-display-unit',{data:'µAU·s'}]]);
    assert.equal(s.body.children.length,0);
});

test('header button opens the same menu and Escape closes it',()=>{
    const s=setup();const button=s.header.children[0];
    assert.equal(button.attrs['aria-label'],'Area units');
    button.listeners.click({preventDefault(){},stopPropagation(){}});
    assert.equal(s.body.children.length,1);
    s.events.keydown({key:'Escape',preventDefault(){}});
    assert.equal(s.body.children.length,0);
});

test('unknown detector units never offer absorbance conversion',()=>{
    const s=setup('Area');s.open();
    assert.equal(s.header.children.length,0);
    assert.equal(s.body.children.length,0);
});
