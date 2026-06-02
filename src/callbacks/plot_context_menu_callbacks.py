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


def _axis_panel_style(store, panel_h=360):
    x = float(store.get('x') or 0)
    y = float(store.get('y') or 0)
    vw = float(store.get('viewport_width') or 1200)
    vh = float(store.get('viewport_height') or 800)

    # Approximate panel size; keeps the menu from spilling off-screen.
    panel_w = 260
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


def _layout_opts(s):
    opts = []
    if s.get('show_grid_x', True):
        opts.append('grid_x')
    if s.get('show_grid_y', True):
        opts.append('grid_y')
    if s.get('show_tick_marks', True):
        opts.append('ticks')
    if s.get('show_minor_ticks', False):
        opts.append('minor_ticks')
    if s.get('show_frame', True):
        opts.append('frame')
    return opts


def _axis_values(s, axis):
    axis = axis if axis in ('x', 'y') else 'x'
    prefix = 'x' if axis == 'x' else 'y'
    return {
        'title': 'X-axis' if axis == 'x' else 'Y-axis',
        'min_label': f'{prefix.upper()} min',
        'max_label': f'{prefix.upper()} max',
        'min': s.get(f'{prefix}_min'),
        'max': s.get(f'{prefix}_max'),
        'label': s.get('x_label') if axis == 'x' else s.get('y1_label'),
        'scale': s.get(f'{prefix}_scale', 'linear'),
        'grid': s.get('show_grid_x', False) if axis == 'x' else s.get('show_grid_y', False),
    }


def _active_axis(store):
    if store and store.get('axis') in ('x', 'y'):
        return store.get('axis')
    return 'x'


