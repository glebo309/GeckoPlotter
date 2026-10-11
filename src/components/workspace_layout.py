"""Organize the existing controls into a compact, contextual workspace."""
from dash import html, dcc
import dash_mantine_components as dmc
from components.axis_inspector import axis_inspector
from components.file_removal_feedback import create_file_removal_feedback


def walk(node):
    if isinstance(node, (list, tuple)):
        for child in node:
            yield from walk(child)
    elif hasattr(node, 'to_plotly_json'):
        yield node
        yield from walk(getattr(node, 'children', None))


def section(title, children, opened=False, **kwargs):
    return html.Details([html.Summary(title), html.Div(children, className='inspector-section-content')],
                        open=opened, className='inspector-section', **kwargs)


def arrange_workspace(root):
    nodes = {n.id:n for n in walk(root) if isinstance(getattr(n,'id',None),str)}
    settings = nodes['plot-tools-container']
    c = list(settings.children)
    # Preserve legacy control IDs for existing callbacks, without duplicate visible controls.
    raw_layout = nodes['pt-raw-layout-wrapper']
    raw_layout.children = [html.Div(raw_layout.children[:2],style={'display':'none'}),raw_layout.children[2]]
    layout_controls = html.Div([raw_layout, c[2], c[3]], id='inspector-separate-controls')
    legacy_axes = html.Div([c[9],c[11],c[12]],style={'display':'none'})
    old_header = c[0]
    old_header.style = {'display':'none'}
    settings.children = [
        old_header,
        html.Div([html.Div('Figure',className='inspector-eyebrow'),
                  html.Div('No figure selected',id='inspector-figure-name'),
                  html.Div('Import data to begin.',id='inspector-figure-summary')],className='inspector-target'),
        section('Axes', [axis_inspector(), legacy_axes,c[10]],True),
        section('Signals', [
            dcc.Store(id='signal-inspector-owner'), dcc.Store(id='signal-inspector-options',data=[]),
            dmc.Select(id='signal-inspector-select',label='Edit signal',data=[],placeholder='Select a signal',size='xs',allowDeselect=False),
            html.Div([
                dmc.ColorInput(id='signal-color',label='Colour',format='hex',value='#e69f00',size='xs'),
                dmc.NumberInput(id='signal-width',label='Line width',value=1.5,min=.1,max=12,step=.25,debounce=True,size='xs'),
                dmc.Select(id='signal-dash',label='Line style',value='solid',data=[{'label':x.title(),'value':x} for x in ['solid','dash','dot','dashdot']],allowDeselect=False,size='xs'),
                dmc.NumberInput(id='signal-opacity',label='Opacity',value=100,min=0,max=100,step=5,suffix=' %',debounce=True,size='xs'),
            ],className='inspector-fields-grid',id='signal-inspector-fields'),
            html.Div(id='signal-inspector-note',className='inspector-note'),
            html.Button('Use figure style',id='signal-reset-btn',n_clicks=0,className='btn btn-secondary inspector-reset'),
            section('All signals', [c[17],c[18],c[19],c[20],c[5],c[6]]),
        ],True),
        section('Labels & legend',[c[22],c[23],
            html.Button('Use data labels', id='pt-axis-labels-auto', n_clicks=0,
                        className='btn btn-secondary inspector-reset',
                        title='Restore axis names and units from the source data'),
            c[24],c[30],c[31]]),
        section('Appearance',[c[13],c[14],c[15],c[26],c[27],c[28],c[33],c[34]]),
        section('Layout & size',[layout_controls,c[4],c[7]],False,id='inspector-layout-section'),
    ]
    # Exact values accompany sliders; their original callbacks remain authoritative.
    pairs = [('pt-smooth-window','smooth-value',0,0,151,1,''),
             ('pt-subplot-spacing','spacing-value',8,2,25,1,' %'),
             ('pt-trace-opacity','opacity-value',100,10,100,1,' %')]
    for slider_id,number_id,value,lo,hi,step,suffix in pairs:
        slider = nodes[slider_id]
        for parent in walk(settings):
            children=getattr(parent,'children',None)
            if isinstance(children,list) and any(child is slider for child in children):
                parent.children=[*children,dmc.NumberInput(id=number_id,value=value,min=lo,max=hi,step=step,
                    suffix=suffix,debounce=True,clampBehavior='blur',size='xs',
                    **{'aria-label':{'smooth-value':'Smoothing window','spacing-value':'Subplot spacing percent','opacity-value':'Opacity percent'}[number_id]},
                    className='slider-exact-value')]
                break
    # Hide diagnostic reset from the everyday workspace.
    nodes['clear-cache-btn'].style={'display':'none'}
    status_bar = next(n for n in walk(root) if getattr(n, 'className', '') == 'status-bar')
    status_bar.children.insert(0, html.Span(id='figure-action-status', role='status',
        className='workspace-status-message', **{'aria-live':'polite', 'aria-atomic':'true'}))
    status_bar.children.insert(2, create_file_removal_feedback())
    nodes['left-top-panel'].style={**nodes['left-top-panel'].style,'height':'38%'}
    nodes['left-bottom-panel'].style={**nodes['left-bottom-panel'].style,'height':'62%'}
    for node in walk(root):
        if getattr(node,'className','')=='panel-header' and getattr(node,'children',None)=='Toolbox':
            node.children='Inspector'
        if getattr(node,'className','')=='panel-header' and isinstance(getattr(node,'children',None),list):
            for child in node.children:
                if getattr(child,'children',None)=='File Explorer':child.children='Files'
    nodes['left-vertical-divider'].__setattr__('data-label-below','Inspector')
    nodes['left-vertical-divider'].__setattr__('data-label-above','Files')
    # Results retain their mounted panels; specialist navigation uses one menu.
    tabs=nodes['analysis-tabs']; nav=tabs.children[0]
    for tab in nav.children:
        value=getattr(tab,'value',None)
        if value in ('data-overview','peak-analysis','metadata'):
            tab.children={'data-overview':'Data','peak-analysis':'Peaks','metadata':'Metadata'}[value]
        else:tab.style={'display':'none'}
    tabs.children[0]=html.Div([nav,dmc.Select(id='results-more',placeholder='More analysis',data=[],size='xs',
        clearable=False,allowDeselect=False,style={'width':'190px'},**{'aria-label':'Additional analysis views'})],className='results-navigation')
    # A single, discoverable primary figure action pair.
    toolbar=nodes['plot-toolbar']
    toolbar.children += [html.Div(className='toolbar-spacer'),
        html.Button('Publication',id='plot-tool-publication',className='plot-tool',title='Create an editable publication copy of this figure',
                    **{'data-current-figure-action':'publication'}),
        html.Button('Export',id='plot-tool-export',n_clicks=0,className='plot-tool plot-tool-primary',title='Export the current figure'),
        html.Details([html.Summary('?',title='Plot gestures and keyboard shortcuts'),
            html.Div(['Drag to zoom',html.Br(),'Cmd/Ctrl-drag to pan',html.Br(),'Shift-drag to integrate',html.Br(),
                      'Double-click an axis to fit that axis',html.Br(),'Double-click the plot to fit both axes',html.Br(),
                      'Esc closes menus and exits integration',html.Br(),'Cmd/Ctrl-Z undoes peak edits'],className='gesture-help-content')],className='gesture-help')]
    # The legacy session actions are placeholders, not functioning save/restore.
    export_children = nodes['export-container'].children
    session_start = next((i for i, child in enumerate(export_children)
                          if getattr(child, 'children', None) == 'Session'), None)
    if session_start is not None:
        nodes['export-container'].children = [*export_children[:session_start],
            html.Div(export_children[session_start:], style={'display':'none'})]
    nodes['export-container'].children.insert(0,html.Div('Exports the figure currently shown.',className='inspector-note'))
    nodes['export-container'].children.append(html.Div(id='exp-fig-status',role='status',className='workspace-feedback'))
    root.children.append(dcc.Store(id='figure-export-request'))
    return root
