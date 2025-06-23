# ui/plot_settings.py 

import streamlit as st
import plotly.graph_objects as go
from typing import Tuple, Optional, Dict, Any
from utils.toast import show_toast
import importlib
from utils.color_utils import hex_to_rgba, rgba_to_hex
from models.calibration import group_peaks_by_retention_time


def initialize_axis_state(full_data_bounds):
    """Initialize session state for axis controls on first load only."""
    x_min, x_max = full_data_bounds['x']
    y_min, y_max = full_data_bounds['y']
    
    # Initialize zoom ranges if they don't exist
    if "zoom_xrange" not in st.session_state:
        st.session_state.zoom_xrange = (x_min, x_max)
    if "zoom_yrange" not in st.session_state:
        st.session_state.zoom_yrange = (y_min, y_max)
    
    # Initialize input values and modification flags
    for bound in ("x_min", "x_max", "y_min", "y_max"):
        input_key = f"{bound}_input"
        modified_key = f"{bound}_modified"
        
        if input_key not in st.session_state:
            if bound == "x_min":
                st.session_state[input_key] = x_min
            elif bound == "x_max":
                st.session_state[input_key] = x_max
            elif bound == "y_min":
                st.session_state[input_key] = y_min
            else:  # y_max
                st.session_state[input_key] = y_max
                
        if modified_key not in st.session_state:
            st.session_state[modified_key] = False

def mark_modified(bound: str):
    """Callback function to mark an axis bound as manually modified."""
    st.session_state[f"{bound}_modified"] = True
    # Force a rerun to apply the change immediately
    st.rerun()

def render_axis_controls():
    """Render the axis control inputs in the sidebar."""
    
    
    st.subheader("Axis Bounds")
    
    # Initialize if needed
    for var in ['x_min_input', 'x_max_input', 'y_min_input', 'y_max_input']:
        if var not in st.session_state:
            st.session_state[var] = 0.0
    
    for var in ['x_min_modified', 'x_max_modified', 'y_min_modified', 'y_max_modified']:
        if var not in st.session_state:
            st.session_state[var] = False
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.caption("X-Axis (Time)")
        new_x_min = st.number_input("X min", value=st.session_state.x_min_input, format="%.3f", step=0.001)
        if new_x_min != st.session_state.x_min_input:
            st.session_state.x_min_input = new_x_min
            st.session_state.x_min_modified = True
        
        new_x_max = st.number_input("X max", value=st.session_state.x_max_input, format="%.3f", step=0.001)
        if new_x_max != st.session_state.x_max_input:
            st.session_state.x_max_input = new_x_max
            st.session_state.x_max_modified = True
    
    with col2:
        st.caption("Y-Axis (Signal)")
        new_y_min = st.number_input("Y min", value=st.session_state.y_min_input, format="%.2f", step=0.01)
        if new_y_min != st.session_state.y_min_input:
            st.session_state.y_min_input = new_y_min
            st.session_state.y_min_modified = True
        
        new_y_max = st.number_input("Y max", value=st.session_state.y_max_input, format="%.2f", step=0.01)
        if new_y_max != st.session_state.y_max_input:
            st.session_state.y_max_input = new_y_max
            st.session_state.y_max_modified = True
    
    if st.button("Reset to Full Data Range", use_container_width=True):
        for var in ['x_min_modified', 'x_max_modified', 'y_min_modified', 'y_max_modified']:
            st.session_state[var] = False
        st.rerun()
    
    # Status indicator
    modified = [k for k in ['x_min_modified', 'x_max_modified', 'y_min_modified', 'y_max_modified'] if st.session_state.get(k, False)]
    if modified:
        axes = [k.replace('_modified', '').replace('_', ' ').title() for k in modified]
        st.caption(f"🔒 Manual: {', '.join(axes)}")
    else:
        st.caption("🔓 Auto zoom")


