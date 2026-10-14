"""Context callbacks for unified per-file UI state.

Plot settings are handled entirely by plot_settings_callbacks.py.
This module only manages non-plot UI state: active-tab, toolbox-tab,
dev-settings, and file-ui-state persistence.  view-mode is derived
from the active plot tab (see app.py derive_view_mode).
"""

import dash
from dash import Input, Output, State


def register_context_callbacks(app, data_manager):
    """Register per-file UI state load/save callbacks."""

    @app.callback(
        [
            Output('file-ui-state', 'data'),
            Output('active-tab', 'data', allow_duplicate=True),
            Output('toolbox-tab', 'data', allow_duplicate=True),
            Output('dev-settings', 'data', allow_duplicate=True),
        ],
        Input('active-file', 'data'),
        State('active-tab', 'data'),
        prevent_initial_call=True,
    )
    def load_file_ui_state(active_file, current_tab):
        """Load persisted UI state when the active file changes.

        The table panel (active-tab) is managed by restore_panel_on_tab_switch
        based on which plot tab is active, so we never override it here.
        Plot settings hydration is handled by plot_settings_callbacks.
        """
        state = data_manager.get_file_state(active_file)

        return (
            state,
            dash.no_update,
            state.get('toolbox_tab', 'plot-tools'),
            state.get('dev_settings', {'show': False}),
        )

    @app.callback(
        Output('file-ui-state', 'data', allow_duplicate=True),
        [
            Input('view-mode', 'data'),
            Input('active-tab', 'data'),
            Input('toolbox-tab', 'data'),
            Input('dev-settings', 'data'),
        ],
        State('active-file', 'data'),
        prevent_initial_call=True,
    )
    def save_file_ui_state(view_mode, active_tab, toolbox_tab, dev_settings, active_file):
        """Persist non-plot UI state for the active file."""
        if not active_file:
            return dash.no_update

        current_state = data_manager.get_file_state(active_file)
        next_state = {
            **current_state,
            'view_mode': view_mode or 'raw',
            'active_tab': active_tab or 'peak-analysis',
            'toolbox_tab': toolbox_tab or 'plot-tools',
            'dev_settings': dev_settings or {'show': False},
        }

        if next_state == current_state:
            return dash.no_update

        return data_manager.save_file_state(active_file, next_state)
