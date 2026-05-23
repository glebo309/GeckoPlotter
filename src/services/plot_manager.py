# =============================================================================
# File: services/plot_manager.py
# =============================================================================
"""
Plot Manager for GeckoPlotter V2 - Clean plotting logic service.
"""

import plotly.graph_objects as go
import pandas as pd
from typing import Optional, Dict, Any


class PlotManager:
    """Manages plot creation for different data types."""

    def __init__(self):
        self.default_colors = ['#ff6b35', '#007acc', '#28a745', '#dc3545', '#ffc107']

    def create_chromatogram_plot(self, data: pd.DataFrame, metadata: Dict[str, Any]) -> go.Figure:
        """Create a chromatogram plot from data."""
        try:
            # Expect columns: 'Time (min)', 'Value (mAU)'
            if 'Time (min)' not in data.columns or 'Value (mAU)' not in data.columns:
                return self._create_error_plot("Invalid chromatogram data format")

            fig = go.Figure()

            # Add chromatogram trace
            fig.add_trace(go.Scatter(
                x=data['Time (min)'],
                y=data['Value (mAU)'],
                mode='lines',
                name='Chromatogram',
                line=dict(color=self.default_colors[0], width=2),
                hovertemplate='Time: %{x:.2f} min<br>Intensity: %{y:.1f} mAU<extra></extra>'
            ))

            # Get wavelength from metadata if available
            wavelength = metadata.get('wavelength_nm', 'Unknown')
            title = f"Chromatogram"
            if wavelength != 'Unknown':
                title += f" (λ = {wavelength} nm)"

            fig.update_layout(
                title=title,
                xaxis_title='Time (min)',
                yaxis_title='Intensity (mAU)',
                template='plotly_white',
                autosize=True,
                showlegend=True,
                hovermode='closest'
            )

            return fig

        except Exception as e:
            return self._create_error_plot(f"Error creating chromatogram plot: {str(e)}")

    def create_uvvis_plot(self, data: pd.DataFrame, metadata: Dict[str, Any], 
                         selected_columns: Optional[list] = None) -> go.Figure:
        """Create a UV-Vis spectrum plot from data."""
        try:
            if 'Wavelength' not in data.columns:
                return self._create_error_plot("No wavelength data found")

            fig = go.Figure()

            # Get intensity columns (exclude Wavelength)
            intensity_cols = [col for col in data.columns if col != 'Wavelength']
            
            # If specific columns selected, use those; otherwise show first few
            if selected_columns:
                cols_to_plot = [col for col in selected_columns if col in intensity_cols]
            else:
                cols_to_plot = intensity_cols[:5]  # Show first 5 wells by default

            # Add traces for each selected column
            for i, col in enumerate(cols_to_plot):
                color = self.default_colors[i % len(self.default_colors)]
                
                fig.add_trace(go.Scatter(
                    x=data['Wavelength'],
                    y=data[col],
                    mode='lines',
                    name=col,
                    line=dict(color=color, width=2),
                    hovertemplate=f'{col}<br>Wavelength: %{{x:.0f}} nm<br>Absorbance: %{{y:.3f}}<extra></extra>'
                ))

            # Get wavelength range from metadata
            wl_range = metadata.get('wavelength_range', (None, None))
            title = "UV-Vis Spectrum"
            if wl_range[0] and wl_range[1]:
                title += f" ({wl_range[0]:.0f}-{wl_range[1]:.0f} nm)"

            fig.update_layout(
                title=title,
                xaxis_title='Wavelength (nm)',
                yaxis_title='Absorbance',
                template='plotly_white',
                autosize=True,
                showlegend=True,
                hovermode='closest'
            )

            return fig

        except Exception as e:
            return self._create_error_plot(f"Error creating UV-Vis plot: {str(e)}")

    def create_lcms_tic_plot(self, data: pd.DataFrame, metadata: Dict[str, Any]) -> go.Figure:
        if data is None or data.empty:
            return self._create_error_plot("No TIC data available")

        fig = go.Figure()
        ion_mode = metadata.get('ionization_mode', 'unknown')
        color = '#27ae60' if ion_mode == 'positive' else '#e74c3c' if ion_mode == 'negative' else '#3498db'

        fig.add_trace(go.Scatter(
            x=data['Time (min)'],
            y=data['Intensity'],
            mode='lines',
            name=f"TIC {ion_mode.upper()}" if ion_mode != 'unknown' else 'TIC',
            line=dict(color=color, width=2),
            hovertemplate='RT: %{x:.2f} min<br>Intensity: %{y:,.0f}<extra></extra>'
        ))

        title = "LC-MS TIC"
        if ion_mode != 'unknown':
            title += f" ({ion_mode.upper()})"

        fig.update_layout(
            title=title,
            xaxis_title='Retention Time (min)',
            yaxis_title='Intensity',
            template='plotly_white',
            height=400,
            showlegend=False,
            hovermode='closest'
        )

        summary_lines = []
        if 'sample_name' in metadata:
            summary_lines.append(f"📊 {metadata['sample_name']}")
        if 'retention_time_range' in metadata:
            summary_lines.append(f"🕒 RT: {metadata['retention_time_range']}")
        if 'mass_range_str' in metadata:
            summary_lines.append(f"⚖️ m/z: {metadata['mass_range_str']}")

        if summary_lines:
            fig.add_annotation(
                text="<br>".join(summary_lines),
                xref='paper',
                yref='paper',
                x=0.02,
                y=0.95,
                xanchor='left',
                yanchor='top',
                showarrow=False,
                bgcolor='rgba(255,255,255,0.85)',
                align='left'
            )

        return fig

    def create_lcms_uv_plot(self, data: pd.DataFrame, metadata: Dict[str, Any]) -> go.Figure:
        if data is None or data.empty:
            return self._create_error_plot("No UV chromatogram available")

        fig = go.Figure()
        wavelength = metadata.get('wavelength', 'Unknown')
        channel = metadata.get('detector_channel', 'Unknown')

        fig.add_trace(go.Scatter(
            x=data['Time (min)'],
            y=data['Intensity (mAU)'],
            mode='lines',
            name=f"UV {channel}",
            line=dict(color='#9b59b6', width=2),
            hovertemplate='RT: %{x:.2f} min<br>Absorbance: %{y:.1f} mAU<extra></extra>'
        ))

        title = "LC-MS UV Chromatogram"
        suffix = []
        if channel != 'Unknown':
            suffix.append(f"Channel {channel}")
        if wavelength:
            suffix.append(f"{wavelength} nm")
        if suffix:
            title += f" ({', '.join(suffix)})"

        fig.update_layout(
            title=title,
            xaxis_title='Retention Time (min)',
            yaxis_title='Absorbance (mAU)',
            template='plotly_white',
            height=400,
            showlegend=False,
            hovermode='closest'
        )

        return fig

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

    def create_generic_table_plot(self, data: pd.DataFrame, metadata: Dict[str, Any]) -> go.Figure:
        """Create a plot for generic CSV/table data.

        Uses auto-detected X/Y columns from metadata when available,
        otherwise falls back to heuristic detection.
        """
        try:
            fig = go.Figure()

            numeric_cols = data.select_dtypes(include='number').columns.tolist()
            numeric_cols = [c for c in numeric_cols if c != '_row_id']

            if not numeric_cols:
                return self.create_empty_plot("No numeric columns found to plot.\nUse the publication plotter to select data manually.")

            auto_x = metadata.get('auto_x')
            auto_y = metadata.get('auto_y', [])

            if auto_x and auto_x in data.columns:
                x_col = auto_x
                x_vals = data[x_col]
                x_title = x_col
            else:
                non_numeric = [c for c in data.columns if c not in numeric_cols and c != '_row_id']
                if non_numeric:
                    x_col = non_numeric[0]
                    x_vals = data[x_col].astype(str)
                    x_title = x_col
                elif len(numeric_cols) >= 2:
                    x_col = numeric_cols[0]
                    x_vals = data[x_col]
                    x_title = x_col
                else:
                    x_col = None
                    x_vals = list(range(len(data)))
                    x_title = 'Index'

            y_cols = [c for c in auto_y if c in data.columns and c != x_col]
            if not y_cols:
                y_cols = [c for c in numeric_cols if c != x_col][:8]

            for i, col in enumerate(y_cols):
                color = self.default_colors[i % len(self.default_colors)]
                fig.add_trace(go.Scatter(
                    x=x_vals,
                    y=pd.to_numeric(data[col], errors='coerce'),
                    mode='lines',
                    name=col,
                    line=dict(color=color, width=2),
                    hovertemplate=f'{col}<br>{x_title}: %{{x}}<br>%{{y:.4f}}<extra></extra>',
                ))

            sample_name = metadata.get('sample_name', '')
            file_name = metadata.get('file_name', metadata.get('name', 'Data'))
            title = sample_name if sample_name else file_name
            wavelength = metadata.get('wavelength', '')
            if wavelength:
                title += f' (λ = {wavelength} nm)'

            y_title = y_cols[0] if len(y_cols) == 1 else 'Value'

            fig.update_layout(
                title=title,
                xaxis_title=x_title,
                yaxis_title=y_title,
                template='plotly_white',
                autosize=True,
                showlegend=len(y_cols) > 1,
                hovermode='closest',
            )
            return fig

        except Exception as e:
            return self._create_error_plot(f"Error plotting table data: {str(e)}")

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
        for idx, (name, file_data) in enumerate(files):
            self._add_traces(fig, name, file_data, color_offset=idx)
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
            for i, (name, fdata) in enumerate(files):
                sub = go.Figure()
                self._add_traces(sub, name, fdata, color_offset=i)
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
        for i, (name, file_data) in enumerate(files):
            row = i + 1
            legend_group = f'group{row}'
            sub_fig = go.Figure()
            self._add_traces(sub_fig, name, file_data, color_offset=i)
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
        """Add traces from file_data to fig using StandardizedResult."""
        sr = file_data.get('standardized')
        if sr is None:
            return

        df = sr.data
        x_cols = sr.x_columns
        y_cols = sr.y_columns

        if not x_cols or not y_cols:
            return

        x_col = x_cols[0]
        if x_col not in df.columns:
            return

        x_vals = df[x_col]

        for j, y_col in enumerate(y_cols):
            if y_col not in df.columns:
                continue
            color = self.default_colors[(color_offset + j) % len(self.default_colors)]
            label = f"{name} — {y_col}" if len(y_cols) > 1 else name
            fig.add_trace(go.Scatter(
                x=x_vals,
                y=pd.to_numeric(df[y_col], errors="coerce"),
                mode="lines",
                name=label,
                line=dict(color=color, width=2),
            ))

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

        title = result.sample_name or result.identity.original_name
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
