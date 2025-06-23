# ui/export_options.py

import streamlit as st
import io
import base64
import pandas as pd
import plotly.io as pio
from utils.toast import show_toast
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.ticker import AutoMinorLocator
import numpy as np
from utils.color_utils import hex_to_rgba, rgba_to_hex
from utils.data_processing import apply_smoothing, calculate_baseline


def generate_matplotlib_figure(chrom_data_list, preprocessed_data, peaks_data=None):
    """
    Generate a publication-quality Matplotlib figure from chromatogram data.
    """
    # Get settings from session state
    config = st.session_state.plot_config
    fonts = st.session_state.font_settings
    plot_settings = st.session_state.plot_settings
    integrate_zero = plot_settings.get('integrate_zero', True)
    
    # Properly scale figure dimensions (convert pixels to inches)
    # A typical figure in a publication is 6-7 inches wide
    fig_width = min(7, plot_settings.get('plot_width', 800) / 120)  # Scale down for better quality
    fig_height = min(5, plot_settings.get('plot_height', 500) / 120)
    
    # Get scientific theme setting for styling
    scientific_theme = plot_settings.get('scientific_theme', 'minimalist')
    
    # Configure matplotlib with high-quality journal settings
    if scientific_theme == 'minimalist':
        plt.style.use('classic')
        mpl.rcParams.update({
            'font.family': fonts.get('font_family', 'Arial'),
            'font.size': fonts.get('tick_fs', 10),
            'axes.titlesize': fonts.get('title_fs', 14),
            'axes.labelsize': fonts.get('axis_fs', 12),
            'xtick.labelsize': fonts.get('tick_fs', 10),
            'ytick.labelsize': fonts.get('tick_fs', 10),
            'legend.fontsize': fonts.get('legend_fs', 10),
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'savefig.bbox': 'tight',
            'axes.linewidth': 1.0,
            'xtick.major.width': 1.0,
            'ytick.major.width': 1.0,
            'xtick.major.size': 3.5,
            'ytick.major.size': 3.5,
            'xtick.minor.size': 2,
            'ytick.minor.size': 2,
            'xtick.minor.width': 0.8,
            'ytick.minor.width': 0.8,
            'xtick.direction': 'out',
            'ytick.direction': 'out',
            'axes.edgecolor': 'black',
            # Explicitly turn off grid in rcParams
            'axes.grid': False,
            'grid.linestyle': ':',
            'grid.linewidth': 0.5,
            'grid.alpha': 0.5,
        })
    elif scientific_theme == 'retro_terminal':
        plt.style.use('dark_background')
        mpl.rcParams.update({
            'font.family': 'monospace',
            'font.size': fonts.get('tick_fs', 10),
            'axes.titlesize': fonts.get('title_fs', 14),
            'axes.labelsize': fonts.get('axis_fs', 12),
            'xtick.labelsize': fonts.get('tick_fs', 10),
            'ytick.labelsize': fonts.get('tick_fs', 10),
            'legend.fontsize': fonts.get('legend_fs', 10),
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'axes.edgecolor': '#33FF33',
            'xtick.color': '#33FF33',
            'ytick.color': '#33FF33',
            'text.color': '#33FF33',
            'axes.labelcolor': '#33FF33',
            'axes.grid': False,  # Explicitly turn off grid
        })
    else:  # web theme
        plt.style.use('default')
        mpl.rcParams.update({
            'font.family': fonts.get('font_family', 'Arial'),
            'font.size': fonts.get('tick_fs', 10),
            'axes.titlesize': fonts.get('title_fs', 14),
            'axes.labelsize': fonts.get('axis_fs', 12),
            'xtick.labelsize': fonts.get('tick_fs', 10),
            'ytick.labelsize': fonts.get('tick_fs', 10),
            'legend.fontsize': fonts.get('legend_fs', 10),
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'axes.grid': False,  # Explicitly turn off grid
        })
    
    # Get grid settings from plot_settings
    horizontal_grid = plot_settings.get('horizontal_grid', False)
    vertical_grid = plot_settings.get('vertical_grid', False)
    
    # Debug info in sidebar
    debug_info = []
    debug_info.append(f"Grid settings - Horizontal: {horizontal_grid}, Vertical: {vertical_grid}")
    
    # Determine if we need separate subplots
    separate_plots = plot_settings.get('separate_plots', False)
    visible_chroms = [c for c in chrom_data_list if c.get('visible', True) and c['id'] in preprocessed_data]
    
    if separate_plots and len(visible_chroms) > 1:
        fig, axes = plt.subplots(
            len(visible_chroms), 
            1, 
            figsize=(fig_width, fig_height * len(visible_chroms) * 0.7),
            sharex=True,
            constrained_layout=True
        )
        if len(visible_chroms) == 1:
            axes = [axes]  # Convert to list for consistency
    else:
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), constrained_layout=True)
        axes = [ax]  # Use list for consistency in code
    
    # Find the global min and max y values for consistent scaling across subplots
    # Instead of starting at 0, we'll find the actual minimum value
    all_y_values = []  # Collect all y values to find true min/max
    
    # Collect all y values across chromatograms for accurate min/max calculation
    for chrom_data in visible_chroms:
        chrom_id = chrom_data['id']
        # Get data
        proc_data = preprocessed_data[chrom_id]
        # Choose smoothed or raw data based on settings
        use_smooth = plot_settings.get('smooth_lines', True)
        y = proc_data['y_smooth'] if use_smooth else proc_data['y']
        all_y_values.extend(y)  # Add all values to our collection
        
        # For debugging, check actual min/max for this dataset
        y_min = np.min(y)
        y_max = np.max(y)
        debug_info.append(f"Chromatogram '{chrom_data['name']}': min={y_min:.2f}, max={y_max:.2f}")
    
    # Calculate true global min/max from all values
    global_y_min = np.min(all_y_values) if all_y_values else 0
    global_y_max = np.max(all_y_values) if all_y_values else 100
    
    # Add padding to min/max (5% of the data range)
    y_range = global_y_max - global_y_min
    # Only go below 0 if actual data is below 0
    if global_y_min < 0:
        global_y_min = global_y_min - 0.05 * y_range
    else:
        global_y_min = 0  # Default minimum to 0 for non-negative data
    
    global_y_max = global_y_max + 0.05 * y_range
    
    # Add final calculated limits to debug info
    debug_info.append(f"Final y-axis limits: min={global_y_min:.2f}, max={global_y_max:.2f}")
    
    # Store debug info in session state to display in sidebar
    st.session_state.export_debug_info = debug_info

    # Plot each chromatogram
    for idx, chrom_data in enumerate(visible_chroms):
        chrom_id = chrom_data['id']
        
        # Get data
        proc_data = preprocessed_data[chrom_id]
        x = proc_data['x']
        
        # Choose smoothed or raw data based on settings
        use_smooth = plot_settings.get('smooth_lines', True)
        y = proc_data['y_smooth'] if use_smooth else proc_data['y']
        
        # Get the current axis for this plot
        if separate_plots and len(axes) > idx:
            curr_ax = axes[idx]
        else:
            curr_ax = axes[0]
        
        # Plot main line - safely convert color
        try:
            if isinstance(chrom_data['color'], str) and chrom_data['color'].startswith('rgba'):
                # Extract RGB components from rgba string
                rgba_parts = chrom_data['color'].replace('rgba(', '').replace(')', '').split(',')
                r = int(rgba_parts[0].strip())
                g = int(rgba_parts[1].strip())
                b = int(rgba_parts[2].strip())
                line_color = f"#{r:02x}{g:02x}{b:02x}"
            else:
                line_color = chrom_data['color']
        except:
            # Fallback to a default color if conversion fails
            line_color = '#1f77b4'  # Default matplotlib blue
        
        curr_ax.plot(
            x, y, 
            label=chrom_data['name'],
            color=line_color,
            linewidth=plot_settings.get('line_thickness', 1.5)
        )
        
        # Plot baseline if integrate_zero is enabled
        if integrate_zero:
            curr_ax.plot(
                x, proc_data['baseline'],
                color=line_color,
                linestyle='--',
                linewidth=0.8,
                alpha=0.6
            )
        
        # Plot peaks if available
        if peaks_data and chrom_id in peaks_data:
            for peak in peaks_data[chrom_id]:
                # Plot peak area if boundaries available
                if 'Start Index' in peak and 'End Index' in peak:
                    start_idx = peak['Start Index']
                    end_idx = peak['End Index']
                    
                    # Extract data segment for peak
                    x_fill = x[start_idx:end_idx+1]
                    y_fill = y[start_idx:end_idx+1]
                    
                    # Safely handle peak color
                    try:
                        if 'color' in peak and isinstance(peak['color'], str) and peak['color'].startswith('rgba'):
                            # Parse RGBA string to get just RGB part and alpha
                            rgba_parts = peak['color'].replace('rgba(', '').replace(')', '').split(',')
                            r = int(rgba_parts[0].strip())
                            g = int(rgba_parts[1].strip())
                            b = int(rgba_parts[2].strip())
                            a = float(rgba_parts[3].strip())
                            peak_color = (r/255, g/255, b/255, a)  # Matplotlib uses 0-1 range
                        else:
                            # Use chromatogram color with default alpha
                            peak_color = line_color
                            a = 0.4
                    except:
                        # Fallback color if parsing fails
                        peak_color = line_color
                        a = 0.4
                    
                    # Fill area
                    curr_ax.fill_between(
                        x_fill, y_fill, 
                        proc_data['baseline'][start_idx:end_idx+1] if integrate_zero else 0,
                        color=peak_color,
                        alpha=a if isinstance(peak_color, str) else None  # Only set alpha if using string color
                    )
                
                # Add peak marker if enabled
                if st.session_state.settings.get('show_peak_markers', False) and 'peak_idx' in peak:
                    peak_idx = peak['peak_idx']
                    curr_ax.plot(
                        x[peak_idx], y[peak_idx],
                        marker='x',
                        markersize=8,
                        color='red'
                    )
    
    # Configure each axis
    for i, curr_ax in enumerate(axes):
        # Keep the box frame but hide ticks on top and right
        for spine in ['top', 'bottom', 'left', 'right']:
            curr_ax.spines[spine].set_visible(True)

        # Hide ticks on top and right while keeping the spines
        curr_ax.tick_params(top=False, right=False, which='both')
        
        # Set axis labels only on the bottom subplot if using separate plots
        if separate_plots and len(axes) > 1:
            if i == len(axes) - 1:  # Last/bottom subplot
                curr_ax.set_xlabel(config.get('xaxis_title', 'Time (min)'))
            else:
                curr_ax.set_xlabel('')
        else:
            curr_ax.set_xlabel(config.get('xaxis_title', 'Time (min)'))
            
        curr_ax.set_ylabel(config.get('yaxis_title', 'Signal (a.u.)'))
        
        # Remove title as requested
        curr_ax.set_title("")
        
        # Apply grid settings from sidebar - very explicitly
        if horizontal_grid:
            curr_ax.grid(True, axis='y', linestyle=':', alpha=0.3)
        else:
            curr_ax.grid(False, axis='y')
            
        if vertical_grid:
            curr_ax.grid(True, axis='x', linestyle=':', alpha=0.3)
        else:
            curr_ax.grid(False, axis='x')
        
        # Add minor ticks for scientific appearance but reduce number of ticks
        curr_ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        curr_ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        
        # Reduce number of major ticks (MaxNLocator to control # of ticks)
        curr_ax.xaxis.set_major_locator(plt.MaxNLocator(5))  # Reduced number of x ticks
        curr_ax.yaxis.set_major_locator(plt.MaxNLocator(5))  # Reduced number of y ticks
        
        # Apply axis color
        axis_color = st.session_state.get('axis_label_color', '#000000')
        curr_ax.xaxis.label.set_color(axis_color)
        curr_ax.yaxis.label.set_color(axis_color)
        
        # Set consistent y-axis limits across all subplots using the global min/max
        curr_ax.set_ylim(bottom=global_y_min, top=global_y_max)
        
        # Apply smart axis ranges if manually set (only for x-axis)
        if not separate_plots or i == 0:  # Only apply to first subplot or single plot
            if st.session_state.get('x_min_modified', False):
                curr_ax.set_xlim(left=st.session_state.get('x_min_input', None))
            if st.session_state.get('x_max_modified', False):
                curr_ax.set_xlim(right=st.session_state.get('x_max_input', None))
        
        # Add legend for each subplot if using separate plots
        if separate_plots and plot_settings.get('show_legend', True) and len(visible_chroms) > 0:
            # Parse legend settings
            legend_pos = config.get('legend_position', {'x': 1.0, 'y': 1.0})
            legend_horizontal = st.session_state.get('legend_orientation', 'vertical') == 'horizontal'
            legend_border = st.session_state.get('legend_border', False)
            
            # Calculate best legend position in matplotlib terms
            x, y = legend_pos.get('x', 1.0), legend_pos.get('y', 1.0)
            
            # Determine best location based on position
            if x <= 0.2 and y >= 0.8:
                loc = 'upper left'
            elif x <= 0.2 and y <= 0.2:
                loc = 'lower left'
            elif x >= 0.8 and y <= 0.2:
                loc = 'lower right'
            elif x >= 0.8 and y >= 0.8:
                loc = 'upper right'
            else:
                # Default to upper right
                loc = 'upper right'
            
            # Add a legend to each subplot if separate plots
            curr_ax.legend(
                loc=loc,
                frameon=legend_border,
                ncol=2 if legend_horizontal else 1
            )
    
    # Add legend to main figure if not using separate plots
    if not separate_plots and plot_settings.get('show_legend', True) and len(visible_chroms) > 0:
        # Parse legend settings
        legend_pos = config.get('legend_position', {'x': 1.0, 'y': 1.0})
        legend_horizontal = st.session_state.get('legend_orientation', 'vertical') == 'horizontal'
        legend_border = st.session_state.get('legend_border', False)
        
        # Calculate best legend position in matplotlib terms
        x, y = legend_pos.get('x', 1.0), legend_pos.get('y', 1.0)
        
        # Determine best location based on position
        if x <= 0.2 and y >= 0.8:
            loc = 'upper left'
        elif x <= 0.2 and y <= 0.2:
            loc = 'lower left'
        elif x >= 0.8 and y <= 0.2:
            loc = 'lower right'
        elif x >= 0.8 and y >= 0.8:
            loc = 'upper right'
        else:
            # Default to upper right
            loc = 'upper right'
        
        # Add the legend to first axis
        axes[0].legend(
            loc=loc,
            frameon=legend_border,
            ncol=2 if legend_horizontal else 1
        )
    
    # Return the figure
    return fig

