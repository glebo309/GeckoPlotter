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
    // A peak's name above it in the plot (a text trace of peak_overlay.add_peak_traces, carrying the peak id). Plotly's
    // drag layer lies over the traces and draws these unclipped names in a layer of their own, so the name is found by
    // its text and position.
    function axisPoint(gd, xref, yref, x, y) {
        var box = gd.getBoundingClientRect(), fl = gd._fullLayout;
        var xa = fl[(xref || 'x').replace(/^x/, 'xaxis')], ya = fl[(yref || 'y').replace(/^y/, 'yaxis')];
        if (!xa || !ya || typeof xa.l2p !== 'function' || typeof ya.l2p !== 'function') return null;
        return {x: box.left + xa._offset + xa.l2p(Number(x)), y: box.top + ya._offset + ya.l2p(Number(y))};
    }
    // Plot units per screen pixel of a subplot (x right, y up): a dragged name is saved in plot units.
    function unitsPerPixel(gd, xref, yref) {
        var fl = gd._fullLayout, xa = fl[(xref || 'x').replace(/^x/, 'xaxis')], ya = fl[(yref || 'y').replace(/^y/, 'yaxis')];
        if (!xa || !ya || typeof xa.p2l !== 'function' || typeof ya.p2l !== 'function') return null;
        return [xa.p2l(1) - xa.p2l(0), ya.p2l(0) - ya.p2l(1)];
    }
    // Where a moved name sits from its peak, in screen pixels (dx right, dy up), and whether its line shows.
    function labelOffset(gd, a) {
        if (a.axref && a.axref !== 'pixel') {
            var fl = gd._fullLayout, xa = fl[a.xref.replace(/^x/, 'xaxis')], ya = fl[a.yref.replace(/^y/, 'yaxis')];
            return [xa.l2p(Number(a.ax)) - xa.l2p(Number(a.x)), ya.l2p(Number(a.y)) - ya.l2p(Number(a.ay))];
        }
        return a.showarrow ? [a.ax || 0, -(a.ay || 0)] : [a.xshift || 0, a.yshift || 0];
    }
    function labelLeader(a) { return !!a.showarrow && a.arrowcolor !== 'rgba(0,0,0,0)'; }
    // A label dragged away from its peak is an annotation named 'peak-label:<id>' (peak_overlay._add_moved_label).
    function movedPeakLabelAt(gd, event) {
        var annotations = (gd._fullLayout && gd._fullLayout.annotations) || [];
        for (var i = 0; i < annotations.length; i++) {
            var a = annotations[i], name = String(a.name || '');
            if (name.indexOf('peak-label:') !== 0) continue;
            var group = gd.querySelector('.annotation[data-index="' + i + '"]');
            var text = group && group.querySelector('.annotation-text');
            if (!text) continue;
            var r = text.getBoundingClientRect();
            if (event.clientX >= r.left - 3 && event.clientX <= r.right + 3 &&
                event.clientY >= r.top - 3 && event.clientY <= r.bottom + 3) {
                return {field: 'peak', peakId: name.slice(11), value: a.text, element: text,
                        home: axisPoint(gd, a.xref, a.yref, a.x, a.y), leader: labelLeader(a),
                        offset: labelOffset(gd, a), units: unitsPerPixel(gd, a.xref, a.yref)};
            }
        }
        return null;
    }
    function peakLabelAt(gd, event) {
        if (!gd || !gd._fullData || !gd._fullLayout || !gd.querySelectorAll) return null;
        var moved = movedPeakLabelAt(gd, event);
        if (moved) return moved;
        var box = gd.getBoundingClientRect(), texts = null;
        for (var i = 0; i < gd._fullData.length; i++) {
            var trace = gd._fullData[i];
            if (trace.meta !== 'peak_overlay' || trace.mode !== 'text' || !trace.customdata || !trace.text) continue;
            var xa = gd._fullLayout[(trace.xaxis || 'x').replace('x', 'xaxis')];
            var ya = gd._fullLayout[(trace.yaxis || 'y').replace('y', 'yaxis')];
            if (!xa || !ya || typeof xa.l2p !== 'function' || typeof ya.l2p !== 'function') continue;
            var px = box.left + xa._offset + xa.l2p(Number(trace.x[0])), name = String(trace.text[0]);
            var py = box.top + ya._offset + ya.l2p(Number(trace.y[0]));
            texts = texts || gd.querySelectorAll('text');
            for (var j = 0; j < texts.length; j++) {
                if (texts[j].textContent !== name) continue;
                var r = texts[j].getBoundingClientRect();
                // The same name stands at the same time in every subplot: the label sits just above its own peak.
                if (!r.width || Math.abs((r.left + r.right) / 2 - px) > 12 || r.bottom < py - 12 || r.top > py + 4) continue;
                if (event.clientX >= r.left - 3 && event.clientX <= r.right + 3 &&
                    event.clientY >= r.top - 3 && event.clientY <= r.bottom + 3) {
                    return {field: 'peak', peakId: trace.customdata[0], value: name, element: texts[j],
                            home: axisPoint(gd, trace.xaxis, trace.yaxis, trace.x[0], trace.y[0]),
                            leader: false, offset: [0, 0], units: unitsPerPixel(gd, trace.xaxis, trace.yaxis)};
                }
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
        if (!hit.fileId && !hit.peakId && !meta.gecko_tab_id) return null;
        var title=hit.field==='title' ? layout.title : (layout[hit.field] || {}).title;
        var value=typeof title==='string' ? title : title && title.text || '';
        if (hit.annotationIndex!==undefined) value=hit.text;
        if (hit.fileId || hit.peakId) value=hit.value;
        if (hit.field==='title') value=value.replace(/^<b>([\s\S]*)<\/b>$/, '$1');
        var input=document.createElement('input'), rect=hit.element.getBoundingClientRect();
        input.type='text';input.value=value;input.className='figure-label-editor';
        input.setAttribute('aria-label',hit.peakId?'Edit peak name':hit.fileId?'Edit dataset name':hit.field==='title'?'Edit plot title':'Edit axis label');
        input.setAttribute('title','Enter to apply · Esc to cancel');
        var width=Math.min(420,Math.max(190,rect.width+40));
        Object.assign(input.style,{position:'fixed',left:Math.max(8,Math.min(rect.left,window.innerWidth-width-8))+'px',
            top:Math.max(8,Math.min(rect.top-6,window.innerHeight-44))+'px',width:width+'px',zIndex:5000});
        var session={gd:gd,input:input,hit:hit,value:value,tab:meta.gecko_tab_id};editing=session;
        function commit() {
            if (editing!==session) return;
            var text=input.value;cancel();
            if(hit.peakId){
                if(text.trim() && text.trim()!==value) window.dash_clientside.set_props('peak-name-edit',{data:{peak_id:hit.peakId,text:text.trim(),ts:Date.now()}});
                return;
            }
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
        var peak=!label && event.type==='dblclick' ? peakLabelAt(gd,event) : null;
        var hit=label ? {field:'dataset',fileId:label.dataset.fileId,value:label.textContent,element:label} : peak || targetAtEvent(gd,event);
        if(!hit) return;
        // Double-click edits a file name in Files or a peak name in the plot straight away; legend names and single
        // clicks need the text tool.
        var direct=event.type==='dblclick' && (label || peak);
        if(!enabled && !direct && (hit.fileId || event.type==='click')) return;
        if(!hit.fileId && !hit.peakId && !(gd.layout && gd.layout.meta && gd.layout.meta.gecko_tab_id)) return;
        event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();
        if((enabled && event.type==='click') || event.type==='dblclick') begin(gd,hit);
    }
    ['pointerdown','mousedown','click','dblclick'].forEach(function(name){document.addEventListener(name,handle,true);});
    // Over a peak name, a double-click renames the peak instead of resetting the zoom.
    document.addEventListener('pointermove',function(event){
        var gd=event.target.closest && event.target.closest('.js-plotly-plot');
        if(!gd || !gd._context) return;
        var over=!!peakLabelAt(gd,event);
        gd.__geckoOverPeakLabel=over;                    // manual-integration.js then leaves the zoom alone
        gd.classList.toggle('over-peak-label',over);     // a grab cursor: the name can be dragged (peak-label-drag.js)
        if(over && gd.__geckoDoubleClick===undefined){gd.__geckoDoubleClick=gd._context.doubleClick;gd._context.doubleClick=false;}
        else if(!over && gd.__geckoDoubleClick!==undefined){gd._context.doubleClick=gd.__geckoDoubleClick;delete gd.__geckoDoubleClick;}
    },true);
    document.addEventListener('gecko:plot-leave',cancel);
    document.addEventListener('keydown',function(event){if(event.key==='Escape'){if(editing)cancel();else setEnabled(false);}},true);
    window.GeckoFigureLabels={targetAtEvent:targetAtEvent,peakLabelAt:peakLabelAt,labelOffset:labelOffset,begin:begin,cancel:cancel,setEnabled:setEnabled};
})();
