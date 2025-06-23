from dash import Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

def register_draw_mode_callbacks(app):
    """
    Register callbacks to switch baseline-mode-store between 'draw' and 'zoom' when the user clicks draw/zoom buttons.
    """
    
    @app.callback(
        Output('baseline-mode-store', 'data', allow_duplicate=True),
        Input('draw-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def set_draw_mode(n_clicks):
        print(f"[CRITICAL DEBUG] Draw button clicked! n_clicks={n_clicks}")
        if n_clicks:
            print(f"[CRITICAL DEBUG] Setting baseline-mode-store to 'draw'")
            return "draw"
        print(f"[CRITICAL DEBUG] Draw button n_clicks was falsy, returning 'zoom'")
        return "zoom"

    @app.callback(
        Output('baseline-mode-store', 'data', allow_duplicate=True),
        Input('zoom-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def set_zoom_mode(n_clicks):
        print(f"[CRITICAL DEBUG] Zoom button clicked! n_clicks={n_clicks}")
        if n_clicks:
            print(f"[CRITICAL DEBUG] Setting baseline-mode-store to 'zoom'")
            return "zoom"
        print(f"[CRITICAL DEBUG] Zoom button n_clicks was falsy, returning 'zoom'")
        return "zoom"
