"""Context and precise controls for the shared figure inspector."""
from dash import Input, Output, State, no_update, ctx, ClientsideFunction
from services.workspace_inspector import active_figure, signal_choices, edit_signal


def register_workspace_callbacks(app, data_manager):
    for source, prop, target in (('main-plot', 'figure', 'main-inspector-context'),
                                 ('pub-preview-graph', 'data', 'publication-inspector-context')):
        app.clientside_callback(
            ClientsideFunction(namespace='inspectorContext', function_name='summarize'),
            Output(target, 'data'), Input(source, prop), State(target, 'data'))
    app.clientside_callback(
        ClientsideFunction(namespace='resize', function_name='syncAnalysisDock'),
        [Output('analysis-dock', 'value'), Output('analysis-dock-owner', 'data')],
        [Input('analysis-tabs', 'value'), Input('analysis-dock', 'value'),
         Input('active-plot-tab', 'data'), Input('plot-tabs', 'data')],
        State('analysis-dock-owner', 'data'),
    )

    @app.callback(
        [Output('inspector-figure-name','children'),Output('inspector-figure-summary','children'),
         Output('inspector-separate-controls','style'),Output('signal-inspector-select','data'),
         Output('signal-inspector-select','value'),Output('signal-inspector-options','data'),
         Output('plot-tool-publication','disabled'),Output('plot-tool-export','disabled'),
         Output('plot-tool-integrate','disabled'),Output('plot-tool-integrate','title')],
        [Input('main-inspector-context','data'),Input('publication-inspector-context','data'),Input('active-plot-tab','data'),
         # Only the owner and layout mode matter here, so unrelated settings edits do not re-run this callback.
         Input('plot-tabs','data'),Input('plot-settings-figure-key','data')],
        State('signal-inspector-select','value'))
    def describe_figure(raw,pub,tab,tabs,settings,selected):
        figure=active_figure(tab,tabs,raw,pub)
        context=(settings or {}).get('_context_key')
        if figure is None or (tab and context and not context.endswith(':'+tab)):
            name=next((t.get('label') for t in tabs or [] if t.get('id')==tab),'No figure selected')
            return name,'Select a figure or import data to begin.',{'display':'none'},[],None,[],True,True,True,'Load source data to integrate peaks'
        preview = any(isinstance(t.get('meta'), dict) and t['meta'].get('pda_preview')
                      for t in figure.get('data', []))
        signals=signal_choices(figure)
        options=[{'value':o['value'],'label':o['label']} for o in signals]
        name=next((t.get('label') for t in tabs or [] if t.get('id')==tab),'No figure selected')
        mode=(settings or {}).get('layout_mode','overlay')
        kind=next((t.get('type') for t in tabs or [] if t.get('id')==tab),'raw')
        summary=(f"{len(signals)} signal{'s' if len(signals)!=1 else ''} · {'Separate' if mode=='stacked' else 'Overlay'}"
                 + (' · Publication copy' if kind=='publication' else '')) if signals else 'Import data to begin.'
        for option in signals:
            option['_context_key']=context
            option['trace']={k:v for k,v in option['trace'].items() if k in ('type','name','meta','line','marker','opacity')}
        return (name,summary,{} if mode=='stacked' else {'display':'none'},options,
                selected if selected in [o['value'] for o in options] else (options[0]['value'] if options else None),
                signals,not bool(signals),not bool(signals),not bool(signals) or kind=='publication',
                'Integrate peaks in the source data tab' if kind=='publication' else
                ('Integrate peaks — drag across a peak. Shortcut: Shift-drag. The previewed wavelength is kept as a channel.'
                 if preview else 'Integrate peaks — drag across a peak. Shortcut: Shift-drag.') if signals else 'Load source data to integrate peaks')

    @app.callback(
        [Output('signal-color','value'),Output('signal-width','value'),Output('signal-dash','value'),
         Output('signal-opacity','value'),Output('signal-inspector-owner','data'),
         Output('current-plot-settings','data',allow_duplicate=True),
         Output('signal-width','disabled'),Output('signal-dash','disabled'),Output('signal-inspector-note','children'),
         Output('signal-color','disabled'),Output('signal-opacity','disabled'),
         Output('signal-reset-btn','disabled'),Output('signal-inspector-select','disabled')],
        [Input('signal-inspector-select','value'),Input('signal-inspector-options','data'),Input('current-plot-settings','data'),
         Input('signal-color','value'),Input('signal-width','value'),Input('signal-dash','value'),Input('signal-opacity','value'),
         Input('signal-reset-btn','n_clicks')],State('signal-inspector-owner','data'),prevent_initial_call=True)
    def signal_style(key,options,settings,color,width,dash,opacity,reset,owner):
        settings=settings or {}; context=settings.get('_context_key')
        option=next((o for o in options or [] if o['value']==key),None)
        if not option:
            return ('',None,'solid',None,None,no_update,True,True,
                    'Select a figure with signals to edit its appearance.',True,True,True,True)
        if option.get('_context_key') != context:
            return (no_update,)*6+(True,True,'Loading figure controls…',True,True,True,True)
        trigger=ctx.triggered_id
        current_owner={'context':context,'signal':key}
        owner_matches=bool(owner and owner.get('context')==context and owner.get('signal')==key)
        hydration=any(item.get('prop_id','').split('.')[0] in (
            'signal-inspector-select','signal-inspector-options','current-plot-settings')
            for item in getattr(ctx,'triggered',[]))
        fields={'signal-color':('color',color),'signal-width':('line_width',width),
                'signal-dash':('line_style',dash),'signal-opacity':('opacity',None if opacity is None else opacity/100)}
        if trigger in fields and owner_matches and not hydration:
            field,value=fields[trigger]
            if value is None:return (no_update,)*13
            if value == (owner.get('values') or {}).get(field):
                return (no_update,)*13
            if field=='color' and (not isinstance(value,str) or not value.startswith('#') or len(value) not in (4,7)):
                return (no_update,)*13
            updated=edit_signal(settings,context,key,{field:value})
            return (no_update,)*5+(updated or no_update,)+(no_update,)*7
        if trigger=='signal-reset-btn' and owner_matches and not hydration:
            from copy import deepcopy
            updated=deepcopy(settings)
            overrides=updated.setdefault('trace_overrides',{})
            overrides.pop(key,None)
            overrides.pop(option['trace'].get('name'),None)
            return (no_update,)*5+(updated,)+(no_update,)*7
        trace=option['trace']; line=trace.get('line') or {}; marker=trace.get('marker') or {}
        overrides=settings.get('trace_overrides') or {}
        override=overrides.get(key,overrides.get(trace.get('name'),{}))
        basecolor=line.get('color') or marker.get('color') or '#e69f00'
        if not isinstance(basecolor,str) or not basecolor.startswith('#'):basecolor='#e69f00'
        isbar=trace.get('type')=='bar'
        values={'color':override.get('color',basecolor),
                'line_width':override.get('line_width',line.get('width',settings.get('line_width',1.5))),
                'line_style':override.get('line_style',line.get('dash','solid')),
                'opacity':override.get('opacity',trace.get('opacity',1))}
        current_owner['values']=values
        return (values['color'],values['line_width'],values['line_style'],100*values['opacity'],
                current_owner,no_update,isbar,isbar,
                'Edits apply only to this signal. Figure style sets the shared defaults.',False,False,False,False)

    @app.callback(Output('toolbox-tabs','value',allow_duplicate=True),Input('plot-tool-export','n_clicks'),prevent_initial_call=True)
    def show_export(clicks):return 'export' if clicks else no_update

    @app.callback(
        [Output('analysis-nav-ms-scan','style'), Output('analysis-nav-ms-eic','style'),
         Output('analysis-nav-ms-peak-mass','style'),
         Output('side-tabs','value',allow_duplicate=True)],
        [Input('active-file','data'), Input('loaded-files','data'), Input('side-tabs','value')],
        prevent_initial_call=True,
    )
    def analysis_capabilities(active_file, _loaded_files, selected):
        from services.analysis_capabilities import has_lcms_scans, MS_ANALYSIS_TABS
        available = has_lcms_scans(data_manager, active_file)
        style = {'flexShrink':0, 'whiteSpace':'nowrap'}
        if not available:
            style['display'] = 'none'
        fallback = 'metadata' if not available and selected in MS_ANALYSIS_TABS else no_update
        return dict(style), dict(style), dict(style), fallback

    @app.callback(Output('figure-action-status', 'children', allow_duplicate=True),
                  Input('file-removal-message', 'children'), prevent_initial_call=True)
    def report_file_action(message):
        return message or no_update

    # Single circular clientside callback: sliders and exact fields share one value.
    app.clientside_callback("""
    function(smooth,spacing,opacity,smoothExact,spacingExact,opacityExact){
      var dc=window.dash_clientside, n=dc.no_update, t=dc.callback_context.triggered;
      var id=t.length?t[0].prop_id.split('.')[0]:'';
      var out=[n,n,n,n,n,n];
      if(id==='smooth-value' && smoothExact!==null && smoothExact!==smooth)out[0]=smoothExact;
      else if(smoothExact!==smooth)out[3]=smooth;
      if(id==='spacing-value' && spacingExact!==null && Math.abs(spacingExact/100-spacing)>0.00001)out[1]=spacingExact/100;
      else if(Math.abs(spacingExact-spacing*100)>0.00001)out[4]=Math.round(spacing*100);
      if(id==='opacity-value' && opacityExact!==null && Math.abs(opacityExact/100-opacity)>0.00001)out[2]=opacityExact/100;
      else if(Math.abs(opacityExact-opacity*100)>0.00001)out[5]=Math.round(opacity*100);
      return out;
    }
    """,[Output('pt-smooth-window','value',allow_duplicate=True),Output('pt-subplot-spacing','value',allow_duplicate=True),
          Output('pt-trace-opacity','value',allow_duplicate=True),Output('smooth-value','value'),Output('spacing-value','value'),Output('opacity-value','value')],
         [Input('pt-smooth-window','value'),Input('pt-subplot-spacing','value'),Input('pt-trace-opacity','value'),
          Input('smooth-value','value'),Input('spacing-value','value'),Input('opacity-value','value')],prevent_initial_call=True)
