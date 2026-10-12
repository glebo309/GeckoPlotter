"""Organize the existing controls into a compact, contextual workspace."""
from dash import html, dcc
import dash_mantine_components as dmc
from components.axis_inspector import axis_inspector
from components.ms_polarity_control import create_ms_polarity_control
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
    # Match the working sequence: prepare data, integrate, format, export.
    inspector_nav = nodes['toolbox-tabs'].children[0]
    inspector_order = ['pub-plotter', 'integration', 'plot-tools', 'export']
    inspector_nav.children = sorted(inspector_nav.children,
                                    key=lambda tab: inspector_order.index(tab.value))
    # Data tools and figure appearance have separate homes. Smoothing remains
    # a reversible display transform; moving its control must not alter areas.
    smoothing = dmc.Slider(id='pt-smooth-window', min=0, max=151, step=1, value=0,
        updatemode='mouseup', size='sm', thumbSize=16, thumbLabel='Smoothing window in points',
        marks=[{'value':0, 'label':'Off'}, {'value':151, 'label':'151'}])
    nodes['pt-smooth-window'] = smoothing
    smoothing_controls = html.Div([
        html.Div([
            html.Label('Window (points)', className='form-label', htmlFor='smooth-value'),
            dmc.NumberInput(id='smooth-value',value=0,min=0,max=151,step=1,
                debounce=True,clampBehavior='blur',size='xs',allowDecimal=False,
                **{'aria-label':'Smoothing window in points'},style={'width':'88px'}),
        ], className='smoothing-value-row'),
        smoothing,
    ], className='smoothing-controls')
    mapper = nodes['pub-plotter-container'].children
    m = list(mapper.children)
    m[0].className = 'inspector-actions'
    m[0].style = {}
    for id_, label in [('transpose-data','Transpose'), ('add-row','Add row'),
                       ('add-column','Add column'), ('add-y1-series','Add series'),
                       ('remove-y1-series','Remove series'), ('clear-x','Clear X'),
                       ('clear-y1','Clear Y'), ('clear-y2','Clear Y₂'),
                       ('save-mapping','Save mapping'), ('load-mapping','Load mapping'),
                       ('clear-all','Clear mapping')]:
        nodes[id_].children = label
        nodes[id_].className = 'btn btn-secondary'
        nodes[id_].style = {}
    m[8].style = m[20].style = {'display':'flex','gap':'6px','flexWrap':'wrap','alignItems':'center'}
    m[2].children = 'X values'
    m[6].children = 'Y values'
    m[12].children[0].children = 'Secondary Y values'
    mapper.children = [
        section('Smoothing', [
            smoothing_controls,
            html.Div('Display only · peak areas unchanged', className='inspector-note',
                     title='Savitzky–Golay smoothing of plotted signals in the current figure. Imported values and peak calculations use the original signal.')], True),
        section('Table editing', [m[0]], True),
        section('Plot mapping', [*m[1:10], section('Statistics', [m[10]]), m[11],
            *m[12:18], m[18], section('Saved mappings', [m[20]])], True),
        *m[21:],
    ]
    settings.children = [
        old_header,
        html.Div([html.Div('Figure',className='inspector-eyebrow'),
                  html.Div('No figure selected',id='inspector-figure-name'),
                  html.Div('Import data to begin.',id='inspector-figure-summary')],className='inspector-target'),
        section('Axes', [axis_inspector(), legacy_axes,c[10]],True),
        section('Signal style', [
            dcc.Store(id='main-inspector-context'), dcc.Store(id='publication-inspector-context'),
            dcc.Store(id='signal-inspector-owner'), dcc.Store(id='signal-inspector-options',data=[]),
            dmc.Select(id='signal-inspector-select',label='Edit signal',data=[],placeholder='Select a signal',size='xs',allowDeselect=False),
            html.Div([
                dmc.ColorInput(id='signal-color',label='Colour',format='hex',value='#e69f00',size='xs'),
                dmc.NumberInput(id='signal-width',label='Line width',value=1.5,min=.1,max=12,step=.25,debounce=True,size='xs'),
                dmc.Select(id='signal-dash',label='Line style',value='solid',data=[{'label':x.title(),'value':x} for x in ['solid','dash','dot','dashdot']],allowDeselect=False,size='xs'),
                dmc.NumberInput(id='signal-opacity',label='Opacity',value=100,min=0,max=100,step=5,suffix=' %',debounce=True,size='xs'),
            ],className='inspector-fields-grid',id='signal-inspector-fields'),
            html.Div(id='signal-inspector-note',className='inspector-note'),
            html.Button('Use figure defaults',id='signal-reset-btn',n_clicks=0,className='btn btn-secondary inspector-reset'),
        ],True),
        # Defaults for every signal, including the colour palette, in one visible section.
        section('Figure style', [
            html.Div('Applies to all signals. Override a single signal above.', className='inspector-note'),
            c[14],c[17],c[18],c[19],c[20]],True),
        section('Labels & legend',[c[22],c[23],
            html.Button('Use data labels', id='pt-axis-labels-auto', n_clicks=0,
                        className='btn btn-secondary inspector-reset',
                        title='Restore axis names and units from the source data'),
            c[24],c[30],c[31]]),
        section('Layout & size',[layout_controls,c[4],c[7]],False,id='inspector-layout-section'),
        section('Appearance', [c[13],c[15],c[26],c[27],c[28],c[33],c[34]]),
    ]
    # Exact values accompany sliders; their original callbacks remain authoritative.
    pairs = [('pt-subplot-spacing','spacing-value',8,2,25,1,' %'),
             ('pt-trace-opacity','opacity-value',100,10,100,1,' %')]
    for slider_id,number_id,value,lo,hi,step,suffix in pairs:
        slider = nodes[slider_id]
        for parent in walk(root):
            children=getattr(parent,'children',None)
            if isinstance(children,list) and any(child is slider for child in children):
                parent.children=[*children,dmc.NumberInput(id=number_id,value=value,min=lo,max=hi,step=step,
                    suffix=suffix,debounce=True,clampBehavior='blur',size='xs',
                    **{'aria-label':{'smooth-value':'Smoothing window','spacing-value':'Subplot spacing percent','opacity-value':'Opacity percent'}[number_id]},
                    className='slider-exact-value')]
                break
    # Keep deconvolution with the other peak creation/editing tools. Matching
    # and display preferences come after the analysis actions.
    integration = nodes['integration-container']
    parts = list(integration.children)
    integration.children = [*parts[:4], parts[5], parts[4]]
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
    # Available analysis views use one horizontally scrolling tab row.
    # Keep the mounted panels and tab values so switching figures retains context.
    tabs = nodes['analysis-tabs']
    nav = tabs.children[0]
    labels = {'data-overview':'Data', 'peak-analysis':'Peaks', 'metadata':'Metadata',
              'across-samples':'Compare samples', 'calibration':'Calibration',
              'pda':'PDA', 'ms-scan':'MS scan', 'ms-eic':'EIC', 'ms-peak-mass':'Peak mass spectrum'}
    for tab in nav.children:
        tab.children = labels.get(getattr(tab, 'value', None), tab.children)
        tab.style = {'flexShrink':0, 'whiteSpace':'nowrap'}
        if getattr(tab, 'value', None) in ('ms-scan','ms-eic','ms-peak-mass','pda'):
            tab.id = 'analysis-nav-' + tab.value
            tab.style['display'] = 'none'
    analysis_order = ['data-overview','peak-analysis','across-samples','calibration',
                      'pda','ms-scan','ms-peak-mass','ms-eic','metadata']
    nav.children = sorted(nav.children, key=lambda tab: analysis_order.index(tab.value))
    nav.style = {'flexWrap':'nowrap', 'width':'max-content', 'minWidth':'100%'}
    tabs.children[0] = html.Div([
        html.Div(nav, style={'overflowX':'auto', 'overflowY':'hidden', 'minWidth':0, 'flex':1}),
        html.Div([
            dmc.SegmentedControl(id='analysis-dock', value='below', size='xs',
                data=[{'label':'Below', 'value':'below'}, {'label':'Right', 'value':'right'}],
                **{'aria-label':'Analysis pane position'}),
            dcc.Store(id='analysis-dock-owner'),
        ], title='Position the analysis pane', style={'flexShrink':0, 'padding':'4px 8px'}),
    ], className='results-navigation',
       style={'display':'flex', 'alignItems':'center', 'minWidth':0})
    nodes['peak-analysis-container'].children.append(html.Div(
        'No peaks yet. Use Integrate or Shift-drag across a signal to add one.',
        id='peak-analysis-empty', className='inspector-empty', role='status'))
    # A single, discoverable primary figure action pair.
    toolbar=nodes['plot-toolbar']
    toolbar.children.insert(3, html.Div(id='plot-channel-controls'))
    toolbar.children.append(create_ms_polarity_control())
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
    # Figure export first; table/peak/calibration downloads form their own group.
    export_children = nodes['export-container'].children
    data_start = next(i for i, child in enumerate(export_children)
                      if getattr(child, 'children', None) == 'Data Export')
    nodes['exp-open-pub-btn'].children = 'Create publication copy'
    nodes['exp-open-pub-btn'].style = {'width':'100%', 'marginBottom':'6px'}
    for id_, label in [('exp-fig-btn','Export figure'),('exp-data-btn','Export table'),
                       ('exp-peaks-btn','Export peaks'),('exp-cal-btn','Export calibration')]:
        nodes[id_].children = label
    nodes['export-container'].children = [
        section('Figure', export_children[1:data_start], True),
        section('Data & results', export_children[data_start+1:], True),
    ]
    nodes['export-container'].children.insert(0,html.Div('Exports the figure currently shown.',className='inspector-note'))
    nodes['export-container'].children.append(html.Div(id='exp-fig-status',role='status',className='workspace-feedback'))
    root.children.append(dcc.Store(id='figure-export-request'))
    return root
