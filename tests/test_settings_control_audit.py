"""Exercise every shared toolbox control through its real Dash callback."""
from types import SimpleNamespace
import dash
import pytest
from callbacks import plot_settings_callbacks as callbacks
from services.data_store import DataStore

CONTROLS = [
 ('pt-smooth-window','smooth_window',9),('pt-plot-type','plot_type','scatter'),
 ('pt-auto-range','auto_range',False),('pt-categorical-x','categorical_x',False),
 ('pt-x-min','x_min',6),('pt-x-max','x_max',8),('pt-y-min','y_min',0),('pt-y-max','y_max',100),
 ('pt-x-scale','x_scale','log'),('pt-y-scale','y_scale','log'),('pt-theme','theme','plotly_dark'),
 ('pt-palette','palette','d3'),('pt-bg-color','bg_color','#abcdef'),('pt-paper-color','paper_color','#fedcba'),
 ('pt-line-width','line_width',2.5),('pt-marker-size','marker_size',8),('pt-line-style','line_style','dash'),
 ('pt-marker-symbol','marker_symbol','diamond'),('pt-trace-opacity','trace_opacity',.6),
 ('pt-bar-gap','bar_gap',.4),('pt-bar-group-gap','bar_group_gap',.3),
 ('pt-title','title','My figure'),('pt-font','font','Verdana'),('pt-font-size','font_size',11),
 ('pt-title-font-size','title_font_size',15),('pt-tick-font-size','tick_font_size',12),
 ('pt-bold-title','bold_title',False),('pt-show-legend','show_legend',False),
 ('pt-legend-pos','legend_pos','bottom-left'),('pt-tick-dir','tick_direction','inside'),
 ('pt-grid-style','grid_style','dot'),('pt-frame-width','frame_width',2),('pt-tick-length','tick_length',8),
 ('pt-layout-mode','layout_mode','stacked'),('pt-shared-axis-labels','shared_axis_labels',False),
 ('pt-x-label','x_label','Time'),('pt-y-label','y1_label','Signal'),('pt-subplot-spacing','subplot_spacing',.15),
 ('pub-subplot-rows','subplot_rows',2),('pub-subplot-cols','subplot_cols',2),
 ('pub-fig-width-mm','figure_width_mm',174.5),('pub-fig-height-mm','figure_height_mm',120.5),
 ('pub-preset','pub_preset','presentation'),('pub-dpi','pub_dpi',600),
 ('pub-export-format','export_format','svg'),('pub-zoom-sync','link_x',False),('plot-y-scope','y_scope','global'),
]

@pytest.mark.parametrize('control,key,value',CONTROLS)
def test_control_changes_are_owned_by_the_active_figure_and_restored(monkeypatch,control,key,value):
 store=DataStore(); store._shared_plot_settings={}
 app=dash.Dash(__name__);callbacks.register_plot_settings_callbacks(app,store)
 hydrate=next(c for c in app.callback_map.values() if c.get('callback') and c['callback'].__wrapped__.__name__=='hydrate_plot_settings')
 edit=next(c for c in app.callback_map.values() if c.get('callback') and c['callback'].__wrapped__.__name__=='user_edit_settings')
 initial=hydrate['callback'].__wrapped__('shared:raw:publication-a',None)
 outputs=hydrate['output']; values={o.component_id:v for o,v in zip(outputs,initial)}
 current=initial[0]
 values[control]=value
 monkeypatch.setattr(callbacks,'callback_context',SimpleNamespace(triggered=[{'prop_id':control+'.value'}]))
 changed=edit['callback'].__wrapped__(*[values.get(i['id']) for i in edit['inputs']],current)
 assert changed[key] == value
 assert changed['_context_key']=='shared:raw:publication-a'
 callbacks._save_settings(store,changed['_context_key'],changed)
 restored=hydrate['callback'].__wrapped__('shared:raw:publication-a',None)
 assert restored[0][key] == value
 assert {o.component_id:v for o,v in zip(outputs,restored)}[control] == value
 other=hydrate['callback'].__wrapped__('shared:raw:publication-b',None)[0]
 assert other['_context_key']=='shared:raw:publication-b'


def test_theme_selection_updates_visible_background_controls():
 app=dash.Dash(__name__); callbacks.register_plot_settings_callbacks(app,DataStore())
 cb=next(c['callback'].__wrapped__ for c in app.callback_map.values() if c.get('callback') and c['callback'].__wrapped__.__name__=='apply_theme_controls')
 bg,paper,opts=cb('plotly_dark',{'theme':'plotly_white'},['ticks','frame'])
 assert bg == paper == '#111111'
 assert 'ticks' in opts