def export_data():
    """Exports data in the selected format."""
    format_type = st.session_state.export_settings['format']
    active_chrom = st.session_state.active_chromatogram
    
    if active_chrom is None or not st.session_state.chromatograms:
        show_toast("No active chromatogram selected", "error")
        return
    
    try:
        # Handle different export formats
        if format_type == "CSV":
            # Export CSV data
            export_csv()
            
        elif format_type in ["SVG", "PDF", "PNG"]:
            # Get all chromatograms
            chrom_data_list = []
            for chrom_id, chromatogram in st.session_state.chromatograms.items():
                # Add ID to the dictionary for reference
                chromatogram_with_id = chromatogram.copy()
                chromatogram_with_id['id'] = chrom_id
                chrom_data_list.append(chromatogram_with_id)
            
            # Get preprocessed data for all chromatograms
            preprocessed_data = {}
            for chrom_id in [c['id'] for c in chrom_data_list]:
                if 'data' in st.session_state.chromatograms[chrom_id]:
                    x = st.session_state.chromatograms[chrom_id]['data']['x']
                    y = st.session_state.chromatograms[chrom_id]['data']['y']
                    
                    smoothing = st.session_state.smoothing
                    y_smooth = apply_smoothing(y, smoothing)
                    baseline = calculate_baseline(
                        y_smooth,
                        iterations=st.session_state.settings['baseline_iterations'],
                        percentile=st.session_state.settings['percentile']
                    )
                    y_corrected = y_smooth - baseline
                    
                    preprocessed_data[chrom_id] = {
                        'x': x,
                        'y': y,
                        'y_smooth': y_smooth,
                        'baseline': baseline,
                        'y_corrected': y_corrected
                    }
            
            # Generate matplotlib figure
            fig = generate_matplotlib_figure(
                chrom_data_list,
                preprocessed_data,
                peaks_data=st.session_state.selected_peaks
            )
            
            # Get DPI from settings
            dpi = st.session_state.export_settings.get('dpi', 300)
            
            # Adjust filename based on active chromatogram
            chrom_name = st.session_state.chromatograms[active_chrom]['name']
            filename = f"{chrom_name}.{format_type.lower()}"
            
            # Save to buffer for download
            buffer = io.BytesIO()
            fig.savefig(
                buffer,
                format=format_type.lower(),
                dpi=dpi,
                bbox_inches='tight'
            )
            buffer.seek(0)
            
            # Create a unique key for the download button
            import time
            unique_key = f"download_{format_type.lower()}_{int(time.time())}"
            
            # Create download button
            st.download_button(
                label=f"Download {format_type}",
                data=buffer,
                file_name=filename,
                mime=f"image/{format_type.lower()}" if format_type != "PDF" else "application/pdf",
                key=unique_key,
                use_container_width=True
            )
            
            # Close the figure to free memory
            plt.close(fig)
            
        else:
            show_toast(f"Unsupported export format: {format_type}", "error")
            
    except Exception as e:
        show_toast(f"Error exporting data: {str(e)}", "error")
        print(f"Error in export_data: {e}")

