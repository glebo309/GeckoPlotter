"""Keep detector filtering attached to the currently displayed raw figure."""
from dash import Input, Output, State, ctx, no_update
from services.ms_polarity import polarity_options


def register_ms_polarity_callbacks(app, data_manager):
    @app.callback(
        [Output('ms-polarity-toolbar', 'style'), Output('ms-polarity-control', 'data'),
         Output('ms-polarity-control', 'value'), Output('ms-polarity-owner', 'data'),
         Output('current-plot-settings', 'data', allow_duplicate=True)],
        [Input('ms-polarity-control', 'value'), Input('current-plot-settings', 'data'),
         Input('active-plot-tab', 'data'), Input('plot-tabs', 'data'),
         Input('active-file', 'data'), Input('loaded-files', 'data')],
        State('ms-polarity-owner', 'data'), prevent_initial_call=True)
    def sync_polarity(value, settings, tab_id, tabs, active_file, loaded, owner):
        from callbacks.viz_callbacks import _get_active_file_group, _get_overlay_group
        settings = settings or {}
        context = settings.get('_context_key')
        tab = next((item for item in tabs or [] if item.get('id') == tab_id), {})
        hidden = ({'display': 'none'}, no_update, no_update, None, no_update)
        if tab.get('type') != 'raw' or not context or not context.endswith(':' + str(tab_id)):
            return hidden
        group = tuple(tab.get('group_key', [])) or _get_active_file_group(data_manager, active_file)
        allowed = set()
        for record in loaded or []:
            allowed.add(record.get('id'))
            bundle = data_manager.get_bundle(record.get('id'))
            if bundle:
                allowed.update(component.component_id for component in bundle.component_list)
        candidates = [(fid, entry) for fid, entry in data_manager.loaded_data.items()
                      if fid in allowed and _get_overlay_group(entry.get('metadata', {}), entry,
                                                               fid, data_manager) == group]
        options = polarity_options({'current': candidates})
        if not options:
            return hidden
        available = [option['value'] for option in options if not option['disabled']]
        current = settings.get('ms_polarity', 'both')
        shown = current if current in available else available[0]
        if (ctx.triggered_id == 'ms-polarity-control' and owner == context
                and value in available and value != shown):
            return {}, options, value, context, {**settings, 'ms_polarity': value}
        if current not in available and current != 'both' and ctx.triggered_id != 'ms-polarity-control':
            # Removing the selected detector must not leave the figure filtered
            # to a mode that no longer exists while the control shows another.
            return {}, options, shown, context, {**settings, 'ms_polarity': shown}
        return {}, options, shown, context, no_update
