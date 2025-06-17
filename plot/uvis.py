# File: plot/uvis.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def create_uvvis_plot(file_data, selected_wells=None, max_wells=5):
    """Create a simple UV-Vis absorption spectrum plot"""
    
    data = file_data['data']
    metadata = file_data['metadata']
    
    if data is None or 'Wavelength' not in data.columns:
        return go.Figure().add_annotation(
            text="No wavelength data available", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    fig = go.Figure()
    
    # Get wavelength column
    wavelengths = data['Wavelength']
    
    # If no wells specified, show first few filled wells
    if selected_wells is None:
        filled_wells = metadata.get('filled_wells', [])
        selected_wells = filled_wells[:max_wells]  # Show first N wells
        
        if not selected_wells:
            # Fallback: show any wells with data
            intensity_columns = metadata.get('intensity_columns', [])
            selected_wells = intensity_columns[:max_wells]
    
    if not selected_wells:
        return go.Figure().add_annotation(
            text="No wells with data found", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    # Plot each selected well
    colors = px.colors.qualitative.Set1
    for i, well in enumerate(selected_wells):
        if well in data.columns:
            absorbance = data[well]
            color = colors[i % len(colors)]
            
            fig.add_trace(go.Scatter(
                x=wavelengths,
                y=absorbance,
                mode='lines',
                name=f'Well {well}',
                line=dict(color=color, width=2),
                hovertemplate=f'<b>Well {well}</b><br>' +
                             'Wavelength: %{x:.0f} nm<br>' +
                             'Absorbance: %{y:.3f}<br>' +
                             '<extra></extra>'
            ))
    
    # Update layout
    reader_type = metadata.get('Reader Type:', 'UV-Vis Reader')
    file_name = metadata.get('file_name', 'Unknown')
    
    fig.update_layout(
        title=f"UV-Vis Absorption Spectrum - {file_name}",
        xaxis_title="Wavelength (nm)",
        yaxis_title="Absorbance (AU)",
        hovermode='x unified',
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60)
    )
    
    # Add info annotation
    wl_range = metadata.get('wavelength_range', 'Unknown')
    date_time = metadata.get('DateTime', metadata.get('Date', ''))
    filled_count = metadata.get('filled_well_count', '?')
    total_wells = metadata.get('total_wells', '?')
    
    info_text = f"📊 {reader_type}<br>📅 {date_time}<br>🌊 {wl_range}<br>🧪 Wells: {filled_count}/{total_wells} filled"
    
    fig.add_annotation(
        text=info_text,
        x=0.02, y=0.98,
        xref='paper', yref='paper',
        xanchor='left', yanchor='top',
        showarrow=False,
        align='left',
        bgcolor='rgba(255,255,255,0.9)',
        bordercolor='rgba(0,0,0,0.2)',
        borderwidth=1,
        font=dict(size=10)
    )
    
    return fig

def create_single_well_plot(file_data, well_name):
    """Create a plot for a single well"""
    
    data = file_data['data']
    metadata = file_data['metadata']
    
    if data is None or 'Wavelength' not in data.columns or well_name not in data.columns:
        return go.Figure().add_annotation(
            text=f"No data available for well {well_name}", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    # Get data for the specific well
    wavelengths = data['Wavelength']
    absorbance = data[well_name]
    
    # Remove NaN values
    valid_mask = ~(pd.isna(wavelengths) | pd.isna(absorbance))
    wavelengths = wavelengths[valid_mask]
    absorbance = absorbance[valid_mask]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=wavelengths,
        y=absorbance,
        mode='lines+markers',
        name=f'Well {well_name}',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=4),
        hovertemplate=f'<b>Well {well_name}</b><br>' +
                     'Wavelength: %{x:.0f} nm<br>' +
                     'Absorbance: %{y:.3f}<br>' +
                     '<extra></extra>'
    ))
    
    # Update layout
    file_name = metadata.get('file_name', 'Unknown')
    
    fig.update_layout(
        title=f"UV-Vis Spectrum - Well {well_name} ({file_name})",
        xaxis_title="Wavelength (nm)",
        yaxis_title="Absorbance (AU)",
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=False
    )
    


    # Add statistics annotation

    # Add statistics annotation
    if len(absorbance) > 0 and len(wavelengths) > 0:
        # Convert to numpy arrays for simple indexing
        abs_values = absorbance.values
        wl_values = wavelengths.values
        
        # Find max absorbance and corresponding wavelength
        max_abs = float(abs_values.max())
        max_idx = abs_values.argmax()  # Get position of max value
        max_wl = float(wl_values[max_idx])  # Get wavelength at that position
        
        stats_text = f"📊 Well {well_name}<br>📈 Max: {max_abs:.3f} AU<br>🎯 Peak: {max_wl:.0f} nm"
        
        fig.add_annotation(
            text=stats_text,
            x=0.02, y=0.98,
            xref='paper', yref='paper',
            xanchor='left', yanchor='top',
            showarrow=False,
            align='left',
            bgcolor='rgba(255,255,255,0.9)',
            bordercolor='rgba(0,0,0,0.2)',
            borderwidth=1,
            font=dict(size=10)
        )





    return fig

def create_well_heatmap(file_data, wavelength=None):
    """Create a heatmap showing absorbance across all wells at a specific wavelength"""
    
    data = file_data['data']
    metadata = file_data['metadata']
    
    if data is None or 'Wavelength' not in data.columns:
        return go.Figure().add_annotation(
            text="No wavelength data available", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    # If no wavelength specified, use the one with highest average absorbance
    if wavelength is None:
        intensity_cols = metadata.get('intensity_columns', [])
        if intensity_cols:
            # Find wavelength with highest average absorbance
            avg_abs = data[intensity_cols].mean(axis=1)
            max_idx = avg_abs.idxmax()
            wavelength = data.loc[max_idx, 'Wavelength']
    
    # Find the closest wavelength in the data
    wl_col = data['Wavelength']
    closest_idx = (wl_col - wavelength).abs().idxmin()
    actual_wl = data.loc[closest_idx, 'Wavelength']
    
    # Extract absorbance values for this wavelength
    intensity_cols = metadata.get('intensity_columns', [])
    abs_values = data.loc[closest_idx, intensity_cols]
    
    # Create 8x12 grid for 96-well plate
    plate_data = []
    rows = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
    cols = list(range(1, 13))
    
    for row in rows:
        row_data = []
        for col in cols:
            well_name = f"{row}{col}"
            if well_name in abs_values:
                row_data.append(abs_values[well_name])
            else:
                row_data.append(0)  # Empty well
        plate_data.append(row_data)
    
    fig = go.Figure(data=go.Heatmap(
        z=plate_data,
        x=[str(i) for i in cols],
        y=rows,
        colorscale='Viridis',
        hovertemplate='Well: %{y}%{x}<br>Absorbance: %{z:.3f}<extra></extra>'
    ))
    
    fig.update_layout(
        title=f"96-Well Plate Heatmap at {actual_wl:.0f} nm",
        xaxis_title="Column",
        yaxis_title="Row",
        template='plotly_white',
        height=400,
        width=600
    )
    
    return fig