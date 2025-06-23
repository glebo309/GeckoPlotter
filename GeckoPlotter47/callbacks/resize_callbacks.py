# File: callbacks/resize_callbacks.py

from dash import Input, Output, State, clientside_callback, ClientsideFunction
import dash

def register_resize_callbacks(app):
    """Register callbacks for dynamic resizing functionality."""
    
    # CLIENT-SIDE CALLBACK FOR DRAG RESIZE
    app.clientside_callback(
        """
        function(n_clicks) {
            // Initialize resize functionality when the page loads
            if (n_clicks === undefined) {
                setTimeout(function() {
                    initializeResizeHandlers();
                }, 100);
                return [60, 30]; // Default heights
            }
            return dash_clientside.no_update;
        }
        """,
        [Output('plot-height-store', 'data'),
         Output('table-height-store', 'data')],
        [Input('dashboard-container', 'style')],
        prevent_initial_call=False
    )
    
    # CALLBACK TO APPLY STORED HEIGHTS TO CSS VARIABLES
    app.clientside_callback(
        """
        function(plot_height, table_height) {
            if (plot_height === null || table_height === null) {
                return dash_clientside.no_update;
            }
            
            // Apply heights to CSS custom properties
            const root = document.documentElement;
            root.style.setProperty('--plot-height', plot_height + 'vh');
            root.style.setProperty('--table-height', table_height + 'vh');
            
            // Force plotly resize on all visible plots
            setTimeout(function() {
                const plots = document.querySelectorAll('.js-plotly-plot');
                plots.forEach(function(plot) {
                    if (plot.style.display !== 'none' && window.Plotly) {
                        window.Plotly.Plots.resize(plot);
                    }
                });
            }, 50);
            
            return dash_clientside.no_update;
        }
        """,
        Output('viz-card', 'id'),  # Dummy output
        [Input('plot-height-store', 'data'),
         Input('table-height-store', 'data')],
        prevent_initial_call=False
    )
    
    # CALLBACK TO TRIGGER RESIZE WHEN SWITCHING FILES
    app.clientside_callback(
        """
        function(tree_clicks, plot_height, table_height) {
            if (tree_clicks === null || tree_clicks === undefined) {
                return dash_clientside.no_update;
            }
            
            // Small delay to ensure new plot is rendered, then resize
            setTimeout(function() {
                // Apply current heights
                const root = document.documentElement;
                root.style.setProperty('--plot-height', plot_height + 'vh');
                root.style.setProperty('--table-height', table_height + 'vh');
                
                // Force plotly resize
                const plots = document.querySelectorAll('.js-plotly-plot');
                plots.forEach(function(plot) {
                    if (plot.style.display !== 'none' && window.Plotly) {
                        window.Plotly.Plots.resize(plot);
                    }
                });
            }, 100);
            
            return dash_clientside.no_update;
        }
        """,
        Output('plot-container', 'id'),  # Dummy output
        [Input('file-tree-container', 'n_clicks'),
         State('plot-height-store', 'data'),
         State('table-height-store', 'data')],
        prevent_initial_call=True
    )

    # ADD THE RESIZE HANDLER JAVASCRIPT
    app.index_string = app.index_string.replace(
        '</footer>',
        '''
        <script>
        function initializeResizeHandlers() {
            let isResizing = false;
            let startY = 0;
            let startPlotHeight = 60;
            let startTableHeight = 30;
            
            const resizeHandle = document.getElementById('resize-handle');
            if (!resizeHandle) return;
            
            resizeHandle.addEventListener('mousedown', function(e) {
                isResizing = true;
                startY = e.clientY;
                
                // Get current heights from CSS custom properties
                const computedStyle = getComputedStyle(document.documentElement);
                const plotHeightStr = computedStyle.getPropertyValue('--plot-height');
                const tableHeightStr = computedStyle.getPropertyValue('--table-height');
                
                startPlotHeight = parseFloat(plotHeightStr.replace('vh', '')) || 60;
                startTableHeight = parseFloat(tableHeightStr.replace('vh', '')) || 30;
                
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
                
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', function(e) {
                if (!isResizing) return;
                
                e.preventDefault();
                
                const deltaY = e.clientY - startY;
                const viewportHeight = window.innerHeight;
                const deltaVH = (deltaY / viewportHeight) * 100;
                
                let newPlotHeight = startPlotHeight + deltaVH;
                let newTableHeight = startTableHeight - deltaVH;
                
                // Constrain heights
                const minPlotHeight = 25;
                const maxPlotHeight = 75;
                const minTableHeight = 15;
                const maxTableHeight = 50;
                
                newPlotHeight = Math.max(minPlotHeight, Math.min(maxPlotHeight, newPlotHeight));
                newTableHeight = Math.max(minTableHeight, Math.min(maxTableHeight, newTableHeight));
                
                // Apply to CSS custom properties
                const root = document.documentElement;
                root.style.setProperty('--plot-height', newPlotHeight + 'vh');
                root.style.setProperty('--table-height', newTableHeight + 'vh');
                
                // Throttled plotly resize
                clearTimeout(window.resizeTimeout);
                window.resizeTimeout = setTimeout(function() {
                    const plots = document.querySelectorAll('.js-plotly-plot');
                    plots.forEach(function(plot) {
                        if (plot.style.display !== 'none' && window.Plotly) {
                            window.Plotly.Plots.resize(plot);
                        }
                    });
                }, 16); // ~60fps
            });
            
            document.addEventListener('mouseup', function(e) {
                if (!isResizing) return;
                
                isResizing = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                
                // Update the Dash stores with final values
                const computedStyle = getComputedStyle(document.documentElement);
                const finalPlotHeight = parseFloat(computedStyle.getPropertyValue('--plot-height').replace('vh', ''));
                const finalTableHeight = parseFloat(computedStyle.getPropertyValue('--table-height').replace('vh', ''));
                
                // Trigger store updates
                const plotStore = document.getElementById('plot-height-store');
                const tableStore = document.getElementById('table-height-store');
                
                if (plotStore && tableStore) {
                    // Update store values (this will trigger the callback)
                    const event = new CustomEvent('storeUpdate', {
                        detail: {
                            plotHeight: finalPlotHeight,
                            tableHeight: finalTableHeight
                        }
                    });
                    document.dispatchEvent(event);
                }
            });
        }
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(initializeResizeHandlers, 500);
        });
        
        // Re-initialize when new content is loaded
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList') {
                    const resizeHandle = document.getElementById('resize-handle');
                    if (resizeHandle && !resizeHandle.hasEventListener) {
                        resizeHandle.hasEventListener = true;
                        setTimeout(initializeResizeHandlers, 100);
                    }
                }
            });
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
        </script>
        </footer>'''
    )