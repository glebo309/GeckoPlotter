"""Save the current analysis as a recipe and apply a recipe to the loaded samples."""
import base64
import logging

import dash
from dash import Input, Output, State, dcc

from services import recipe_service
from services.research_package import safe_name

log = logging.getLogger(__name__)


def register_recipe_callbacks(app, data_manager):

    @app.callback(
        [Output('recipe-download', 'data'), Output('status-text', 'children', allow_duplicate=True)],
        Input('recipe-save-btn', 'n_clicks'),
        [State('int-rt-tolerance', 'value'), State('integration-baseline', 'value')],
        prevent_initial_call=True,
    )
    def save_recipe(n_clicks, tolerance, baseline_mode):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        name = (getattr(data_manager, 'session_meta', None) or {}).get('project_name') or 'recipe'
        try:
            recipe = recipe_service.build_recipe(data_manager, name=name, rt_tolerance=tolerance or 0.3,
                                                 baseline_mode=baseline_mode or 'linear')
        except recipe_service.RecipeError as exc:
            return dash.no_update, str(exc)
        windows = sum(len(s['windows']) for s in recipe['signals'])
        return (dcc.send_string(recipe_service.dumps(recipe), safe_name(name) + '.geckorecipe'),
                f'Recipe saved: {windows} compound window(s), integration settings'
                + (' and calibrations.' if recipe.get('calibrations') else '.'))

    @app.callback(
        [Output('peak-change-trigger', 'data', allow_duplicate=True),
         Output('status-text', 'children', allow_duplicate=True)],
        Input('recipe-apply-upload', 'contents'),
        [State('recipe-apply-upload', 'filename'), State('peak-change-trigger', 'data')],
        prevent_initial_call=True,
    )
    def apply_recipe(contents, filename, trigger_counter):
        if not contents:
            raise dash.exceptions.PreventUpdate
        try:
            encoded = contents.split(',', 1)[1]
            if len(encoded) > 14_000_000:
                raise recipe_service.RecipeError('This recipe file is too large.')
            recipe = recipe_service.loads(base64.b64decode(encoded).decode('utf-8-sig'))
            report = recipe_service.apply_recipe(data_manager, recipe)
        except (recipe_service.RecipeError, ValueError, IndexError) as exc:
            return dash.no_update, f'Recipe not applied: {exc}'
        except Exception:
            log.exception('Applying recipe %s failed', filename)
            return dash.no_update, 'Recipe not applied: something went wrong, nothing was changed that could be undone.'
        return (trigger_counter or 0) + 1, recipe_service.summarize(report)
