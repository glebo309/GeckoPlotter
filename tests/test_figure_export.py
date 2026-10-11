import base64
import copy
from unittest.mock import patch

import plotly.graph_objects as go
import pytest

from services.figure_export import export_displayed_figure


def test_export_preserves_displayed_ranges_margins_and_scales_to_actual_dpi():
    figure = {'data': [{'x': [0, 10], 'y': [0, 100], 'type': 'scatter'}],
              'layout': {'xaxis': {'range': [6, 9], 'autorange': False},
                         'margin': {'l': 18, 'r': 12, 't': 12, 'b': 18}}}
    original = copy.deepcopy(figure)
    seen = {}
    def render(fig, **kwargs):
        seen.update(kwargs, figure=fig.to_dict())
        return b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400" viewBox="0 0 600 400"></svg>'
    with patch.object(go.Figure, 'to_image', render):
        result = export_displayed_figure(figure, 'svg', 84, 56, 300, 600, 'control / 10 mM')
    assert seen['figure']['layout']['xaxis']['range'] == [6, 9]
    assert seen['figure']['layout']['margin']['l'] == 18
    assert seen['width'] == 600 and seen['height'] == 400
    assert b'width="84mm"' in base64.b64decode(result['content'])
    assert result['filename'] == 'control-10-mM.svg'
    assert figure == original


def test_raster_export_uses_dpi_once_and_embeds_resolution():
    import io
    from PIL import Image
    seen = {}
    def render(fig, **kwargs):
        seen.update(kwargs)
        buf = io.BytesIO()
        Image.new('RGB', (992, 743)).save(buf, 'PNG')
        return buf.getvalue()
    with patch.object(go.Figure, 'to_image', render):
        result = export_displayed_figure({'data': []}, 'png', 84, 63, 300, 307)
    assert seen['scale'] == pytest.approx(84 * 300 / 25.4 / 307)
    image = Image.open(io.BytesIO(base64.b64decode(result['content'])))
    assert image.size == (992, 744)
    assert image.info['dpi'][0] == pytest.approx(300, abs=.1)


def test_pdf_physical_size_does_not_depend_on_raster_dpi():
    with patch.object(go.Figure, 'to_image', return_value=b'pdf') as render:
        export_displayed_figure({'data': []}, 'pdf', 84, 63, 1200, 307)
    assert render.call_args.kwargs['scale'] == pytest.approx(84 * 96 / 25.4 / 307)
