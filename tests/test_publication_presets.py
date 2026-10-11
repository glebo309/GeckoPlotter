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


def test_publication_axes_use_compact_gaps_without_changing_user_font_sizes():
    source = {'data':[{'x':[0,1], 'y':[0,1], 'name':'Signal'}],
              'layout': {'xaxis':{'title':{'text':'Time (min)'}},
                         'yaxis':{'title':{'text':'Absorbance (mAU)'}}}}
    for preset in ['single-col','full-width','presentation']:
        settings = publication_preset_settings(preset)
        figure = editable_publication_figure(source, settings)
        assert figure.layout.xaxis.title.standoff <= 3
        assert figure.layout.yaxis.title.standoff <= 3
        assert figure.layout.margin.r <= 5
        assert figure.layout.margin.b <= 5
        assert figure.layout.yaxis.tickfont.size == settings['tick_font_size']


def test_slide_plot_column_uses_remaining_space_instead_of_shrinking_to_content():
    from components.paper_mock import create_paper_mock
    from test_publication_page_view import find
    slide = find(create_paper_mock(), 'pub-slide-chart-column')
    assert slide is not None
    assert slide.style['minWidth'] == 0
    assert slide.style['flex'] == '1 1 0'
    notes = find(create_paper_mock(), 'pub-slide-notes')
    assert notes.style['flex'] == '0 0 150px'
