"""Live mode: redraw the screen after an agent changed the workspace (services/live_agent, assets/js/agent-live.js).

The page puts the app's change counter into ``agent-live-version`` when it moves; this rebuilds the file tree, the
active file's views, the plot and the tables from the store, as after an upload. The file the user looks at stays
active while it exists.
"""
import dash
from dash import Input, Output, State, html


def register_live_callbacks(app, data_manager):

    @app.callback(
        [Output('loaded-files', 'data', allow_duplicate=True),
         Output('file-tree', 'children', allow_duplicate=True),
         Output('active-file', 'data', allow_duplicate=True),
         Output('metadata-container', 'children', allow_duplicate=True),
         Output('table-editor-container', 'children', allow_duplicate=True),
         Output('pub-data-store', 'data', allow_duplicate=True),
         Output('render-trigger', 'data', allow_duplicate=True),
         Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('hidden-files', 'data', allow_duplicate=True)],
        Input('agent-live-version', 'data'),
        [State('active-file', 'data'), State('active-plot-tab', 'data'), State('file-order', 'data'),
         State('render-trigger', 'data'), State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def redraw_after_agent(version, active, plot_tab, file_order, render_counter, peak_counter):
        if not version:
            raise dash.exceptions.PreventUpdate
        from callbacks.upload_callbacks import build_active_file_views, render_file_tree_with_bundles_selected
        from components.data_table_editor import create_data_table_editor
        from services.channel_visibility import visible_component_id
        from services.data_store import BundleType

        if not (active and (data_manager.get_data_by_id(active) or data_manager.get_bundle(active))):
            active = None
            bundles = list(data_manager.iter_bundles())
            shown = [b for b in bundles if data_manager.visibility_state.get(b.bundle_id, True)] or bundles
            if shown:
                last = shown[-1]
                runs = (BundleType.CHROMATOGRAM, BundleType.LCMS)
                active = visible_component_id(data_manager, last) if last.bundle_type in runs else last.bundle_id
        files = data_manager.get_loaded_files_list()
        if active:
            table, editor, pub_data = build_active_file_views(data_manager, active)
        else:
            table = html.Div('No file selected', style={'color': '#666', 'padding': '20px', 'textAlign': 'center'})
            editor, pub_data = create_data_table_editor(None, table_id='pub-table'), None
        tree = render_file_tree_with_bundles_selected(files, data_manager, active, active_plot_tab=plot_tab,
                                                      file_order=file_order or {})
        hidden = [fid for fid, visible in data_manager.visibility_state.items() if not visible]
        return (files, tree, active, table, editor, pub_data, (render_counter or 0) + 1, (peak_counter or 0) + 1,
                hidden)