def export_csv():
    """Export active chromatogram data as CSV."""
    active_chrom = st.session_state.active_chromatogram
    if active_chrom is None or not st.session_state.chromatograms:
        show_toast("No active chromatogram selected", "error")
        return False
    
    try:
        chrom_data = st.session_state.chromatograms[active_chrom]
        
        # Create DataFrame from chromatogram data
        if 'data' in chrom_data:
            df = pd.DataFrame({
                'Time (min)': chrom_data['data']['x'],
                'Signal (a.u.)': chrom_data['data']['y']
            })
            
            # Add processed data
            x = chrom_data['data']['x']
            y = chrom_data['data']['y']
            
            smoothing = st.session_state.smoothing
            y_smooth = apply_smoothing(y, smoothing)
            baseline = calculate_baseline(
                y_smooth,
                iterations=st.session_state.settings['baseline_iterations'],
                percentile=st.session_state.settings['percentile']
            )
            y_corrected = y_smooth - baseline
            
            df['Smoothed Signal'] = y_smooth
            df['Baseline'] = baseline
            df['Corrected Signal'] = y_corrected
            
            # Convert to CSV string
            csv = df.to_csv(index=False, sep=st.session_state.export_settings['csv_delimiter'])
            
            # Create download button
            import time
            unique_key = f"download_csv_{int(time.time())}"
            
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"{chrom_data['name']}.csv",
                mime="text/csv",
                key=unique_key,
                use_container_width=True
            )
            
            return True
    except Exception as e:
        show_toast(f"Error generating CSV export: {str(e)}", "error")
        print(f"Error in export_csv: {e}")
        return False

