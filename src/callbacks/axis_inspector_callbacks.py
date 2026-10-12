"""Active-figure axis inspector with owner-checked, debounced edits."""
import dash
from dash import Input, Output, State, ALL, ctx
from components.axis_inspector import axis_cards
from services.axis_inspector import axis_descriptors, update_axis_override, reset_axis_settings, preserve_other_axes


def active_axis_figure(main, publication, tab, tabs):
    descriptor = next((item for item in tabs or [] if item.get('id') == tab), {})
    figure = publication if descriptor.get('type') == 'publication' or str(tab).startswith('publication-') else main
    if not figure or not figure.get('data'):
        return None
    meta = figure.get('layout', {}).get('meta') or {}
    if isinstance(meta, dict) and meta.get('gecko_tab_id') not in (None, tab):
        return None
    return figure


def register_axis_inspector_callbacks(app):
    @app.callback(
        Output('axis-inspector-cards', 'children'),
        Input('main-inspector-context', 'data'), Input('publication-inspector-context', 'data'),
        Input('active-plot-tab', 'data'), Input('current-plot-settings', 'data'),
        State('plot-tabs', 'data'), State('active-plot-context', 'data'),
    )
    def hydrate_axes(main, publication, tab, settings, tabs, owner):
        if not owner or (settings or {}).get('_context_key') != owner:
            return axis_cards([], {}, owner)
        figure = active_axis_figure(main, publication, tab, tabs)
        if figure is None:
            return axis_cards([], {}, owner)
        return axis_cards(axis_descriptors(figure), settings or {}, owner)

    @app.callback(
        Output('current-plot-settings', 'data', allow_duplicate=True),
        Output('axis-inspector-error', 'children'),
        Input({'type':'axis-inspector-mode','axis':ALL,'owner':ALL}, 'value'),
        Input({'type':'axis-inspector-min','axis':ALL,'owner':ALL}, 'value'),
        Input({'type':'axis-inspector-max','axis':ALL,'owner':ALL}, 'value'),
        Input({'type':'axis-inspector-scale','axis':ALL,'owner':ALL}, 'value'),
        State({'type':'axis-inspector-mode','axis':ALL,'owner':ALL}, 'id'),
        State('current-plot-settings', 'data'), State('active-plot-context', 'data'),
        State('axis-inspector-view', 'data'), State('active-plot-tab', 'data'),
        prevent_initial_call=True,
    )
    def edit_axis(modes, minima, maxima, scales, identities, settings, owner, view, tab):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict) or trigger.get('owner') != owner:
            return dash.no_update, dash.no_update
        index = next((i for i,item in enumerate(identities)
                      if item.get('axis') == trigger.get('axis') and item.get('owner') == owner), None)
        if index is None or any(index >= len(values) for values in (modes,minima,maxima,scales)):
            return dash.no_update, dash.no_update
        try:
            result = update_axis_override(settings, owner, trigger['axis'], modes[index],
                                          minima[index], maxima[index], scales[index])
        except (ValueError, TypeError) as error:
            return dash.no_update, str(error)
        if result is not None and view and view.get('tab') == tab:
            preserve_other_axes(result, view, trigger['axis'])
        return (result if result is not None else dash.no_update), ''


    @app.callback(
        Output('current-plot-settings', 'data', allow_duplicate=True),
        Input('axis-inspector-reset', 'data'),
        State('main-plot', 'figure'), State('pub-preview-graph', 'data'),
        State('active-plot-tab', 'data'), State('plot-tabs', 'data'),
        State('current-plot-settings', 'data'), State('active-plot-context', 'data'),
        prevent_initial_call=True,
    )
    def reset_axis(event, main, publication, tab, tabs, settings, owner):
        if not event or event.get('tab') != tab or (settings or {}).get('_context_key') != owner:
            return dash.no_update
        figure = active_axis_figure(main, publication, tab, tabs)
        if figure is None:
            return dash.no_update
        result = reset_axis_settings(settings, figure, event.get('axis'), event.get('axes', {}))
        return result if result is not None else dash.no_update
