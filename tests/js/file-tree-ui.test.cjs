const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('keyboard activation selects a file row without handling eye or delete buttons', () => {
    const events = {};
    const context = {window: {}, Set, document: {
        body: {}, querySelectorAll: () => [], getElementById: () => null,
        addEventListener: (event, listener) => events[event] = listener,
    }, MutationObserver: class {observe() {}},};
    vm.runInNewContext(fs.readFileSync('src/assets/js/file-tree-ui.js', 'utf8'), context);
    assert.equal(typeof events.keydown, 'function');
    let clicked = 0, prevented = 0;
    const row = {click: () => clicked++};
    const target = {closest: selector => selector === '.file-tree-item' ? row : null};
    events.keydown({key: 'Enter', target, preventDefault: () => prevented++});
    events.keydown({key: ' ', target, preventDefault: () => prevented++});
    events.keydown({key: 'Enter', target: {closest: () => null}});
    assert.equal(clicked, 2);
    assert.equal(prevented, 2);
});

test('group headings are keyboard disclosures and leave their sort button independent', () => {
    const events = {}, headerEvents = {}, attributes = {};
    const container = {id: '{"type":"file-group","index":"tab-lcms"}',style:{},classList:{contains:()=>true}};
    const indicator = {};
    const header = {tagName:'DIV',style:{},nextElementSibling:container,
        querySelector:()=>indicator,closest:()=>null,
        setAttribute:(key,value)=>attributes[key]=value,
        addEventListener:(event,listener)=>headerEvents[event]=listener,
        click:()=>headerEvents.click({target:header})};
    const context = {window:{},Set,document:{body:{},getElementById:()=>null,
        querySelectorAll:selector=>selector==='.file-group-header'?[header]:[],
        addEventListener:(event,listener)=>events[event]=listener},
        MutationObserver:class{observe(){}}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/file-tree-ui.js','utf8'),context);
    events.DOMContentLoaded();
    assert.equal(attributes.role,'button');
    assert.equal(attributes.tabindex,'0');
    assert.equal(attributes['aria-expanded'],'true');
    let prevented=0;
    headerEvents.keydown({key:'Enter',target:header,preventDefault:()=>prevented++});
    assert.equal(container.style.display,'none');
    assert.equal(attributes['aria-expanded'],'false');
    headerEvents.keydown({key:' ',target:header,preventDefault:()=>prevented++});
    assert.equal(container.style.display,'');
    assert.equal(attributes['aria-expanded'],'true');
    headerEvents.keydown({key:' ',target:{tagName:'BUTTON'},preventDefault:()=>prevented++});
    assert.equal(container.style.display,'');
    assert.equal(prevented,2);
});

test('sample visibility does not overwrite the server channel choice', () => {
    const attrs = {'aria-checked':'true','data-channel-sources':'["a250","b250"]','data-channel-label':'250 nm'};
    const mark = {textContent:'✓'};
    const button = {getAttribute:key=>attrs[key],setAttribute:(key,value)=>attrs[key]=value,
        querySelector:()=>mark,title:''};
    const context = {window:{},Set,document:{body:{},getElementById:()=>null,
        querySelectorAll:selector=>selector==='.group-channel-toggle'?[button]:[],
        addEventListener:()=>{}},MutationObserver:class{observe(){}}};
    vm.runInNewContext(fs.readFileSync('src/assets/js/file-tree-ui.js','utf8'),context);
    context.window._geckoApplyHiddenFiles(['a250']);
    assert.equal(attrs['aria-checked'],'true');
    assert.equal(mark.textContent,'✓');
    context.window._geckoApplyHiddenFiles(['a250','b250']);
    assert.equal(attrs['aria-checked'],'true');
    context.window._geckoApplyHiddenFiles([]);
    assert.equal(attrs['aria-checked'],'true');
});
