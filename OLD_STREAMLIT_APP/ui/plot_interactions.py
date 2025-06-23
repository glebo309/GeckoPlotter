#  ui/plot_interactions.py 
#  Interactive Title Editing Feature

import streamlit as st
import plotly.graph_objects as go

def make_titles_editable(fig):
    """
    Make plot titles interactively editable via click events.
    
    Parameters:
    -----------
    fig : plotly.graph_objects.Figure
        The figure to modify
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The modified figure with editable titles
    """
    # Add custom JavaScript for title editing
    fig.update_layout(
        clickmode='event',
        # Add custom title styling that indicates editability
        title=dict(
            font=dict(
                color='#2c3e50',  # Darker color
                family='Arial'
            ),
            # Add subtle indicator that titles are editable
            pad=dict(b=10, t=10),
        ),
    )
    
    # Add custom JavaScript for title editing via config
    config = {
        'displayModeBar': True,
        'scrollZoom': True,
        'modeBarButtonsToAdd': [
            'zoomIn2d',
            'zoomOut2d',
            'autoScale2d',
            'resetScale2d',
            'hoverClosestCartesian',
            'toggleSpikelines'
        ],
        # Add custom JavaScript for title editing
        'toImageButtonOptions': {
            'format': 'png',
            'filename': 'plot',
        }
    }
    
    # Add editable flag to session state
    if 'editable_titles' not in st.session_state:
        st.session_state.editable_titles = True
    
    return fig, config

def implement_title_editing_ui():
    """
    Implement UI components for title editing functionality
    """

    
    # Create JavaScript for Streamlit components
    title_edit_js = """
    <script>
    // Function to make titles editable
    function makeTitlesEditable() {
        // Select all title elements
        const titles = document.querySelectorAll('.gtitle, .xtitle, .ytitle');
        
        titles.forEach(title => {
            // Add edit styling
            title.style.cursor = 'pointer';
            
            // Add click event
            title.addEventListener('click', function(e) {
                e.stopPropagation();
                
                // Get current text
                const currentText = this.textContent;
                
                // Create input for editing
                const input = document.createElement('input');
                input.type = 'text';
                input.value = currentText;
                input.style.width = '100%';
                input.style.padding = '4px';
                input.style.fontSize = window.getComputedStyle(this).fontSize;
                
                // Replace title with input
                this.innerHTML = '';
                this.appendChild(input);
                
                // Focus on input
                input.focus();
                
                // Handle input events
                input.addEventListener('keydown', function(event) {
                    if (event.key === 'Enter') {
                        // Save changes
                        const newText = this.value;
                        this.parentNode.textContent = newText;
                        
                        // Update Streamlit with the change
                        // This would need to be implemented with a custom component
                        // For now, just update the DOM
                    }
                });
                
                // Handle blur (clicking away)
                input.addEventListener('blur', function() {
                    const newText = this.value;
                    this.parentNode.textContent = newText;
                });
            });
        });
    }
    
    // Run when DOM is loaded
    document.addEventListener('DOMContentLoaded', function() {
        // Wait a bit for Plotly to render
        setTimeout(makeTitlesEditable, 1000);
        
        // Also set up a mutation observer to handle dynamically added plots
        const observer = new MutationObserver(function(mutations) {
            setTimeout(makeTitlesEditable, 500);
        });
        
        observer.observe(document.body, { 
            childList: true,
            subtree: true
        });
    });
    </script>
    """
    
    # Use Streamlit components to inject JavaScript
    st.components.v1.html(title_edit_js, height=0)

