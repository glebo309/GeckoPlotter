const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('diagnostic clicks and errors never include input values or error messages', () => {
    const events = {}, sent = [];
    const window = {fetch: (url, options) => {sent.push(JSON.parse(options.body)); return Promise.resolve({});},
        addEventListener: (name, fn) => events[name] = fn};
    const document = {addEventListener: (name, fn) => events[name] = fn};
    vm.runInNewContext(fs.readFileSync('src/assets/js/diagnostics.js','utf8'), {window,document,Date,JSON});
    events.click({target:{closest:()=>({id:'session-name-confirm',value:'SECRET',textContent:'SECRET'})}});
    events.error({message:'SECRET data failed',error:{name:'TypeError',message:'SECRET'}});
    assert.ok(sent.some(e=>e.control==='session-name-confirm' && e.action==='click'));
    assert.ok(sent.some(e=>e.event==='client_error' && e.error_type==='TypeError'));
    assert.ok(!JSON.stringify(sent).includes('SECRET'));
});
