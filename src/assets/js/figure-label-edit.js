// Edit the live plot's text in place, including a scaled paper/slide preview.
(function () {
    'use strict';
    var editing = null, enabled = false;
    function setEnabled(value) {
        enabled = !!value; cancel();
        document.body.classList.toggle('gecko-text-edit-mode', enabled);
        var button=document.getElementById('plot-tool-edit-text');
        if(button){button.classList.toggle('active',enabled);button.setAttribute('aria-pressed',String(enabled));}
        if(enabled && window.dash_clientside){
            window.dash_clientside.set_props('baseline-mode',{data:'navigate'});
            window.dash_clientside.set_props('selected-peak-idx',{data:null});
            if(window.GeckoPlotterManualIntegration) window.GeckoPlotterManualIntegration.syncDrawMode('main-plot','navigate');
        }
    }
    function targetAtEvent(gd, event) {
        if (!gd || !event || !event.target) return null;
        var element = event.target;
        var legend=element.closest && element.closest('g.traces');
        if(legend && legend.querySelector && legend.querySelector('.legendtext')) {
            var datum=legend.__data__, item=Array.isArray(datum)?datum[0]:datum;
            var trace=item && (item.trace || item), meta=trace && trace.meta;
            if(meta && meta.file_id) {
                var name=trace.name || '', suffix=meta.y_column ? ' — '+meta.y_column : '';
                if(suffix && name.endsWith(suffix)) name=name.slice(0,-suffix.length);
                return {field:'dataset',fileId:meta.rename_file_id || meta.file_id,value:meta.rename_label || name,element:legend.querySelector('.legendtext')};
            }
        }
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
            if (annotation && (annotation.name === 'gecko-shared-y' || annotation.name === 'gecko-live-shared-y')) {
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
        var layout=gd && gd.layout || {}, meta=layout.meta || {};
        if (!hit.fileId && !meta.gecko_tab_id) return null;
        var title=hit.field==='title' ? layout.title : (layout[hit.field] || {}).title;
        var value=typeof title==='string' ? title : title && title.text || '';
        if (hit.annotationIndex!==undefined) value=hit.text;
        if (hit.fileId) value=hit.value;
        if (hit.field==='title') value=value.replace(/^<b>([\s\S]*)<\/b>$/, '$1');
        var input=document.createElement('input'), rect=hit.element.getBoundingClientRect();
        input.type='text';input.value=value;input.className='figure-label-editor';
        input.setAttribute('aria-label',hit.fileId?'Edit dataset name':hit.field==='title'?'Edit plot title':'Edit axis label');
        input.setAttribute('title','Enter to apply · Esc to cancel');
        var width=Math.min(420,Math.max(190,rect.width+40));
        Object.assign(input.style,{position:'fixed',left:Math.max(8,Math.min(rect.left,window.innerWidth-width-8))+'px',
            top:Math.max(8,Math.min(rect.top-6,window.innerHeight-44))+'px',width:width+'px',zIndex:5000});
        var session={gd:gd,input:input,hit:hit,value:value,tab:meta.gecko_tab_id};editing=session;
        function commit() {
            if (editing!==session) return;
            var text=input.value;cancel();
            if(hit.fileId){
                if(text.trim() && text.trim()!==value) window.dash_clientside.set_props('dataset-name-edit',{data:{file_id:hit.fileId,text:text.trim(),ts:Date.now()}});
                return;
            }
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
        if(event.target.closest && event.target.closest('.figure-label-editor')) return;
        var tool=event.target.closest && event.target.closest('#plot-tool-edit-text');
        if(tool){if(event.type==='click')setEnabled(!enabled);return;}
        if(event.type==='click' && event.target.closest && event.target.closest('#plot-tool-integrate')) setEnabled(false);
        var label=event.target.closest && event.target.closest('.dataset-name');
        var gd=event.target.closest && event.target.closest('.js-plotly-plot');
        var hit=label ? {field:'dataset',fileId:label.dataset.fileId,value:label.textContent,element:label} : targetAtEvent(gd,event);
        if(!hit) return;
        if(!enabled && (hit.fileId || event.type==='click')) return;
        if(!hit.fileId && !(gd.layout && gd.layout.meta && gd.layout.meta.gecko_tab_id)) return;
        event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
        if((enabled && event.type==='click') || event.type==='dblclick') begin(gd,hit);
    }
    ['pointerdown','mousedown','click','dblclick'].forEach(function(name){document.addEventListener(name,handle,true);});
    document.addEventListener('gecko:plot-leave',cancel);
    document.addEventListener('keydown',function(event){if(event.key==='Escape'){if(editing)cancel();else setEnabled(false);}},true);
    window.GeckoFigureLabels={targetAtEvent:targetAtEvent,begin:begin,cancel:cancel,setEnabled:setEnabled};
})();