def capture_zoom_events(relayout_data):
    """Capture zoom/pan events and update session state."""
    if not relayout_data:
        print("📊 capture_zoom_events: No relayout_data received")
        return
    
    print(f"📊 capture_zoom_events: Received relayout_data: {relayout_data}")
    
    # Handle X-axis zoom/pan
    if "xaxis.range[0]" in relayout_data and "xaxis.range[1]" in relayout_data:
        old_xrange = st.session_state.get('zoom_xrange', 'None')
        st.session_state.zoom_xrange = (
            relayout_data["xaxis.range[0]"],
            relayout_data["xaxis.range[1]"]
        )
        print(f"📊 X-axis zoom detected: {old_xrange} → {st.session_state.zoom_xrange}")
        
        # Clear manual X overrides when zooming
        st.session_state.x_min_modified = False
        st.session_state.x_max_modified = False
        print("📊 Cleared X manual overrides")
        
        # Update input values to match zoom
        st.session_state.x_min_input = relayout_data["xaxis.range[0]"]
        st.session_state.x_max_input = relayout_data["xaxis.range[1]"]
        print(f"📊 Updated X inputs: {st.session_state.x_min_input}, {st.session_state.x_max_input}")
    
    # Handle Y-axis zoom/pan  
    if "yaxis.range[0]" in relayout_data and "yaxis.range[1]" in relayout_data:
        old_yrange = st.session_state.get('zoom_yrange', 'None')
        st.session_state.zoom_yrange = (
            relayout_data["yaxis.range[0]"],
            relayout_data["yaxis.range[1]"]
        )
        print(f"📊 Y-axis zoom detected: {old_yrange} → {st.session_state.zoom_yrange}")
        
        # Clear manual Y overrides when zooming
        st.session_state.y_min_modified = False
        st.session_state.y_max_modified = False
        print("📊 Cleared Y manual overrides")
        
        # Update input values to match zoom
        st.session_state.y_min_input = relayout_data["yaxis.range[0]"]
        st.session_state.y_max_input = relayout_data["yaxis.range[1]"]
        print(f"📊 Updated Y inputs: {st.session_state.y_min_input}, {st.session_state.y_max_input}")


def apply_axis_ranges(fig, relayout_data=None):
    """Apply the computed axis ranges to the plotly figure."""
    print(f"📊 apply_axis_ranges called with relayout_data: {relayout_data}")
    
    # Handle double-click reset
    if relayout_data:
        if relayout_data.get("xaxis.autorange"):
            print("📊 X-axis autorange detected - resetting to manual inputs")
            fig.update_xaxes(range=[
                st.session_state.get('x_min_input', 0),
                st.session_state.get('x_max_input', 1)
            ])
            return
        
        if relayout_data.get("yaxis.autorange"):
            print("📊 Y-axis autorange detected - resetting to manual inputs")
            fig.update_yaxes(range=[
                st.session_state.get('y_min_input', 0),
                st.session_state.get('y_max_input', 1)
            ])
            return
    
    # Apply computed ranges
    try:
        (xmin, xmax), (ymin, ymax) = compute_final_ranges()
        print(f"📊 Applying axis ranges: X=[{xmin:.3f}, {xmax:.3f}], Y=[{ymin:.3f}, {ymax:.3f}]")
        
        fig.update_xaxes(range=[xmin, xmax])
        fig.update_yaxes(range=[ymin, ymax])
        
        print("📊 Successfully applied axis ranges to figure")
    except Exception as e:
        print(f"📊 Error applying axis ranges: {e}")
        # Fallback - don't modify axes if there's an error


def compute_final_ranges():
    """Compute the final axis ranges by merging zoom state with manual overrides."""
    # Start from zoom state
    xmin, xmax = st.session_state.get('zoom_xrange', (0, 1))
    ymin, ymax = st.session_state.get('zoom_yrange', (0, 1))
    
    print(f"📊 compute_final_ranges - Starting from zoom: X=[{xmin:.3f}, {xmax:.3f}], Y=[{ymin:.3f}, {ymax:.3f}]")
    
    # Override with manual inputs if modified
    if st.session_state.get('x_min_modified', False):
        xmin = st.session_state.get('x_min_input', xmin)
        print(f"📊 Overriding X min with manual input: {xmin:.3f}")
    if st.session_state.get('x_max_modified', False):
        xmax = st.session_state.get('x_max_input', xmax)
        print(f"📊 Overriding X max with manual input: {xmax:.3f}")
    if st.session_state.get('y_min_modified', False):
        ymin = st.session_state.get('y_min_input', ymin)
        print(f"📊 Overriding Y min with manual input: {ymin:.3f}")
    if st.session_state.get('y_max_modified', False):
        ymax = st.session_state.get('y_max_input', ymax)
        print(f"📊 Overriding Y max with manual input: {ymax:.3f}")
    
    print(f"📊 Final computed ranges: X=[{xmin:.3f}, {xmax:.3f}], Y=[{ymin:.3f}, {ymax:.3f}]")
    return (xmin, xmax), (ymin, ymax)


