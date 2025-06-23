# ui/fonts_labels.py - Enhanced with Font Family Selection

import streamlit as st
from utils.toast import show_toast

def render_fonts_labels():
    """
    Render the fonts and labels UI with controls for font sizes,
    font families, and plot labels.
    """
  
### Initialize session state for font settings and plot config ###

    # Initialize font settings in session state if they don't exist
    if 'font_settings' not in st.session_state:
        st.session_state.font_settings = {
            'font_family': 'Arial',
            'title_fs': 18,
            'axis_fs': 18,
            'legend_fs': 18,
            'tick_fs': 18,
            'wavelength_fs': 18
        }

    # Initialize plot config with all legend settings
    if 'plot_config' not in st.session_state:
        st.session_state.plot_config = {
            'title': 'Chromatogram Analysis',
            'xaxis_title': 'Time (min)',
            'yaxis_title': 'Signal (a.u.)',
            'legend_position': {'x': 0.9, 'y': 0.95},
            'legend_orientation': 'horizontal',
            'legend_border': False,
            'legend_borderwidth': 2,
            'legend_bordercolor': 'black',
            'legend_bgcolor': 'rgba(255, 255, 255, 0.9)',
            'legend_itemsizing': 'constant',
            'legend_itemclick': 'toggle',
            'legend_itemdoubleclick': 'toggleothers',
            'legend_groupclick': 'toggleitem'
        }

    font_settings = st.session_state.font_settings
    plot_config   = st.session_state.plot_config

######################### until here #########################

    # Font Family Selector
    st.subheader("Font Family")
    
    # Define font options - organized in categories but displayed without categories
    fonts = [
        # Scientific & Technical
        "Arial",
        "Helvetica",
        "Times New Roman", 
        "Georgia",
        "Cambria",
        
        # Modern Sans
        "Roboto",
        "Open Sans",
        "Montserrat",
        "Verdana",
        "Segoe UI",
        
        # Data Visualization 
        "Inter",
        "Lato",
        "Source Sans Pro",
        "Ubuntu",
        
        # Elegant & Clean
        "Futura",
        "Gill Sans",
        "Century Gothic",
        "Optima",
        "Garamond"
    ]
    
    # Current font selection
    current_font = font_settings.get('font_family', 'Arial')
    if current_font not in fonts:
        current_font = 'Arial'  # Default if somehow we have an invalid font
    
    # Font family selector
    font_select_key = f"font_family_select_{current_font}"
    selected_font = st.selectbox(
        "Select Font Family",
        options=fonts,
        index=fonts.index(current_font),
        key=font_select_key
    )
    
    # Update font if changed
    if selected_font != current_font:
        font_settings['font_family'] = selected_font
        st.session_state.force_redraw = True
        show_toast(f"Font changed to {selected_font}", "info")
        st.rerun()

    #####################
    # Font sizes with columns for better layout
    st.subheader("Font Sizes")
    col1, col2 = st.columns(2)
    
    with col1:
        # Title font size
        prev_title_fs = font_settings['title_fs']
        title_fs = st.number_input(
            "Title Font", 
            min_value=8, 
            max_value=30,
            value=prev_title_fs,
            key=f"title_fs_input_{prev_title_fs}"
        )
        
        if title_fs != prev_title_fs:
            font_settings['title_fs'] = title_fs
            show_toast(f"Title font size set to {title_fs}", "info")
            st.session_state.force_redraw = True
        
        # Axis font size
        prev_axis_fs = font_settings['axis_fs']
        axis_fs = st.number_input(
            "Axis Font", 
            min_value=6, 
            max_value=24,
            value=prev_axis_fs,
            key=f"axis_fs_input_{prev_axis_fs}"
        )
        
        if axis_fs != prev_axis_fs:
            font_settings['axis_fs'] = axis_fs
            show_toast(f"Axis font size set to {axis_fs}", "info")
            st.session_state.force_redraw = True
    
    with col2:
        # Legend font size
        prev_legend_fs = font_settings['legend_fs']
        legend_fs = st.number_input(
            "Legend Font", 
            min_value=6, 
            max_value=24,
            value=prev_legend_fs,
            key=f"legend_fs_input_{prev_legend_fs}"
        )
        
        if legend_fs != prev_legend_fs:
            font_settings['legend_fs'] = legend_fs
            show_toast(f"Legend font size set to {legend_fs}", "info")
            st.session_state.force_redraw = True
        
        # Tick font size
        prev_tick_fs = font_settings['tick_fs']
        tick_fs = st.number_input(
            "Tick Font", 
            min_value=6, 
            max_value=24,
            value=prev_tick_fs,
            key=f"tick_fs_input_{prev_tick_fs}"
        )
        
        if tick_fs != prev_tick_fs:
            font_settings['tick_fs'] = tick_fs
            show_toast(f"Tick font size set to {tick_fs}", "info")
            st.session_state.force_redraw = True
    

    
    # Plot labels
    st.subheader("Axis Labels")
    
    # Axis labels
    col1, col2 = st.columns(2)
    
    with col1:
        prev_x_label = plot_config.get('xaxis_title', 'Time (min)')
        x_label = st.text_input(
            "X-Axis", 
            value=prev_x_label,
            key=f"x_label_input_{hash(prev_x_label)}"
        )
        
        if x_label != prev_x_label:
            plot_config['xaxis_title'] = x_label
            show_toast(f"X-axis label updated", "info")
            st.session_state.force_redraw = True
    
    with col2:
        prev_y_label = plot_config.get('yaxis_title', 'Relative Abundance (%)')
        y_label = st.text_input(
            "Y-Axis", 
            value=prev_y_label,
            key=f"y_label_input_{hash(prev_y_label)}"
        )
        
        if y_label != prev_y_label:
            plot_config['yaxis_title'] = y_label
            show_toast(f"Y-axis label updated", "info")
            st.session_state.force_redraw = True


    # ─── Axis Label Color ───
    if 'axis_label_color' not in st.session_state:
        st.session_state.axis_label_color = '#000000'

    axis_color = st.color_picker(
        "Axis Label Color",
        st.session_state.axis_label_color
    )
    if axis_color != st.session_state.axis_label_color:
        st.session_state.axis_label_color = axis_color
        show_toast(f"Axis label color set to {axis_color}", "info")
        st.rerun()

    # Legend 
    st.subheader("Legend Settings")

    col1, col2 = st.columns(2)
    with col1:
        # X position between 0 (left) and 1 (right)
        lp_x = st.number_input(
            "Legend X",
            min_value=0.0, max_value=1.0, step=0.01,
            value=st.session_state.plot_config['legend_position']['x']
        )
        st.session_state.plot_config['legend_position']['x'] = lp_x

    with col2:
        # Y position; 0 = bottom, 1 = top, >1 = above the plot
        lp_y = st.number_input(
            "Legend Y",
            min_value=0.0, max_value=2.0, step=0.01,
            value=st.session_state.plot_config['legend_position']['y']
        )
        st.session_state.plot_config['legend_position']['y'] = lp_y

