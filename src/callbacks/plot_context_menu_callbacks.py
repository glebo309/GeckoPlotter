"""Right-click plot customization panel callbacks.

Proof of concept: right-clicking the main plot X-axis opens a small editor
that reads and writes the same ``current-plot-settings`` state as the Plot
Settings toolbox.
"""

import copy

import dash
from dash import Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

from services.plot_settings_service import DEFAULT_PLOT_SETTINGS


_PANEL_BASE = {
    'position': 'fixed',
    'zIndex': 4050,
}

_HIDDEN = {'display': 'none'}


def _triggered_id():
    if not callback_context.triggered:
        return None
    return callback_context.triggered[0]['prop_id'].split('.')[0]


def _axis_panel_style(store):
    x = float(store.get('x') or 0)
    y = float(store.get('y') or 0)
    vw = float(store.get('viewport_width') or 1200)
    vh = float(store.get('viewport_height') or 800)

    # Approximate panel size; keeps the menu from spilling off-screen.
    panel_w = 260
    panel_h = 170
    left = min(max(8, x), max(8, vw - panel_w - 8))
    top = min(max(8, y), max(8, vh - panel_h - 8))

    return {
        **_PANEL_BASE,
        'display': 'block',
        'left': f'{left}px',
        'top': f'{top}px',
    }


def _settings(settings):
    return {**DEFAULT_PLOT_SETTINGS, **(settings or {})}


def _range_row_state(auto_range):
    disabled = bool(auto_range)
    return (
        {
            'display': 'flex',
            'gap': '8px',
            'marginTop': '4px',
            'opacity': 0.45 if disabled else 1,
        },
        disabled,
        disabled,
    )


def register_plot_context_menu_callbacks(app: dash.Dash, data_manager) -> None:
    """Register the right-click plot customization proof of concept."""

    @app.callback(
        [
            Output('axis-context-panel', 'style'),
            Output('axis-ctx-title', 'children'),
            Output('axis-ctx-auto-range', 'checked'),
            Output('axis-ctx-x-min', 'value'),
            Output('axis-ctx-x-max', 'value'),
        ],
        [
            Input('axis-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('axis-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_axis_panel(store, settings, panel_style):
        """Open the X-axis panel, or keep it synced while already open."""
        trig = _triggered_id()
        s = _settings(settings)

        if trig == 'axis-context-menu-store':
            if not store or store.get('axis') != 'x':
                raise PreventUpdate
            style = _axis_panel_style(store)
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update

        return (
            style,
            'X-axis',
            bool(s.get('auto_range', True)),
            s.get('x_min'),
            s.get('x_max'),
        )

    @app.callback(
        Output('axis-context-panel', 'style', allow_duplicate=True),
        Input('axis-context-menu-close-store', 'data'),
        prevent_initial_call=True,
    )
    def close_axis_panel(close_event):
        if not close_event:
            raise PreventUpdate
        return _HIDDEN

    @app.callback(
        [
            Output('axis-ctx-range-row', 'style'),
            Output('axis-ctx-x-min', 'disabled'),
            Output('axis-ctx-x-max', 'disabled'),
        ],
        Input('axis-ctx-auto-range', 'checked'),
    )
    def update_axis_range_state(auto_range):
        return _range_row_state(auto_range)

    @app.callback(
        Output('current-plot-settings', 'data', allow_duplicate=True),
        [
            Input('axis-ctx-auto-range', 'checked'),
            Input('axis-ctx-x-min', 'value'),
            Input('axis-ctx-x-max', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('axis-context-panel', 'style'),
        ],
        prevent_initial_call=True,
    )
    def edit_x_axis_from_context(auto_range, x_min, x_max, current_settings, panel_style):
        """Write X-axis context edits into the same store as Plot Settings."""
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update

        s = _settings(current_settings)
        new_settings = copy.deepcopy(s)
        new_settings['auto_range'] = bool(auto_range)
        new_settings['x_min'] = x_min
        new_settings['x_max'] = x_max

        if new_settings == s:
            return dash.no_update

        return new_settings

    @app.callback(
        [
            Output('pt-auto-range', 'checked', allow_duplicate=True),
            Output('pt-x-min', 'value', allow_duplicate=True),
            Output('pt-x-max', 'value', allow_duplicate=True),
        ],
        Input('current-plot-settings', 'data'),
        State('axis-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def sync_toolbox_axis_controls(settings, panel_style):
        """Mirror context-menu edits into the visible Plot Settings controls."""
        if not panel_style or panel_style.get('display') == 'none':
            raise PreventUpdate
        s = _settings(settings)
        return (
            bool(s.get('auto_range', True)),
            s.get('x_min'),
            s.get('x_max'),
        )
