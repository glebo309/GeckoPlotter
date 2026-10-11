const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('all open plot menus dismiss on an outside click or Escape regardless of portal placement', () => {
    const listeners = {}, props = [];
    const document = {addEventListener:(name,fn)=>listeners[name]=fn,
        getElementById(id) {return id.endsWith('dropdown') ? {offsetParent:{},contains:t=>t==='inside'} : null;},
        querySelector:()=>null};
    const window = {dash_clientside:{set_props:(id,value)=>props.push([id,value])}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/context-menu-dismiss.js'),'utf8'),
        {window,document,Date});
    listeners.pointerdown({target:'inside'});
    assert.equal(props.length,0);
    listeners.pointerdown({target:'outside'});
    for (const id of ['context-menu','ms-plot-context-menu']) {
        assert.ok(props.some(p=>p[0]===id && p[1].opened===false));
    }
    props.length=0;
    listeners.keydown({key:'Escape'});
    assert.ok(props.some(p=>p[0]==='context-menu' && p[1].opened===false));
});