def get_data_bounds(preprocessed_data: Dict) -> Dict[str, Tuple[float, float]]:
    """Calculate the full data bounds from preprocessed chromatogram data."""
    if not preprocessed_data:
        return {'x': (0, 1), 'y': (0, 1)}
    
    all_x = []
    all_y = []
    
    for chrom_id, data in preprocessed_data.items():
        if st.session_state.chromatograms[chrom_id]['visible']:
            all_x.extend(data['x'])
            # Use smoothed data for bounds calculation
            all_y.extend(data['y_smooth'])
    
    if not all_x or not all_y:
        return {'x': (0, 1), 'y': (0, 1)}
    
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    
    # Add small padding
    x_padding = (x_max - x_min) * 0.02
    y_padding = (y_max - y_min) * 0.05
    
    return {
        'x': (x_min - x_padding, x_max + x_padding),
        'y': (y_min - y_padding, y_max + y_padding)
    }

def render_plot_settings():
    """
    Render the plot settings UI with controls for line thickness,
    display options, and plot dimensions.
    """
    st.subheader("Plot Appearance")
    
    # Initialize plot settings in session state if they don't exist
    if 'plot_settings' not in st.session_state:
        st.session_state.plot_settings = {
            'line_thickness': 1.5,
            'smooth_lines': True,
            'separate_plots': False,
            'show_legend': True,
            'horizontal_grid': False,
            'vertical_grid': False,
            'plot_width': 800,
            'plot_height': 500,
            'color_theme': 'Default',
            'scientific_theme': 'minimalist'
        }
    
    settings = st.session_state.plot_settings
    
    # Line settings
    prev_thickness = settings['line_thickness']
    line_thickness = st.slider(
        "Line Thickness", 
        min_value=0.5, 
        max_value=5.0, 
        value=prev_thickness, 
        step=0.1,
        key=f"line_thickness_slider_{prev_thickness}",
        help="Adjust the thickness of plot lines"
    )
    
    if line_thickness != prev_thickness:
        settings['line_thickness'] = line_thickness
        show_toast(f"Line thickness set to {line_thickness}", "info")
        st.rerun()
    
    # Separate plots toggle
    separate_plots = st.checkbox(
        "Separate Plots", 
        value=settings.get('separate_plots', False),
        key=f"separate_plots_cb_{settings.get('separate_plots', False)}"
    )
    if separate_plots != settings.get('separate_plots', False):
        settings['separate_plots'] = separate_plots
        show_toast(f"Separate plots {'enabled' if separate_plots else 'disabled'}", "info")
        st.rerun()
    
    # Display options with columns for better layout
    col1, col2 = st.columns(2)
    
    with col1:
        smooth_lines = st.checkbox(
            "Smooth Lines", 
            value=settings['smooth_lines'],
            key=f"smooth_lines_cb_{settings['smooth_lines']}"
        )
        if smooth_lines != settings['smooth_lines']:
            settings['smooth_lines'] = smooth_lines
            show_toast(f"Smooth lines {'enabled' if smooth_lines else 'disabled'}", "info")
            st.rerun()
        
        show_legend = st.checkbox(
            "Show Legend", 
            value=settings['show_legend'],
            key=f"show_legend_cb_{settings['show_legend']}"
        )
        if show_legend != settings['show_legend']:
            settings['show_legend'] = show_legend
            show_toast(f"Legend {'shown' if show_legend else 'hidden'}", "info")
            st.rerun()
    
    with col2:
        horizontal_grid = st.checkbox(
            "Horizontal Grid", 
            value=settings['horizontal_grid'],
            key=f"horizontal_grid_cb_{settings['horizontal_grid']}"
        )
        if horizontal_grid != settings['horizontal_grid']:
            settings['horizontal_grid'] = horizontal_grid
            show_toast(f"Horizontal grid {'enabled' if horizontal_grid else 'disabled'}", "info")
            st.rerun()
        
        vertical_grid = st.checkbox(
            "Vertical Grid", 
            value=settings['vertical_grid'],
            key=f"vertical_grid_cb_{settings['vertical_grid']}"
        )
        if vertical_grid != settings['vertical_grid']:
            settings['vertical_grid'] = vertical_grid
            show_toast(f"Vertical grid {'enabled' if vertical_grid else 'disabled'}", "info")
            st.rerun()
    
    # Color theme selector
    try:
        # Import the color maps module
        colourmaps = importlib.import_module("utils.colourmaps")
        
        # Get available color themes from the module
        color_themes = {
            # Scientific Qualitative (Distinct)
            'Default': 'get_color_from_palette',  # Keep default
            'Set1': 'get_set1_palette',           # Bold distinct colors
            'Paired': 'get_paired_palette',       # Light/dark pairs
            'Tableau10': 'get_tableau10_palette', # Modern categorical palette
            
            # Scientific Sequential
            'Batlow': 'get_batlow_palette',       # Scientific rainbow
            'Viridis': 'get_viridis_palette',     # Blue-green-yellow
            'Lajolla': 'get_lajolla_palette',     # Earth tones
            
            # Scientific Diverging
            'Turku': 'get_turku_palette',         # Blue-white-red
            'RdYlBu': 'get_rdylbu_palette',       # Red-yellow-blue
            
            # Artistic
            'Wes Anderson': 'get_wes_anderson_palette',  # Film-inspired
            'Retro 80s': 'get_retro80s_palette',         # Neon synthwave
            'Vintage Print': 'get_vintage_print_palette', # Muted poster colors
            
            # Fun & Easter Eggs
            'Candy': 'get_candy_palette',               # Sweet bright colors
            'Fruits': 'get_fruits_palette',             # Fruit-inspired colors
            'Midnight Synth': 'get_midnight_synthwave_palette', # Dark with neon
            'Crayon Box': 'get_crayon_box_palette',     # Childhood nostalgia
            'Gameboy': 'get_gameboy_palette'            # Retro gaming
        }

        prev_theme = settings.get('color_theme', 'Default')
        color_theme = st.selectbox(
            "Color Theme",
            options=list(color_themes.keys()),
            index=list(color_themes.keys()).index(prev_theme),
            key=f"color_theme_select_{prev_theme}"
        )
        
        if color_theme != prev_theme:
            settings['color_theme'] = color_theme
            settings['color_palette_function'] = color_themes[color_theme]
            
            # Get the palette function
            palette_func = getattr(colourmaps, color_themes[color_theme])
            
            # Function to convert RGB tuple to hex
            def palette_color_to_hex(color_tuple):
                r, g, b = color_tuple
                return f"#{r:02X}{g:02X}{b:02X}"
            
            # Update chromatogram colors
            if 'chromatograms' in st.session_state:
                # Update colors for each chromatogram
                for i, (chrom_id, chrom_data) in enumerate(st.session_state.chromatograms.items()):
                    # Get RGB values from the palette
                    rgb = palette_func(i)
                    # Convert to hex
                    hex_color = palette_color_to_hex(rgb)
                    # Update the chromatogram color
                    chrom_data['color'] = hex_color
            
            # Update peak colors while respecting retention time grouping
            if 'selected_peaks' in st.session_state:
                from utils.color_utils import hex_to_rgba
                from models.calibration import group_peaks_by_retention_time
                
                # Function to convert RGB tuple to hex
                def palette_color_to_hex(color_tuple):
                    if color_tuple is None:
                        return "#FF0000"  # Default red if color is None
                    r, g, b = color_tuple
                    return f"#{r:02X}{g:02X}{b:02X}"
                
                # Collect all peaks for grouping
                all_peaks = []
                for chrom_id, peaks in st.session_state.selected_peaks.items():
                    for peak in peaks:
                        peak_info = {
                            'chromatogram_id': chrom_id,
                            'peak': peak,  # Store the actual peak object
                            'midpoint': peak['Midpoint (min)']
                        }
                        all_peaks.append(peak_info)
                
                # Get time window from session state or use default
                time_window = st.session_state.get('peak_matching_window', 0.2)
                
                # Group peaks by retention time
                peak_groups = group_peaks_by_retention_time(all_peaks, time_window)
                
                # Update colors based on groups
                for group_idx, group in enumerate(peak_groups):
                    # Get one color for this group
                    try:
                        rgb = palette_func(group_idx)
                        hex_color = palette_color_to_hex(rgb)
                        
                        # Apply to all peaks in this group
                        for peak_info in group:
                            peak = peak_info['peak']
                            opacity = peak.get('opacity', 0.4)
                            peak['hex_color'] = hex_color
                            peak['color'] = hex_to_rgba(hex_color, opacity)
                    except Exception as e:
                        print(f"Error setting peak color for group {group_idx}: {e}")
                        # Use a fallback color
                        hex_color = "#FF5733"
                        for peak_info in group:
                            peak = peak_info['peak']
                            opacity = peak.get('opacity', 0.4)
                            peak['hex_color'] = hex_color
                            peak['color'] = hex_to_rgba(hex_color, opacity)

            show_toast(f"Color theme set to {color_theme}", "info")
            st.rerun()
            
    except (ImportError, AttributeError) as e:
        st.error(f"Could not load color themes: {str(e)}")

    # Scientific publication theme selector
    st.subheader("Plot Style")
    
    # Initialize the scientific theme setting if it doesn't exist
    if 'scientific_theme' not in st.session_state.plot_settings:
        st.session_state.plot_settings['scientific_theme'] = 'minimalist'
    
    # Theme options with descriptions
    scientific_themes = {
        'web': "Web",
        'minimalist': "Minimal",
        'retro_terminal': "Terminal Style"
    }
    
    prev_sci_theme = st.session_state.plot_settings.get('scientific_theme', 'minimalist')
    scientific_theme = st.selectbox(
        "Choose Style",
        options=list(scientific_themes.keys()),
        format_func=lambda x: scientific_themes[x],
        index=list(scientific_themes.keys()).index(prev_sci_theme),
        key=f"scientific_theme_select_{prev_sci_theme}"
    )
    
    if scientific_theme != prev_sci_theme:
        st.session_state.plot_settings['scientific_theme'] = scientific_theme
        show_toast(f"Plot style set to {scientific_themes[scientific_theme]}", "info")
        # Force a redraw to apply the new theme
        st.session_state['force_redraw'] = True
        st.rerun()

    # Plot dimensions
    st.subheader("Plot Dimensions")
    dims_cols = st.columns(2)
    
    with dims_cols[0]:
        prev_width = settings['plot_width']
        plot_width = st.number_input(
            "Width (px)", 
            min_value=300, 
            max_value=2000, 
            value=prev_width, 
            step=50,
            key=f"plot_width_input_{prev_width}"
        )
        if plot_width != prev_width:
            settings['plot_width'] = plot_width
            show_toast(f"Plot width set to {plot_width}px", "info")
            st.rerun()
    
    with dims_cols[1]:
        prev_height = settings['plot_height']
        plot_height = st.number_input(
            "Height (px)", 
            min_value=200, 
            max_value=1200, 
            value=prev_height, 
            step=50,
            key=f"plot_height_input_{prev_height}"
        )
        if plot_height != prev_height:
            settings['plot_height'] = plot_height
            show_toast(f"Plot height set to {plot_height}px", "info")
            st.rerun()
    

    # Debug section - shows what's in session state
    if st.checkbox("Show Debug Info", value=False):
        st.write("**🔍 Debug Info:**")
        st.write(f"zoom_xrange: {st.session_state.get('zoom_xrange', 'Not set')}")
        st.write(f"zoom_yrange: {st.session_state.get('zoom_yrange', 'Not set')}")
        st.write(f"x_min_input: {st.session_state.get('x_min_input', 'Not set')}")
        st.write(f"x_max_input: {st.session_state.get('x_max_input', 'Not set')}")
        st.write(f"y_min_input: {st.session_state.get('y_min_input', 'Not set')}")
        st.write(f"y_max_input: {st.session_state.get('y_max_input', 'Not set')}")
        st.write(f"x_min_modified: {st.session_state.get('x_min_modified', 'Not set')}")
        st.write(f"x_max_modified: {st.session_state.get('x_max_modified', 'Not set')}")
        st.write(f"y_min_modified: {st.session_state.get('y_min_modified', 'Not set')}")
        st.write(f"y_max_modified: {st.session_state.get('y_max_modified', 'Not set')}")
        
        # Show computed final ranges
        try:
            (xmin, xmax), (ymin, ymax) = compute_final_ranges()
            st.write(f"**Final computed ranges:**")
            st.write(f"X: [{xmin:.3f}, {xmax:.3f}]")
            st.write(f"Y: [{ymin:.3f}, {ymax:.3f}]")
        except:
            st.write("**Final ranges:** Error computing")

    render_axis_controls()


