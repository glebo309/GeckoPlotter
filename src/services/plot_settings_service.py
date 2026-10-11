"""Service for managing chromatogram plot settings in GeckoPlotter V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Dict, List, Optional

import plotly.graph_objects as go


# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

COLOR_PALETTES: Dict[str, List[str]] = {
    "okabe_ito": [
        "#E69F00",
        "#56B4E9",
        "#009E73",
        "#F0E442",
        "#0072B2",
        "#D55E00",
        "#CC79A7",
    ],
    "plotly": [
        "#636EFA",
        "#EF553B",
        "#00CC96",
        "#AB63FA",
        "#FFA15A",
        "#19D3F3",
        "#FF6692",
        "#B6E880",
        "#FF97FF",
        "#FECB52",
    ],
    "d3": [
        "#1F77B4",
        "#FF7F0E",
        "#2CA02C",
        "#D62728",
        "#9467BD",
        "#8C564B",
        "#E377C2",
        "#7F7F7F",
        "#BCBD22",
        "#17BECF",
    ],
    "pastel": [
        "#A8D8EA",
        "#FFB7B2",
        "#B5EAD7",
        "#FFDAC1",
        "#C7CEEA",
        "#E2C2F8",
        "#F5E6CC",
        "#D4E09B",
        "#F6D6AD",
        "#CBDFBD",
    ],
    # Crameri scientific colour maps — categorical (CVD-friendly, perceptually uniform)
    # Ref: Crameri (2018) doi:10.5281/zenodo.1243862
    "batlow": [
        "#011959",
        "#103F60",
        "#1C6B71",
        "#44877D",
        "#7AAB78",
        "#B8CC6B",
        "#EEDA71",
        "#FAB85D",
        "#E88556",
        "#D94D4D",
    ],
    "hawaii": [
        "#8C0273",
        "#8B2B8B",
        "#77539B",
        "#5878A2",
        "#3E98A0",
        "#3CB491",
        "#5FCC72",
        "#96DE51",
        "#C9EC53",
        "#F1F1B0",
    ],
    "roma": [
        "#7E1900",
        "#B14F12",
        "#D98B3B",
        "#F2C971",
        "#FEFEBB",
        "#87CFBA",
        "#3D9BA5",
        "#1D6688",
        "#1B3764",
        "#1A0C3C",
    ],
}

# ---------------------------------------------------------------------------
# Legend position lookup
# ---------------------------------------------------------------------------

_LEGEND_COORDS: Dict[str, dict] = {
    "top-right": {"x": 0.98, "y": 0.94, "xanchor": "right", "yanchor": "top"},
    "top-left": {"x": 0.02, "y": 0.94, "xanchor": "left", "yanchor": "top"},
    "bottom-right": {"x": 0.98, "y": 0.06, "xanchor": "right", "yanchor": "bottom"},
    "bottom-left": {"x": 0.02, "y": 0.06, "xanchor": "left", "yanchor": "bottom"},
}


# ---------------------------------------------------------------------------
# Default plot settings (normalized booleans, single source of truth)
# ---------------------------------------------------------------------------

DEFAULT_PLOT_SETTINGS: Dict[str, object] = {
    # Data Selector
    "plot_type": "bar",
    "x_label": "Retention Time (min)",
    "y1_label": "Signal (mAU)",
    "y2_label": "",
    "y1_stats": [],
    "show_raw_points": False,
    "y2_enable": False,
    "y1_series_count": 1,
    # Axes
    "auto_range": True,
    "x_min": None,
    "x_max": None,
    "y_min": None,
    "y_max": None,
    "x_scale": "linear",
    "y_scale": "linear",
    "categorical_x": True,
    # Theme & Colors
    "theme": "plotly_white",
    "palette": "okabe_ito",
    "bg_color": "#ffffff",
    "paper_color": "#ffffff",
    # Traces
    "line_width": 1.5,
    "line_style": "solid",
    "marker_size": 6,
    "marker_symbol": "circle",
    "trace_opacity": 1.0,
    "smooth_window": 0,
    "bar_gap": 0.2,
    "bar_group_gap": 0.1,
    # Labels
    "title": "",
    "shared_axis_labels": True,
    # Typography
    "font": "Arial",
    "font_size": 10,
    "title_font_size": 12,
    "tick_font_size": 14,
    "bold_title": True,
    # Legend
    "show_legend": True,
    "legend_pos": "top-right",
    # Grid & Frame
    "show_grid_x": False,
    "show_grid_y": False,
    "show_tick_marks": True,
    "show_minor_ticks": False,
    "tick_direction": "outside",
    "tick_length": 5,
    "frame_width": 1,
    "show_frame": True,
    "grid_style": "solid",
    # Layout
    "layout_mode": "overlay",
    "subplot_spacing": 0.08,
    # Per-figure view and publication controls
    "subplot_rows": 1, "subplot_cols": 1,
    "figure_width_mm": 84, "figure_height_mm": 63,
    "pub_preset": "single-col", "pub_dpi": 300, "export_format": "png",
    "link_x": True, "y_scope": "independent",
    # Per-trace overrides
    "trace_overrides": {},
}


# ---------------------------------------------------------------------------
# PlotSettings dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlotSettings:
    """All settings required to render a publication-quality plot."""

    # -- 1. Plot type --
    plot_type: str = "bar"               # bar, line, scatter

    # -- 2. Axes --
    auto_range: bool = True
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    x_scale: str = "linear"              # linear, log
    y_scale: str = "linear"              # linear, log
    categorical_x: bool = True

    # -- 3. Style / Theme --
    theme: str = "plotly_white"
    palette: str = "okabe_ito"
    bg_color: str = "#ffffff"            # plot area background
    paper_color: str = "#ffffff"         # surrounding paper

    # -- 4. Traces --
    line_width: float = 1.5
    line_style: str = "solid"            # solid, dash, dot, dashdot
    marker_size: float = 6
    marker_symbol: str = "circle"        # circle, square, diamond, cross, x
    trace_opacity: float = 1.0
    smooth_window: int = 0                # display-only Savitzky-Golay window
    bar_gap: float = 0.2                 # gap between bars (0-1)
    bar_group_gap: float = 0.1           # gap between grouped bars (0-1)

    # -- 5. Labels --
    title: str = ""
    x_label: str = "Retention Time (min)"
    y_label: str = "Signal (mAU)"
    title_font_size: int = 12

    # -- 6. Typography --
    font: str = "Arial"
    font_size: int = 10
    tick_font_size: int = 14
    bold_title: bool = True

    # -- 7. Legend --
    show_legend: bool = True
    legend_pos: str = "top-right"

    # -- 8. Grid & Frame --
    show_grid_x: bool = True
    show_grid_y: bool = True
    show_tick_marks: bool = True         # tick marks on axes
    show_minor_ticks: bool = False
    tick_direction: str = "outside"      # inside, outside, none
    tick_length: int = 5
    frame_width: float = 1
    show_frame: bool = True              # box around plot area
    grid_style: str = "solid"            # solid, dash, dot

    # -- 9. Subplot labels --
    shared_axis_labels: bool = True

    # -- 10. Chromatogram-specific --
    show_baseline: bool = False
    show_peaks: bool = True
    peak_opacity: float = 0.3

    # -- 11. Layout --
    layout_mode: str = "overlay"         # overlay, stacked
    subplot_spacing: float = 0.08        # vertical gap between subplots (0-0.3)
    plot_height: int = 500
    plot_width: int = 800

    # -- 12. Per-trace overrides --
    trace_overrides: Dict[str, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PlotSettingsService
# ---------------------------------------------------------------------------

class PlotSettingsService:
    """Create, serialize, and apply :class:`PlotSettings` to Plotly figures."""

    # -- Constructors / serialization ----------------------------------------

    @staticmethod
    def get_defaults() -> PlotSettings:
        """Return a :class:`PlotSettings` instance with all default values."""
        return PlotSettings()

    @staticmethod
    def from_dict(d: dict) -> PlotSettings:
        """Create a :class:`PlotSettings` from a dict (e.g. ``dcc.Store`` data).

        Missing keys are filled with defaults. Unknown keys are silently
        ignored so that forward-compatible stores do not break older code.
        """
        if not d:
            return PlotSettings()
        valid_keys = {f.name for f in fields(PlotSettings)}
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return PlotSettings(**filtered)

    @staticmethod
    def to_dict(settings: PlotSettings) -> dict:
        """Serialize a :class:`PlotSettings` to a plain dict for ``dcc.Store``."""
        return asdict(settings)

    # -- Color palettes ------------------------------------------------------

    @staticmethod
    def get_color_palette(name: str) -> List[str]:
        """Return the colour list for *name*, falling back to ``okabe_ito``."""
        return list(COLOR_PALETTES.get(name, COLOR_PALETTES["okabe_ito"]))

    # -- Legend coordinates --------------------------------------------------

    @staticmethod
    def get_legend_coords(position: str) -> dict:
        """Convert a position string to Plotly legend ``x/y/xanchor/yanchor``."""
        return dict(_LEGEND_COORDS.get(position, _LEGEND_COORDS["top-right"]))

    # -- Figure styling ------------------------------------------------------

    @classmethod
    def apply_to_figure(
        cls, fig: go.Figure, settings: PlotSettings
    ) -> go.Figure:
        """Apply *settings* to *fig* in-place and return it.

        Single entry-point for turning a raw Plotly figure into a
        publication-ready plot.
        """
        import re
        _DASH_MAP = {'solid': 'solid', 'dash': 'dash', 'dot': 'dot', 'dashdot': 'dashdot'}

        # -- Template / theme ------------------------------------------------
        # Strip the template entirely to prevent Plotly.js client-side
        # validation errors from coloraxis/colorscale entries that get
        # serialised into dcc.Store JSON.  All visual properties are set
        # explicitly below.
        import plotly.io as pio
        theme = pio.templates[settings.theme].layout if settings.theme in pio.templates else pio.templates['plotly_white'].layout
        foreground = '#f2f5fa' if settings.theme == 'plotly_dark' else '#444'
        fig.layout.template = None
        # Also strip any coloraxis entries that may have leaked in
        layout_json = fig.layout.to_plotly_json()
        for key in list(layout_json.keys()):
            if key.startswith('coloraxis'):
                fig.layout[key] = None

        # -- Background colours ----------------------------------------------
        fig.update_layout(
            plot_bgcolor=settings.bg_color,
            paper_bgcolor=settings.paper_color,
        )

        # -- Global font -----------------------------------------------------
        fig.update_layout(
            font=dict(family=settings.font, size=settings.font_size, color=foreground),
        )

        # -- Title -----------------------------------------------------------
        title_text = settings.title or None
        fig.update_layout(
            title=dict(
                text=f"<b>{title_text}</b>" if title_text and settings.bold_title else title_text,
                font=dict(size=settings.title_font_size),
            ),
        )

        # -- Axes ------------------------------------------------------------
        x_range = None if settings.auto_range else [settings.x_min, settings.x_max]
        y_range = None if settings.auto_range else [settings.y_min, settings.y_max]

        import math
        if not settings.auto_range:
            def bounds(values, scale):
                return [None if v in (None, '') else (math.log10(v) if v > 0 else None)
                        for v in values] if scale == 'log' else [None if v == '' else v for v in values]
            x_range = bounds(x_range, settings.x_scale)
            y_range = bounds(y_range, settings.y_scale)

        tick_cfg = {}
        if settings.show_tick_marks and settings.tick_direction != 'none':
            tick_cfg = dict(ticks=settings.tick_direction, ticklen=settings.tick_length)
        else:
            tick_cfg = dict(ticks='')

        grid_dash = _DASH_MAP.get(settings.grid_style, 'solid')
        minor_cfg = dict(
            ticks=settings.tick_direction if settings.show_minor_ticks and settings.tick_direction != 'none' else '',
            ticklen=max(1, int(settings.tick_length * 0.6)),
            showgrid=False,
        )

        axis_title_font = dict(size=settings.tick_font_size, color=foreground)

        axis_common_x = dict(
            title=dict(text=settings.x_label or '', standoff=10, font=axis_title_font),
            showgrid=settings.show_grid_x,
            griddash=grid_dash,
            color=foreground,
            gridcolor=theme.xaxis.gridcolor or "#ddd",
            zeroline=False,
            type=settings.x_scale,
            tickfont=dict(size=settings.tick_font_size, color=foreground),
            showline=settings.show_frame,
            linewidth=settings.frame_width,
            mirror=settings.show_frame,
            minor=minor_cfg,
            automargin=True,
            **tick_cfg,
        )
        axis_common_y = dict(
            title=dict(text=settings.y_label or '', standoff=10, font=axis_title_font),
            showgrid=settings.show_grid_y,
            griddash=grid_dash,
            color=foreground,
            gridcolor=theme.xaxis.gridcolor or "#ddd",
            zeroline=False,
            type=settings.y_scale,
            tickfont=dict(size=settings.tick_font_size, color=foreground),
            showline=settings.show_frame,
            linewidth=settings.frame_width,
            mirror=settings.show_frame,
            minor=minor_cfg,
            automargin=True,
            **tick_cfg,
        )
        if not settings.auto_range:
            axis_common_x['range'] = x_range
            axis_common_x['autorange'] = (True if x_range == [None, None] else
                                           'min' if x_range[0] is None else
                                           'max' if x_range[1] is None else False)
            axis_common_y['range'] = y_range
            axis_common_y['autorange'] = (True if y_range == [None, None] else
                                           'min' if y_range[0] is None else
                                           'max' if y_range[1] is None else False)

        # Update all x/y axes (subplots: xaxis, xaxis2, …)
        # Preserve categorical tick config set by publication_plot
        _xaxis_re = re.compile(r'^xaxis\d*$')
        _yaxis_re = re.compile(r'^yaxis\d*$')
        layout_json = fig.layout.to_plotly_json()
        layout_keys = list(layout_json.keys())

        _categorical_keys = ('ticktext', 'tickvals', 'tickmode')

        x_axes = sorted(k for k in layout_keys if _xaxis_re.match(k))
        y_axes = sorted(k for k in layout_keys if _yaxis_re.match(k))
        has_subplots = len(x_axes) > 1 or len(y_axes) > 1
        last_xaxis = x_axes[-1] if x_axes else 'xaxis'

        shared = settings.shared_axis_labels and has_subplots

        for key in layout_keys:
            if _xaxis_re.match(key):
                existing = layout_json.get(key, {})
                merged = dict(axis_common_x)
                suffix = key[len('xaxis'):]
                y_domain = layout_json.get('yaxis' + suffix, {}).get('domain', [0, 1])
                if shared and y_domain[0] > 0:
                    merged['title'] = dict(text='', standoff=20)
                if existing.get('tickmode') == 'array' and settings.categorical_x:
                    for ck in _categorical_keys:
                        if ck in existing:
                            merged[ck] = existing[ck]
                    merged.pop('type', None)
                if existing.get('tickmode') == 'array' and not settings.categorical_x:
                    merged.update(tickmode='auto', ticktext=None, tickvals=None)
                fig.update_layout(**{key: merged})
            elif _yaxis_re.match(key):
                merged = dict(axis_common_y)
                existing_y = layout_json.get(key, {})
                existing_title = existing_y.get('title', {})
                has_custom_label = isinstance(existing_title, dict) and existing_title.get('text', '')
                if shared and not has_custom_label:
                    merged['title'] = dict(text='', standoff=20)
                elif has_custom_label and settings.y_label == DEFAULT_PLOT_SETTINGS['y1_label']:
                    merged['title'] = dict(axis_common_y['title'], text=existing_title['text'])
                fig.update_layout(**{key: merged})

        if not x_axes:
            fig.update_layout(xaxis=axis_common_x)
        if not y_axes:
            fig.update_layout(yaxis=axis_common_y)

        # Shared Y label as a centered annotation (skip if subplots have custom labels)
        any_custom_y = any(
            isinstance(layout_json.get(k, {}).get('title', {}), dict)
            and layout_json.get(k, {}).get('title', {}).get('text', '')
            for k in layout_keys if _yaxis_re.match(k)
        )
        if shared and settings.y_label and not any_custom_y:
            fig.add_annotation(
                text=settings.y_label,
                xref='paper', yref='paper',
                x=0, y=0.5,
                xanchor='right',
                xshift=-25,
                showarrow=False,
                textangle=-90,
                font=dict(size=settings.tick_font_size),
            )

        # -- Bar gap ---------------------------------------------------------
        fig.update_layout(bargap=settings.bar_gap, bargroupgap=settings.bar_group_gap)

        # -- Legend ----------------------------------------------------------
        fig.layout.showlegend = settings.show_legend
        # Apply visibility to all legends (legend, legend2, legend3, …)
        _legend_re = re.compile(r'^legend\d*$')
        legend_keys = [k for k in layout_json if _legend_re.match(k)]
        if not legend_keys:
            legend_keys = ['legend']
        for lk in legend_keys:
            lk_kwargs = dict(visible=settings.show_legend)
            if settings.show_legend:
                coords = cls.get_legend_coords(settings.legend_pos)
                if len(legend_keys) > 1:
                    suffix = lk[len('legend'):]
                    y_domain = layout_json.get('yaxis' + suffix, {}).get('domain', [0, 1])
                    x_domain = layout_json.get('xaxis' + suffix, {}).get('domain', [0, 1])
                    coords['y'] = y_domain[0] + coords['y'] * (y_domain[1] - y_domain[0])
                    coords['x'] = x_domain[0] + coords['x'] * (x_domain[1] - x_domain[0])
                lk_kwargs.update(coords)
                lk_kwargs.update(bgcolor=_hex_to_rgba(settings.paper_color, .85), borderwidth=0,
                                 font=dict(size=settings.font_size, color=foreground))
            fig.update_layout(**{lk: lk_kwargs})

        # -- Colour palette & trace styling ----------------------------------
        # Always apply the selected palette to data traces so lines and
        # peaks share a single colour source of truth.
        palette = cls.get_color_palette(settings.palette)
        line_dash = _DASH_MAP.get(settings.line_style, 'solid')

        data_trace_idx = 0
        for trace in fig.data:
            is_bar = isinstance(trace, go.Bar)

            # Skip peak overlay traces (fills, deselect catchers, baselines)
            trace_name = getattr(trace, 'name', '') or ''
            is_peak_trace = (
                getattr(trace, 'fill', None) is not None
                or trace_name.startswith('peak:')
                or trace_name == '__deselect__'
                or 'baseline' in trace_name.lower()
            )
            if is_peak_trace:
                continue

            color = palette[data_trace_idx % len(palette)]

            trace.update(opacity=settings.trace_opacity)

            if not is_bar and hasattr(trace, "line") and trace.line is not None:
                trace.line.width = settings.line_width
                trace.line.color = color
                trace.line.dash = line_dash

            if is_bar:
                if hasattr(trace, "marker") and trace.marker is not None:
                    trace.marker.color = color
            elif hasattr(trace, "marker") and trace.marker is not None:
                trace.marker.size = settings.marker_size
                trace.marker.color = color
                trace.marker.symbol = settings.marker_symbol

            # Per-trace overrides (keyed by trace name)
            overrides = (settings.trace_overrides or {}).get(trace_name)
            if overrides:
                if 'color' in overrides:
                    color = overrides['color']
                    if hasattr(trace, 'line') and trace.line is not None:
                        trace.line.color = color
                    if hasattr(trace, 'marker') and trace.marker is not None:
                        trace.marker.color = color
                if 'mode' in overrides and not is_bar:
                    trace.mode = overrides['mode']
                if not is_bar and hasattr(trace, 'line') and trace.line is not None:
                    if 'line_width' in overrides:
                        trace.line.width = overrides['line_width']
                    if 'line_style' in overrides:
                        trace.line.dash = _DASH_MAP.get(overrides['line_style'], 'solid')
                if not is_bar and 'markers' in (overrides.get('mode') or ''):
                    if not hasattr(trace, 'marker') or trace.marker is None:
                        trace.marker = {}
                    if 'marker_size' in overrides:
                        trace.marker.size = overrides['marker_size']
                    if 'marker_symbol' in overrides:
                        trace.marker.symbol = overrides['marker_symbol']
                    if 'color' in overrides:
                        trace.marker.color = overrides['color']
                elif hasattr(trace, 'marker') and trace.marker is not None and not is_bar:
                    if 'marker_size' in overrides:
                        trace.marker.size = overrides['marker_size']
                    if 'marker_symbol' in overrides:
                        trace.marker.symbol = overrides['marker_symbol']
                if 'opacity' in overrides:
                    trace.update(opacity=overrides['opacity'])

            data_trace_idx += 1

        # -- Dimensions & margins --------------------------------------------
        fig.update_layout(
            autosize=True,
            margin=dict(l=20, r=20, t=30 if not title_text else 50, b=40, autoexpand=True),
        )

        return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str, opacity: float) -> str:
    """Convert a hex colour string to an ``rgba(…)`` string."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{opacity})"
