from copy import deepcopy
import io
from unittest.mock import patch
import pytest
import plotly.graph_objects as go
from PIL import Image

from services.figure_sanitization import clean_figure_for_output
from services.figure_actions import publication_snapshot
from services.publication_figure import editable_publication_figure
from services.figure_export import export_displayed_figure


def selected_figure():
    return {'data':[
        {'type':'scatter','name':'Signal','x':[0,1,2],'y':[0,5,0],'meta':{'file_id':'uv'}},
        {'type':'scatter','name':'Baseline fit','x':[0,2],'y':[.2,.2],'line':{'dash':'dot','width':2}},
        {'type':'scatter','x':[0,1,2,2,0],'y':[0,5,0,0,0], 'meta':'peak_overlay',
         'customdata':['p1']*5, 'fill':'toself','fillcolor':'rgba(230, 159, 0, 0.58)',
         'mode':'lines','line':{'color':'#e69f00','width':2}},
        {'type':'scatter','x':[0,2],'y':[0,0],'mode':'markers','meta':'peak_overlay',
         'customdata':[['p1','p-point'],['p1','p-point']]},
        {'type':'scatter','x':[0,2,2,0],'y':[0,0,5,5],'fill':'toself','meta':'peak_overlay',
         'customdata':[['__deselect__','catcher']]*4},
        {'type':'scatter','x':[1],'y':[5],'mode':'text','text':['Product'],'meta':'peak_overlay'},
    ], 'layout':{
        'xaxis':{'range':[.2,1.8],'autorange':False},
        'shapes':[{'type':'line','name':'baseline:p1','editable':True,'x0':0,'y0':0,'x1':2,'y1':0},
                  {'type':'line','name':'baseline:reference','editable':False,'x0':0,'y0':.2,'x1':2,'y1':.2},
                  {'type':'rect','name':'Author highlight','x0':.5,'x1':1.5,'y0':0,'y1':5}],
        'annotations':[{'text':'Reaction complete','x':1,'y':5,'showarrow':True}],
        'meta':{'gecko_peak_geometry':{'p1':{'file_id':'uv','bounds':[0,2],'baseline':[[0,0],[2,0]]}}}}}


def assert_clean(figure):
    figure = figure.to_plotly_json() if hasattr(figure,'to_plotly_json') else figure
    assert len(figure['data']) == 4
    fill = next(t for t in figure['data'] if t.get('fill')=='toself')
    assert fill['fillcolor'] == 'rgba(230, 159, 0, 0.30)'
    assert fill['line']['width'] == 0
    assert not any(s.get('name')=='baseline:p1' for s in figure['layout'].get('shapes',[]))
    assert any(s.get('name')=='baseline:reference' for s in figure['layout'].get('shapes',[]))
    assert any(s.get('name')=='Author highlight' for s in figure['layout'].get('shapes',[]))
    assert figure['data'][1]['name']=='Baseline fit'
    assert figure['data'][-1]['text']==['Product']
    assert figure['layout']['annotations'][0]['text']=='Reaction complete'
    assert figure['layout']['meta']['gecko_peak_geometry']['p1']['file_id']=='uv'


def test_sanitizer_removes_only_editor_artifacts_and_does_not_mutate_source():
    source=selected_figure(); original=deepcopy(source)
    clean=clean_figure_for_output(source)
    assert_clean(clean)
    assert source == original
    assert clean_figure_for_output(clean) == clean
    assert clean['layout']['xaxis']['range']==[.2,1.8]


def test_new_publication_stores_clean_copy_and_existing_publication_is_cleaned_on_render():
    source=selected_figure()
    _,tab,entries=publication_snapshot(source,[],{})
    assert_clean(entries[tab]['figure'])
    assert_clean(editable_publication_figure(source,{'layout_mode':'overlay'}))
    assert len(source['data'])==6


@pytest.mark.parametrize('fmt',['png','svg','pdf','tiff','html'])
def test_all_export_formats_share_sanitizer(fmt):
    captured=[]
    def render(fig, **kwargs):
        captured.append(fig)
        if kwargs['format']=='svg':return b'<svg width="307" height="230"></svg>'
        if kwargs['format']=='pdf':return b'pdf'
        out=io.BytesIO();Image.new('RGB',(50,50)).save(out,'PNG');return out.getvalue()
    def html(fig, **kwargs):captured.append(fig);return '<html></html>'
    with patch.object(go.Figure,'to_image',render),patch.object(go.Figure,'to_html',html):
        export_displayed_figure(selected_figure(),fmt,84,63,300,307)
    assert_clean(captured[0])


@pytest.mark.parametrize('mode,window',[('overlay',9),('stacked',9),('overlay',0)])
def test_old_baked_publication_never_restores_editor_artifacts_during_settings_edits(mode,window):
    source=selected_figure(); original=deepcopy(source)
    figure=editable_publication_figure(source,{'layout_mode':mode,'smooth_window':window}, {'layout_mode':'overlay'})
    assert_clean(figure)
    assert source==original


def test_raw_grid_relayout_can_preserve_interactive_handles_and_selected_fill():
    figure=editable_publication_figure(selected_figure(),{'layout_mode':'stacked'},
                                       {'layout_mode':'overlay'}, clean_output=False)
    assert any(shape.name=='baseline:p1' and shape.editable for shape in figure.layout.shapes)
    assert any(trace.meta=='peak_overlay' and trace.mode=='markers' for trace in figure.data)
    fill=next(trace for trace in figure.data if trace.meta=='peak_overlay' and trace.fill=='toself')
    assert fill.line.width==2
    assert '0.58' in fill.fillcolor


def test_source_trace_with_editor_like_customdata_is_not_removed():
    source=selected_figure()
    source['data'][0]['customdata']=[['sample','p-point']]*3
    assert_clean(clean_figure_for_output(source))
    source['data'][0]['customdata']=[['sample','catcher']]*3
    assert_clean(clean_figure_for_output(source))
