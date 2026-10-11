import plotly.graph_objects as go
import pytest
from services.plot_settings_service import PlotSettingsService, DEFAULT_PLOT_SETTINGS


def render(settings=None, fig=None):
 fig = fig or go.Figure(go.Scatter(x=[1,2,3],y=[1,4,2],mode='lines+markers',name='Signal'))
 s={**DEFAULT_PLOT_SETTINGS, **(settings or {})}
 PlotSettingsService.apply_to_figure(fig, PlotSettingsService.from_dict(dict(s,y_label=s.get('y1_label'))))
 return fig


@pytest.mark.parametrize('setting,value,read', [
 ('x_scale','log',lambda f:f.layout.xaxis.type),('y_scale','log',lambda f:f.layout.yaxis.type),
 ('bg_color','#abcdef',lambda f:f.layout.plot_bgcolor),('paper_color','#fedcba',lambda f:f.layout.paper_bgcolor),
 ('line_width',3.5,lambda f:f.data[0].line.width),('line_style','dash',lambda f:f.data[0].line.dash),
 ('marker_size',11,lambda f:f.data[0].marker.size),('marker_symbol','diamond',lambda f:f.data[0].marker.symbol),
 ('trace_opacity',.3,lambda f:f.data[0].opacity),('bar_gap',.4,lambda f:f.layout.bargap),
 ('bar_group_gap',.3,lambda f:f.layout.bargroupgap),('font','Verdana',lambda f:f.layout.font.family),
 ('font_size',11,lambda f:f.layout.legend.font.size),('title_font_size',17,lambda f:f.layout.title.font.size),
 ('tick_font_size',11,lambda f:f.layout.xaxis.tickfont.size),('show_legend',False,lambda f:f.layout.legend.visible),
 ('show_grid_x',True,lambda f:f.layout.xaxis.showgrid),('show_grid_y',True,lambda f:f.layout.yaxis.showgrid),
 ('tick_direction','inside',lambda f:f.layout.xaxis.ticks),('tick_length',8,lambda f:f.layout.yaxis.ticklen),
 ('frame_width',2,lambda f:f.layout.xaxis.linewidth),('show_frame',False,lambda f:f.layout.yaxis.showline),
 ('grid_style','dot',lambda f:f.layout.xaxis.griddash),('x_label','Minutes',lambda f:f.layout.xaxis.title.text),
 ('y1_label','My signal',lambda f:f.layout.yaxis.title.text),
])
def test_every_style_control_reaches_the_rendered_figure(setting,value,read):
 assert read(render({setting:value})) == value


def test_opacity_can_restore_full_opacity_on_captured_source():
 fig=render({'trace_opacity':.3})
 assert render({'trace_opacity':1},fig).data[0].opacity == 1


def test_y_label_and_font_can_override_captured_axis():
 fig=go.Figure(go.Scatter(x=[1,2],y=[2,3]))
 fig.update_yaxes(title=dict(text='Old unit',font=dict(size=30)))
 result=render({'y1_label':'New label','tick_font_size':9},fig)
 assert result.layout.yaxis.title.text == 'New label'
 assert result.layout.yaxis.title.font.size == 9


def test_disabling_categorical_ticks_removes_stale_tick_mapping():
 fig=go.Figure(go.Scatter(x=[1,2],y=[2,3]))
 fig.update_xaxes(tickmode='array',tickvals=[1,2],ticktext=['A','B'])
 result=render({'categorical_x':False},fig)
 assert result.layout.xaxis.tickmode == 'auto'
 assert result.layout.xaxis.ticktext is None


def test_dark_theme_sets_legible_neutral_axis_and_legend_text():
 fig=render({'theme':'plotly_dark','bg_color':'#111111','paper_color':'#111111'})
 assert fig.layout.font.color == '#f2f5fa'
 assert fig.layout.xaxis.color == '#f2f5fa'
 assert fig.layout.legend.bgcolor != 'rgba(255,255,255,0.85)'


def test_log_axis_limits_are_entered_in_data_units():
 fig=render({'auto_range':False,'x_scale':'log','x_min':10,'x_max':1000})
 assert list(fig.layout.xaxis.range)==[1,3]