def register_plot_context_menu_callbacks(app: dash.Dash, data_manager) -> None:
    """Register the right-click plot customization proof of concept."""

    @app.callback(
        [
            Output('axis-context-panel', 'style'),
            Output('axis-ctx-title', 'children'),
            Output('axis-ctx-min-label', 'children'),
            Output('axis-ctx-max-label', 'children'),
            Output('axis-ctx-auto-range', 'checked'),
            Output('axis-ctx-x-min', 'value'),
            Output('axis-ctx-x-max', 'value'),
            Output('axis-ctx-scale', 'value'),
            Output('axis-ctx-grid', 'checked'),
            Output('axis-ctx-minor-ticks', 'checked'),
            Output('axis-ctx-tick-dir', 'value'),
            Output('axis-ctx-tick-length', 'value'),
        ],
        [
            Input('axis-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('axis-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_axis_panel(store, settings, panel_style):
        """Open the axis panel, or keep it synced while already open."""
        trig = _triggered_id()
        s = _settings(settings)
        axis = _active_axis(store)

        if trig == 'axis-context-menu-store':
            if not store or store.get('axis') not in ('x', 'y'):
                raise PreventUpdate
            style = _axis_panel_style(store)
            axis = store.get('axis')
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update

        vals = _axis_values(s, axis)
        return (
            style,
            vals['title'],
            vals['min_label'],
            vals['max_label'],
            bool(s.get('auto_range', True)),
            vals['min'],
            vals['max'],
            vals['scale'],
            bool(vals['grid']),
            bool(s.get('show_minor_ticks', False)),
            s.get('tick_direction', 'outside'),
            s.get('tick_length', 5),
        )

    @app.callback(
        Output('axis-context-panel', 'style', allow_duplicate=True),
        [
            Input('axis-context-menu-close-store', 'data'),
            Input('axis-ctx-close', 'n_clicks'),
        ],
        prevent_initial_call=True,
    )
    def close_axis_panel(close_event, close_clicks):
        if not close_event and not close_clicks:
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
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('zoom-state', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
        ],
        [
            Input('axis-ctx-auto-range', 'checked'),
            Input('axis-ctx-x-min', 'value'),
            Input('axis-ctx-x-max', 'value'),
            Input('axis-ctx-scale', 'value'),
            Input('axis-ctx-grid', 'checked'),
            Input('axis-ctx-minor-ticks', 'checked'),
            Input('axis-ctx-tick-dir', 'value'),
            Input('axis-ctx-tick-length', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('axis-context-panel', 'style'),
            State('axis-context-menu-store', 'data'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def edit_axis_from_context(auto_range, axis_min, axis_max,
                               axis_scale, grid, minor_ticks, tick_dir,
                               tick_length,
                               current_settings, panel_style,
                               store, render_counter):
        """Write axis context edits into the same store as Plot Settings."""
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update, dash.no_update, dash.no_update

        s = _settings(current_settings)
        axis = _active_axis(store)
        prefix = 'x' if axis == 'x' else 'y'
        new_settings = copy.deepcopy(s)
        new_settings['auto_range'] = bool(auto_range)
        new_settings[f'{prefix}_min'] = axis_min
        new_settings[f'{prefix}_max'] = axis_max
        new_settings[f'{prefix}_scale'] = axis_scale or 'linear'
        if axis == 'x':
            new_settings['show_grid_x'] = bool(grid)
        else:
            new_settings['show_grid_y'] = bool(grid)
        new_settings['show_minor_ticks'] = bool(minor_ticks)
        new_settings['tick_direction'] = tick_dir or 'outside'
        new_settings['tick_length'] = tick_length if tick_length is not None else 5

        if new_settings == s:
            return dash.no_update, dash.no_update, dash.no_update

        return new_settings, None, (render_counter or 0) + 1

    @app.callback(
        [
            Output('pt-auto-range', 'checked', allow_duplicate=True),
            Output('pt-x-min', 'value', allow_duplicate=True),
            Output('pt-x-max', 'value', allow_duplicate=True),
            Output('pt-y-min', 'value', allow_duplicate=True),
            Output('pt-y-max', 'value', allow_duplicate=True),
            Output('pt-x-label', 'value', allow_duplicate=True),
            Output('pt-y-label', 'value', allow_duplicate=True),
            Output('pt-x-scale', 'value', allow_duplicate=True),
            Output('pt-y-scale', 'value', allow_duplicate=True),
            Output('pt-layout-opts', 'value', allow_duplicate=True),
            Output('pt-tick-dir', 'value', allow_duplicate=True),
            Output('pt-tick-length', 'value', allow_duplicate=True),
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
            s.get('y_min'),
            s.get('y_max'),
            s.get('x_label'),
            s.get('y1_label'),
            s.get('x_scale', 'linear'),
            s.get('y_scale', 'linear'),
            _layout_opts(s),
            s.get('tick_direction', 'outside'),
            s.get('tick_length', 5),
        )

    @app.callback(
        [
            Output('legend-context-panel', 'style'),
            Output('legend-ctx-show', 'checked'),
            Output('legend-ctx-pos', 'value'),
        ],
        [
            Input('legend-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('legend-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_legend_panel(store, settings, panel_style):
        """Open the legend panel, or keep it synced while already open."""
        trig = _triggered_id()
        s = _settings(settings)

        if trig == 'legend-context-menu-store':
            if not store:
                raise PreventUpdate
            style = _axis_panel_style(store, panel_h=160)
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update

        return (
            style,
            bool(s.get('show_legend', True)),
            s.get('legend_pos', 'top-right'),
        )

    @app.callback(
        Output('legend-context-panel', 'style', allow_duplicate=True),
        [
            Input('legend-context-menu-close-store', 'data'),
            Input('legend-ctx-close', 'n_clicks'),
        ],
        prevent_initial_call=True,
    )
    def close_legend_panel(close_event, close_clicks):
        if not close_event and not close_clicks:
            raise PreventUpdate
        return _HIDDEN

    @app.callback(
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
        ],
        [
            Input('legend-ctx-show', 'checked'),
            Input('legend-ctx-pos', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('legend-context-panel', 'style'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def edit_legend_from_context(show_legend, legend_pos, current_settings,
                                 panel_style, render_counter):
        """Write legend context edits into the same store as Plot Settings."""
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update, dash.no_update

        s = _settings(current_settings)
        new_settings = copy.deepcopy(s)
        new_settings['show_legend'] = bool(show_legend)
        new_settings['legend_pos'] = legend_pos or 'top-right'

        if new_settings == s:
            return dash.no_update, dash.no_update

        return new_settings, (render_counter or 0) + 1

    @app.callback(
        [
            Output('pt-show-legend', 'checked', allow_duplicate=True),
            Output('pt-legend-pos', 'value', allow_duplicate=True),
        ],
        Input('current-plot-settings', 'data'),
        State('legend-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def sync_toolbox_legend_controls(settings, panel_style):
        """Mirror legend context-menu edits into Plot Settings controls."""
        if not panel_style or panel_style.get('display') == 'none':
            raise PreventUpdate
        s = _settings(settings)
        return (
            bool(s.get('show_legend', True)),
            s.get('legend_pos', 'top-right'),
        )

    # ------------------------------------------------------------------
    # Trace context menu
    # ------------------------------------------------------------------

    def _trace_defaults(s):
        """Global trace defaults from current settings."""
        return {
            'color': '#E69F00',
            'line_width': s.get('line_width', 1.5),
            'line_style': s.get('line_style', 'solid'),
            'opacity': s.get('trace_opacity', 1.0),
            'marker_size': s.get('marker_size', 6),
            'marker_symbol': s.get('marker_symbol', 'circle'),
        }

    def _trace_current_color(s, trace_name):
        """Get the current color assigned to a trace by palette position."""
        from services.plot_settings_service import PlotSettingsService
        palette = PlotSettingsService.get_color_palette(s.get('palette', 'okabe_ito'))
        overrides = s.get('trace_overrides') or {}
        ov = overrides.get(trace_name, {})
        if 'color' in ov:
            return ov['color']
        return palette[0]

    def _mode_section_styles(mode):
        has_lines = 'lines' in (mode or 'lines')
        has_markers = 'markers' in (mode or 'lines')
        line_style = {'marginTop': '8px'} if has_lines else {'marginTop': '8px', 'display': 'none'}
        marker_style = {'marginTop': '8px'} if has_markers else {'marginTop': '8px', 'display': 'none'}
        return line_style, marker_style

    @app.callback(
        [
            Output('trace-context-panel', 'style'),
            Output('trace-ctx-title', 'children'),
            Output('trace-ctx-color', 'value'),
            Output('trace-ctx-mode', 'value'),
            Output('trace-ctx-line-width', 'value'),
            Output('trace-ctx-line-style', 'value'),
            Output('trace-ctx-opacity', 'value'),
            Output('trace-ctx-marker-size', 'value'),
            Output('trace-ctx-marker-symbol', 'value'),
            Output('trace-ctx-line-section', 'style'),
            Output('trace-ctx-marker-section', 'style'),
        ],
        [
            Input('trace-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('trace-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_trace_panel(store, settings, panel_style):
        trig = _triggered_id()
        s = _settings(settings)
        overrides = s.get('trace_overrides') or {}

        if trig == 'trace-context-menu-store':
            if not store or not store.get('trace_name'):
                raise PreventUpdate
            style = _axis_panel_style(store, panel_h=380)
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update
            store = store or {}

        trace_name = store.get('trace_name', '')
        ov = overrides.get(trace_name, {})
        defaults = _trace_defaults(s)

        from services.plot_settings_service import PlotSettingsService
        palette = PlotSettingsService.get_color_palette(s.get('palette', 'okabe_ito'))
        curve_number = store.get('curve_number', 0)
        palette_color = palette[curve_number % len(palette)] if palette else '#E69F00'

        mode = ov.get('mode', 'lines')
        line_sec, marker_sec = _mode_section_styles(mode)

        return (
            style,
            trace_name or 'Trace',
            ov.get('color', palette_color),
            mode,
            ov.get('line_width', defaults['line_width']),
            ov.get('line_style', defaults['line_style']),
            ov.get('opacity', defaults['opacity']),
            ov.get('marker_size', defaults['marker_size']),
            ov.get('marker_symbol', defaults['marker_symbol']),
            line_sec,
            marker_sec,
        )

    @app.callback(
        [
            Output('trace-ctx-line-section', 'style', allow_duplicate=True),
            Output('trace-ctx-marker-section', 'style', allow_duplicate=True),
        ],
        Input('trace-ctx-mode', 'value'),
        prevent_initial_call=True,
    )
    def toggle_trace_mode_sections(mode):
        return _mode_section_styles(mode)

    @app.callback(
        Output('trace-context-panel', 'style', allow_duplicate=True),
        [
            Input('trace-context-menu-close-store', 'data'),
            Input('trace-ctx-close', 'n_clicks'),
        ],
        prevent_initial_call=True,
    )
    def close_trace_panel(close_event, close_clicks):
        if not close_event and not close_clicks:
            raise PreventUpdate
        return _HIDDEN

    @app.callback(
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
        ],
        [
            Input('trace-ctx-color', 'value'),
            Input('trace-ctx-mode', 'value'),
            Input('trace-ctx-line-width', 'value'),
            Input('trace-ctx-line-style', 'value'),
            Input('trace-ctx-opacity', 'value'),
            Input('trace-ctx-marker-size', 'value'),
            Input('trace-ctx-marker-symbol', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('trace-context-panel', 'style'),
            State('trace-context-menu-store', 'data'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def edit_trace_from_context(color, mode, line_width, line_style, opacity,
                                marker_size, marker_symbol,
                                current_settings, panel_style, store,
                                render_counter):
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update, dash.no_update
        if not store or not store.get('trace_name'):
            return dash.no_update, dash.no_update

        s = _settings(current_settings)
        trace_name = store['trace_name']
        new_settings = copy.deepcopy(s)
        overrides = new_settings.setdefault('trace_overrides', {})

        ov = {}
        if color:
            ov['color'] = color
        if mode:
            ov['mode'] = mode
        if line_width is not None:
            ov['line_width'] = line_width
        if line_style:
            ov['line_style'] = line_style
        if opacity is not None:
            ov['opacity'] = opacity
        if marker_size is not None:
            ov['marker_size'] = marker_size
        if marker_symbol:
            ov['marker_symbol'] = marker_symbol

        overrides[trace_name] = ov

        if new_settings == s:
            return dash.no_update, dash.no_update

        return new_settings, (render_counter or 0) + 1

    @app.callback(
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
            Output('trace-context-panel', 'style', allow_duplicate=True),
        ],
        Input('trace-ctx-reset', 'n_clicks'),
        [
            State('current-plot-settings', 'data'),
            State('trace-context-menu-store', 'data'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def reset_trace_overrides(n_clicks, current_settings, store, render_counter):
        if not n_clicks or not store or not store.get('trace_name'):
            raise PreventUpdate
        s = _settings(current_settings)
        trace_name = store['trace_name']
        overrides = (s.get('trace_overrides') or {})
        if trace_name not in overrides:
            raise PreventUpdate
        new_settings = copy.deepcopy(s)
        del new_settings['trace_overrides'][trace_name]
        return new_settings, (render_counter or 0) + 1, _HIDDEN

    # ------------------------------------------------------------------
    # Title / axis label context menu
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output('title-context-panel', 'style'),
            Output('title-ctx-header', 'children'),
            Output('title-ctx-title', 'value'),
            Output('title-ctx-title-size', 'value'),
            Output('title-ctx-bold', 'checked'),
            Output('title-ctx-font', 'value'),
        ],
        [
            Input('title-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('title-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_title_panel(store, settings, panel_style):
        trig = _triggered_id()
        s = _settings(settings)

        if trig == 'title-context-menu-store':
            if not store:
                raise PreventUpdate
            style = _axis_panel_style(store, panel_h=240)
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update

        return (
            style,
            'Plot Title',
            s.get('title', ''),
            s.get('title_font_size', 12),
            bool(s.get('bold_title', True)),
            s.get('font', 'Arial'),
        )

    @app.callback(
        Output('title-context-panel', 'style', allow_duplicate=True),
        [
            Input('title-context-menu-close-store', 'data'),
            Input('title-ctx-close', 'n_clicks'),
        ],
        prevent_initial_call=True,
    )
    def close_title_panel(close_event, close_clicks):
        if not close_event and not close_clicks:
            raise PreventUpdate
        return _HIDDEN

    @app.callback(
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
        ],
        [
            Input('title-ctx-title', 'value'),
            Input('title-ctx-title-size', 'value'),
            Input('title-ctx-bold', 'checked'),
            Input('title-ctx-font', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('title-context-panel', 'style'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def edit_title_from_context(title, title_size, bold, font,
                                current_settings, panel_style,
                                render_counter):
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update, dash.no_update

        s = _settings(current_settings)
        new_settings = copy.deepcopy(s)
        new_settings['title'] = title or ''
        if title_size is not None:
            new_settings['title_font_size'] = title_size
        new_settings['bold_title'] = bool(bold)
        if font:
            new_settings['font'] = font

        if new_settings == s:
            return dash.no_update, dash.no_update

        return new_settings, (render_counter or 0) + 1

    # ------------------------------------------------------------------
    # Axis label context menu
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output('label-context-panel', 'style'),
            Output('label-ctx-header', 'children'),
            Output('label-ctx-text', 'value'),
            Output('label-ctx-font-size', 'value'),
            Output('label-ctx-font', 'value'),
        ],
        [
            Input('label-context-menu-store', 'data'),
            Input('current-plot-settings', 'data'),
        ],
        State('label-context-panel', 'style'),
        prevent_initial_call=True,
    )
    def open_or_sync_label_panel(store, settings, panel_style):
        trig = _triggered_id()
        s = _settings(settings)

        if trig == 'label-context-menu-store':
            if not store:
                raise PreventUpdate
            style = _axis_panel_style(store, panel_h=200)
        else:
            if not panel_style or panel_style.get('display') == 'none':
                raise PreventUpdate
            style = dash.no_update
            store = store or {}

        axis = store.get('axis', 'x')
        header = 'X-Axis Label' if axis == 'x' else 'Y-Axis Label'
        label_text = s.get('x_label', '') if axis == 'x' else s.get('y1_label', '')

        return (
            style,
            header,
            label_text,
            s.get('tick_font_size', 14),
            s.get('font', 'Arial'),
        )

    @app.callback(
        Output('label-context-panel', 'style', allow_duplicate=True),
        [
            Input('label-context-menu-close-store', 'data'),
            Input('label-ctx-close', 'n_clicks'),
        ],
        prevent_initial_call=True,
    )
    def close_label_panel(close_event, close_clicks):
        if not close_event and not close_clicks:
            raise PreventUpdate
        return _HIDDEN

    @app.callback(
        [
            Output('current-plot-settings', 'data', allow_duplicate=True),
            Output('render-trigger', 'data', allow_duplicate=True),
        ],
        [
            Input('label-ctx-text', 'value'),
            Input('label-ctx-font-size', 'value'),
            Input('label-ctx-font', 'value'),
        ],
        [
            State('current-plot-settings', 'data'),
            State('label-context-panel', 'style'),
            State('label-context-menu-store', 'data'),
            State('render-trigger', 'data'),
        ],
        prevent_initial_call=True,
    )
    def edit_label_from_context(label_text, font_size, font,
                                current_settings, panel_style, store,
                                render_counter):
        if not panel_style or panel_style.get('display') == 'none':
            return dash.no_update, dash.no_update

        s = _settings(current_settings)
        axis = (store or {}).get('axis', 'x')
        new_settings = copy.deepcopy(s)

        if axis == 'x':
            new_settings['x_label'] = label_text or ''
        else:
            new_settings['y1_label'] = label_text or ''
            new_settings['y_label'] = label_text or ''

        if font_size is not None:
            new_settings['tick_font_size'] = font_size
        if font:
            new_settings['font'] = font

        if new_settings == s:
            return dash.no_update, dash.no_update

        return new_settings, (render_counter or 0) + 1

