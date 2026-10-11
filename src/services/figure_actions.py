"""Create independent publication views from any displayed figure."""
from copy import deepcopy
from uuid import uuid4
import re


def publication_plot_settings(figure, settings=None):
    """Carry source settings, using the clicked figure's actual pane layout."""
    settings = deepcopy(settings or {})
    domains = {tuple(axis.get('domain', [0, 1]))
               for key, axis in (figure.get('layout') or {}).items()
               if re.fullmatch(r'yaxis\d*', key) and isinstance(axis, dict)}
    settings['layout_mode'] = 'stacked' if len(domains) > 1 else 'overlay'
    return settings


def publication_snapshot(figure, tabs, figures, label='Plot', plot_settings=None):
    from services.figure_sanitization import clean_figure_for_output
    figure = clean_figure_for_output(figure)
    index = 1 + sum(tab.get('type') == 'publication' for tab in (tabs or []))
    tab_id = f'publication-{index}-{uuid4().hex[:8]}'
    tab = {'id': tab_id, 'label': f'Publication {index}', 'type': 'publication'}
    from services.publication_presets import publication_preset_settings, publication_pane_rows
    from services.plot_settings_service import DEFAULT_PLOT_SETTINGS
    settings = publication_plot_settings(figure, plot_settings)
    defaults = publication_preset_settings(settings.get('pub_preset', 'single-col'),
                                          publication_pane_rows(figure, settings))
    for name, value in defaults.items():
        if name not in settings or settings[name] == DEFAULT_PLOT_SETTINGS.get(name):
            settings[name] = value
    entry = {'figure': deepcopy(figure), 'source_label': label,
             'plot_settings': settings}
    return [*(tabs or []), tab], tab_id, {**(figures or {}), tab_id: entry}
