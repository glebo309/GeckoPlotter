import dash
import pytest

from components.paper_mock import create_paper_mock
from callbacks.publication_preview_callbacks import register_publication_preview_callbacks
from services.data_store import DataStore


def find(component, target):
    if getattr(component, 'id', None) == target:
        return component
    children = getattr(component, 'children', [])
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        found = find(child, target)
        if found is not None:
            return found


def test_publication_opens_in_paper_context_with_figure_view_optional():
    root = create_paper_mock()
    mode = find(root, 'pub-view-mode')
    assert mode.value == 'page'
    assert {item['value'] for item in mode.data} == {'page', 'figure'}
    assert find(root, 'pub-paper-container').style['display'] == 'flex'
    assert find(root, 'pub-figure-container').style['display'] == 'none'


@pytest.mark.parametrize('preset,paper,slide', [
    ('single-col', 'flex', 'none'), ('full-width', 'flex', 'none'),
    ('presentation', 'none', 'flex'),
])
def test_page_preview_presets_keep_journal_and_slide_context(preset, paper, slide):
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    callback = next(value['callback'].__wrapped__ for value in app.callback_map.values()
                    if value['inputs'] == [{'id': 'pub-preset', 'property': 'value'},
                                            {'id': 'pub-view-mode', 'property': 'value'}])
    paper_style, slide_style, editor_style = callback(preset, None)
    assert paper_style['display'] == paper
    assert slide_style['display'] == slide
    assert editor_style['display'] == 'none'
    paper_style, slide_style, editor_style = callback(preset, 'figure')
    assert paper_style['display'] == slide_style['display'] == 'none'
    assert editor_style['display'] == 'flex'


def test_a4_columns_and_figure_dimensions_use_one_physical_scale():
    from components.paper_mock import PAGE_SCREEN_WIDTH
    root = create_paper_mock()
    page = find(root, 'pub-paper-page')
    assert float(page.style['paddingLeft'].removesuffix('px')) == pytest.approx(PAGE_SCREEN_WIDTH * 18 / 210)
    assert float(find(root, 'pub-two-col-body').style['gap'].removesuffix('px')) == pytest.approx(PAGE_SCREEN_WIDTH * 6 / 210)
    app = dash.Dash(__name__)
    register_publication_preview_callbacks(app, DataStore())
    callback = next(value['callback'].__wrapped__ for value in app.callback_map.values()
                    if value['inputs'] == [{'id': 'pub-fig-width-mm', 'property': 'value'},
                                           {'id': 'pub-fig-height-mm', 'property': 'value'},
                                           {'id': 'pub-dpi', 'property': 'value'}])
    for width, height in [(84,63), (174,104), (80,60)]:
        slot, right, readout, slide = callback(width,height,300)
        assert float(slot['width'].removesuffix('px')) == pytest.approx(PAGE_SCREEN_WIDTH * width / 210)
        assert slot['aspectRatio'] == f'{width} / {height}'
        assert right.get('display') == ('none' if width > 84 else None)
        assert readout == f'{width} × {height} mm · 300 DPI'
