"""Plot settings callbacks — clean single-owner architecture.

Stores
------
- ``active-plot-context``  – string key for the currently visible plot
- ``current-plot-settings`` – ONE runtime source of truth (normalized bools)

Callback paths (no overlap)
---------------------------
1. **Context Resolution** – computes ``active-plot-context`` from file/tab/view
2. **Context Load / Hydrate** – loads saved settings, populates controls + store
3. **User Edit** – all controls → ``current-plot-settings`` (sole runtime writer)
4. **Persist** – saves ``current-plot-settings`` to persistence under context key

Render lives in publication_callbacks.update_pub_plot (reads current-plot-settings).
"""

import copy
import dash
from dash import Input, Output, State, callback_context

from services.plot_settings_service import DEFAULT_PLOT_SETTINGS


def _build_layout_opts(s):
    """Convert normalized booleans back to the pt-layout-opts checklist value."""
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


def register_plot_settings_callbacks(app, data_manager):
    """Register the 4 plot-settings callbacks (resolve, hydrate, edit, persist)."""

    # ------------------------------------------------------------------
    # 1. Context Resolution
    # ------------------------------------------------------------------
    @app.callback(
        Output('active-plot-context', 'data'),
        [Input('active-file', 'data'),
         Input('view-mode', 'data'),
         Input('active-tab', 'data'),
         Input('active-plot-tab', 'data')],
    )
    def resolve_plot_context(active_file, view_mode, active_tab, plot_tab):
        """Compute the context key for the currently visible plot.

        Shared tabs get their own context so settings persist across file switches.
        Plot tab is included so each plot tab keeps independent settings.
        """
        suffix = f':{plot_tab}' if plot_tab else ''
        if active_tab in ('peak-analysis', 'across-samples'):
            return f'shared:{active_tab}{suffix}'
        if (view_mode or 'raw') == 'raw':
            return f'shared:raw{suffix}'
        if active_file:
            return f'file:{active_file}{suffix}'
        return None

    # ------------------------------------------------------------------
    # 2. Context Load / Hydrate
    # ------------------------------------------------------------------
    @app.callback(
        [
            # Runtime store
            Output('current-plot-settings', 'data'),
            # Data Selector controls
            Output('plot-type', 'value', allow_duplicate=True),
            Output('y1-stats', 'value', allow_duplicate=True),
            Output('x-label-input', 'value', allow_duplicate=True),  # hidden
            Output('y1-label-input', 'value', allow_duplicate=True),  # hidden
            Output('y2-label-input', 'value', allow_duplicate=True),  # hidden
            Output('show-raw-points', 'checked', allow_duplicate=True),
            Output('y2-enable', 'checked', allow_duplicate=True),
            Output('y1-series-count', 'data', allow_duplicate=True),
            Output('y1-series-container', 'children', allow_duplicate=True),
            Output('y1-count', 'children', allow_duplicate=True),
            # Plot Settings controls
            Output('pt-smooth-window', 'value', allow_duplicate=True),
            Output('pt-plot-type', 'value', allow_duplicate=True),
            Output('pt-auto-range', 'checked', allow_duplicate=True),
            Output('pt-categorical-x', 'checked', allow_duplicate=True),
            Output('pt-x-min', 'value', allow_duplicate=True),
            Output('pt-x-max', 'value', allow_duplicate=True),
            Output('pt-y-min', 'value', allow_duplicate=True),
            Output('pt-y-max', 'value', allow_duplicate=True),
            Output('pt-x-scale', 'value', allow_duplicate=True),
            Output('pt-y-scale', 'value', allow_duplicate=True),
            Output('pt-theme', 'value', allow_duplicate=True),
            Output('pt-palette', 'value', allow_duplicate=True),
            Output('pt-bg-color', 'value', allow_duplicate=True),
            Output('pt-paper-color', 'value', allow_duplicate=True),
            Output('pt-line-width', 'value', allow_duplicate=True),
            Output('pt-marker-size', 'value', allow_duplicate=True),
            Output('pt-line-style', 'value', allow_duplicate=True),
            Output('pt-marker-symbol', 'value', allow_duplicate=True),
            Output('pt-trace-opacity', 'value', allow_duplicate=True),
            Output('pt-bar-gap', 'value', allow_duplicate=True),
            Output('pt-bar-group-gap', 'value', allow_duplicate=True),
            Output('pt-title', 'value', allow_duplicate=True),
            Output('pt-font', 'value', allow_duplicate=True),
            Output('pt-font-size', 'value', allow_duplicate=True),
            Output('pt-title-font-size', 'value', allow_duplicate=True),
            Output('pt-tick-font-size', 'value', allow_duplicate=True),
            Output('pt-bold-title', 'checked', allow_duplicate=True),
            Output('pt-show-legend', 'checked', allow_duplicate=True),
            Output('pt-legend-pos', 'value', allow_duplicate=True),
            Output('pt-layout-opts', 'value', allow_duplicate=True),
            Output('pt-tick-dir', 'value', allow_duplicate=True),
            Output('pt-grid-style', 'value', allow_duplicate=True),
            Output('pt-frame-width', 'value', allow_duplicate=True),
            Output('pt-tick-length', 'value', allow_duplicate=True),
            Output('pt-layout-mode', 'value', allow_duplicate=True),
            Output('pt-shared-axis-labels', 'checked', allow_duplicate=True),
            Output('pt-x-label', 'value', allow_duplicate=True),
            Output('pt-y-label', 'value', allow_duplicate=True),
            Output('pt-subplot-spacing', 'value', allow_duplicate=True),
        ],
        Input('active-plot-context', 'data'),
        prevent_initial_call=True,
    )
    def hydrate_plot_settings(context_key):
        """Load saved settings for the active context and push to controls."""
        import logging
        _log = logging.getLogger('geckoplotter.settings')
        from callbacks.publication_callbacks import build_y1_series_controls

        # Load from persistence (or defaults)
        saved = _load_settings(data_manager, context_key)
        s = {**DEFAULT_PLOT_SETTINGS, **(saved or {})}
        _log.debug(f"HYDRATE [{context_key}] y1_stats={s.get('y1_stats')} categorical_x={s.get('categorical_x')}")

        series_count = max(1, s.get('y1_series_count', 1))

        return (
            # current-plot-settings
            s,
            # Data Selector controls
            s['plot_type'],
            s['y1_stats'],
            s['x_label'],
            s['y1_label'],
            s['y2_label'],
            bool(s['show_raw_points']),
            bool(s['y2_enable']),
            series_count,
            build_y1_series_controls(series_count),
            f"{series_count} series",
            # Plot Settings controls
            s.get('smooth_window', 0),
            s['plot_type'],
            bool(s['auto_range']),
            bool(s.get('categorical_x', True)),
            s['x_min'],
            s['x_max'],
            s['y_min'],
            s['y_max'],
            s['x_scale'],
            s['y_scale'],
            s['theme'],
            s['palette'],
            s['bg_color'],
            s['paper_color'],
            s['line_width'],
            s['marker_size'],
            s['line_style'],
            s['marker_symbol'],
            s['trace_opacity'],
            s['bar_gap'],
            s['bar_group_gap'],
            s['title'],
            s['font'],
            s['font_size'],
            s['title_font_size'],
            s['tick_font_size'],
            bool(s['bold_title']),
            bool(s['show_legend']),
            s['legend_pos'],
            _build_layout_opts(s),
            s['tick_direction'],
            s['grid_style'],
            s.get('frame_width', 1),
            s.get('tick_length', 5),
            s.get('layout_mode', 'overlay'),
            bool(s.get('shared_axis_labels', False)),
            s['x_label'],
            s['y1_label'],
            s.get('subplot_spacing', 0.08),
        )

    # ------------------------------------------------------------------
    # 3. User Edit → current-plot-settings
    # ------------------------------------------------------------------
    @app.callback(
        Output('current-plot-settings', 'data', allow_duplicate=True),
        # Data Selector controls
        [Input('plot-type', 'value'),
         Input('y1-stats', 'value'),
         Input('show-raw-points', 'checked'),
         Input('y2-enable', 'checked'),
         # Plot Settings controls
         Input('pt-smooth-window', 'value'),
         Input('pt-plot-type', 'value'),
         Input('pt-auto-range', 'checked'),
         Input('pt-categorical-x', 'checked'),
         Input('pt-x-min', 'value'),
         Input('pt-x-max', 'value'),
         Input('pt-y-min', 'value'),
         Input('pt-y-max', 'value'),
         Input('pt-x-scale', 'value'),
         Input('pt-y-scale', 'value'),
         Input('pt-theme', 'value'),
         Input('pt-palette', 'value'),
         Input('pt-bg-color', 'value'),
         Input('pt-paper-color', 'value'),
         Input('pt-line-width', 'value'),
         Input('pt-marker-size', 'value'),
         Input('pt-line-style', 'value'),
         Input('pt-marker-symbol', 'value'),
         Input('pt-trace-opacity', 'value'),
         Input('pt-bar-gap', 'value'),
         Input('pt-bar-group-gap', 'value'),
         Input('pt-title', 'value'),
         Input('pt-font', 'value'),
         Input('pt-font-size', 'value'),
         Input('pt-title-font-size', 'value'),
         Input('pt-tick-font-size', 'value'),
         Input('pt-bold-title', 'checked'),
         Input('pt-show-legend', 'checked'),
         Input('pt-legend-pos', 'value'),
         Input('pt-layout-opts', 'value'),
         Input('pt-tick-dir', 'value'),
         Input('pt-grid-style', 'value'),
         Input('pt-frame-width', 'value'),
         Input('pt-tick-length', 'value'),
         Input('pt-layout-mode', 'value'),
         Input('pt-shared-axis-labels', 'checked'),
         Input('pt-x-label', 'value'),
         Input('pt-y-label', 'value'),
         Input('pt-subplot-spacing', 'value')],
        State('current-plot-settings', 'data'),
        prevent_initial_call=True,
    )
    def user_edit_settings(
        # Data Selector
        ds_plot_type, y1_stats,
        show_raw, y2_enable,
        # Plot Settings
        pt_smooth_window,
        pt_plot_type, pt_auto_range, pt_categorical_x,
        pt_x_min, pt_x_max, pt_y_min, pt_y_max,
        pt_x_scale, pt_y_scale,
        pt_theme, pt_palette, pt_bg_color, pt_paper_color,
        pt_line_width, pt_marker_size, pt_line_style, pt_marker_symbol,
        pt_trace_opacity, pt_bar_gap, pt_bar_group_gap,
        pt_title, pt_font, pt_font_size,
        pt_title_font_size, pt_tick_font_size,
        pt_bold_title, pt_show_legend, pt_legend_pos,
        pt_layout_opts, pt_tick_dir, pt_grid_style,
        pt_frame_width, pt_tick_length,
        pt_layout_mode,
        pt_shared_axis_labels,
        pt_x_label, pt_y_label,
        pt_subplot_spacing,
        # State
        current_settings,
    ):
        """Merge control values into one normalized settings object."""
        current_settings = current_settings or dict(DEFAULT_PLOT_SETTINGS)

        # Resolve plot_type: prefer whichever control just changed
        trigger = ''
        if callback_context.triggered:
            trigger = callback_context.triggered[0]['prop_id']

        if 'plot-type.value' in trigger and 'pt-plot-type' not in trigger:
            plot_type = ds_plot_type
        else:
            plot_type = pt_plot_type

        layout_opts = pt_layout_opts or []

        # Axis labels: pt-x-label / pt-y-label are the sole source;
        # None means the field was never touched → keep current value
        eff_x_label = pt_x_label if pt_x_label is not None else current_settings.get('x_label', '')
        eff_y_label = pt_y_label if pt_y_label is not None else current_settings.get('y1_label', '')

        new_settings = {
            # Data Selector (normalized)
            'plot_type': plot_type or 'bar',
            'y1_stats': y1_stats or [],
            'x_label': eff_x_label,
            'y1_label': eff_y_label,
            'y2_label': '',
            'show_raw_points': bool(show_raw),
            'y2_enable': bool(y2_enable),
            'y1_series_count': current_settings.get('y1_series_count', 1),
            # Axes
            'auto_range': bool(pt_auto_range),
            'categorical_x': bool(pt_categorical_x),
            'x_min': pt_x_min,
            'x_max': pt_x_max,
            'y_min': pt_y_min,
            'y_max': pt_y_max,
            'x_scale': pt_x_scale or 'linear',
            'y_scale': pt_y_scale or 'linear',
            # Theme & Colors
            'theme': pt_theme or 'plotly_white',
            'palette': pt_palette or 'okabe_ito',
            'bg_color': pt_bg_color or '#ffffff',
            'paper_color': pt_paper_color or '#ffffff',
            # Traces
            'line_width': pt_line_width if pt_line_width is not None else 1.5,
            'line_style': pt_line_style or 'solid',
            'marker_size': pt_marker_size if pt_marker_size is not None else 6,
            'marker_symbol': pt_marker_symbol or 'circle',
            'trace_opacity': pt_trace_opacity if pt_trace_opacity is not None else 1.0,
            'smooth_window': int(pt_smooth_window or 0),
            'bar_gap': pt_bar_gap if pt_bar_gap is not None else 0.2,
            'bar_group_gap': pt_bar_group_gap if pt_bar_group_gap is not None else 0.1,
            # Labels
            'title': pt_title or '',
            # Typography
            'font': pt_font or 'Arial',
            'font_size': pt_font_size if pt_font_size is not None else 12,
            'title_font_size': pt_title_font_size if pt_title_font_size is not None else 14,
            'tick_font_size': pt_tick_font_size if pt_tick_font_size is not None else 10,
            'bold_title': bool(pt_bold_title),
            # Legend
            'show_legend': bool(pt_show_legend),
            'legend_pos': pt_legend_pos or 'top-right',
            # Grid & Frame
            'show_grid_x': 'grid_x' in layout_opts,
            'show_grid_y': 'grid_y' in layout_opts,
            'show_tick_marks': 'ticks' in layout_opts,
            'show_minor_ticks': 'minor_ticks' in layout_opts,
            'tick_direction': pt_tick_dir or 'outside',
            'tick_length': pt_tick_length if pt_tick_length is not None else 5,
            'frame_width': pt_frame_width if pt_frame_width is not None else 1,
            'show_frame': 'frame' in layout_opts,
            'grid_style': pt_grid_style or 'solid',
            # Layout
            'layout_mode': pt_layout_mode or 'overlay',
            # Subplot labels
            'shared_axis_labels': bool(pt_shared_axis_labels),
            'subplot_spacing': pt_subplot_spacing if pt_subplot_spacing is not None else 0.08,
            # Preserve per-trace overrides (managed by trace context menu)
            'trace_overrides': current_settings.get('trace_overrides', {}),
        }

        # Break hydration loop: if nothing changed, don't propagate
        if new_settings == current_settings:
            return dash.no_update

        return new_settings

    # ------------------------------------------------------------------
    # 4. Persist
    # ------------------------------------------------------------------
    @app.callback(
        Output('dummy-output', 'children', allow_duplicate=True),
        [Input('current-plot-settings', 'data')],
        [State('active-plot-context', 'data')],
        prevent_initial_call=True,
    )
    def persist_plot_settings(settings, context_key):
        """Save current-plot-settings to persistence under the active context."""
        import logging
        _log = logging.getLogger('geckoplotter.settings')
        if not context_key or not settings:
            return dash.no_update
        _log.debug(f"PERSIST [{context_key}] y1_stats={settings.get('y1_stats')}")
        _save_settings(data_manager, context_key, settings)
        return dash.no_update

    # ------------------------------------------------------------------
    # 5. Visibility — context-aware panel sections
    # ------------------------------------------------------------------
    _SHOW = {}  # display: default (visible)
    _HIDE = {'display': 'none'}

    @app.callback(
        [
            # Phase 1.1 — dynamic header
            Output('pt-panel-header', 'children'),
            # Phase 1.2 — analysis-only vs raw-only wrappers
            Output('pt-plot-type-wrapper', 'style'),
            Output('pt-raw-layout-wrapper', 'style'),
            Output('pt-theme-wrapper', 'style'),
            # Phase 1.3 — plot-type-specific wrappers
            Output('pt-bar-wrapper', 'style'),
            Output('pt-line-controls-wrapper', 'style'),
            Output('pt-marker-wrapper', 'style'),
            # Phase 1.4 — conditional dependents
            Output('pt-range-wrapper', 'style'),
            Output('pt-legend-pos-wrapper', 'style'),
            Output('pt-tick-grid-detail-wrapper', 'style'),
        ],
        [
            Input('view-mode', 'data'),
            Input('current-plot-settings', 'data'),
        ],
    )
    def update_panel_visibility(view_mode, settings):
        """Toggle settings panel sections based on view-mode and current settings."""
        s = {**DEFAULT_PLOT_SETTINGS, **(settings or {})}
        is_raw = (view_mode or 'raw') == 'raw'
        plot_type = s.get('plot_type', 'bar')
        auto_range = s.get('auto_range', True)
        show_legend = s.get('show_legend', True)
        layout_opts = []
        if s.get('show_grid_x'):
            layout_opts.append('grid_x')
        if s.get('show_grid_y'):
            layout_opts.append('grid_y')
        if s.get('show_tick_marks'):
            layout_opts.append('ticks')

        # 1.1 — header text
        header = 'Raw Plot Settings' if is_raw else 'Analysis Plot Settings'

        # 1.2 — analysis-only vs raw-only
        plot_type_vis = _HIDE if is_raw else _SHOW
        raw_layout_vis = _SHOW if is_raw else _HIDE
        theme_vis = _SHOW  # always visible

        # 1.3 — plot-type-specific (only in analysis mode)
        if is_raw:
            bar_vis = _HIDE
            line_vis = _SHOW   # line width matters for raw
            marker_vis = _HIDE
        else:
            bar_vis = _SHOW if plot_type == 'bar' else _HIDE
            line_vis = _SHOW if plot_type in ('line', 'scatter') else _HIDE
            marker_vis = _SHOW if plot_type in ('scatter', 'line') else _HIDE

        # 1.4 — conditional dependents
        range_vis = _HIDE if auto_range else _SHOW
        legend_pos_vis = _SHOW if show_legend else _HIDE
        has_grid_or_ticks = ('grid_x' in layout_opts or 'grid_y' in layout_opts
                            or 'ticks' in layout_opts)
        tick_grid_vis = _SHOW if has_grid_or_ticks else _HIDE

        return (
            header,
            plot_type_vis,
            raw_layout_vis,
            theme_vis,
            bar_vis,
            line_vis,
            marker_vis,
            range_vis,
            legend_pos_vis,
            tick_grid_vis,
        )


