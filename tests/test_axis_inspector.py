import copy
import pytest
import plotly.graph_objects as go
from services.axis_inspector import axis_descriptors, apply_axis_overrides, update_axis_override
from services.plot_settings_service import PlotSettingsService
from services.publication_figure import editable_publication_figure


def sample():
    f=go.Figure([go.Scatter(x=[0,5,10],y=[0,2e6,0],name='TIC'),
                 go.Scatter(x=[0,5,10],y=[0,500,0],name='UV',yaxis='y2')])
    f.update_layout(xaxis_title='Time (min)',yaxis_title='Ion Count',
                    yaxis2=dict(title='Absorbance (mAU)',overlaying='y',side='right'),
                    meta={'gecko_axis_units':{'yaxis':'Ion Count','yaxis2':'Absorbance (mAU)'}})
    return f


def test_named_axis_groups_are_stable_across_layout_and_custom_labels():
    f=sample()
    descriptors=axis_descriptors(f)
    assert [d['label'] for d in descriptors]==['Time (min)','Ion Count','Absorbance (mAU)']
    PlotSettingsService.apply_to_figure(f,PlotSettingsService.from_dict({'x_label':'Minutes custom'}))
    assert [d['id'] for d in axis_descriptors(f)]==[d['id'] for d in descriptors]
    source=sample().to_plotly_json()
    separate=editable_publication_figure(source,{'layout_mode':'stacked'})
    assert set(d['id'] for d in axis_descriptors(separate))==set(d['id'] for d in descriptors)


def test_one_axis_partial_limit_keeps_other_unit_automatic():
    f=sample(); key=axis_descriptors(f)[2]['id']
    apply_axis_overrides(f,{key:{'mode':'manual','min':10,'max':None,'scale':'linear'}})
    assert list(f.layout.yaxis2.range)==[10,None]
    assert f.layout.yaxis2.autorange=='max'
    assert f.layout.yaxis.range is None
    assert f.layout.xaxis.range is None


def test_log_values_are_data_units_and_automatic_clears_old_range():
    f=sample(); key=axis_descriptors(f)[1]['id']
    apply_axis_overrides(f,{key:{'mode':'manual','min':10,'max':1000,'scale':'log'}})
    assert list(f.layout.yaxis.range)==[1,3]
    apply_axis_overrides(f,{key:{'mode':'auto','min':10,'max':1000,'scale':'linear'}})
    assert f.layout.yaxis.range is None
    assert f.layout.yaxis.autorange is True


def test_publication_manual_axis_survives_auto_reset_and_layout_change():
    source=sample().to_plotly_json(); key=axis_descriptors(source)[2]['id']
    f=editable_publication_figure(source,{'layout_mode':'stacked','_axis_range_revision':1,
        'axis_overrides':{key:{'mode':'manual','min':20,'max':200,'scale':'linear'}}})
    assert list(f.layout.yaxis2.range)==[20,200]
    assert f.layout.yaxis2.autorange is False


def test_edit_rejects_stale_context_and_invalid_range_without_mutation():
    settings={'_context_key':'raw:b','axis_overrides':{},'_axis_range_revision':3}
    original=copy.deepcopy(settings)
    assert update_axis_override(settings,'raw:a','y:mau','manual',0,100,'linear') is None
    with pytest.raises(ValueError,match='Minimum'):
        update_axis_override(settings,'raw:b','y:mau','manual',100,0,'linear')
    with pytest.raises(ValueError,match='positive'):
        update_axis_override(settings,'raw:b','y:mau','manual',0,100,'log')
    assert settings==original
    edited=update_axis_override(settings,'raw:b','y:mau','manual',0,None,'linear')
    assert edited['_axis_range_revision']==4
    assert edited['axis_overrides']['y:mau']['min']==0


