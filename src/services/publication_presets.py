"""Publication defaults sized for the visible panel layout."""
import math


def publication_pane_rows(figure, settings):
    if settings.get('layout_mode') != 'stacked':
        return 1
    traces = [t for t in (figure or {}).get('data', [])
              if not (t.get('fill') or str(t.get('name', '')).startswith(('peak:', '__deselect__'))
                      or 'baseline' in str(t.get('name', '')).lower())]
    return max(int(settings.get('subplot_rows') or 1),
               math.ceil(len(traces) / max(1, int(settings.get('subplot_cols') or 1))))


def publication_preset_settings(preset, pane_rows=1):
    rows = max(1, pane_rows)
    if preset == 'presentation':
        width, height, font, tick, title = 254, 143, 14, 14, 18
    elif preset == 'full-width':
        width, height, font, tick, title = 174, max(104, 28 * rows + 12), 10, 10, 13
    else:
        width, height, font, tick, title = 84, max(63, 30 * rows + 12), 8, 9, 11
    return dict(figure_width_mm=width, figure_height_mm=height,
                font_size=font, tick_font_size=tick, title_font_size=title)
