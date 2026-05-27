# =============================================================================
# File: callbacks/peak_overlay.py
# =============================================================================
"""
Shared peak overlay rendering for GeckoPlotter V2.

Consolidates duplicated peak rendering code from baseline_callbacks.py
and viz_callbacks.py into a single module.
"""

import numpy as np
from scipy import interpolate


FILL_COLORS = [
    'rgba(180, 120, 220, 0.30)',
    'rgba(100, 180, 120, 0.30)',
    'rgba(80, 160, 220, 0.30)',
    'rgba(220, 160, 80, 0.30)',
    'rgba(220, 100, 120, 0.30)',
    'rgba(120, 200, 200, 0.30)',
]


def rgba(hex_color, alpha):
    """Convert #RRGGBB to rgba(...) while accepting existing rgba values."""
    if isinstance(hex_color, str) and hex_color.startswith('#') and len(hex_color) == 7:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return f'rgba({r}, {g}, {b}, {alpha})'
    return hex_color


def _y_curve(time_arr, signal_arr, x):
    """Get chromatogram intensity at time x via interpolation."""
    interp_fn = interpolate.interp1d(time_arr, signal_arr, bounds_error=False, fill_value=0)
    return max(0, float(interp_fn(x)))


def add_deselect_catcher(fig, time_arr, signal_arr):
    """Add a near-transparent plot-area trace that clicks to deselect."""
    import plotly.graph_objects as go

    x_vals = np.asarray(time_arr, dtype=float)
    y_vals = np.asarray(signal_arr, dtype=float)
    finite_x = x_vals[np.isfinite(x_vals)]
    finite_y = y_vals[np.isfinite(y_vals)]
    if finite_x.size < 2 or finite_y.size < 2:
        return

    x0, x1 = float(np.nanmin(finite_x)), float(np.nanmax(finite_x))
    y0, y1 = float(np.nanmin(finite_y)), float(np.nanmax(finite_y))
    y_pad = max((y1 - y0) * 0.08, 1e-9)
    y0 -= y_pad
    y1 += y_pad

    fig.add_trace(go.Scatter(
        x=[x0, x1, x1, x0, x0],
        y=[y0, y0, y1, y1, y0],
        fill='toself',
        fillcolor='rgba(255,255,255,0.001)',
        mode='lines',
        line=dict(width=0, color='rgba(255,255,255,0)'),
        customdata=[['__deselect__', 'catcher']] * 5,
        hoverinfo='skip',
        showlegend=False,
        meta='peak_overlay',
    ))


def add_selected_baseline_handle(fig, peak, row=None):
    """Show the selected peak's baseline plus visible p-point markers."""
    import plotly.graph_objects as go

    if not peak.p_line or len(peak.p_line) != 2:
        return

    line_color = peak.color or '#E69F00'
    p0, p1 = peak.p_line

    xref = 'x' if not row or row == 1 else f'x{row}'
    yref = 'y' if not row or row == 1 else f'y{row}'

    fig.add_shape(
        type='line',
        x0=p0[0], y0=p0[1],
        x1=p1[0], y1=p1[1],
        xref=xref, yref=yref,
        name=f'baseline:{peak.peak_id}',
        line=dict(color=line_color, width=2, dash='dot'),
        editable=True,
    )

    add_kw = dict(row=row, col=1) if row else {}
    fig.add_trace(go.Scatter(
        x=[p0[0], p1[0]],
        y=[p0[1], p1[1]],
        mode='markers',
        marker=dict(
            size=9,
            color='#ffffff',
            line=dict(color=line_color, width=2),
            symbol='circle',
        ),
        customdata=[[peak.peak_id, 'p-point'], [peak.peak_id, 'p-point']],
        hoverinfo='skip',
        showlegend=False,
        meta='peak_overlay',
    ), **add_kw)


def cleanup_peak_traces(fig):
    """Remove all existing peak overlay traces and shapes from the figure."""
    fig.data = [t for t in fig.data if not (hasattr(t, 'meta') and t.meta == 'peak_overlay')]
    fig.layout.shapes = ()
    fig.update_layout(uirevision='main-plot')


