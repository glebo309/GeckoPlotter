# =============================================================================
# File: services/plot_manager.py
# =============================================================================
"""
Plot Manager for GeckoPlotter V2 - Clean plotting logic service.
"""

import plotly.graph_objects as go
import pandas as pd
from typing import Dict, Any

from services.plot_settings_service import COLOR_PALETTES


class PlotManager:
    """Manages plot creation for different data types."""

    def __init__(self):
        self.default_colors = list(COLOR_PALETTES['muted'])

    def create_empty_plot(self, message: str = "Select a file to view data") -> go.Figure:
        fig = go.Figure()
        fig.update_layout(
            template='plotly_white',
            xaxis={'visible': False},
            yaxis={'visible': False},
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            annotations=[dict(
                text=f"🦎  {message}",
                xref='paper', yref='paper',
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=15, color='#bbb'),
            )],
        )
        return fig

    def create_multi_file_plot(
        self,
        groups: dict,
        layout_mode: str = 'overlay',
        subplot_spacing: float = 0.08,
    ) -> go.Figure:
        """Build a raw plot combining traces from grouped visible files.

        Parameters
        ----------
        groups : dict of {group_key: [(name, file_data), ...]}
        layout_mode : 'overlay' or 'stacked'
        subplot_spacing : vertical gap between subplots (0-0.3)
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
                return self._create_stacked_plot(files, subplot_spacing)
            return self._create_overlay_plot(files)

        # Multiple groups → each group gets its own subplot section
        return self._create_grouped_plot(groups, layout_mode, subplot_spacing)

    # -- overlay (superposed) ------------------------------------------------

    def _create_overlay_plot(self, files: list) -> go.Figure:
        fig = go.Figure()
        trace_idx = 0
        for idx, (name, file_data) in enumerate(files):
            trace_idx = self._add_traces(fig, name, file_data, color_offset=trace_idx)
        units = {}
        axes_by_unit = {}
        traces_by_unit = {}
        for trace in fig.data:
            source = next((data for _, data in files
                           if data.get('record', {}).get('id') == trace.meta.get('file_id')), files[0][1])
            label = self._measurement_label(source)
            if label not in axes_by_unit:
                index = len(axes_by_unit) + 1
                axes_by_unit[label] = ('y' if index == 1 else f'y{index}',
                                       'yaxis' if index == 1 else f'yaxis{index}')
            ref, key = axes_by_unit[label]
            trace.yaxis = ref
            traces_by_unit.setdefault(label, []).append(trace)
            units[key] = label
        for index, (label, traces) in enumerate(traces_by_unit.items(), 1):
            _, key = axes_by_unit[label]
            color = '#444'
            axis = dict(title=dict(text=label, font=dict(color=color)),
                        tickfont=dict(color=color), color=color, autorange=True,
                        automargin=True, showgrid=index == 1)
            if index > 1:
                axis.update(overlaying='y', anchor='free', side='right',
                            autoshift=True, tickmode='sync')
            fig.update_layout(**{key: axis})
        sr = files[0][1].get('standardized')
        fig.update_layout(
            template='plotly_white',
            autosize=True,
            showlegend=True,
            hovermode='closest',
            meta={'gecko_axis_units': units},
            xaxis_title=sr.x_columns[0] if sr and sr.x_columns else '',
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

    @staticmethod
    def _vertical_spacing(rows: int, requested: float) -> float:
        # Plotly requires total gaps < 1. Reserve at least half the figure for
        # the actual data panes when many channels are visible.
        return min(max(0.02, requested), 0.5 / max(1, rows - 1))

    def _create_grouped_plot(self, groups: dict, layout_mode: str, subplot_spacing: float = 0.08) -> go.Figure:
        """Each data-type group gets its own subplot row with its own legend."""
        from plotly.subplots import make_subplots

        group_keys = list(groups.keys())
        n = len(group_keys)

        fig = make_subplots(
            rows=n, cols=1, shared_xaxes=False,
            vertical_spacing=self._vertical_spacing(n, subplot_spacing),
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
            axis_key = 'yaxis' if row_idx == 1 else f'yaxis{row_idx}'
            low, high = fig.layout[axis_key].domain
            y_top = high - (high - low) * 0.06
            key = 'legend' if row_idx == 1 else f'legend{row_idx}'
            legend_kwargs[key] = dict(
                x=0.98, y=y_top, xanchor='right', yanchor='top',
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

    _YLABEL_MAP = {
        'ms_positive': 'Ion Count',
        'ms_negative': 'Ion Count',
        'lcms_ms': 'Ion Count',
        'lcms_uv': 'Absorbance (mAU)',
        'vwd_a': 'Absorbance (mAU)',
        'vwd_b': 'Absorbance (mAU)',
    }

    def _measurement_label(self, file_data):
        sr = file_data.get('standardized')
        role = file_data.get('record', {}).get('type', '')
        category = sr.source_category.value if sr else ''
        return (self._YLABEL_MAP.get(role) or self._YLABEL_MAP.get(category)
                or (sr.y_columns[0] if sr and sr.y_columns else 'Intensity'))

    def _create_stacked_plot(self, files: list, subplot_spacing: float = 0.08) -> go.Figure:
        from plotly.subplots import make_subplots

        n = len(files)
        fig = make_subplots(
            rows=n, cols=1, shared_xaxes=True,
            vertical_spacing=self._vertical_spacing(n, subplot_spacing),
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

            role = file_data.get('record', {}).get('type', '')
            sr = file_data.get('standardized')
            cat = sr.source_category.value if sr else ''
            if sr and sr.x_columns:
                # Capture the measurement identity on every pane before shared
                # axis styling hides upper titles.
                fig.update_xaxes(title_text=sr.x_columns[0], row=row, col=1)
            y_label = self._measurement_label(file_data)
            if y_label:
                axis_key = 'yaxis' if row == 1 else f'yaxis{row}'
                fig.update_layout(**{axis_key: dict(title_text=y_label)})

        legend_kwargs = {}
        for row in range(1, n + 1):
            axis_key = 'yaxis' if row == 1 else f'yaxis{row}'
            low, high = fig.layout[axis_key].domain
            y_top = high - (high - low) * 0.06
            key = 'legend' if row == 1 else f'legend{row}'
            legend_kwargs[key] = dict(
                x=0.98, y=y_top, xanchor='right', yanchor='top',
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
        from ingestion.types import PlotHint
        from services.decimation import for_display

        sr = file_data.get('standardized')
        if sr is None:
            return color_offset

        file_id = file_data.get('record', {}).get('id', '')
        trace_meta = {'file_id': file_id}
        metadata = file_data.get('metadata', {})
        if (getattr(sr.source_category, 'value', None) in ('chromatogram', 'lcms_uv', 'lcms_ms')
                and metadata.get('parent_bundle_id')):
            trace_meta.update(rename_file_id=metadata['parent_bundle_id'],
                              rename_label=metadata.get('parent_bundle_name', ''))

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
        is_lollipop = getattr(sr, 'plot_hint', None) == PlotHint.LOLLIPOP

        for j, y_col in enumerate(y_cols):
            if y_col not in df.columns:
                continue
            color = self.default_colors[idx % len(self.default_colors)]
            label = f"{name} — {y_col}" if len(y_cols) > 1 else name
            trace_cls = go.Scattergl if len(x_vals) > 5000 else go.Scatter

            if is_lollipop:
                y_vals = pd.to_numeric(df[y_col], errors="coerce")
                xs, ys = [], []
                for xv, yv in zip(x_vals, y_vals):
                    xs.extend([xv, xv, None])
                    ys.extend([0, yv, None])
                fig.add_trace(trace_cls(
                    x=xs, y=ys, mode='lines',
                    name=label,
                    line=dict(color=color, width=1),
                    meta={**trace_meta, 'y_column': y_col},
                ))
            else:
                y_vals = pd.to_numeric(df[y_col], errors="coerce")
                # Draw at most ~3000 points per trace (every peak top kept); the data itself stays complete.
                x_draw, y_draw = for_display(x_vals.to_numpy(), y_vals.to_numpy())
                fig.add_trace(trace_cls(
                    x=x_draw,
                    y=y_draw,
                    mode="lines",
                    name=label,
                    line=dict(color=color, width=2),
                    meta={**trace_meta, 'y_column': y_col, **({'full_points': len(y_vals)} if len(y_draw) < len(y_vals) else {})},
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
        from services.decimation import for_display
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

            if result.plot_hint == PlotHint.LOLLIPOP:
                y_vals = pd.to_numeric(df[col], errors="coerce")
                xs, ys = [], []
                for xv, yv in zip(x_vals, y_vals):
                    xs.extend([xv, xv, None])
                    ys.extend([0, yv, None])
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode='lines',
                    name=col,
                    line=dict(color=color, width=1),
                    hovertemplate=f"{col}<br>{x_title}: %{{x:.4g}}<br>%{{y:.4g}}<extra></extra>",
                ))
            else:
                y_vals = pd.to_numeric(df[col], errors="coerce")
                x_draw, y_draw = ((x_vals, y_vals) if 'markers' in str(mode)
                                  else for_display(pd.Series(x_vals).to_numpy(), y_vals.to_numpy()))
                fig.add_trace(go.Scatter(
                    x=x_draw,
                    y=y_draw,
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
