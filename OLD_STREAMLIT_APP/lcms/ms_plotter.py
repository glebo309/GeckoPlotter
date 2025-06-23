#lcms/ms_plotter.py
# 
import plotly.graph_objects as go
from ui.plot_interactions import make_titles_editable
import numpy as np
import streamlit as st


def plot_tic(rt, intensity):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rt, y=intensity, mode='lines', name='TIC'))
    fig.update_layout(title="Total Ion Chromatogram", xaxis_title="Time (min)", yaxis_title="Intensity")
    return fig


def plot_mass_spectrum(mz, intensity, color='#1f77b4', name='MS Spectrum', peak_info=None, top_n_labels=5):
    """
    Clean lollipop MS1 spectrum: no grid, one hover per peak, smart title.
    Normalizes intensity to 100% for standard MS visualization.
    """
    import numpy as np
    import plotly.graph_objects as go
    from ui.plot_settings import apply_plot_settings
    from ui.fonts_labels import apply_font_settings
    from ui.plot_interactions import make_titles_editable
    import streamlit as st

    # Normalize intensity to 100%
    intensity = (np.array(intensity) / np.max(intensity)) * 100

    # Load fonts
    fonts = st.session_state.get('font_settings', {
        'title_fs': 24,
        'axis_fs': 18,
        'tick_fs': 14
    })
    
    # Apply color theme if available
    if 'plot_settings' in st.session_state and 'color_theme' in st.session_state.plot_settings:
        theme = st.session_state.plot_settings['color_theme']
        theme_colors = {
            'Default': '#008000',
            'Set1': '#E41A1C',
            'Paired': '#1F78B4',
            'Tableau10': '#1F77B4',
            'Batlow': '#0E4C6A',
            'Viridis': '#440154',
            'Lajolla': '#131023',
            'Turku': '#15286D',
            'RdYlBu': '#A50026',
            'Wes Anderson': '#78C0BA',
            'Retro 80s': '#FF59FD',
            'Vintage Print': '#D95040',
            'Candy': '#FF69B4',
            'Fruits': '#FF3214',
            'Midnight Synth': '#050519',
            'Crayon Box': '#ED0A3F',
            'Gameboy': '#0F380F',
        }
        if theme in theme_colors:
            color = theme_colors[theme]
    
    # Build title
    title = name
    if peak_info:
        parts = []
        if 'name' in peak_info:
            parts.append(peak_info['name'])
        if 'RT' in peak_info:
            parts.append(f"{peak_info['RT']:.2f} min")
        if parts:
            title = "MS Spectrum – " + " @ ".join(parts)

    # Flatten into one trace
    xs, ys = [], []
    for x, y in zip(mz, intensity):
        xs += [x, x, None]
        ys += [0, y, None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode='lines',
        line=dict(color=color, width=2),
        hoverinfo='x+y',
        showlegend=False
    ))

    # Annotate top N peaks
    if top_n_labels and len(mz) >= top_n_labels:
        top_idxs = np.argsort(intensity)[-top_n_labels:]
        for i in top_idxs:
            fig.add_annotation(
                x=mz[i],
                y=intensity[i],
                text=f"{mz[i]:.1f}",
                showarrow=False,
                yshift=6,
                font=dict(size=10)
            )

    fig.update_layout(
        title=title,
        xaxis=dict(
            title="m/z",
            title_font=dict(size=fonts['axis_fs']),
            tickfont=dict(size=fonts['tick_fs'])
        ),
        yaxis=dict(
            title="Relative Intensity (%)",
            title_font=dict(size=fonts['axis_fs']),
            tickfont=dict(size=fonts['tick_fs']),
            range=[0, 105]
        ),
        hovermode='closest',
        margin=dict(t=60, b=40, l=60, r=40),
        height=350
    )

    fig = apply_plot_settings(fig)
    fig = apply_font_settings(fig)

    # Final title update
    if fig.layout.title.text != title:
        fig.update_layout(title=title)

    fig, config = make_titles_editable(fig)
    config['scrollZoom'] = True

    return fig, config

