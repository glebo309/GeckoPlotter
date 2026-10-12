"""Client reduction must preserve the complete visible inspector behaviour."""
import json
import subprocess
from copy import deepcopy

from services.axis_inspector import axis_descriptors
from services.axis_labels import sync_automatic_labels
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
from callbacks.workspace_callbacks import register_workspace_callbacks


def test_compact_client_context_has_same_axes_labels_signal_style_and_capabilities(monkeypatch):
    figure = {'data': [
        {'name':'Sample · 250 nm','type':'scatter','x':list(range(3000)), 'y':[2]*3000,
         'meta':{'file_id':'channel','pda_preview':True}, 'line':{'color':'#112233','width':2,'dash':'dot'},
         'marker':{'color':'#445566','size':[5]*3000}, 'opacity':.5},
        {'name':'peak:one','fill':'toself','x':[1,2,3],'y':[1,2,1]}],
        'layout':{'xaxis':{'title':{'text':'Time (min)'}}, 'yaxis':{'title':{'text':'Absorbance (mAU)'}},
                  'meta':{'gecko_tab_id':'raw','gecko_axis_units':{'xaxis':'Time (min)','yaxis':'Absorbance (mAU)'}}}}
    script = """const fs=require('node:fs'),vm=require('node:vm');
    global.window={dash_clientside:{no_update:null}};
    vm.runInThisContext(fs.readFileSync('src/assets/js/inspector-context.js','utf8'));
    console.log(JSON.stringify(window.dash_clientside.inspectorContext.summarize(JSON.parse(fs.readFileSync(0,'utf8')),null)));
    """
    compact = json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(figure).encode()))
    settings={**DEFAULT_PLOT_SETTINGS,'_context_key':'shared:raw:raw'}
    assert axis_descriptors(compact) == axis_descriptors(figure)
    assert sync_automatic_labels(settings,compact) == sync_automatic_labels(settings,figure)
    class App:
        functions={}
        def callback(self,*args,**kwargs):
            def wrap(fn): self.functions[fn.__name__]=fn; return fn
            return wrap
        def clientside_callback(self,*args,**kwargs):pass
    app=App();register_workspace_callbacks(app,None)
    describe=app.functions['describe_figure']
    rest=(None,'raw',[{'id':'raw','type':'raw','label':'Chromatograms'}],settings,None)
    compact_result, full_result = describe(deepcopy(compact),*rest), describe(deepcopy(figure),*rest)
    assert compact_result[:5] + compact_result[6:] == full_result[:5] + full_result[6:]
    # The complete hydrated style UI is identical, without unused marker-size arrays.
    from types import SimpleNamespace
    import callbacks.workspace_callbacks as callbacks
    monkeypatch.setattr(callbacks, 'ctx', SimpleNamespace(triggered_id='signal-inspector-options', triggered=[]))
    style=app.functions['signal_style']
    assert style(compact_result[4],compact_result[5],settings,None,None,None,None,0,None) == style(full_result[4],full_result[5],settings,None,None,None,None,0,None)
    assert len(json.dumps(compact)) < len(json.dumps(figure))/20
