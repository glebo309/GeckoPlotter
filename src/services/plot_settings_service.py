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
}

# ---------------------------------------------------------------------------
# Legend position lookup
# ---------------------------------------------------------------------------

_LEGEND_COORDS: Dict[str, dict] = {
    "top-right": {"x": 1, "y": 1, "xanchor": "right", "yanchor": "top"},
    "top-left": {"x": 0, "y": 1, "xanchor": "left", "yanchor": "top"},
    "bottom-right": {"x": 1, "y": 0, "xanchor": "right", "yanchor": "bottom"},
    "bottom-left": {"x": 0, "y": 0, "xanchor": "left", "yanchor": "bottom"},
}


# ---------------------------------------------------------------------------
# Default plot settings (normalized booleans, single source of truth)
# ---------------------------------------------------------------------------

DEFAULT_PLOT_SETTINGS: Dict[str, object] = {
    # Data Selector
    "plot_type": "bar",
    "x_label": "X",
    "y1_label": "Y1",
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
    "bar_gap": 0.2,
    "bar_group_gap": 0.1,
    # Labels
    "title": "",
    # Typography
    "font": "Arial",
    "font_size": 12,
    "title_font_size": 14,
    "tick_font_size": 10,
    "bold_title": True,
    # Legend
    "show_legend": True,
    "legend_pos": "top-right",
    # Grid & Frame
    "show_grid_x": True,
    "show_grid_y": True,
    "show_tick_marks": True,
    "tick_direction": "outside",
    "show_frame": True,
    "grid_style": "solid",
    # Layout
    "layout_mode": "overlay",
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
    bar_gap: float = 0.2                 # gap between bars (0-1)
    bar_group_gap: float = 0.1           # gap between grouped bars (0-1)

    # -- 5. Labels --
    title: str = ""
    x_label: str = "Retention Time (min)"
    y_label: str = "Signal (mAU)"
    title_font_size: int = 14

    # -- 6. Typography --
    font: str = "Arial"
    font_size: int = 12
    tick_font_size: int = 10
    bold_title: bool = True

    # -- 7. Legend --
    show_legend: bool = True
    legend_pos: str = "top-right"

    # -- 8. Grid & Frame --
    show_grid_x: bool = True
    show_grid_y: bool = True
    show_tick_marks: bool = True         # tick marks on axes
    tick_direction: str = "outside"      # inside, outside, none
    show_frame: bool = True              # box around plot area
    grid_style: str = "solid"            # solid, dash, dot

    # -- 9. Chromatogram-specific --
    show_baseline: bool = False
    show_peaks: bool = True
    peak_opacity: float = 0.3

    # -- 10. Layout --
    layout_mode: str = "overlay"         # overlay, stacked
    plot_height: int = 500
    plot_width: int = 800


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
            font=dict(family=settings.font, size=settings.font_size),
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

        tick_cfg = {}
        if settings.show_tick_marks and settings.tick_direction != 'none':
            tick_cfg = dict(ticks=settings.tick_direction, ticklen=5)
        else:
            tick_cfg = dict(ticks='')

        grid_dash = _DASH_MAP.get(settings.grid_style, 'solid')

        axis_common_x = dict(
            title_text=settings.x_label,
            showgrid=settings.show_grid_x,
            griddash=grid_dash,
            type=settings.x_scale,
            tickfont=dict(size=settings.tick_font_size),
            showline=settings.show_frame,
            mirror=settings.show_frame,
            **tick_cfg,
        )
        axis_common_y = dict(
            title_text=settings.y_label,
            showgrid=settings.show_grid_y,
            griddash=grid_dash,
            type=settings.y_scale,
            tickfont=dict(size=settings.tick_font_size),
            showline=settings.show_frame,
            mirror=settings.show_frame,
            **tick_cfg,
        )
        if not settings.auto_range:
            axis_common_x['range'] = x_range
            axis_common_x['autorange'] = False
            axis_common_y['range'] = y_range
            axis_common_y['autorange'] = False

        # Update all x/y axes (subplots: xaxis, xaxis2, …)
        # Exclude coloraxis, polar axis, etc.
        _xaxis_re = re.compile(r'^xaxis\d*$')
        _yaxis_re = re.compile(r'^yaxis\d*$')
        layout_keys = list(fig.layout.to_plotly_json().keys())
        for key in layout_keys:
            if _xaxis_re.match(key):
                fig.update_layout(**{key: axis_common_x})
            elif _yaxis_re.match(key):
                fig.update_layout(**{key: axis_common_y})

        if not any(_xaxis_re.match(k) for k in layout_keys):
            fig.update_layout(xaxis=axis_common_x)
        if not any(_yaxis_re.match(k) for k in layout_keys):
            fig.update_layout(yaxis=axis_common_y)

        # -- Bar gap ---------------------------------------------------------
        fig.update_layout(bargap=settings.bar_gap, bargroupgap=settings.bar_group_gap)

        # -- Legend ----------------------------------------------------------
        legend_kwargs = dict(visible=settings.show_legend)
        if settings.show_legend:
            legend_kwargs.update(cls.get_legend_coords(settings.legend_pos))
        fig.update_layout(legend=legend_kwargs)

        # -- Colour palette & trace styling ----------------------------------
        palette = cls.get_color_palette(settings.palette)
        line_dash = _DASH_MAP.get(settings.line_style, 'solid')
        recolor = settings.palette != 'okabe_ito'

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

            if recolor:
                color = palette[data_trace_idx % len(palette)]
            else:
                color = None

            if settings.trace_opacity < 1.0:
                trace.update(opacity=settings.trace_opacity)

            if not is_bar and hasattr(trace, "line") and trace.line is not None:
                trace.line.width = settings.line_width
                if color:
                    trace.line.color = color
                trace.line.dash = line_dash

            if is_bar:
                if color and hasattr(trace, "marker") and trace.marker is not None:
                    trace.marker.color = color
            elif hasattr(trace, "marker") and trace.marker is not None:
                trace.marker.size = settings.marker_size
                if color:
                    trace.marker.color = color
                trace.marker.symbol = settings.marker_symbol

            data_trace_idx += 1

        # -- Dimensions & margins --------------------------------------------
        fig.update_layout(
            autosize=True,
            margin=dict(l=50, r=20, t=30 if not title_text else 50, b=40),
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
