from types import SimpleNamespace
from copy import deepcopy
import dash
import plotly.graph_objects as go
from services.axis_labels import sync_automatic_labels, label_modes
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS, PlotSettingsService
from services.data_store import DataStore
from callbacks import plot_settings_callbacks as callbacks


def spectrum():
    return {'data':[{'type':'scatter','name':'Spectrum','x':[400,500], 'y':[0,.8]}],
            'layout':{'xaxis':{'title':{'text':'Wavelength (nm)'}},
                      'yaxis':{'title':{'text':'Absorbance (Solution #3)'}},
                      'meta':{'gecko_tab_id':'spectra'}}}


def test_automatic_labels_follow_figure_without_changing_title():
    s={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:spectra','title':'title',
       'axis_label_modes':{'x':'auto','y':'auto'}}
    updated=sync_automatic_labels(s,spectrum())
    assert updated['x_label']=='Wavelength (nm)'
    assert updated['y1_label']=='Absorbance (Solution #3)'
    assert updated['title']=='title'
    assert s['x_label']=='Retention Time (min)'
    assert sync_automatic_labels(updated,spectrum()) is None


def test_explicit_custom_label_equal_to_old_default_is_not_overridden():
    s={**DEFAULT_PLOT_SETTINGS,'axis_label_modes':{'x':'custom','y':'custom'}}
    assert sync_automatic_labels(s,spectrum()) is None
    fig=go.Figure(spectrum())
    PlotSettingsService.apply_to_figure(fig,PlotSettingsService.from_dict(dict(s,y_label=s['y1_label'])))
    assert fig.layout.xaxis.title.text=='Retention Time (min)'
    assert fig.layout.yaxis.title.text=='Signal (mAU)'
    assert fig.layout.meta['gecko_axis_identities']['xaxis']['label']=='Wavelength (nm)'


def test_auto_labels_do_not_overwrite_measurement_titles():
    fig=go.Figure(spectrum())
    s={**DEFAULT_PLOT_SETTINGS,'axis_label_modes':{'x':'auto','y':'auto'}}
    PlotSettingsService.apply_to_figure(fig,PlotSettingsService.from_dict(dict(s,y_label=s['y1_label'])))
    assert fig.layout.xaxis.title.text=='Wavelength (nm)'
    assert fig.layout.yaxis.title.text=='Absorbance (Solution #3)'


def test_label_edit_is_explicit_and_survives_context_hydration(monkeypatch):
    store=DataStore();store._shared_plot_settings={}
    app=dash.Dash(__name__);callbacks.register_plot_settings_callbacks(app,store)
    entries={c['callback'].__wrapped__.__name__:c for c in app.callback_map.values() if c.get('callback')}
    hydrate=entries['hydrate_plot_settings'];edit=entries['user_edit_settings']
    initial=hydrate['callback'].__wrapped__('shared:raw:spectra',None)
    values={o.component_id:v for o,v in zip(hydrate['output'],initial)}
    current=initial[0]
    values['pt-x-label']='Wavelength / nm'
    monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':'pt-x-label.value'}]))
    changed=edit['callback'].__wrapped__(*[values.get(i['id']) for i in edit['inputs']],current)
    assert changed['axis_label_modes']['x']=='custom'
    callbacks._save_settings(store,changed['_context_key'],changed)
    restored=hydrate['callback'].__wrapped__('shared:raw:spectra',None)[0]
    assert restored['x_label']=='Wavelength / nm'
    assert restored['axis_label_modes']['x']=='custom'


def test_use_data_labels_restores_source_on_custom_publication_snapshot():
    from services.publication_figure import editable_publication_figure
    fig=go.Figure(spectrum())
    settings={**DEFAULT_PLOT_SETTINGS,'x_label':'Custom X','y1_label':'Custom Y',
              'axis_label_modes':{'x':'custom','y':'custom'}}
    PlotSettingsService.apply_to_figure(fig,PlotSettingsService.from_dict(dict(settings,y_label='Custom Y')))
    restored=sync_automatic_labels(settings,fig,reset=True)
    assert restored['x_label']=='Wavelength (nm)'
    assert restored['y1_label']=='Absorbance (Solution #3)'
    published=editable_publication_figure(fig.to_plotly_json(),restored)
    assert published.layout.xaxis.title.text=='Wavelength (nm)'
    assert published.layout.yaxis.title.text=='Absorbance (Solution #3)'


def test_visible_label_hydration_is_not_misclassified_as_user_edit(monkeypatch):
    store=DataStore();store._shared_plot_settings={}
    app=dash.Dash(__name__);callbacks.register_plot_settings_callbacks(app,store)
    entries={c['callback'].__wrapped__.__name__:c for c in app.callback_map.values() if c.get('callback')}
    hydrate=entries['hydrate_plot_settings']; edit=entries['user_edit_settings']
    initial=hydrate['callback'].__wrapped__('shared:raw:spectra',None)
    values={o.component_id:v for o,v in zip(hydrate['output'],initial)}
    sync=entries['sync_axis_label_controls']['callback'].__wrapped__
    monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':'main-plot.figure'}]))
    result=sync(spectrum(),None,'spectra',None,[{'id':'spectra','type':'raw'}],initial[0],'shared:raw:spectra')
    assert result[1:3]==('Wavelength (nm)','Absorbance (Solution #3)')
    values['pt-x-label'],values['pt-y-label']=result[1:3]
    monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':'pt-x-label.value'}]))
    echoed=edit['callback'].__wrapped__(*[values.get(i['id']) for i in edit['inputs']],result[0])
    assert echoed is dash.no_update
    assert result[0]['axis_label_modes']=={'x':'auto','y':'auto'}


def test_label_sync_rejects_previous_tab_and_reset_keeps_user_title(monkeypatch):
    app=dash.Dash(__name__);callbacks.register_plot_settings_callbacks(app,DataStore())
    sync=next(c['callback'].__wrapped__ for c in app.callback_map.values() if c.get('callback') and
              c['callback'].__wrapped__.__name__=='sync_axis_label_controls')
    s={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:spectra','x_label':'Custom',
       'axis_label_modes':{'x':'custom','y':'auto'},'title':'title'}
    monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':'pt-axis-labels-auto.n_clicks'}]))
    updated=sync(spectrum(),None,'spectra',1,[{'id':'spectra','type':'raw'}],s,'shared:raw:spectra')[0]
    assert updated['title']=='title'
    assert updated['x_label']=='Wavelength (nm)'
    assert updated['axis_label_modes']['x']=='auto'
    assert all(value is dash.no_update for value in sync(spectrum(),None,'other',1,[],s,'shared:raw:other'))
