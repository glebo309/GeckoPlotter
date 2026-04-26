"""
Table Manager for GeckoPlotter V2
Handles data table operations for the Table Editor
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Optional, Tuple, Any

# Okabe-Ito colorblind-friendly palette
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]


class TableManager:
    """Manages table data operations and plotting for Table Editor"""
    
    def __init__(self):
        self.df = None
        self.original_df = None
        
    def load_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Load data into table manager"""
        if data is None or data.empty:
            return pd.DataFrame()
        
        df = data.copy()
        
        # Add row ID if not present
        if '_row_id' not in df.columns:
            df.insert(0, '_row_id', range(len(df)))
        
        self.df = df
        self.original_df = df.copy()
        return df
    
    def transpose_data(self) -> pd.DataFrame:
        """Transpose the dataframe"""
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        # Remove _row_id temporarily
        df_no_id = self.df.drop(columns=['_row_id'])
        
        # Transpose
        df_t = df_no_id.T
        
        # Use first row as column names if possible
        try:
            df_t.columns = [str(c) for c in df_t.iloc[0]]
            df_t = df_t.iloc[1:]
        except:
            pass
        
        # Reset index to become a column
        df_t = df_t.reset_index()
        df_t.columns = ['Variable'] + list(df_t.columns[1:])
        
        # Clean up None/NaN
        df_t = df_t.fillna('')
        df_t = df_t.replace(['None', 'nan', 'NaN'], '')
        
        # Add new row IDs
        df_t.insert(0, '_row_id', range(len(df_t)))
        
        self.df = df_t
        return df_t
    
    def get_columns(self) -> List[str]:
        """Get list of column names (excluding _row_id)"""
        if self.df is None or self.df.empty:
            return []
        return [col for col in self.df.columns if col != '_row_id']
    
    def create_plot(
        self,
        x_col: Optional[str] = None,
        y1_cols: Optional[List[str]] = None,
        y2_col: Optional[str] = None,
        error_col: Optional[str] = None,
        plot_type: str = 'scatter',
        show_stats: bool = False,
        group_col: Optional[str] = None
    ) -> go.Figure:
        """
        Create plot from table data
        
        Args:
            x_col: Column for X axis
            y1_cols: List of columns for Y1 axis
            y2_col: Column for Y2 axis (secondary)
            error_col: Column for error bars
            plot_type: 'scatter', 'bar', 'line'
            show_stats: Show mean ± error
            group_col: Column for grouping/coloring
        """
        if self.df is None or self.df.empty:
            return self._empty_plot("No data loaded")
        
        y1_cols = y1_cols or []
        
        if not y1_cols and not y2_col:
            return self._empty_plot("Select columns to plot")
        
        # Create figure
        if y2_col:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
        else:
            fig = go.Figure()
        
        # Get X values
        if x_col and x_col in self.df.columns:
            x_vals = self.df[x_col].tolist()
            x_is_numeric = pd.api.types.is_numeric_dtype(self.df[x_col])
        else:
            x_vals = list(range(len(self.df)))
            x_is_numeric = True
        
        # Plot Y1 series
        for idx, y_col in enumerate(y1_cols):
            if y_col not in self.df.columns:
                continue
            
            y_vals = pd.to_numeric(self.df[y_col], errors='coerce').tolist()
            color = OKABE_ITO[idx % len(OKABE_ITO)]
            
            # Get error bars if specified
            error_y = None
            if error_col and error_col in self.df.columns:
                errors = pd.to_numeric(self.df[error_col], errors='coerce').tolist()
                error_y = dict(type='data', array=errors, visible=True)
            
            if plot_type == 'bar':
                trace = go.Bar(
                    x=x_vals, y=y_vals, name=y_col,
                    marker_color=color,
                    error_y=error_y
                )
            elif plot_type == 'line':
                trace = go.Scatter(
                    x=x_vals, y=y_vals, name=y_col,
                    mode='lines+markers',
                    line=dict(color=color, width=2),
                    marker=dict(size=8),
                    error_y=error_y
                )
            else:  # scatter
                trace = go.Scatter(
                    x=x_vals, y=y_vals, name=y_col,
                    mode='markers',
                    marker=dict(size=10, color=color),
                    error_y=error_y
                )
            
            if y2_col:
                fig.add_trace(trace, secondary_y=False)
            else:
                fig.add_trace(trace)
        
        # Plot Y2 if specified
        if y2_col and y2_col in self.df.columns:
            y2_vals = pd.to_numeric(self.df[y2_col], errors='coerce').tolist()
            color = OKABE_ITO[len(y1_cols) % len(OKABE_ITO)]
            
            trace = go.Scatter(
                x=x_vals, y=y2_vals, name=y2_col,
                mode='lines+markers',
                line=dict(color=color, width=2, dash='dash'),
                marker=dict(size=8)
            )
            fig.add_trace(trace, secondary_y=True)
        
        # Update layout
        fig.update_layout(
            template='plotly_white',
            autosize=True,
            showlegend=True,
            hovermode='x unified',
            xaxis_title=x_col or 'Index',
            yaxis_title='Value',
            font=dict(size=12)
        )
        
        if y2_col:
            fig.update_yaxes(title_text=y1_cols[0] if y1_cols else 'Y1', secondary_y=False)
            fig.update_yaxes(title_text=y2_col, secondary_y=True)
        
        return fig
    
    def calculate_stats(
        self,
        columns: List[str],
        stat_type: str = 'mean'
    ) -> Dict[str, float]:
        """
        Calculate statistics for columns
        
        Args:
            columns: List of column names
            stat_type: 'mean', 'median', 'std', 'sem'
        """
        if self.df is None or self.df.empty:
            return {}
        
        stats = {}
        for col in columns:
            if col not in self.df.columns:
                continue
            
            values = pd.to_numeric(self.df[col], errors='coerce').dropna()
            
            if len(values) == 0:
                stats[col] = np.nan
                continue
            
            if stat_type == 'mean':
                stats[col] = values.mean()
            elif stat_type == 'median':
                stats[col] = values.median()
            elif stat_type == 'std':
                stats[col] = values.std()
            elif stat_type == 'sem':
                stats[col] = values.sem()
            else:
                stats[col] = np.nan
        
        return stats
    
    def add_column(self, col_name: str, default_value: Any = '') -> pd.DataFrame:
        """Add a new column to the dataframe"""
        if self.df is None:
            return pd.DataFrame()
        
        self.df[col_name] = default_value
        return self.df
    
    def delete_column(self, col_name: str) -> pd.DataFrame:
        """Delete a column from the dataframe"""
        if self.df is None or col_name not in self.df.columns:
            return self.df
        
        if col_name != '_row_id':  # Never delete row ID
            self.df = self.df.drop(columns=[col_name])
        
        return self.df
    
    def update_cell(self, row_id: int, col_name: str, value: Any) -> bool:
        """Update a single cell value"""
        if self.df is None:
            return False
        
        try:
            self.df.loc[self.df['_row_id'] == row_id, col_name] = value
            return True
        except:
            return False
    
    def export_data(self, format: str = 'csv') -> bytes:
        """Export data in specified format"""
        if self.df is None or self.df.empty:
            return b''
        
        # Remove _row_id for export
        df_export = self.df.drop(columns=['_row_id'])
        
        if format == 'csv':
            return df_export.to_csv(index=False).encode('utf-8')
        elif format == 'excel':
            import io
            buffer = io.BytesIO()
            df_export.to_excel(buffer, index=False)
            return buffer.getvalue()
        else:
            return b''
    
    def _empty_plot(self, message: str) -> go.Figure:
        """Create empty plot with message"""
        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color='#999')
        )
        fig.update_layout(
            template='plotly_white',
            autosize=True,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        return fig
