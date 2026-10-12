import plotly.graph_objects as go
from services.plot_settings_service import PlotSettingsService


def test_free_legend_position_and_type_size_survive_render():
    fig = go.Figure(go.Scatter(x=[0, 1], y=[1, 2]))
    settings = PlotSettingsService.from_dict({'legend_font_size': 18,
        'legend_positions': {'legend': {'x': .35, 'y': .65, 'xanchor': 'left', 'yanchor': 'top'}}})
    PlotSettingsService.apply_to_figure(fig, settings)
    assert fig.layout.legend.x == .35
    assert fig.layout.legend.y == .65
    assert fig.layout.legend.font.size == 18


def test_hiding_source_removes_its_peak_from_publication_snapshot():
    from services.legend_visibility import apply_file_visibility
    fig=go.Figure([
        go.Scatter(x=[0,1],y=[0,2],meta={'file_id':'a'}),
        go.Scatter(x=[0,1,0],y=[0,2,0],fill='toself',meta='peak_overlay',customdata=['p']*3),
        go.Scatter(x=[0,1],y=[1,3],meta={'file_id':'b'})])
    fig.update_layout(meta={'gecko_peak_geometry':{'p':{'file_id':'a'}}})
    apply_file_visibility(fig,{'a':False})
    assert len(fig.data)==1
    assert fig.data[0].meta['file_id']=='b'