def render_export_options():
    """
    Render the export options UI with settings for file format,
    quality, and CSV delimiter.
    """
    st.subheader("Export Settings")
    
    # Initialize export settings in session state if they don't exist
    if 'export_settings' not in st.session_state:
        st.session_state.export_settings = {
            'format': 'PNG',
            'dpi': 300,
            'csv_delimiter': ',',
        }
    
    settings = st.session_state.export_settings
    
    # File format selection
    format_options = ["PNG", "SVG", "PDF", "CSV"]
    selected_format = st.selectbox(
        "File Format", 
        options=format_options, 
        index=format_options.index(settings['format'])
    )
    
    if selected_format != settings['format']:
        settings['format'] = selected_format
        show_toast(f"Export format set to {selected_format}", "info")
    
    # DPI option for raster formats
    if selected_format in ["PNG"]:
        dpi_options = [150, 300, 600]
        dpi = st.select_slider(
            "DPI (Resolution)", 
            options=dpi_options,
            value=settings['dpi'],
            help="Higher DPI = larger file but better quality"
        )
        
        if dpi != settings['dpi']:
            settings['dpi'] = dpi
            show_toast(f"Export DPI set to {dpi}", "info")
    
    # CSV options if CSV is selected
    if selected_format == "CSV":
        delimiter_options = [",", ";", "Tab"]
        delimiter_values = {",": ",", ";": ";", "Tab": "\t"}
        
        # Find the current index based on the actual delimiter character
        current_delimiter = next(
            (k for k, v in delimiter_values.items() if v == settings['csv_delimiter']), 
            ","
        )
        
        selected_delimiter = st.selectbox(
            "CSV Delimiter", 
            options=delimiter_options,
            index=delimiter_options.index(current_delimiter)
        )
        
        # Convert display name to actual delimiter character
        actual_delimiter = delimiter_values[selected_delimiter]
        
        if actual_delimiter != settings['csv_delimiter']:
            settings['csv_delimiter'] = actual_delimiter
            show_toast(f"CSV delimiter set to {selected_delimiter}", "info")
    
    # Get active chromatogram for filename preview
    active_chrom = st.session_state.active_chromatogram
    if active_chrom is not None and active_chrom in st.session_state.chromatograms:
        chrom_name = st.session_state.chromatograms[active_chrom]['name']
        filename = f"{chrom_name}.{selected_format.lower()}"
        st.caption(f"Filename: {filename}")
    
    # Journal-ready export note
    if selected_format in ["SVG", "PDF"]:
        st.info("💡 SVG and PDF formats are best for publication-quality journal figures.")
    
    # Display debug information if available
    if st.checkbox("Show Debug Info", value=False, key="export_debug_checkbox"):
        if 'export_debug_info' in st.session_state and st.session_state.export_debug_info:
            st.write("**🔍 Export Debug Information:**")
            for line in st.session_state.export_debug_info:
                st.text(line)
        else:
            st.text("No debug information available yet. Export a figure first.")
    
    # Export button
    if st.button("Export", use_container_width=True):
        export_data()