"""Capture displayed figure and export all linked research data locally."""
import base64
import logging
from dash import Input, Output, State, ClientsideFunction, no_update
from services.research_package import build_research_package, record_analysis_state, safe_name

FIELDS = ['title','description','creators','orcid','affiliation','record-url','article-doi','license','funding','keywords','methods']


def register_research_export_callbacks(app, store):
    app.clientside_callback(
        ClientsideFunction(namespace='geckoFigureActions',function_name='packageRequest'),
        Output('pkg-request','data'), Input('pkg-download-btn','n_clicks'),
        [State('exp-preset','value'), State('exp-width','value'), State('exp-height','value'), State('exp-dpi','value')],
        prevent_initial_call=True)

    @app.callback([Output('pkg-download','data'),Output('pkg-status','children')],
        Input('pkg-request','data'),
        [State('pkg-'+field,'value') for field in FIELDS]+[State('pkg-formats','value'),State('current-plot-settings','data'),State('pkg-include-code','checked')],
        running=[(Output('pkg-download-btn','loading'),True,False)],prevent_initial_call=True)
    def export_package(request,*values):
        if not request: return no_update,no_update
        metadata={field.replace('-','_'):v for field,v in zip(FIELDS,values)}
        formats,settings,include_code=values[-3:]
        try:
            if request.get('error'): raise ValueError(request['error'])
            record_analysis_state(store, settings, ['export-settings'])
            content=build_research_package(store,metadata,request,formats or [],include_code=bool(include_code))
            return {'content':base64.b64encode(content).decode(),'base64':True,
                'filename':safe_name(metadata.get('title') or 'fair-data-package')+'.zip'}, 'Package ready. Open report.html to review it.'
        except Exception as exc:
            logging.getLogger(__name__).exception('Research package export failed')
            return no_update,'Export failed: '+str(exc)


# Rendering and control hydration cannot edit scientific state. Unknown/new
# callbacks remain captured so adding a feature cannot silently lose its history.
# record_analysis_state() only looks at signals (names/metadata/roles/data), the plot settings it is handed, file_ui_state,
# peaks, calibrations and integration settings; a callback may be listed here only when it touches none of those
# (callbacks that output ``current-plot-settings``, edit peaks/calibration/integration/data stay recorded).
_READ_ONLY_CALLBACKS = {
    'callbacks.viz_callbacks': {'master_render'},
    'callbacks.pda_callbacks': {'show_pda_tab', 'update_pda_views', 'sync_pda_main_view', 'preview_integration_controls'},
    'callbacks.workspace_callbacks': {'describe_figure', 'analysis_capabilities', 'show_export', 'report_file_action'},
    'callbacks.axis_inspector_callbacks': {'hydrate_axes'},
    'callbacks.plot_settings_callbacks': {
        'resolve_plot_context',
        'persist_plot_settings',     # writes the browser-side settings cache to disk only
        'apply_theme_controls',      # fills colour controls; the change itself arrives via user_edit_settings (recorded)
    },
    'callbacks.file_tree_callbacks': {
        'toggle_bundle_expansion', 'toggle_group_expansion', 'toggle_file_expansion', 'sync_file_tree_selection',
        'update_plot_channel_controls',
        'update_pda_channel_controls',    # channel checkboxes, display only
        'toggle_group_sort', 'handle_drag_reorder',   # tree / overlay order (file-order store), not in provenance
        'handle_visibility_toggles', 'sync_loaded_file_visibility', 'toggle_group_channel',   # visibility_state only
    },
    'callbacks.integration_callbacks': {'detection_target', 'explain_sensitivity'},
    'callbacks.lcms_callbacks': {
        'configure_scan_slider', 'update_mass_spectrum', 'scrub_mass_spectrum', 'update_eic_graph', 'update_eic_list',
        'update_peak_mass_selector', 'show_peak_mass', 'peak_mass_polarity_visibility',
        'sync_polarity_toggle', 'sync_client_scan_event',   # toggle / slider mirrors, display only
    },
    'callbacks.session_callbacks': {
        'save_project', 'autosave_project', 'check_last_session',   # write files / banners; the store is only read
    },
    'callbacks.tab_callbacks': {
        'show_peak_table_empty_state', 'cross_calibration_disabled',   # style / disabled flags
        'update_group_options_on_slider', 'sync_group_selector_to_plot_tab',   # selector options / value
    },
}


def _outputs_include_settings(outputs):
    if isinstance(outputs, dict):
        return outputs.get('id') == 'current-plot-settings'
    if isinstance(outputs, (list, tuple)):
        return any(_outputs_include_settings(item) for item in outputs)
    return False


def register_provenance_capture(app,store):
    from flask import request
    from threading import RLock
    lock=RLock()
    @app.server.after_request
    def capture_analysis(response):
        if request.path != '/_dash-update-component' or response.status_code != 200:
            return response
        body=request.get_json(silent=True) or {}
        changed=body.get('changedPropIds',[])
        callback = app.callback_map.get(body.get('output'), {}).get('callback')
        if (getattr(callback, '__name__', None) in
                _READ_ONLY_CALLBACKS.get(getattr(callback, '__module__', None), set())):
            return response
        if not changed or not store.all_bundles(): return response
        try:
            outputs = body.get('outputs', [])
            if isinstance(outputs, dict):
                outputs = [outputs]
            settings = None
            # Figure/PDA responses can contain millions of numbers. Decode only
            # callbacks actually returning settings; state already lives server-side.
            if _outputs_include_settings(outputs):
                result = response.get_json(silent=True) or {}
                settings = result.get('response', {}).get('current-plot-settings', {}).get('data')
            with lock:
                record_analysis_state(store,settings,changed)
        except Exception:
            logging.getLogger(__name__).exception('Could not record analysis provenance')
        return response
