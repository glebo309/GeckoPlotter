from services.publication_presets import publication_preset_settings
from services.figure_actions import publication_snapshot
from services.publication_figure import editable_publication_figure


def test_single_column_preset_gives_separate_panes_room_and_readable_type():
    style = publication_preset_settings('single-col', 4)
    assert style['figure_width_mm'] == 84
    assert style['figure_height_mm'] >= 120
    assert style['tick_font_size'] <= 10
    assert style['font_size'] <= 10
    assert publication_preset_settings('single-col', 1)['figure_height_mm'] == 63


def test_publication_initial_defaults_fit_source_panes_without_changing_layout():
    fig = {'data':[{'x':[0,1],'y':[0,1],'yaxis':'y'}, {'x':[0,1],'y':[0,2],'yaxis':'y2'}],
           'layout':{'yaxis':{'domain':[.55,1]},'yaxis2':{'domain':[0,.45]}}}
    _, key, entries = publication_snapshot(fig,[],{},plot_settings={'layout_mode':'stacked'})
    settings = entries[key]['plot_settings']
    assert settings['layout_mode'] == 'stacked'
    assert settings['figure_height_mm'] >= 72
    assert settings['tick_font_size'] <= 10
