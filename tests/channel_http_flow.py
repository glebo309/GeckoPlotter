import sys,json,logging
from pathlib import Path
sys.path[:0]=['.','src','tests']
import app
from components.workspace_layout import walk
from services.workspace_loader import load_files
from callbacks.viz_callbacks import _get_overlay_group,_tab_id_from_group
from services.channel_visibility import channel_controls
client=app.app.server.test_client();client.get('/_dash-layout')
store=app._workspace_registry.for_session(client.get_cookie('gecko_sid').value)
if len(sys.argv) > 1:
 p=Path(sys.argv[1])
 r=load_files(store,[(f.name,f.read_bytes()) for f in p.iterdir() if f.suffix.lower() in ('.cdf','.csv')]);b=r.bundles[0]
else:
 from test_channel_visibility import signal
 from services.data_store import Bundle, BundleType, ComponentRole
 from ingestion.types import SourceCategory
 from services.channel_visibility import initialize_imported_channels
 b=Bundle('run','LC-MS run',BundleType.LCMS,component_list=[
  signal('uv250',250,ComponentRole.VWD_A,SourceCategory.LCMS_UV),
  signal('uv280',280,ComponentRole.VWD_B,SourceCategory.LCMS_UV),
  signal('pos',role=ComponentRole.MS_POSITIVE,category=SourceCategory.LCMS_MS),
  signal('neg',role=ComponentRole.MS_NEGATIVE,category=SourceCategory.LCMS_MS)])
 store.add_bundle(b);initialize_imported_channels(store,[b])
browser={}
for n in walk(app._layout_body):
 if isinstance(getattr(n,'id',None),str):
  for prop in ('data','value','checked','n_clicks'):browser[n.id+'.'+prop]=getattr(n,prop,None)
entry=store.get_data_by_id(b.bundle_id);group=_get_overlay_group(entry['metadata'],entry,b.bundle_id,store);tab=_tab_id_from_group(group)
browser.update({'active-file.data':b.primary.component_id,'active-plot-tab.data':tab,'loaded-files.data':store.get_loaded_files_list(),'plot-tabs.data':[{'id':tab,'type':'raw','group_key':list(group)}]})
controls=channel_controls(store,[b.bundle_id]);ids=[{'type':'group-channel-btn','group':tab,'channel':c['key']} for c in controls]
def invoke(name,changed,pattern=None):
 key,cb=next((k,c) for k,c in app.app.callback_map.items() if c.get('callback') and c['callback'].__wrapped__.__name__==name)
 def deps(items):return [{**d,'value':browser.get(d['id']+'.'+d['property'])} for d in items]
 outs=cb['output'];outs=[{'id':o.component_id,'property':o.component_property} for o in outs] if isinstance(outs,list) else {'id':outs.component_id,'property':outs.component_property}
 res=client.post('/_dash-update-component',json={'output':key,'outputs':outs,'inputs':pattern or deps(cb['inputs']),'state':deps(cb['state']),'changedPropIds':[changed]})
 assert res.status_code in (200,204),(name,res.status_code,res.get_data(as_text=True)[:500])
 payload=res.get_json() or {} if res.status_code==200 else {}
 for section in ('response','sideUpdate'):
  for comp,props in payload.get(section,{}).items():
   for prop,value in props.items():browser[comp+'.'+prop]=value
 return payload

def render():
 out=invoke('master_render','render-trigger.data')
 figure=browser.get('main-plot.figure',{});browser['main-inspector-context.data']=figure
 return [x.get('name') for x in figure.get('data',[]) if x.get('visible', True) is not False]
before=render()
for selected in ids:
 out=invoke('toggle_group_channel',json.dumps(selected,sort_keys=True,separators=(',',':'))+'.n_clicks',[[{'id':i,'property':'n_clicks','value':int(i==selected)} for i in ids]])
 after=render()
 assert after != before, selected
 browser['undo-trigger.data']=(browser.get('undo-trigger.data') or 0)+1
 invoke('handle_workspace_history','undo-trigger.data')
 assert render()==before, 'Undo did not restore the plotted channels'
 browser['redo-trigger.data']=(browser.get('redo-trigger.data') or 0)+1
 invoke('handle_workspace_history','redo-trigger.data')
 assert render()==after, 'Redo did not restore the plotted channels'
 before=after
 print('PASS channel click, plot refresh, undo and redo:',selected['channel'])
