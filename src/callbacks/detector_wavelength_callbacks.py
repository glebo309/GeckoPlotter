"""The Metadata view asks for the wavelength of a UV channel whose file does not record it (services/detector_wavelengths)."""
import dash
from dash import Input, Output, State

from services.detector_wavelengths import needs_wavelength, remembered, set_wavelength


def register_detector_wavelength_callbacks(app, data_manager):

    @app.callback(
        [Output('wavelength-bar', 'style'), Output('wavelength-bar-label', 'children'),
         Output('detector-wavelength', 'value')],
        [Input('active-file', 'data'), Input('loaded-files', 'data')],
    )
    def show_wavelength_bar(active_file, _loaded):
        entry = data_manager.get_data_by_id(active_file) if active_file else None
        detector = needs_wavelength((entry or {}).get('metadata'))
        if not detector:
            return {'display': 'none'}, '', dash.no_update
        meta = entry['metadata']
        entered = meta.get('wavelength_source') == 'entered'
        label = (f'Wavelength of {detector}' if entered
                 else f'Wavelength of {detector} (not in the file)')
        value = meta.get('wavelength_nm') if entered else remembered().get(detector)
        return {}, label, value

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('status-text', 'children', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True)],
        Input('detector-wavelength-set', 'n_clicks'),
        [State('detector-wavelength', 'value'), State('active-file', 'data'), State('render-trigger', 'data')],
        prevent_initial_call=True,
    )
    def apply_wavelength(clicks, value, active_file, counter):
        entry = data_manager.get_data_by_id(active_file) if active_file else None
        detector = needs_wavelength((entry or {}).get('metadata'))
        try:
            nm = float(value)
        except (TypeError, ValueError):
            raise dash.exceptions.PreventUpdate
        if not clicks or not detector or not 100 <= nm <= 1100:
            raise dash.exceptions.PreventUpdate
        changed = set_wavelength(data_manager, detector, nm)
        from callbacks.viz_callbacks import create_data_table, create_bundle_data_table
        bundle = data_manager.get_bundle_by_id(active_file)          # the same view the file selection shows
        file_data = data_manager.get_data_by_id(active_file)
        metadata = create_bundle_data_table(bundle, file_data, data_manager) if bundle else create_data_table(file_data)
        return (data_manager.get_loaded_files_list(), (counter or 0) + 1,
                f'{detector} set to {nm:g} nm in {changed} run{"s" if changed != 1 else ""}; '
                f'used for {detector} files loaded later on this computer.', metadata)
