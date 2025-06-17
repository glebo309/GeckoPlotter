#interactions/base_interaction

import plotly.graph_objects as go

class BasePlotController:
    def __init__(self, plot_id):
        self.plot_id = plot_id
    
    def enhance_interactivity(self, fig):

        """Add base interactive features to any plot"""
        fig.update_layout(
            # Enhanced zoom and pan
            dragmode='zoom',
            selectdirection='d',  # Fixed: 'd' not 'diagonal'
            
            # Better legend
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.99,
                xanchor="left", 
                x=1.01,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(0,0,0,0.2)",
                borderwidth=1
            ),
            
            # Hover improvements
            hovermode='closest',
            
            # Click improvements
            clickmode='event+select'
        )
        
        # Enhanced axes
        fig.update_xaxes(
            showspikes=True,
            spikecolor="rgba(0,0,0,0.3)",
            spikesnap="cursor",
            spikemode="across",
            spikethickness=1
        )
        
        fig.update_yaxes(
            showspikes=True,
            spikecolor="rgba(0,0,0,0.3)",
            spikesnap="cursor", 
            spikemode="across",
            spikethickness=1
        )
        
        return fig