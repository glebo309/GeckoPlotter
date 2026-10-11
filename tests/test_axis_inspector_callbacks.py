from types import SimpleNamespace
import dash
import callbacks.axis_inspector_callbacks as callbacks
from components.axis_inspector import axis_cards


class App:
    def __init__(self):
        self.functions={}
    def callback(self,*args,**kwargs):
        def decorate(function):
            self.functions[function.__name__]=function
            return function
        return decorate


def registered():
    app=App(); callbacks.register_axis_inspector_callbacks(app)
    return app.functions


def test_axis_edit_hydration_is_noop_and_old_owner_cannot_write(monkeypatch):
    edit=registered()['edit_axis']
    identity={'type':'axis-inspector-min','axis':'x:min','owner':'raw:a'}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id=identity))
    s={'_context_key':'raw:a','auto_range':True,'axis_overrides':{}}
    result,error=edit(['auto'],[None],[None],['linear'],[identity],s,'raw:a',None,'a')
    assert result is dash.no_update
    assert not error
    result,error=edit(['manual'],[5],[9],['linear'],[identity],s,'raw:b',None,'b')
    assert result is dash.no_update


def test_numeric_commit_keeps_unedited_live_axis_and_context(monkeypatch):
    edit=registered()['edit_axis']
    identity={'type':'axis-inspector-max','axis':'y:ioncount','owner':'raw:a'}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id=identity))
    s={'_context_key':'raw:a','auto_range':True,'axis_overrides':{}}
    view={'tab':'a','layout':{'xaxis':{'title':{'text':'Time (min)'}}},
          'axes':{'xaxis':{'range':[5,9],'type':'linear','userZoom':True,'autorange':False}}}
    result,error=edit(['manual'],[0],[600],['linear'],[identity],s,'raw:a',view,'a')
    assert not error
    assert result['_context_key']=='raw:a'
    assert result['axis_overrides']['y:ioncount']['max']==600
    assert result['axis_overrides']['x:min']['min']==5
    assert result['axis_overrides']['x:min']['max']==9


def test_invalid_limits_show_error_without_writing_settings(monkeypatch):
    edit=registered()['edit_axis']
    identity={'type':'axis-inspector-min','axis':'x:min','owner':'raw:a'}
    monkeypatch.setattr(callbacks,'ctx',SimpleNamespace(triggered_id=identity))
    result,error=edit(['manual'],[9],[5],['linear'],[identity],{'_context_key':'raw:a'},'raw:a',None,'a')
    assert result is dash.no_update
    assert 'Minimum' in error


def test_numeric_fields_commit_on_enter_or_blur():
    cards=axis_cards([{'id':'x:min','label':'Time (min)','direction':'x','axes':['xaxis']}],
                     {'auto_range':False},'raw:a')
    minimum,maximum=cards[0].children[2].children
    assert minimum.debounce is True
    assert maximum.debounce is True
    assert minimum.disabled is False