def test_axis_reset_clears_its_manual_limit_and_saves_other_zoom():
    from services.axis_inspector import reset_axis_settings
    f=sample()
    ykey=axis_descriptors(f)[1]['id']; xkey=axis_descriptors(f)[0]['id']
    settings={'_context_key':'raw:a','axis_overrides':{ykey:{'mode':'manual','min':0,'max':600,'scale':'linear'}}}
    changed=reset_axis_settings(settings,f,'yaxis',{
        'xaxis':{'range':[5,9],'type':'linear','userZoom':True}, 'yaxis':{'range':[0,600],'type':'linear'},
        'yaxis2':{'range':[0,500],'type':'linear'}})
    assert changed['axis_overrides'][ykey]=={'mode':'auto','min':None,'max':None,'scale':'linear'}
    assert changed['axis_overrides'][xkey]['min']==5
    assert changed['axis_overrides'][xkey]['max']==9
    apply_axis_overrides(f,changed['axis_overrides'])
    assert list(f.layout.xaxis.range)==[5,9]
    assert f.layout.yaxis.autorange is True


def test_edit_keeps_other_axis_live_zoom_in_the_settings():
    from services.axis_inspector import preserve_other_axes
    f=sample(); descriptors=axis_descriptors(f)
    key=descriptors[1]['id']; xkey=descriptors[0]['id']
    settings={'_context_key':'raw:a','axis_overrides':{}}
    edited=update_axis_override(settings,'raw:a',key,'manual',0,600,'linear')
    view={'layout':f.layout.to_plotly_json(), 'axes':{'xaxis':{'range':[5,9],'type':'linear','userZoom':True},
        'yaxis':{'range':[0,2000000],'type':'linear'},'yaxis2':{'range':[0,500],'type':'linear'}}}
    preserve_other_axes(edited,view,key)
    assert edited['axis_overrides'][xkey]['min']==5
    assert edited['axis_overrides'][xkey]['max']==9
    assert edited['axis_overrides'][key]['max']==600


def test_custom_x_label_does_not_break_axis_settings_on_layout_switch():
    f=sample()
    PlotSettingsService.apply_to_figure(f, PlotSettingsService.from_dict({'x_label':'Minutes'}))
    fig=editable_publication_figure(f.to_plotly_json(), {'layout_mode':'stacked','x_label':'Minutes',
        'axis_overrides':{'x:min':{'mode':'manual','min':5,'max':9,'scale':'linear'}}})
    assert list(fig.layout.xaxis.range)==[5,9]
    assert list(fig.layout.xaxis2.range)==[5,9]


def test_custom_y_title_does_not_merge_incompatible_measurements():
    source=sample()
    separate=editable_publication_figure(source.to_plotly_json(),{'layout_mode':'stacked','y1_label':'Response'})
    overlay=editable_publication_figure(separate.to_plotly_json(),{'layout_mode':'overlay','y1_label':'Response'})
    assert {trace.yaxis for trace in overlay.data}=={'y','y2'}
    assert {d['id'] for d in axis_descriptors(overlay) if d['direction']=='y'}=={'y:ioncount','y:mau'}


def test_edit_does_not_freeze_automatic_publication_axes_with_snapshot_ranges():
    from services.axis_inspector import preserve_other_axes
    f=sample(); settings={'axis_overrides':{}}
    view={'layout':f.layout.to_plotly_json(), 'axes':{'yaxis':{
        'range':[0,2000000],'type':'linear','autorange':False,'userZoom':False}}}
    preserve_other_axes(settings,view,'x:min')
    assert settings['axis_overrides']=={}


def test_axis_reset_does_not_convert_untouched_automatic_axis_to_manual():
    from services.axis_inspector import reset_axis_settings
    f=sample()
    changed=reset_axis_settings({'axis_overrides':{}},f,'xaxis',{
        'xaxis':{'range':[0,10],'type':'linear','userZoom':False},
        'yaxis':{'range':[0,2000000],'type':'linear','userZoom':False}})
    assert 'y:ioncount' not in changed['axis_overrides']