def apply_plot_settings(fig):
    """
    Apply plot settings from session state to a plotly figure.
    
    Args:
        fig: A plotly figure object to modify
    
    Returns:
        The modified figure
    """
    if 'plot_settings' not in st.session_state:
        return fig
    
    settings = st.session_state.plot_settings
    
    # Apply line thickness to all traces
    for trace in fig.data:
        if hasattr(trace, 'line') and trace.line:
            trace.line.width = settings['line_thickness']
    
    # Apply layout settings
    fig.update_layout(
        showlegend=settings['show_legend'],
        width=settings['plot_width'],
        height=settings['plot_height']
    )
    
    # Get scientific theme setting
    scientific_theme = settings.get('scientific_theme', 'minimalist')
    
    # Apply scientific theme styling
    if scientific_theme == 'minimalist':
        # Minimalist style - clean and minimal
        fig.update_layout(
            font=dict(family="Helvetica", size=12, color="#333333"),
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=40, r=40, t=40, b=40)
        )
        
        fig.update_xaxes(
            showline=True,
            linewidth=1,
            linecolor='#333333',
            mirror=True,
            ticks="outside",
            tickwidth=1,
            tickcolor='#333333',
            ticklen=4,
            showgrid=False  # No grid for minimalist
        )
        
        fig.update_yaxes(
            showline=True,
            linewidth=1,
            linecolor='#333333', 
            mirror=True,
            ticks="outside",
            tickwidth=1,
            tickcolor='#333333',
            ticklen=4,
            showgrid=False  # No grid for minimalist
        )
    
    elif scientific_theme == 'retro_terminal':
        # Retro computer terminal style
        fig.update_layout(
            font=dict(family="Courier New", size=14, color="#33FF33"),
            plot_bgcolor="black",
            paper_bgcolor="black",
            title_font=dict(size=16, color="#33FF33")
        )
        
        fig.update_xaxes(
            showline=True,
            linewidth=1,
            linecolor='#33FF33', 
            mirror=True,
            ticks="outside",
            tickwidth=1,
            tickcolor='#33FF33',
            ticklen=4,
            title_font=dict(color="#33FF33"),
            tickfont=dict(color="#33FF33"),
            showgrid=settings['vertical_grid'],
            gridcolor='#003300'
        )
        
        fig.update_yaxes(
            showline=True,
            linewidth=1,
            linecolor='#33FF33', 
            mirror=True,
            ticks="outside",
            tickwidth=1,
            tickcolor='#33FF33',
            ticklen=4,
            title_font=dict(color="#33FF33"),
            tickfont=dict(color="#33FF33"),
            showgrid=settings['horizontal_grid'],
            gridcolor='#003300'
        )
        
        # Update trace colors for visibility on dark background
        for trace in fig.data:
            if hasattr(trace, 'line') and trace.line:
                if trace.line.color == 'blue':
                    trace.line.color = '#00FFFF'  # Cyan
                elif trace.line.color == 'red':
                    trace.line.color = '#FF5555'  # Bright red
                elif trace.line.color == 'green':
                    trace.line.color = '#33FF33'  # Bright green
                elif trace.line.color == 'black':
                    trace.line.color = '#FFFFFF'  # White
    
    else:  # web
        # Default Plotly style - just apply grid settings
        fig.update_xaxes(showgrid=settings['vertical_grid'])
        fig.update_yaxes(showgrid=settings['horizontal_grid'])
    
    return fig