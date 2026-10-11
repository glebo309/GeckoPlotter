"""Export the displayed figure without rebuilding data or replacing its styling."""
import base64
import io
import re

import plotly.graph_objects as go


def export_displayed_figure(figure, fmt, width_mm, height_mm, dpi=300,
                            render_width=624, label='figure'):
    """Keep the viewport and relative typography; apply physical output size once."""
    fmt = fmt or 'png'
    if fmt not in {'png', 'svg', 'pdf', 'tiff', 'html'}:
        raise ValueError('Choose PNG, SVG, PDF, TIFF or HTML.')
    width_mm, height_mm = max(1, float(width_mm)), max(1, float(height_mm))
    dpi = max(72, min(1200, int(dpi or 300)))
    width = max(100, int(render_width or 624))
    height = max(1, round(width * height_mm / width_mm))
    fig = go.Figure(figure)
    fig.update_layout(autosize=False, width=width, height=height)
    name = re.sub(r'[^\w.-]+', '-', str(label or 'figure')).strip('-')[:100] or 'figure'
    if fmt == 'html':
        return {'content': fig.to_html(include_plotlyjs=True), 'filename': f'{name}.html'}
    if fmt == 'svg':
        content = fig.to_image(format='svg', width=width, height=height)
        # SVG is vector: declare physical size, preserving its native viewBox.
        content = re.sub(rb'(<svg\b[^>]*?)\bwidth="[^"]*"',
                         lambda m: m[1] + f'width="{width_mm:g}mm"'.encode(), content, count=1)
        content = re.sub(rb'(<svg\b[^>]*?)\bheight="[^"]*"',
                         lambda m: m[1] + f'height="{height_mm:g}mm"'.encode(), content, count=1)
    else:
        resolution = 96 if fmt == 'pdf' else dpi
        scale = width_mm * resolution / 25.4 / width
        content = fig.to_image(format='pdf' if fmt == 'pdf' else 'png',
                               width=width, height=height, scale=scale)
        if fmt in {'png', 'tiff'}:
            from PIL import Image
            image = Image.open(io.BytesIO(content))
            target_size = (round(width_mm * dpi / 25.4), round(height_mm * dpi / 25.4))
            if image.size != target_size:
                image = image.resize(target_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            options = {'compression': 'tiff_lzw'} if fmt == 'tiff' else {}
            image.save(output, format='TIFF' if fmt == 'tiff' else 'PNG', dpi=(dpi, dpi), **options)
            content = output.getvalue()
    return {'content': base64.b64encode(content).decode(),
            'filename': f'{name}.{fmt}', 'base64': True}
