"""Editable calibration standards, fitted curve and saved model controls."""
from dash import html, dcc, dash_table
import dash_mantine_components as dmc


def _empty_graph(message):
    return {'data':[], 'layout':{
        'template':'plotly_white', 'autosize':True,
        'margin':{'l':42,'r':12,'t':16,'b':38},
        'xaxis':{'visible':False}, 'yaxis':{'visible':False},
        'annotations':[{'text':message,'xref':'paper','yref':'paper','x':.5,'y':.5,
                        'showarrow':False,'font':{'size':12,'color':'#777'}}]}}


def create_calibration_panel():
    return html.Div(id='calibration-content', className='calibration-workspace', children=[
        dcc.Store(id='cal-revision', data=0),
        dcc.Download(id='cal-download'),
        html.Div(id='calibration-container', children=[
            html.Div([
                dmc.Select(id='cal-active-model', label='Calibration', placeholder='New calibration',
                    data=[], size='xs', clearable=False, allowDeselect=False, className='cal-model-select'),
                html.Div([
                    dmc.Button('New',id='cal-new-btn',n_clicks=0,size='xs',variant='default'),
                    dcc.Upload(id='cal-load-upload', accept='.json,application/json', multiple=False,
                        children=dmc.Button('Load JSON',size='xs',variant='default')),
                    dmc.Button('Save JSON',id='cal-save-btn',n_clicks=0,disabled=True,size='xs',variant='default'),
                ],className='cal-actions'),
            ],className='cal-toolbar'),
            html.Div(id='cal-feedback',role='status',className='cal-feedback',
                **{'aria-live':'polite','aria-atomic':'true'}),
            html.Div([
                html.Div([
                    html.Section([
                        html.H4('Standards & fit',className='cal-heading'),
                        html.Div([
                            dmc.TextInput(id='cal-analyte-name',label='Analyte',placeholder='Analyte name',size='xs'),
                            dmc.TextInput(id='cal-units',label='Concentration units',placeholder='e.g. mM or mg/mL',size='xs'),
                            dmc.Select(id='cal-fit-type',label='Fit',value='linear',size='xs',clearable=False,
                                allowDeselect=False,data=[{'label':x.title(),'value':x} for x in ('linear','quadratic','power')]),
                        ],className='cal-fields'),
                        html.Div([
                            html.Div([html.Label('Peak response',className='cal-field-label'),
                                dmc.SegmentedControl(id='cal-response-type',value='area',size='xs',
                                    data=[{'label':'Area','value':'area'},{'label':'Height','value':'height'}],
                                    **{'aria-label':'Calibration peak response'})]),
                            dmc.Switch(id='cal-force-zero',label='Force through zero',checked=False,size='sm'),
                        ],className='cal-response-row'),
                        dmc.MultiSelect(id='cal-peak-picker',label='Integrated peaks',data=[],value=[],
                            placeholder='Search samples and peaks…',searchable=True,clearable=True,size='xs'),
                        html.Div([
                            dmc.Button('Add selected peaks',id='cal-add-peaks-btn',n_clicks=0,size='xs',variant='default'),
                            dmc.Button('Add manual row',id='cal-add-manual-btn',n_clicks=0,size='xs',variant='default'),
                            dmc.Button('Use as matching peak',id='cal-link-peak-btn',n_clicks=0,
                                size='xs',variant='default',
                                attributes={'title':'Use one selected peak to identify the signal and position for a saved calibration without refitting it.'}),
                        ],className='cal-actions cal-add-actions'),
                        html.P('Enter known concentrations. Checked rows are included in the fit.',className='cal-note'),
                        html.Div(dash_table.DataTable(id='cal-standards-table',data=[],
                            columns=[{'name':'Sample','id':'sample_name','type':'text'},
                                     {'name':'Position','id':'position','type':'numeric','editable':False},
                                     {'name':'Concentration','id':'concentration','type':'numeric'},
                                     {'name':'Peak area','id':'area','type':'numeric'}],
                            editable=True,row_deletable=True,row_selectable='multi',selected_rows=[],
                            style_table={'minWidth':'480px','maxHeight':'300px','overflowY':'auto'},
                            style_cell={'fontFamily':'inherit','fontSize':'12px','padding':'7px 9px',
                                        'textAlign':'right','minWidth':'78px','whiteSpace':'normal','height':'auto'},
                            style_cell_conditional=[{'if':{'column_id':'sample_name'},'textAlign':'left','minWidth':'125px'}],
                            style_header={'fontWeight':'600','backgroundColor':'#f4f4f5','color':'#333',
                                          'border':'1px solid #dedee1','textAlign':'left'},
                            style_data={'border':'1px solid #e5e5e7'},
                            style_data_conditional=[{'if':{'state':'selected'},'backgroundColor':'#eef3ee',
                                                     'border':'1px solid #789077'}]),
                            id='cal-standards-scroll',className='cal-standards-scroll',role='region',tabIndex=0,
                            **{'aria-label':'Calibration standards. Scroll horizontally to reach every column.'}),
                    ],className='cal-section'),
                    html.Div([
                        dmc.Button('Fit calibration',id='cal-fit-btn',n_clicks=0,size='xs',variant='filled'),
                        html.Span('Refit after changing standards or settings.',className='cal-note'),
                    ],className='cal-fit-actions'),
                    html.Section([
                        html.H4('Find this peak in other samples',className='cal-heading'),
                        html.Div(id='cal-match-label',children='Select an integrated peak to match its signal and position.',className='cal-note'),
                        html.Div([
                            dmc.NumberInput(id='cal-match-position',label='Expected peak position',placeholder='From selected peak',
                                value=None,step=.1,decimalScale=4,debounce=True,size='xs'),
                            dmc.NumberInput(id='cal-match-tolerance',label='Allowed shift (±)',value=.2,min=0,
                                step=.05,decimalScale=4,debounce=True,size='xs'),
                        ],className='cal-match-fields'),
                        dmc.Switch(id='cal-auto-apply',label='Calculate concentrations for matching peaks',
                                   checked=True,size='sm'),
                    ],className='cal-section'),
                ],className='cal-editor'),
                html.Div([
                    html.Section([
                        html.H4('Calibration curve',className='cal-heading'),
                        dcc.Graph(id='cal-curve-graph',figure=_empty_graph('Fit standards to view the calibration curve.'),
                            responsive=True,config={'displaylogo':False,'responsive':True},className='cal-curve',
                            style={'minHeight':'360px'}),
                    ],className='cal-section cal-curve-section'),
                ],className='cal-diagnostics'),
            ],className='cal-workspace-grid'),
        ]),
    ])