def plot_extracted_ion_chromatogram(rt, intensity, mz_value, color='#ff7f0e', name=None):
    """
    Plot an Extracted Ion Chromatogram (EIC/XIC).

    rt : array-like
    intensity : array-like
    mz_value : float
    color : str
    name : str
    """
    import plotly.graph_objects as go
    from ui.plot_settings import apply_plot_settings
    from ui.fonts_labels import apply_font_settings
    from ui.plot_interactions import make_titles_editable
    
    # Apply color theme if available
    if 'plot_settings' in st.session_state and 'color_theme' in st.session_state.plot_settings:
        theme = st.session_state.plot_settings['color_theme']
        # Map theme names to specific colors for XIC plots
        theme_colors = {
            'Default': '#22AA22',         # Darker Green
            'Set1': '#377EB8',            # Blue
            'Paired': '#A6CEE3',          # Light Blue
            'Tableau10': '#FF7F0E',       # Orange
            'Batlow': '#55C667',          # Green
            'Viridis': '#21908D',         # Teal
            'Lajolla': '#9E4443',         # Rust
            'Turku': '#C12F2F',           # Red 
            'RdYlBu': '#FF7F00',          # Orange
            'Wes Anderson': '#E1553A',    # Red
            'Retro 80s': '#4AF6F2',       # Cyan
            'Vintage Print': '#2A717D',   # Teal
            'Candy': '#7FFFFA',           # Aquamarine
            'Fruits': '#FF8C00',          # Orange
            'Midnight Synth': '#C837FF',  # Electric Purple
            'Crayon Box': '#FF7F30',      # Orange
            'Gameboy': '#306930',         # Dark Green
        }
        
        # Use theme color if available, otherwise fallback
        if theme in theme_colors:
            color = theme_colors[theme]
    
    # Load fonts
    fonts = st.session_state.get('font_settings', {
        'title_fs': 24,
        'axis_fs': 18,
        'tick_fs': 14,
    })

    if name is None:
        name = f"XIC m/z = {mz_value:.2f}"
    
    # Store title for later
    title = f"Extracted Ion Chromatogram (m/z = {mz_value:.2f})"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rt,
        y=intensity,
        mode='lines',
        line=dict(color=color, width=1.5),
        name=name,
        showlegend=False
    ))

    # Basic layout settings
    fig.update_layout(
        xaxis_title="Time (min)",
        yaxis_title="Intensity",
        height=400,
        margin=dict(t=60, b=40, l=60, r=40)
    )

    # Apply your global styling - this will apply our scientific themes
    fig = apply_plot_settings(fig)
    
    # Then apply any font settings 
    fig = apply_font_settings(fig)
    
    # Override title to ensure it's maintained after styling
    fig.update_layout(title=dict(text=title))

    # make titles editable
    fig, config = make_titles_editable(fig)
    config['scrollZoom'] = True

    return fig, config

###

### new function ### 
### new function ### 
### new function ### 






def plot_mass_spectrum_comparison(mz_values, intensity_values, labels, colors=None):
    """
    Plot multiple mass spectra for comparison.
    
    Parameters:
    -----------
    mz_values : list of array-like
        List of m/z value arrays for each spectrum
    intensity_values : list of array-like
        List of intensity value arrays for each spectrum
    labels : list of str
        Names for each spectrum
    colors : list of str, optional
        Colors for each spectrum
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The comparison figure
    dict
        Configuration for plotly_chart
    """
    # Create figure
    fig = go.Figure()
    
    # Default colors if not provided
    if colors is None:
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    
    # Add traces for each spectrum
    for i, (mz, intensity, label) in enumerate(zip(mz_values, intensity_values, labels)):
        color = colors[i % len(colors)]
        
        fig.add_trace(go.Scatter(
            x=mz,
            y=intensity,
            mode='lines',
            name=label,
            line=dict(color=color, width=1.5)
        ))
    
    # Apply layout
    fig.update_layout(
        title="Mass Spectra Comparison",
        xaxis_title="m/z",
        yaxis_title="Intensity (a.u.)",
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    
    return fig


def identify_significant_peaks(mz, intensity, threshold_percentage=5):
    """
    Identify significant peaks in a mass spectrum.
    
    Parameters:
    -----------
    mz : array-like
        m/z values
    intensity : array-like
        Intensity values
    threshold_percentage : float, optional
        Percentage of base peak intensity to use as threshold (default: 5%)
        
    Returns:
    --------
    list of tuples
        (m/z, intensity, relative_intensity) for significant peaks
    """
    # Convert to numpy arrays for processing
    mz = np.array(mz)
    intensity = np.array(intensity)
    
    # Find the base peak (maximum intensity)
    base_peak_intensity = np.max(intensity)
    if base_peak_intensity <= 0:
        return []
    
    # Calculate threshold
    threshold = base_peak_intensity * threshold_percentage / 100
    
    # Find local maxima above threshold
    peaks = []
    for i in range(1, len(intensity) - 1):
        if (intensity[i] > intensity[i-1] and 
            intensity[i] >= intensity[i+1] and 
            intensity[i] > threshold):
            
            relative_intensity = (intensity[i] / base_peak_intensity) * 100
            peaks.append((mz[i], intensity[i], relative_intensity))
    
    # Sort by intensity (descending)
    peaks.sort(key=lambda x: x[1], reverse=True)
    
    return peaks


def plot_mass_spectrum_with_labels(mz, intensity, color='#1f77b4', name='Mass Spectrum',
                                  label_threshold_percentage=5, max_labels=10, peak_info=None):
    """
    Plot a mass spectrum with peak labels for significant peaks.
    
    Parameters:
    -----------
    mz : array-like
        m/z values
    intensity : array-like
        Intensity values
    color : str, optional
        Line color (default: '#1f77b4')
    name : str, optional
        Name of the spectrum (default: 'Mass Spectrum')
    label_threshold_percentage : float, optional
        Percentage of base peak intensity to use as label threshold (default: 5%)
    max_labels : int, optional
        Maximum number of peak labels to show (default: 10)
    peak_info : dict, optional
        Information about the peak (for better titling)
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The labeled mass spectrum figure
    dict
        Configuration for plotly_chart
    """
    # Get font settings from session state
    font = st.session_state.get('font_settings', {})
    
    # Create figure
    fig = go.Figure()
    
    # Add spectrum trace
    fig.add_trace(go.Scatter(
        x=mz,
        y=intensity,
        mode='lines',
        name=name,
        line=dict(color=color, width=1.5)
    ))
    
    # Identify significant peaks
    peaks = identify_significant_peaks(mz, intensity, label_threshold_percentage)
    
    # Limit to max_labels
    if len(peaks) > max_labels:
        peaks = peaks[:max_labels]
    
    # Add peak annotations
    for mz_val, intensity_val, rel_intensity in peaks:
        fig.add_annotation(
            x=mz_val,
            y=intensity_val,
            text=f"{mz_val:.1f}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.5,
            arrowcolor=color,
            font=dict(size=12),
            ax=0,
            ay=-30
        )
    
    # Generate a meaningful title
    title = "Mass Spectrum"
    if peak_info:
        # If we have peak information, use it to enhance the title
        if 'name' in peak_info:
            title = f"MS Spectrum of {peak_info['name']}"
        if 'RT' in peak_info:
            title += f" (RT: {peak_info['RT']:.2f} min)"
    
    # Apply layout with improved title and consistent styling
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=font.get('title_fs', 24))
        ),
        xaxis=dict(
            title="m/z",
            title_font=dict(size=font.get('axis_fs', 18)),
            tickfont=dict(size=font.get('tick_fs', 14))
        ),
        yaxis=dict(
            title="Relative Intensity (%)",
            title_font=dict(size=font.get('axis_fs', 18)),
            tickfont=dict(size=font.get('tick_fs', 14))
        ),
        height=400,
        margin=dict(t=60, b=40, l=60, r=40),
        font=dict(size=font.get('legend_fs', 14))
    )
    
    # Make titles editable
    fig, config = make_titles_editable(fig)
    
    return fig, config


