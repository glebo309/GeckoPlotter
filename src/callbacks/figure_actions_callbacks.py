import dash
from dash import ALL, ClientsideFunction, Input, Output, State
from services.figure_actions import publication_snapshot


def register_figure_actions_callbacks(app):
    app.clientside_callback(
        ClientsideFunction(namespace='geckoFigureActions', function_name='dispatch'),
        Output('figure-context-close', 'data'),
        Input({'type': 'figure-action', 'context': ALL, 'action': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )

    @app.callback(
        [Output('plot-tabs', 'data', allow_duplicate=True),
         Output('active-plot-tab', 'data', allow_duplicate=True),
         Output('custom-plot-figures', 'data', allow_duplicate=True),
         Output('toolbox-tab', 'data', allow_duplicate=True)],
        Input('figure-action-event', 'data'),
        [State('plot-tabs', 'data'), State('custom-plot-figures', 'data'),
         State('current-plot-settings', 'data')],
        prevent_initial_call=True,
    )
    def send_to_publication(event, tabs, figures, plot_settings):
        if not event or event.get('action') != 'publication' or not event.get('figure'):
            raise dash.exceptions.PreventUpdate
        next_tabs, tab_id, next_figures = publication_snapshot(
            event['figure'], tabs, figures, event.get('label', 'Plot'), plot_settings)
        return next_tabs, tab_id, next_figures, 'plot-tools'

    app.clientside_callback(
        'function() { return false; }',
        Output('figure-context-menu', 'opened', allow_duplicate=True),
        [Input('active-plot-tab', 'data'), Input('active-tab', 'data'),
         Input('figure-context-close', 'data')],
        prevent_initial_call=True,
    )
