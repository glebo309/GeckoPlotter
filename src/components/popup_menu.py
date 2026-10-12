"""Plain-HTML popup menus.

Mantine's Menu family is flagged ``dashChildrenUpdate``. For every such component Dash's renderer rescans every
layout path on every store update, which made each callback in this app cost several times more (about 45% of all
renderer time while loading data). These menus are opened and closed by toggling ``hidden``.
"""
from dash import html


def popup_menu(menu_id, items):
    """A menu positioned by its (fixed) anchor; closed by default, shown with ``hidden=False``."""
    return html.Div(items, id=menu_id, className='gecko-menu', role='menu', hidden=True)


def menu_item(label, **kwargs):
    kwargs.setdefault('n_clicks', 0)
    return html.Button(label, type='button', role='menuitem', className='gecko-menu-item', **kwargs)


def menu_divider():
    return html.Div(className='gecko-menu-divider', role='separator')
