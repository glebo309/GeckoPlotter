# =============================================================================
# File: services/plot_manager.py
# =============================================================================
"""
Plot Manager for GeckoPlotter V2 - Clean plotting logic service.
"""

import plotly.graph_objects as go
import pandas as pd
from typing import Dict, Any


class PlotManager:
    """Manages plot creation for different data types."""

    def __init__(self):
        self.default_colors = [
            '#E69F00', '#56B4E9', '#009E73', '#F0E442',
            '#0072B2', '#D55E00', '#CC79A7',
        ]

    def create_empty_plot(self, message: str = "Select a file to view data") -> go.Figure:
        """Create an empty placeholder plot."""
        fig = go.Figure()
        
        fig.update_layout(
            title=message,
            xaxis_title='X Axis',
            yaxis_title='Y Axis',
            template='plotly_white',
            height=400,
            showlegend=False
        )
        
        return fig

    def create_multi_file_plot(
        self,
        groups: dict,
        layout_mode: str = 'overlay',
    ) -> go.Figure:
        """Build a raw plot combining traces from grouped visible files.

        Parameters
        ----------
        groups : dict of {group_key: [(name, file_data), ...]}
        layout_mode : 'overlay' or 'stacked'
        """
        if not groups:
            return self.create_hidden_state_plot()

        # Flatten all files across groups for total count
        all_files = []
        for files in groups.values():
            all_files.extend(files)

        if not all_files:
            return self.create_hidden_state_plot()

        # Single group → simple overlay/stacked
        if len(groups) == 1:
            files = list(groups.values())[0]
            if layout_mode == 'stacked' and len(files) > 1:
                return self._create_stacked_plot(files)
            return self._create_overlay_plot(files)

        # Multiple groups → each group gets its own subplot section
        return self._create_grouped_plot(groups, layout_mode)

    # -- overlay (superposed) ------------------------------------------------

    def _create_overlay_plot(self, files: list) -> go.Figure:
        fig = go.Figure()
        trace_idx = 0
        for idx, (name, file_data) in enumerate(files):
            trace_idx = self._add_traces(fig, name, file_data, color_offset=trace_idx)
        fig.update_layout(
            template='plotly_white',
            autosize=True,
            showlegend=True,
            hovermode='closest',
        )
        return fig

    # -- grouped (different data types in separate subplots) ----------------

    _GROUP_LABELS = {
        'chromatogram': 'Chromatograms',
        'uvvis': 'UV-Vis Spectra',
        'lcms_ms': 'LC-MS TIC',
        'lcms_uv': 'LC-MS UV',
        'table': 'Tables',
        'other': 'Other',
    }

    def _create_grouped_plot(self, groups: dict, layout_mode: str) -> go.Figure:
        """Each data-type group gets its own subplot row with its own legend."""
        from plotly.subplots import make_subplots

        group_keys = list(groups.keys())
        n = len(group_keys)

        fig = make_subplots(
            rows=n, cols=1, shared_xaxes=False,
            vertical_spacing=max(0.03, 0.14 / n),
        )

        for row_idx, key in enumerate(group_keys, start=1):
            files = groups[key]
            legend_group = f'group{row_idx}'
            trace_idx = 0
            for i, (name, fdata) in enumerate(files):
                sub = go.Figure()
                trace_idx = self._add_traces(sub, name, fdata, color_offset=trace_idx)
                for trace in sub.data:
                    trace.showlegend = True
                    trace.legendgroup = legend_group
                    # Assign per-subplot legend (legend, legend2, legend3, …)
                    if row_idx > 1:
                        trace.legend = f'legend{row_idx}'
                    fig.add_trace(trace, row=row_idx, col=1)

        # Position per-subplot legends inside each subplot
        legend_kwargs = {}
        for row_idx in range(1, n + 1):
            # Compute vertical position for this subplot's legend
            # Subplots go top to bottom; row 1 is top
            y_top = 1.0 - (row_idx - 1) / n
            key = 'legend' if row_idx == 1 else f'legend{row_idx}'
            legend_kwargs[key] = dict(
                x=1, y=y_top, xanchor='right', yanchor='top',
                bgcolor='rgba(255,255,255,0.7)',
                font=dict(size=11),
            )

        fig.update_layout(
            template='plotly_white',
            autosize=True,
            hovermode='closest',
            **legend_kwargs,
        )
        return fig

    # -- stacked (separate subplots) ----------------------------------------

    def _create_stacked_plot(self, files: list) -> go.Figure:
        from plotly.subplots import make_subplots

        n = len(files)
        fig = make_subplots(
            rows=n, cols=1, shared_xaxes=True,
            vertical_spacing=max(0.03, 0.14 / n),
        )
        trace_idx = 0
        for i, (name, file_data) in enumerate(files):
            row = i + 1
            legend_group = f'group{row}'
            sub_fig = go.Figure()
            trace_idx = self._add_traces(sub_fig, name, file_data, color_offset=trace_idx)
            for trace in sub_fig.data:
                trace.showlegend = True
                trace.legendgroup = legend_group
                if row > 1:
                    trace.legend = f'legend{row}'
                fig.add_trace(trace, row=row, col=1)

        # Per-subplot legends
        legend_kwargs = {}
        for row in range(1, n + 1):
            y_top = 1.0 - (row - 1) / n
            key = 'legend' if row == 1 else f'legend{row}'
            legend_kwargs[key] = dict(
                x=1, y=y_top, xanchor='right', yanchor='top',
                bgcolor='rgba(255,255,255,0.7)',
                font=dict(size=11),
            )

        fig.update_layout(
            template='plotly_white',
            autosize=True,
            hovermode='closest',
            **legend_kwargs,
        )
        return fig

    # -- helper: add traces from one file to a figure -----------------------

    def _add_traces(self, fig, name, file_data, color_offset=0):
        """Add traces from file_data to fig. Returns next color index."""
        sr = file_data.get('standardized')
        if sr is None:
            return color_offset

        df = sr.data
        x_cols = sr.x_columns
        y_cols = sr.y_columns

        if not x_cols or not y_cols:
            return color_offset

        x_col = x_cols[0]
        if x_col not in df.columns:
            return color_offset

        x_vals = df[x_col]
        idx = color_offset

        for j, y_col in enumerate(y_cols):
            if y_col not in df.columns:
                continue
            color = self.default_colors[idx % len(self.default_colors)]
            label = f"{name} — {y_col}" if len(y_cols) > 1 else name
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=pd.to_numeric(df[y_col], errors="coerce"),
                mode="lines",
                name=label,
                line=dict(color=color, width=2),
            ))
            idx += 1

        return idx

    # -- hidden / empty state -----------------------------------------------

    def create_hidden_state_plot(self) -> go.Figure:
        """A styled empty state shown when all traces are hidden."""
        fig = go.Figure()
        fig.update_layout(
            template='plotly_white',
            autosize=True,
            showlegend=False,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            plot_bgcolor='#fafafa',
            paper_bgcolor='#fafafa',
            annotations=[dict(
                text=(
                    '<span style="font-size:36px">&#129422;</span><br>'
                    '<b>No visible traces</b><br>'
                    '<span style="color:#999;font-size:13px">'
                    'Click the eye icon in the file explorer<br>'
                    'to show or hide traces</span>'
                ),
                xref='paper', yref='paper',
                x=0.5, y=0.5,
                xanchor='center', yanchor='middle',
                showarrow=False,
                font=dict(size=16, color='#666'),
                align='center',
            )],
        )
        return fig

    def _create_error_plot(self, error_message: str) -> go.Figure:
        """Create an error plot with message."""
        fig = go.Figure()
        
        fig.add_annotation(
            text=f"Error: {error_message}",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            xanchor='center', yanchor='middle',
            showarrow=False,
            font=dict(size=16, color="red")
        )
        
        fig.update_layout(
            title="Plot Error",
            xaxis_title='X Axis',
            yaxis_title='Y Axis',
            template='plotly_white',
            height=400,
            showlegend=False
        )
        
        return fig

    def create_standardized_plot(self, result) -> go.Figure:
        """Create a plot from a StandardizedResult. Format-agnostic."""
        from src.ingestion.types import ColumnRole, PlotHint

        fig = go.Figure()
        df = result.data

        x_cols = result.x_columns
        y_cols = result.y_columns

        if x_cols:
            x_col = x_cols[0]
            x_vals = df[x_col]
            x_title = x_col
        else:
            x_vals = list(range(len(df)))
            x_title = "Index"

        if not y_cols:
            return self.create_empty_plot("No Y columns identified")

        mode_map = {
            PlotHint.LINE: "lines",
            PlotHint.SCATTER: "markers",
            PlotHint.MULTI_Y: "lines",
        }
        mode = mode_map.get(result.plot_hint, "lines")

        for i, col in enumerate(y_cols[:8]):
            color = self.default_colors[i % len(self.default_colors)]
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=pd.to_numeric(df[col], errors="coerce"),
                mode=mode,
                name=col,
                line=dict(color=color, width=2),
                hovertemplate=f"{col}<br>{x_title}: %{{x}}<br>%{{y:.4f}}<extra></extra>",
            ))

        import os
        raw_title = result.sample_name or result.identity.original_name
        title = os.path.splitext(raw_title)[0]
        wl = result.metadata.get("wavelength", "")
        if wl:
            title += f" ({wl} nm)"

        y_title = y_cols[0] if len(y_cols) == 1 else "Value"

        fig.update_layout(
            title=title,
            xaxis_title=x_title,
            yaxis_title=y_title,
            template="plotly_white",
            autosize=True,
            showlegend=len(y_cols) > 1,
            hovermode="closest",
        )
        return fig

    def get_plot_for_file(self, file_data: Dict[str, Any]) -> go.Figure:
        """Get plot for a file. StandardizedResult is the only path."""
        try:
            sr = file_data.get('standardized')
            if sr is not None:
                return self.create_standardized_plot(sr)
            return self._create_error_plot("No standardized data available")
        except Exception as e:
            return self._create_error_plot(f"Plot error: {str(e)}")