def update_figure_title_events(fig, title_key):
    """
    Add event handling to a figure for title editing.
    
    Parameters:
    -----------
    fig : plotly.graph_objects.Figure
        The figure to modify
    title_key : str
        A unique key for this title in session state
        
    Returns:
    --------
    plotly.graph_objects.Figure
        The modified figure
    """
    # Create a unique key for storing this title
    if title_key not in st.session_state:
        # Initialize with current title
        current_title = fig.layout.title.text if hasattr(fig.layout, 'title') and hasattr(fig.layout.title, 'text') else ""
        st.session_state[title_key] = current_title
    
    # Use a text input for editing, but hide it initially
    # This isn't ideal, but Streamlit limitations make direct editing challenging
    with st.expander("Edit Plot Titles", expanded=False):
        new_title = st.text_input(
            "Main Title:",
            value=st.session_state[title_key],
            key=f"{title_key}_input"
        )
        
        if new_title != st.session_state[title_key]:
            st.session_state[title_key] = new_title
            fig.update_layout(title_text=new_title)
            st.experimental_rerun()
    
    return fig

def capture_title_changes(plotly_events):
    """
    Capture title changes from Plotly events and store them in session state.
    """
    if not plotly_events:
        return
    
    # Check for title updates from editable mode
    if 'updatemenus.title' in plotly_events:
        new_title = plotly_events['updatemenus.title']
        
        # Remove extra <b> tags if present
        if new_title and new_title.startswith('<b>') and new_title.endswith('</b>'):
            new_title = new_title[3:-4]
        
        # Store in session state for persistence
        if 'plot_config' not in st.session_state:
            st.session_state.plot_config = {}
        
        st.session_state.plot_config['title'] = new_title

def capture_legend_position(plotly_events):
    """Save legend position when user moves it"""
    if not plotly_events:
        return
        
    if "relayoutData" in plotly_events:
        relayout = plotly_events["relayoutData"]
        if "legend.x" in relayout and "legend.y" in relayout:
            # Initialize if needed
            if 'plot_config' not in st.session_state:
                st.session_state.plot_config = {}
                
            st.session_state.plot_config['legend_position'] = {
                'x': relayout["legend.x"],
                'y': relayout["legend.y"]
            }
            # Uncomment for debugging
            print(f"Legend position saved: {relayout['legend.x']}, {relayout['legend.y']}")

            
def add_title_editing_html():
    """Add HTML/JS for plot title editing"""
    html = """
    <div style="margin-bottom: 1rem;">
        <button id="enable-title-edit" class="stButton">
            <div style="display: flex; align-items: center;">
                <span>✏️ Enable Title Editing</span>
            </div>
        </button>
        <div id="edit-instructions" style="display: none; margin-top: 0.5rem; padding: 0.5rem; 
                                         background-color: #f8f9fa; border-radius: 0.3rem;">
            Click on any plot title or axis label to edit it directly.
        </div>
    </div>
    
    <script>
    // Enable title editing when button is clicked
    document.getElementById('enable-title-edit').addEventListener('click', function() {
        const instructions = document.getElementById('edit-instructions');
        instructions.style.display = 'block';
        
        // Find all plotly figures
        const figures = document.querySelectorAll('.js-plotly-plot');
        
        figures.forEach(figure => {
            // Make main title editable
            const mainTitle = figure.querySelector('.gtitle');
            if (mainTitle) makeEditable(mainTitle);
            
            // Make axis titles editable
            const axisTitles = figure.querySelectorAll('.xtitle, .ytitle');
            axisTitles.forEach(title => makeEditable(title));
        });
    });
    
    function makeEditable(element) {
        element.style.cursor = 'pointer';
        element.title = 'Click to edit';
        
        element.addEventListener('click', function(e) {
            e.stopPropagation();
            
            const currentText = this.textContent;
            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentText;
            input.style.width = '100%';
            input.style.padding = '4px';
            input.style.fontSize = window.getComputedStyle(this).fontSize;
            
            this.innerHTML = '';
            this.appendChild(input);
            input.focus();
            
            input.addEventListener('keydown', function(event) {
                if (event.key === 'Enter') {
                    const newText = this.value;
                    this.parentNode.textContent = newText;
                }
            });
            
            input.addEventListener('blur', function() {
                const newText = this.value;
                this.parentNode.textContent = newText;
            });
        });
    }
    </script>
    """
    
    st.components.v1.html(html, height=80)