def plot_3d_lcms(retention_times, mz_values, intensities, colorscale='Viridis'):
    """
    Create a 3D surface plot of LC-MS data.
    
    Parameters:
    -----------
    retention_times : array-like
        Retention time values
    mz_values : array-like
        m/z values
    intensities : 2D array
        Intensity values with shape (len(retention_times), len(mz_values))
    colorscale : str, optional
        Colorscale for the surface plot (default: 'Viridis')
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The 3D LC-MS figure
    dict
        Configuration for plotly_chart
    """
    # Create figure
    fig = go.Figure(data=[go.Surface(
        z=intensities,
        x=retention_times,
        y=mz_values,
        colorscale=colorscale
    )])
    
    # Apply layout
    fig.update_layout(
        title="LC-MS 3D View",
        scene=dict(
            xaxis_title="Retention Time (min)",
            yaxis_title="m/z",
            zaxis_title="Intensity",
            xaxis=dict(showbackground=True),
            yaxis=dict(showbackground=True),
            zaxis=dict(showbackground=True)
        ),
        margin=dict(l=0, r=0, b=0, t=50),
        height=700,
        width=800
    )
    
    # Configuration with additional 3D controls
    config = {
        'displayModeBar': True,
        'scrollZoom': True,
        'modeBarButtonsToAdd': [
            'zoom3d',
            'pan3d',
            'resetCameraLastSave3d',
            'hoverClosest3d'
        ]
    }
    
    return fig, config


def plot_contour_lcms(retention_times, mz_values, intensities, colorscale='Viridis'):
    """
    Create a contour plot of LC-MS data.
    
    Parameters:
    -----------
    retention_times : array-like
        Retention time values
    mz_values : array-like
        m/z values
    intensities : 2D array
        Intensity values with shape (len(retention_times), len(mz_values))
    colorscale : str, optional
        Colorscale for the contour plot (default: 'Viridis')
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The contour LC-MS figure
    dict
        Configuration for plotly_chart
    """
    # Create figure
    fig = go.Figure(data=go.Contour(
        z=intensities.T,  # Transpose for correct orientation
        x=retention_times,
        y=mz_values,
        colorscale=colorscale,
        contours=dict(
            start=0,
            end=np.max(intensities) * 0.8,
            size=np.max(intensities) / 20,
            showlabels=True
        )
    ))
    
    # Apply layout
    fig.update_layout(
        title="LC-MS Contour Plot",
        xaxis_title="Retention Time (min)",
        yaxis_title="m/z",
        height=600,
        width=800
    )
    
    # Apply consistent styling
    fig = apply_plot_settings(fig)
    fig = apply_font_settings(fig)
    
    # Make titles editable
    fig, config = make_titles_editable(fig)
    
    return fig, config