const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('publication snapshots and SVG export use the clicked figure, including its current zoom', () => {
    const props = [], downloads = [];
    const gd = {data:[{x:[100,200],y:[30,100],name:'Peak mass'}],
        layout:{xaxis:{range:[100,200]}},getBoundingClientRect:()=>({width:900,height:500})};
    const window = {dash_clientside:{set_props:(id,value)=>props.push([id,value])},
        Plotly:{downloadImage:(graph,options)=>downloads.push([graph,options])}};
    const document = {addEventListener(){},getElementById:()=>null};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/figure-actions.js'),'utf8'),
        {window,document,ArrayBuffer,Date,JSON});
    window.GeckoFigureActions.run('publication',gd);
    const event = props.find(p=>p[0]==='figure-action-event')[1].data;
    assert.deepEqual(Array.from(event.figure.layout.xaxis.range),[100,200]);
    assert.equal(event.figure.data[0].name,'Peak mass');
    window.GeckoFigureActions.run('export',gd);
    assert.equal(downloads[0][0],gd);
    assert.equal(downloads[0][1].format,'svg');
});

test('a Dash menu-item click dispatches publication using the right-clicked overlay', () => {
    const props = [], listeners = [];
    const gd = {data:[{name:'TIC',x:[0,1],y:[0,5e6],yaxis:'y'},
                      {name:'UV',x:[0,1],y:[0,250],yaxis:'y2'}],
                layout:{yaxis2:{overlaying:'y'}}};
    const window = {Plotly:{},dash_clientside:{no_update:{},
        callback_context:{triggered:[{prop_id:JSON.stringify({type:'figure-action',context:'figure',action:'publication'})+'.n_clicks',value:1}]},
        set_props:(id,value)=>props.push([id,value])}};
    const document = {addEventListener:(name,fn,capture)=>listeners.push({name,fn,capture}),getElementById:()=>null};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/figure-actions.js'),'utf8'),
        {window,document,ArrayBuffer,Date,JSON});
    listeners.find(l=>l.name==='contextmenu' && l.capture).fn({target:{closest:()=>gd}});
    window.dash_clientside.geckoFigureActions.dispatch([1]);
    const event = props.find(p=>p[0]==='figure-action-event')[1].data;
    assert.equal(event.figure.data.length,2);
    assert.equal(event.figure.layout.yaxis2.overlaying,'y');
});

test('the plain figure menu opens even when zoom/integration already prevented the native menu', () => {
    const props = [], listeners = [];
    const gd = {data:[],layout:{}};
    const window = {innerWidth:1200,innerHeight:800,Plotly:{},
        dash_clientside:{set_props:(id,value)=>props.push([id,value])}};
    const document = {addEventListener:(name,fn,capture)=>listeners.push({name,fn,capture}),getElementById:()=>null};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/figure-actions.js'),'utf8'),
        {window,document,ArrayBuffer,Date,JSON});
    listeners.find(l=>l.name==='contextmenu' && !l.capture).fn({defaultPrevented:true,
        target:{closest:()=>gd},clientX:400,clientY:300,preventDefault(){}});
    assert.ok(props.some(p=>p[0]==='figure-context-menu' && p[1].opened));
});

test('publication is captured before the menu auto-closes and unmounts its Dash input', () => {
    const props = [], listeners = [];
    const gd = {data:[{name:'UV',x:[0,1],y:[0,250]}],layout:{yaxis:{title:{text:'Absorbance (mAU)'}}}};
    const window = {Plotly:{},dash_clientside:{set_props:(id,value)=>props.push([id,value])}};
    const document = {addEventListener:(name,fn,capture)=>listeners.push({name,fn,capture}),getElementById:()=>null};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../src/assets/js/figure-actions.js'),'utf8'),
        {window,document,ArrayBuffer,Date,JSON});
    listeners.find(l=>l.name==='contextmenu' && l.capture).fn({target:{closest:()=>gd}});
    const click = listeners.find(l=>l.name==='click' && l.capture);
    assert.ok(click, 'handle the action before Mantine removes the clicked menu item');
    let stopped = false;
    click.fn({target:{closest:()=>({getAttribute:()=> 'publication'})},preventDefault(){},stopPropagation(){stopped=true;}});
    assert.equal(props.filter(p=>p[0]==='figure-action-event').length,1);
    assert.equal(props.find(p=>p[0]==='figure-action-event')[1].data.figure.data[0].name,'UV');
    assert.ok(stopped, 'avoid dispatching the same action a second time through Dash');
});