# ----------------------------------------------------------------------
# Persistence helpers (keyed by context string)
# ----------------------------------------------------------------------

def _load_settings(data_manager, context_key):
    """Load saved plot settings for a context key."""
    if not context_key:
        return dict(DEFAULT_PLOT_SETTINGS)

    if context_key.startswith('shared:'):
        # Shared settings stored in data_manager under a special key
        shared_store = getattr(data_manager, '_shared_plot_settings', {})
        return shared_store.get(context_key, dict(DEFAULT_PLOT_SETTINGS))

    if context_key.startswith('file:'):
        file_id = context_key[5:]  # strip 'file:'
        state = data_manager.get_file_state(file_id)
        saved = state.get('plot_settings', {})
        if saved:
            return saved
        return dict(DEFAULT_PLOT_SETTINGS)

    return dict(DEFAULT_PLOT_SETTINGS)


def _save_settings(data_manager, context_key, settings):
    """Save plot settings for a context key to persistence."""
    if not context_key or not settings:
        return

    if context_key.startswith('shared:'):
        if not hasattr(data_manager, '_shared_plot_settings'):
            data_manager._shared_plot_settings = {}
        data_manager._shared_plot_settings[context_key] = copy.deepcopy(settings)
        return

    if context_key.startswith('file:'):
        file_id = context_key[5:]
        current_state = data_manager.get_file_state(file_id)
        current_state['plot_settings'] = copy.deepcopy(settings)
        data_manager.save_file_state(file_id, current_state)
