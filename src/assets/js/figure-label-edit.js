// Edit the live plot's text in place, including a scaled paper/slide preview.
(function () {
    'use strict';
    var editing = null;
    function targetAtEvent(gd, event) {
        if (!gd || !event || !event.target) return null;
        var element = event.target;
        while (element && String(element.tagName).toLowerCase() === 'tspan') element = element.parentElement;
        if (!element || String(element.tagName).toLowerCase() !== 'text' || !gd.contains(element)) return null;
        var classes = (element.getAttribute('class') || '').split(/\s+/);
        for (var i=0;i<classes.length;i++) {
            if (classes[i] === 'gtitle') return {field:'title',element:element};
            var match = classes[i].match(/^([xy])(\d*)title$/);
            if (match) return {field:match[1]+'axis'+match[2],element:element};
        }
        // Shared publication Y titles are Plotly annotations.
        if (classes.indexOf('annotation-text') !== -1 && element.closest) {
            var group = element.closest('.annotation'), index = group && Number(group.getAttribute('data-index'));
            var annotation = gd.layout && gd.layout.annotations && gd.layout.annotations[index];
            if (annotation && annotation.name === 'gecko-shared-y') {
                var remembered=(gd.layout.meta || {}).gecko_axis_identities || {};
                var units=(gd.layout.meta || {}).gecko_axis_units || {};
                var axis = Object.keys(gd.layout).find(function(key){
                    return /^yaxis\d*$/.test(key) && ((gd.layout[key].title || {}).text === annotation.text ||
                        units[key]===annotation.text || (remembered[key] || {}).label===annotation.text);
                });
                if (!axis) axis=Object.keys(gd.layout).find(function(key){
                    var domain=(gd.layout[key] || {}).domain;
                    return /^yaxis\d*$/.test(key) && domain && annotation.y>=domain[0] && annotation.y<=domain[1];
                });
                return {field:axis || 'yaxis',element:element,annotationIndex:index,text:annotation.text};
            }
        }
        return null;
    }
    function cancel() {
        if (!editing) return;
        var old=editing; editing=null; old.input.remove();
    }
    function begin(gd, hit) {
        cancel();
        var layout=gd.layout || {}, meta=layout.meta || {};
        if (!meta.gecko_tab_id) return null;
        var title=hit.field==='title' ? layout.title : (layout[hit.field] || {}).title;
        var value=typeof title==='string' ? title : title && title.text || '';
        if (hit.annotationIndex!==undefined) value=hit.text;
        if (hit.field==='title') value=value.replace(/^<b>([\s\S]*)<\/b>$/, '$1');
        var input=document.createElement('input'), rect=hit.element.getBoundingClientRect();
        input.type='text';input.value=value;input.className='figure-label-editor';
        input.setAttribute('aria-label',hit.field==='title'?'Edit plot title':'Edit axis label');
        input.setAttribute('title','Enter to apply · Esc to cancel');
        var width=Math.min(420,Math.max(190,rect.width+40));
        Object.assign(input.style,{position:'fixed',left:Math.max(8,Math.min(rect.left,window.innerWidth-width-8))+'px',
            top:Math.max(8,Math.min(rect.top-6,window.innerHeight-44))+'px',width:width+'px',zIndex:5000});
        var session={gd:gd,input:input,hit:hit,value:value,tab:meta.gecko_tab_id};editing=session;
        function commit() {
            if (editing!==session) return;
            var text=input.value;cancel();
            if (text===value || gd.style.display==='none' || !gd.getBoundingClientRect().width) return;
            var current=gd.layout || {}, captured={meta:current.meta || {}};
            Object.keys(current).forEach(function(key){
                if (/^[xy]axis\d*$/.test(key)) captured[key]={title:current[key].title,visible:current[key].visible};
            });
            window.dash_clientside.set_props('figure-label-edit',{data:{
                tab:session.tab,field:hit.field,text:text,layout:captured,ts:Date.now()}});
            var update={};
            var property=hit.annotationIndex!==undefined ? 'annotations['+hit.annotationIndex+'].text' :
                hit.field==='title'?'title.text':hit.field+'.title.text';
            update[property]=text;
            window.Plotly.relayout(gd,update);
        }
        input.addEventListener('keydown',function(event){
            event.stopPropagation();
            if(event.key==='Enter'){event.preventDefault();commit();}
            else if(event.key==='Escape'){event.preventDefault();cancel();}
        });
        input.addEventListener('blur',commit);
        document.body.appendChild(input);input.focus();input.select();return input;
    }
    function handle(event) {
        var gd=event.target && event.target.closest && event.target.closest('.js-plotly-plot');
        var hit=targetAtEvent(gd,event);
        if (!hit || !(gd.layout && gd.layout.meta && gd.layout.meta.gecko_tab_id)) return;
        // Keep Plotly's plot/axis double-click reset away from editable text.
        event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
        if(event.type==='dblclick') begin(gd,hit);
    }
    ['pointerdown','mousedown','dblclick'].forEach(function(name){document.addEventListener(name,handle,true);});
    document.addEventListener('gecko:plot-leave',cancel);
    document.addEventListener('keydown',function(event){if(event.key==='Escape')cancel();},true);
    window.GeckoFigureLabels={targetAtEvent:targetAtEvent,begin:begin,cancel:cancel};
})();