#### gui buttons for legend position ###

    # Orientation: Horizontal vs. Vertical
    st.radio("Orientation", options=["horizontal", "vertical"], key="legend_orientation")
    st.checkbox("Show legend border", key="legend_border")





def apply_font_settings(fig):
    """
    Apply font settings from session state to a plotly figure.
    
    Args:
        fig: A plotly figure object to modify
    
    Returns:
        The modified figure
    """
    if 'font_settings' not in st.session_state or 'plot_config' not in st.session_state:
        return fig
    
    font_settings = st.session_state.font_settings
    plot_config = st.session_state.plot_config
    
    # Get font family
    font_family = font_settings.get('font_family', 'Arial')
    
    # Apply global font family
    fig.update_layout(
        font=dict(family=font_family)
    )
    
    # Check if this is a mass spectrum (x-axis title contains "m/z")
    is_mass_spectrum = False
    if hasattr(fig.layout, 'xaxis') and hasattr(fig.layout.xaxis, 'title'):
        x_title = getattr(fig.layout.xaxis.title, 'text', '')
        if 'm/z' in str(x_title).lower():
            is_mass_spectrum = True

    # FORCE OVERRIDE THE TITLE FONT 
    # Store the current title text
    if hasattr(fig.layout, 'title') and hasattr(fig.layout.title, 'text') and fig.layout.title.text is not None:
        current_title = fig.layout.title.text
    else:
        current_title = plot_config.get('title', 'Chromatogram Analysis')
    
    # Apply title with the font settings from the sidebar
    fig.update_layout(
        title=dict(
            text=current_title,
            font=dict(
                family=font_family,
                size=font_settings.get('title_fs', 18)
            )
        )
    )
    



