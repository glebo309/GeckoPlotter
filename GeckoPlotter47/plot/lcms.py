# File: plot/lcms.py
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from interactions.base_interactions import BasePlotController


def create_tic_plot(file_data):
    """Create Total Ion Current chromatogram plot with rich metadata"""
    
    data = file_data['data']
    metadata = file_data['metadata']
    
    if data is None or data.empty:
        return go.Figure().add_annotation(
            text="No TIC data available", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    if 'Time (min)' not in data.columns or 'Intensity' not in data.columns:
        return go.Figure().add_annotation(
            text="Invalid TIC data format", 
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    fig = go.Figure()
    
    # Get metadata for styling and labels
    ionization_mode = metadata.get('ionization_mode', 'unknown')
    sample_name = metadata.get('sample_name', 'Unknown')
    scan_count = metadata.get('scan_count', '?')
    max_intensity = metadata.get('max_intensity', 0)
    
    # Color based on ionization mode
    line_color = '#e74c3c' if ionization_mode == 'negative' else '#27ae60' if ionization_mode == 'positive' else '#3498db'
    
    # Plot TIC
    fig.add_trace(go.Scatter(
        x=data['Time (min)'],
        y=data['Intensity'],
        mode='lines',
        name=f'TIC {ionization_mode.upper()}' if ionization_mode != 'unknown' else 'TIC',
        line=dict(color=line_color, width=1.5),
        hovertemplate='<b>Total Ion Current</b><br>' +
                     'RT: %{x:.2f} min<br>' +
                     'Intensity: %{y:,.0f}<br>' +
                     '<extra></extra>'
    ))
    
    # Create informative title
    mode_indicator = f" ({ionization_mode.upper()})" if ionization_mode != 'unknown' else ""
    title = f"TIC - {sample_name}{mode_indicator}"
    
    fig.update_layout(
        title=title,
        xaxis_title="Retention Time (min)",
        yaxis_title="Intensity",
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=False
    )
    
    # Rich info annotation using all metadata
    rt_range = metadata.get('retention_time_range', 'Unknown')
    mass_range = metadata.get('mass_range_str', 'Unknown')
    instrument = metadata.get('instrument_name', '')
    injection_time = metadata.get('injection_date_time_stamp', '')
    
    # Format injection time if available
    if injection_time and len(injection_time) >= 12:
        try:
            from datetime import datetime
            dt = datetime.strptime(injection_time[:12], "%Y%m%d%H%M")
            injection_formatted = dt.strftime("%Y-%m-%d %H:%M")
        except:
            injection_formatted = injection_time
    else:
        injection_formatted = injection_time
    
    info_lines = [
        f"📊 Sample: {sample_name}",
        f"⚡ Mode: {ionization_mode.upper()}" if ionization_mode != 'unknown' else "",
        f"🕒 RT: {rt_range}",
        f"⚖️ m/z: {mass_range}",
        f"📈 Scans: {scan_count} | Max: {max_intensity:,.0f}",
        f"🔬 {instrument}" if instrument else "",
        f"📅 {injection_formatted}" if injection_formatted else ""
    ]
    
    info_text = "<br>".join([line for line in info_lines if line])
    
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

def create_mass_spectrum_plot(file_data, scan_number=None):
    """Create mass spectrum at specific retention time (placeholder for future)"""
    
    # For now, return a placeholder
    return go.Figure().add_annotation(
        text="Mass spectrum plotting not yet implemented", 
        xref="paper", yref="paper",
        x=0.5, y=0.5, xanchor='center', yanchor='middle',
        showarrow=False, font_size=16
    )

def create_extracted_ion_plot(file_data, mz_value, tolerance=0.5):
    """Create extracted ion chromatogram for specific m/z (placeholder for future)"""
    
    # For now, return a placeholder
    return go.Figure().add_annotation(
        text="Extracted ion chromatogram not yet implemented", 
        xref="paper", yref="paper",
        x=0.5, y=0.5, xanchor='center', yanchor='middle',
        showarrow=False, font_size=16
    )

def create_lcms_overlay_plot(bundle_data):
    """Overlay LC and TIC chromatograms (placeholder for future)"""
    
    # For now, return a placeholder
    return go.Figure().add_annotation(
        text="LC-MS overlay plotting not yet implemented", 
        xref="paper", yref="paper",
        x=0.5, y=0.5, xanchor='center', yanchor='middle',
        showarrow=False, font_size=16
    )


###############

def create_lcms_uv_plot(component_data):
    """Create UV chromatogram plot for LC-MS data with rich metadata"""
    data = component_data['data']
    metadata = component_data['metadata']
    
    if data is None or data.empty:
        return go.Figure().add_annotation(
            text="No UV data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    if 'Time (min)' not in data.columns or 'Intensity (mAU)' not in data.columns:
        return go.Figure().add_annotation(
            text="Invalid UV data format",
            xref="paper", yref="paper", 
            x=0.5, y=0.5, xanchor='center', yanchor='middle',
            showarrow=False, font_size=16
        )
    
    fig = go.Figure()
    
    # Get metadata for styling
    wavelength = metadata.get('wavelength', '?')
    channel = metadata.get('detector_channel', '?')
    sample_name = metadata.get('sample_name', 'Unknown')
    max_intensity = metadata.get('max_intensity', 0)
    data_points = metadata.get('data_points', len(data))
    
    # Color based on channel
    line_color = '#3498db' if channel == 'A' else '#9b59b6' if channel == 'B' else '#1f77b4'
    
    # Plot UV chromatogram
    fig.add_trace(go.Scatter(
        x=data['Time (min)'],
        y=data['Intensity (mAU)'],
        mode='lines',
        name=f"UV-{channel} {wavelength}nm",
        line=dict(color=line_color, width=1.5),
        hovertemplate=f'<b>UV Channel {channel}</b><br>' +
                     'RT: %{x:.2f} min<br>' +
                     'Absorbance: %{y:.1f} mAU<br>' +
                     '<extra></extra>'
    ))
    
    # Create informative title
    title = f"UV Chromatogram - {sample_name} (Channel {channel}, {wavelength} nm)"
    

    # In create_tic_plot function, replace fig.update_layout():
    fig.update_layout(
        title=title,
        xaxis_title="Retention Time (min)",
        yaxis_title="Intensity",
        template='plotly_white',
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=False
    )

    # Add interactivity
    controller = BasePlotController('data-plot')
    fig = controller.enhance_interactivity(fig)

    # In create_lcms_uv_plot function, replace fig.update_layout():
    fig.update_layout(
        title=title,
        xaxis_title="Retention Time (min)",
        yaxis_title="Absorbance (mAU)",
        template="plotly_white",
        height=500,
        margin=dict(l=60, r=60, t=80, b=60),
        showlegend=False
    )

    # Add interactivity  
    controller = BasePlotController('uv-plot')
    fig = controller.enhance_interactivity(fig)
    
    # Rich info annotation
    rt_range = metadata.get('retention_time_range', 'Unknown')
    detector_name = metadata.get('detector_name', f'VWD1{channel}')
    instrument = metadata.get('instrument_name', '')
    injection_time = metadata.get('injection_date_time_stamp', '')
    
    # Format injection time
    if injection_time and len(injection_time) >= 12:
        try:
            from datetime import datetime
            dt = datetime.strptime(injection_time[:12], "%Y%m%d%H%M")
            injection_formatted = dt.strftime("%Y-%m-%d %H:%M")
        except:
            injection_formatted = injection_time
    else:
        injection_formatted = injection_time
    
    info_lines = [
        f"📊 Sample: {sample_name}",
        f"🌊 {detector_name}, {wavelength} nm",
        f"🕒 RT: {rt_range}",
        f"📈 Points: {data_points} | Max: {max_intensity:.1f} mAU",
        f"🔬 {instrument}" if instrument else "",
        f"📅 {injection_formatted}" if injection_formatted else ""
    ]
    
    info_text = "<br>".join([line for line in info_lines if line])
    
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

##