from copy import deepcopy
import plotly.graph_objects as go
from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS


def source():
    return {'data':[{'x':[0,1],'y':[1,2]}], 'layout':{'meta':{'gecko_tab_id':'publication-a'},
        'xaxis':{'title':{'text':'Time (min)'}},
        'yaxis':{'title':{'text':'Ion Count'}},
        'yaxis2':{'title':{'text':'Absorbance (mAU)'},'overlaying':'y','side':'right'}}}


def edit(field,text,tab='publication-a'):
    return {'tab':tab,'field':field,'text':text,'layout':source()['layout']}


def test_direct_title_edit_is_owned_persistent_and_non_mutating():
    from services.figure_labels import edit_figure_label
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:publication-a'}
    original=deepcopy(settings)
    updated=edit_figure_label(settings,edit('title','My figure'),'publication-a',settings['_context_key'])
    assert updated['title']=='My figure'
    assert settings==original
    assert edit_figure_label(settings,edit('title','Wrong','raw-b'),'publication-a',settings['_context_key']) is None
    assert edit_figure_label(settings,edit('title','Wrong'),'publication-a','shared:raw:other') is None


def test_secondary_axis_label_edit_changes_only_its_measurement_axes():
    from services.figure_labels import edit_figure_label
    from services.publication_figure import editable_publication_figure
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:publication-a',
              'axis_label_modes':{'x':'auto','y':'auto'}}
    updated=edit_figure_label(settings,edit('yaxis2','UV response'),'publication-a',settings['_context_key'])
    rendered=editable_publication_figure(source(),updated,settings)
    assert rendered.layout.yaxis.title.text=='Ion Count'
    assert rendered.layout.yaxis2.title.text=='UV response'
    assert rendered.layout.xaxis.title.text=='Time (min)'
    assert updated['axis_label_overrides']


def test_primary_label_syncs_inspector_and_use_data_labels_clears_direct_edits():
    from services.figure_labels import edit_figure_label
    from services.axis_labels import sync_automatic_labels
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:publication-a',
              'axis_label_modes':{'x':'auto','y':'auto'}}
    updated=edit_figure_label(settings,edit('xaxis','Retention time'),'publication-a',settings['_context_key'])
    assert updated['x_label']=='Retention time'
    reset=sync_automatic_labels(updated,source(),reset=True)
    assert not reset['axis_label_overrides']
    assert reset['x_label']=='Time (min)'


def test_blank_axis_title_is_an_explicit_edit_not_restored_by_autolabels():
    from services.figure_labels import edit_figure_label
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:publication-a'}
    updated=edit_figure_label(settings,edit('xaxis',''),'publication-a',settings['_context_key'])
    fig=go.Figure(source())
    PlotSettingsService.apply_to_figure(fig,PlotSettingsService.from_dict(updated))
    assert fig.layout.xaxis.title.text==''


def test_direct_x_edit_preserves_shared_title_placement_between_panes():
    from services.figure_labels import apply_figure_label_overrides
    fig=go.Figure(layout={'xaxis':{'title':{'text':''}},
        'xaxis2':{'title':{'text':'Time (min)'}},'meta':{'gecko_axis_identities':{
            'xaxis':{'id':'x:min','label':'Time (min)'},
            'xaxis2':{'id':'x:min','label':'Time (min)'}}}})
    apply_figure_label_overrides(fig,{'x:min':'Retention time'})
    assert fig.layout.xaxis.title.text==''
    assert fig.layout.xaxis2.title.text=='Retention time'