def add_peak_traces(fig, all_peaks, time_arr, signal_arr, selected_peak_id=None, row=None):
    """Add peak overlay traces to the figure.

    Parameters
    ----------
    fig : go.Figure
        The figure to add peaks to.
    all_peaks : list
        Peak objects from peak_service.get_peaks().
    time_arr, signal_arr : array-like
        Chromatogram data for interpolation.
    selected_peak_id : str, optional
        Currently selected peak for highlighting.
    row : int, optional
        Subplot row (1-based). When set, traces go to that row.
    """
    import plotly.graph_objects as go

    if not all_peaks:
        return

    add_kw = dict(row=row, col=1) if row else {}

    for i, peak in enumerate(all_peaks):
        is_selected = peak.peak_id == selected_peak_id
        fill_color = rgba(peak.color, 0.58 if is_selected else 0.30) if peak.color else FILL_COLORS[i % len(FILL_COLORS)]
        line_color = peak.color if is_selected else 'rgba(0,0,0,0)'

        has_custom_label = bool(peak.label) if hasattr(peak, 'label') else False

        if peak.poly_x and peak.poly_y:
            poly_x = list(peak.poly_x)
            poly_y = list(peak.poly_y)
            fig.add_trace(go.Scatter(
                x=poly_x, y=poly_y,
                fill='toself', fillcolor=fill_color,
                mode='lines',
                line=dict(color=line_color, width=2 if is_selected else 0),
                customdata=[peak.peak_id] * len(poly_x),
                hoverinfo='skip',
                showlegend=False, meta='peak_overlay',
            ), **add_kw)
            if has_custom_label:
                fig.add_trace(go.Scatter(
                    x=[peak.rt],
                    y=[peak.height],
                    mode='text',
                    text=[peak.label],
                    textposition='top center',
                    textfont=dict(size=9, color='#333'),
                    hoverinfo='skip',
                    showlegend=False,
                    meta='peak_overlay',
                ), **add_kw)
            if is_selected:
                add_selected_baseline_handle(fig, peak, row=row)

        elif has_custom_label:
            marker_y = _y_curve(time_arr, signal_arr, peak.rt)
            fig.add_trace(go.Scatter(
                x=[peak.rt],
                y=[marker_y],
                mode='text',
                text=[peak.label],
                textposition='top center',
                textfont=dict(size=9, color='#333'),
                hovertemplate=f'{peak.name} ({peak.source})<br>RT: {peak.rt:.3f} min<br>Area: {peak.area:.1f}<extra></extra>',
                showlegend=False,
                meta='peak_overlay',
            ), **add_kw)


def overlay_peaks_on_figure(all_peaks, figure, time_arr, signal_arr, selected_peak_id=None):
    """Rebuild the current figure, adding all peak overlays.

    Backward-compatible wrapper: cleans up old traces, then adds new ones.
    """
    import plotly.graph_objects as go

    fig = go.Figure(figure) if isinstance(figure, dict) else (
        go.Figure(figure) if figure else go.Figure()
    )

    cleanup_peak_traces(fig)
    add_peak_traces(fig, all_peaks, time_arr, signal_arr, selected_peak_id)
    return fig


def patch_figure_with_peaks(all_peaks, current_figure, time_arr, signal_arr, selected_peak_id=None):
    """Patch only peak overlays and editable shapes, leaving plot layout untouched.

    Parameters
    ----------
    all_peaks : list
        List of peak objects from peak_service.get_peaks().
    current_figure : dict
        The current figure dict from the Dash store.
    time_arr : array-like
        Time values from the chromatogram.
    signal_arr : array-like
        Signal values from the chromatogram.
    selected_peak_id : str, optional
        ID of the currently selected peak for highlighting.

    Returns
    -------
    Patch
        A Dash Patch object with updated peak overlays.
    """
    from dash import Patch

    fig = overlay_peaks_on_figure(all_peaks, current_figure, time_arr, signal_arr, selected_peak_id)
    fig_json = fig.to_plotly_json()
    old_traces = (current_figure or {}).get('data', []) if isinstance(current_figure, dict) else []
    old_overlays = [t for t in old_traces if isinstance(t, dict) and t.get('meta') == 'peak_overlay']
    new_overlays = [t for t in fig_json.get('data', []) if isinstance(t, dict) and t.get('meta') == 'peak_overlay']

    patch = Patch()
    for trace in old_overlays:
        patch['data'].remove(trace)
    for trace in new_overlays:
        patch['data'].append(trace)
    patch['layout']['shapes'] = fig_json.get('layout', {}).get('shapes', [])
    patch['layout']['uirevision'] = 'main-plot'
    return patch
