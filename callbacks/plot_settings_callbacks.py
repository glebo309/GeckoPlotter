# callbacks/plot_settings_callbacks.py - Fixed duplicate outputs

from dash import Input, Output, State, callback_context, no_update
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash

def register_plot_settings_callbacks(app, data_manager):
    """Register plot settings callbacks that don't conflict with existing ones."""
    
    # Only handle the axis bounds reset - other settings will be handled in viz_callbacks
    @app.callback(
        [Output("x-min-input", "value", allow_duplicate=True),
         Output("x-max-input", "value", allow_duplicate=True),
         Output("y-min-input", "value", allow_duplicate=True),
         Output("y-max-input", "value", allow_duplicate=True)],
        Input("reset-axis-bounds-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def reset_axis_inputs(reset_clicks):
        """Clear axis input fields when reset button is clicked."""
        if reset_clicks:
            return None, None, None, None
        return no_update, no_update, no_update, no_update


def get_plot_settings_from_inputs(line_thickness, layout_options, grid_options, 
                                x_min, x_max, y_min, y_max, x_label, y_label):
    """
    Extract plot settings from component values (called from viz_callbacks).
    
    Returns:
        tuple: (line_width, plot_options, axis_range, axis_labels)
    """
    
    plot_options = {
        'separate_plots': 'separate_plots' in (layout_options or []),
        'show_legend': 'legend' in (layout_options or []),
        'smooth_lines': 'smooth' in (layout_options or []),
        'horizontal_grid': 'horizontal' in (grid_options or []),
        'vertical_grid': 'vertical' in (grid_options or [])
    }
    
    axis_range = {
        'x_min': x_min,
        'x_max': x_max,
        'y_min': y_min,
        'y_max': y_max,
        'auto_range': not any([x_min, x_max, y_min, y_max])
    }
    
    axis_labels = {
        'x_label': x_label or "Time (min)",
        'y_label': y_label or "Signal Intensity"
    }
    
    return line_thickness or 1.5, plot_options, axis_range, axis_labels


def apply_plot_settings(fig, plot_options=None, line_width=1.5, axis_range=None, axis_labels=None):
    """Apply plot settings with better styling."""
    
    if plot_options is None:
        plot_options = {
            'show_legend': True,
            'horizontal_grid': False,
            'vertical_grid': False,
            'smooth_lines': False
        }
    
    # Apply line thickness to all traces
    for trace in fig.data:
        if hasattr(trace, 'line') and trace.line:
            trace.line.width = line_width
        
        # Apply line smoothing if enabled
        if plot_options.get('smooth_lines', False) and hasattr(trace, 'line'):
            trace.line.shape = 'spline'
        else:
            if hasattr(trace, 'line'):
                trace.line.shape = 'linear'
    
    # Apply better layout settings
    fig.update_layout(
        showlegend=plot_options.get('show_legend', True),
        template='plotly_white',  # Clean white background instead of gray
        plot_bgcolor='white',     # Ensure plot area is white
        paper_bgcolor='white',    # Ensure paper is white
        font=dict(
            family="Segoe UI, Arial, sans-serif",
            size=12,
            color="#2c3e50"
        ),
        # Better legend positioning
        legend=dict(
            x=1.02, 
            y=1, 
            xanchor='left', 
            yanchor='top',
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='rgba(0,0,0,0.1)',
            borderwidth=1
        )
    )
    
    # Apply grid settings with subtle styling
    fig.update_xaxes(
        showgrid=plot_options.get('vertical_grid', False),
        gridwidth=1,
        gridcolor='rgba(128,128,128,0.2)',  # Very subtle grid
        linecolor='#ddd',
        linewidth=1
    )
    
    fig.update_yaxes(
        showgrid=plot_options.get('horizontal_grid', False),
        gridwidth=1,
        gridcolor='rgba(128,128,128,0.2)',  # Very subtle grid
        linecolor='#ddd',
        linewidth=1
    )
    
    # Apply axis labels
    if axis_labels:
        fig.update_xaxes(title=axis_labels.get('x_label', 'Time (min)'))
        fig.update_yaxes(title=axis_labels.get('y_label', 'Signal Intensity'))
    
    # Apply axis ranges if specified
    if axis_range and not axis_range.get('auto_range', True):
        if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
            fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']])
        
        if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
            fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']])
    
    return fig


def create_separate_plots(data_dict, plot_options=None, line_width=1.5, axis_range=None, axis_labels=None):
    """
    Create separate subplots for each chromatogram.
    
    Args:
        data_dict: Dictionary with chromatogram data
        plot_options: Plot settings
        line_width: Line thickness
        axis_range: Axis range settings
        axis_labels: Axis label settings
    
    Returns:
        Plotly figure with subplots
    """
    
    if not data_dict:
        return go.Figure()
    
    n_plots = len(data_dict)
    
    # Create subplots
    fig = make_subplots(
        rows=n_plots, 
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=list(data_dict.keys())
    )
    
    # Add traces to subplots
    for i, (name, data) in enumerate(data_dict.items(), 1):
        fig.add_trace(
            go.Scatter(
                x=data.get('x', []),
                y=data.get('y', []),
                mode='lines',
                name=name,
                line=dict(width=line_width),
                showlegend=False  # Turn off legend for subplots
            ),
            row=i, col=1
        )
    
    # Update layout
    fig.update_layout(
        height=300 * n_plots,  # Scale height with number of plots
        title_text="Chromatograms (Separate Views)"
    )
    
    # Apply grid settings to all subplots
    if plot_options:
        for i in range(1, n_plots + 1):
            fig.update_xaxes(
                showgrid=plot_options.get('vertical_grid', False),
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.3)',
                row=i, col=1
            )
            fig.update_yaxes(
                showgrid=plot_options.get('horizontal_grid', False),
                gridwidth=1,
                gridcolor='rgba(128,128,128,0.3)',
                row=i, col=1
            )
    
    # Apply axis labels to bottom plot
    if axis_labels:
        fig.update_xaxes(title=axis_labels.get('x_label', 'Time (min)'), row=n_plots, col=1)
        for i in range(1, n_plots + 1):
            fig.update_yaxes(title=axis_labels.get('y_label', 'Signal Intensity'), row=i, col=1)
    
    # Apply axis ranges if specified
    if axis_range and not axis_range.get('auto_range', True):
        for i in range(1, n_plots + 1):
            if axis_range.get('x_min') is not None and axis_range.get('x_max') is not None:
                fig.update_xaxes(range=[axis_range['x_min'], axis_range['x_max']], row=i, col=1)
            
            if axis_range.get('y_min') is not None and axis_range.get('y_max') is not None:
                fig.update_yaxes(range=[axis_range['y_min'], axis_range['y_max']], row=i, col=1)
    
    return fig


def prepare_chromatogram_data_for_plotting(file_data):
    """
    Convert file data to format expected by plot settings functions.
    
    Args:
        file_data: Your existing file data structure
        
    Returns:
        dict: {'filename': {'x': [...], 'y': [...]}}
    """
    data_dict = {}
    
    try:
        if not file_data:
            return data_dict
            
        filename = file_data.get('filename', 'Unknown')
        data = file_data.get('data')
        
        if data is None:
            return data_dict
        
        # Handle different data formats
        if isinstance(data, dict):
            # Data is already in dict format with x/y keys
            if 'x' in data and 'y' in data:
                data_dict[filename] = {'x': data['x'], 'y': data['y']}
            else:
                # Try to extract x/y from other keys
                x_data = data.get('time', data.get('rt', data.get('retention_time', [])))
                y_data = data.get('intensity', data.get('signal', data.get('absorbance', [])))
                if x_data and y_data:
                    data_dict[filename] = {'x': x_data, 'y': y_data}
        
        elif hasattr(data, 'index') and hasattr(data, 'values'):
            # Pandas-like DataFrame
            data_dict[filename] = {
                'x': data.index.tolist() if hasattr(data.index, 'tolist') else list(data.index),
                'y': data.values.tolist() if hasattr(data.values, 'tolist') else list(data.values)
            }
        
        elif hasattr(data, 'columns') and len(data.columns) >= 2:
            # Multi-column DataFrame - use first two columns
            columns = list(data.columns)
            data_dict[filename] = {
                'x': data[columns[0]].tolist(),
                'y': data[columns[1]].tolist()
            }
        
        elif isinstance(data, list) and len(data) > 0:
            # List of values - assume it's Y data, create X as indices
            data_dict[filename] = {
                'x': list(range(len(data))),
                'y': data
            }
    
    except Exception as e:
        print(f"Error preparing data for plotting: {e}")
        return {}
    
    return data_dict