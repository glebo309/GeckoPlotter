from dash import Input, Output, html, callback_context


def register_interaction_callbacks(app, data_manager):
    
    @app.callback(
        Output('plot-title-display', 'children'),
        [Input('ms-plot', 'clickData'),
        Input('uv-chromatogram-plot', 'clickData'),
        Input('uvvis-plate-plot', 'clickData')],
        prevent_initial_call=True
    )
    def handle_plot_clicks(ms_click, uv_click, uvvis_click):
        ctx = callback_context
        if not ctx.triggered:
            return "Interactive Plots"
        
        triggered_plot = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if triggered_plot == 'ms-plot' and ms_click:
            point = ms_click['points'][0]
            return f"📊 RT: {point['x']:.2f} min | Intensity: {point['y']:,.0f}"
            
        elif triggered_plot == 'uv-chromatogram-plot' and uv_click:
            point = uv_click['points'][0]
            return f"📈 RT: {point['x']:.2f} min | Signal: {point['y']:.2f}"
            
        elif triggered_plot == 'uvvis-plate-plot' and uvvis_click:
            point = uvvis_click['points'][0]
            return f"🧪 λ: {point['x']:.0f} nm | Abs: {point['y']:.3f}"
        
        return "Interactive Plots"