import dash
from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
from services.data_store import DataStore


def test_publication_switch_controls_workspace_visibility_not_callback_graph():
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    entry = next(cb for cb in app.callback_map.values()
                 if any(output.component_id == 'pub-preview-wrapper'
                        for output in (cb['output'] if isinstance(cb['output'], list) else [cb['output']])))
    assert any(output.component_id == 'plot-workspace' for output in entry['output'])
    callback = entry['callback'].__wrapped__
    preview, workspace = callback('raw', [{'id':'raw','type':'raw'}])
    assert preview['display'] == 'none'
    assert workspace.get('display') != 'none'


from types import SimpleNamespace
from dash import no_update
import callbacks.workspace_callbacks as callbacks


class App:
    def __init__(self):self.functions={}
    def callback(self,*args,**kwargs):
        def register(f):self.functions[f.__name__]=f;return f
        return register
    def clientside_callback(self,*args,**kwargs):pass


def style_callback():
    app=App(); callbacks.register_workspace_callbacks(app,None)
    return app.functions['signal_style']


def options(owner='shared:raw:a'):
    return [{'value':'trace:0','label':'Signal','_context_key':owner,
             'trace':{'type':'scatter','name':'Signal','line':{'color':'#123456','width':1.5,'dash':'solid'},'opacity':1}}]


def test_hydration_echo_does_not_create_per_signal_override(monkeypatch):
    fn=style_callback(); s={'_context_key':'shared:raw:a','trace_overrides':{}}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id='signal-inspector-options',triggered=[]))
    hydrated=fn('trace:0',options(),s,None,None,None,None,None,None)
    owner=hydrated[4]
    for trigger,values in [('signal-color',('#123456',1.5,'solid',100)),
                           ('signal-width',('#123456',1.5,'solid',100)),
                           ('signal-opacity',('#123456',1.5,'solid',100))]:
        monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id=trigger,triggered=[]))
        echoed=fn('trace:0',options(),s,*values,None,owner)
        assert echoed[5] is no_update
    assert s['trace_overrides']=={}


def test_previous_figure_options_cannot_be_hydrated_as_the_new_owner(monkeypatch):
    fn=style_callback(); s={'_context_key':'shared:raw:b','trace_overrides':{}}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id='current-plot-settings',triggered=[]))
    result=fn('trace:0',options('shared:raw:a'),s,'#123456',1.5,'solid',100,None,
              {'context':'shared:raw:a','signal':'trace:0'})
    assert result[4] is no_update
    assert result[5] is no_update


def test_real_signal_edit_changes_only_requested_field(monkeypatch):
    fn=style_callback(); s={'_context_key':'shared:raw:a','trace_overrides':{}}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id='signal-inspector-options',triggered=[]))
    hydrated=fn('trace:0',options(),s,None,None,None,None,None,None)
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id='signal-width',triggered=[]))
    result=fn('trace:0',options(),s,'#123456',4,'solid',100,None,hydrated[4])
    assert result[5]['trace_overrides']=={'trace:0':{'line_width':4}}


def test_context_hydration_wins_over_simultaneous_control_echo(monkeypatch):
    fn=style_callback(); s={'_context_key':'shared:raw:a','trace_overrides':{}}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id='signal-width',triggered=[
        {'prop_id':'signal-width.value'}, {'prop_id':'signal-inspector-options.data'}]))
    result=fn('trace:0',options(),s,'#123456',4,'solid',100,None,
              {'context':'shared:raw:a','signal':'trace:0'})
    assert result[5] is no_update


def test_integration_action_only_available_for_source_figures():
    app=App();callbacks.register_workspace_callbacks(app,None)
    describe=app.functions['describe_figure']
    raw={'data':[{'name':'Signal','type':'scatter','y':[1,2]}],
         'layout':{'meta':{'gecko_tab_id':'raw-a'}}}
    pub={'data':raw['data'],'layout':{'meta':{'gecko_tab_id':'publication-a'}}}
    tabs=[{'id':'raw-a','type':'raw','label':'Data'}, {'id':'publication-a','type':'publication','label':'Publication 1'}]
    assert describe(raw,pub,'raw-a',tabs,{'_context_key':'shared:raw:raw-a'},None)[8] is False
    published=describe(raw,pub,'publication-a',tabs,{'_context_key':'shared:raw:publication-a'},None)
    assert published[8] is True
    assert 'source data tab' in published[9]
    empty=describe(None,None,None,[],{},None)
    assert empty[8] is True


def test_file_removal_feedback_reaches_shared_status_bar():
    app=App();callbacks.register_workspace_callbacks(app,None)
    report=app.functions['report_file_action']
    assert report('Removed sample') == 'Removed sample'
    assert report('Restored sample') == 'Restored sample'
    assert report(None) is no_update


def test_figure_inspector_never_resets_selected_analysis_tab_on_file_change():
    app = dash.Dash(__name__)
    callbacks.register_workspace_callbacks(app, None)
    for callback in app.callback_map.values():
        outputs = callback['output']
        if not isinstance(outputs,list):outputs=[outputs]
        assert not any(output.component_id=='analysis-tabs' for output in outputs)