###### apply legend settings ######

    lp = plot_config['legend_position']
    orient_code = 'h' if st.session_state.legend_orientation == 'horizontal' else 'v'
    border_w = plot_config['legend_borderwidth'] if st.session_state.legend_border else 0


    fig.update_layout(
        legend=dict(
            font=dict(
                family=font_settings['font_family'],
                size=font_settings['legend_fs']
            ),
            orientation=orient_code,
            x=1.0,
            y=1.0,
            xanchor='right',
            yanchor='top',
            xref='paper',
            yref='paper',
            borderwidth=border_w,
            bordercolor=plot_config['legend_bordercolor'],
            bgcolor=plot_config['legend_bgcolor'],
            itemsizing=plot_config['legend_itemsizing'],
            itemclick=plot_config['legend_itemclick'],
            itemdoubleclick=plot_config['legend_itemdoubleclick'],
            groupclick=plot_config['legend_groupclick']
        )
    )


    
    # Check if we have multiple subplots
    is_subplot = False
    for key in fig.layout:
        if key.startswith('yaxis') and key != 'yaxis':
            is_subplot = True
            break
    
    if is_subplot:
        # For subplots, update all axes
        
        # Update all x-axes
        fig.update_xaxes(
            tickfont=dict(
                family=font_family,
                size=font_settings.get('tick_fs', 18)
            ),
        )
        
        # Set title only on bottom x-axis
        last_xaxis = None
        for key in fig.layout:
            if key.startswith('xaxis'):
                last_xaxis = key
        
        if last_xaxis:
            # Update the bottom x-axis with title
            fig.update_xaxes(
                title=dict(
                    text=plot_config.get('xaxis_title', 'Time (min)'),
                    font=dict(
                        family=font_family,
                        size=font_settings.get('axis_fs', 18)
                    )
                ),
                selector=dict(id=last_xaxis)
            )
        
        # Update all y-axes tick fonts
        fig.update_yaxes(
            tickfont=dict(
                family=font_family,
                size=font_settings.get('tick_fs', 18)
            ),
        )
        
        # Update or add the y-axis annotation
        found_y_annotation = False
        y_label = plot_config.get('yaxis_title', 'Relative Abundance (%)')
        
        if hasattr(fig.layout, 'annotations') and fig.layout.annotations:
            for i, annotation in enumerate(fig.layout.annotations):
                # Check if this is our y-axis label annotation
                if (hasattr(annotation, 'text') and annotation.text == y_label and 
                    hasattr(annotation, 'textangle') and annotation.textangle == -90):
                    # Update font size and family
                    fig.layout.annotations[i].font.size = font_settings.get('axis_fs', 18)
                    fig.layout.annotations[i].font.family = font_family
                    found_y_annotation = True
                    break
        
        # If we didn't find the y-axis annotation, add it
        if not found_y_annotation:
            fig.add_annotation(
                x=-0.1,  # Position to the left of the plots
                y=0.5,   # Middle of the figure
                xref="paper",
                yref="paper",
                text=y_label,
                textangle=-90,
                showarrow=False,
                font=dict(
                    family=font_family,
                    size=font_settings.get('axis_fs', 18)
                )
            )
    else:
        # For single plot, update axes directly
        fig.update_xaxes(
            title=dict(
                text=plot_config.get('xaxis_title', 'Time (min)'),
                font=dict(
                    family=font_family,
                    size=font_settings.get('axis_fs', 18)
                )
            ),
            tickfont=dict(
                family=font_family,
                size=font_settings.get('tick_fs', 18)
            )
        )
        
        fig.update_yaxes(
            title=dict(
                text=plot_config.get('yaxis_title', 'Relative Abundance (%)'),
                font=dict(
                    family=font_family,
                    size=font_settings.get('axis_fs', 18)
                )
            ),
            tickfont=dict(
                family=font_family,
                size=font_settings.get('tick_fs', 18)
            )
        )
    
    axis_color = st.session_state.get('axis_label_color', '#000000')

    # apply to both axes
    fig.update_xaxes(title_font=dict(color=axis_color))
    fig.update_yaxes(title_font=dict(color=axis_color))


    return fig