from types import SimpleNamespace
import dash
import pytest
import plotly.graph_objects as go
from callbacks import plot_settings_callbacks as callbacks
from services.data_store import DataStore
from services.figure_actions import publication_snapshot
from services.publication_figure import editable_publication_figure
from services.plot_settings_service import PlotSettingsService


def settings_fixture():
    store = DataStore(); store._shared_plot_settings = {}
    app = dash.Dash(__name__)
    callbacks.register_plot_settings_callbacks(app, store)
    cbs = {value['callback'].__wrapped__.__name__: value for value in app.callback_map.values() if value.get('callback')}
    return store, cbs


@pytest.mark.parametrize('frame,stale', [(True, None), (True, []), (False, ['frame', 'ticks'])])
def test_unrelated_control_edits_do_not_replace_frame_with_a_stale_checklist(monkeypatch, frame, stale):
    store, cbs = settings_fixture()
    callbacks._save_settings(store, 'shared:raw:a', {'show_frame': frame})
    hydrate = cbs['hydrate_plot_settings']
    result = hydrate['callback'].__wrapped__('shared:raw:a', None)
    values = {out.component_id: value for out, value in zip(hydrate['output'], result)}
    values.update({'pt-layout-opts': stale, 'pt-line-width': 2.5})
    monkeypatch.setattr(callbacks, 'callback_context', SimpleNamespace(triggered=[{'prop_id':'pt-line-width.value'}]))
    edit = cbs['user_edit_settings']
    changed = edit['callback'].__wrapped__(*[values.get(item['id']) for item in edit['inputs']], result[0])
    assert changed['show_frame'] is frame
    assert changed['line_width'] == 2.5


@pytest.mark.parametrize('enabled', [True, False])
def test_theme_changes_use_saved_frame_state_not_a_stale_checklist(enabled):
    _, cbs = settings_fixture()
    theme = cbs['apply_theme_controls']['callback'].__wrapped__
    _, _, options = theme('plotly_dark', {'theme':'plotly_white', 'show_frame':enabled}, [] if enabled else ['frame'])
    assert ('frame' in options) is enabled


def test_explicit_frame_off_survives_tabs_and_publication(monkeypatch):
    store, cbs = settings_fixture()
    hydrate = cbs['hydrate_plot_settings']
    result = hydrate['callback'].__wrapped__('shared:raw:a', None)
    values = {out.component_id:value for out,value in zip(hydrate['output'], result)}
    assert result[0]['show_frame'] is True
    values['pt-layout-opts'] = ['ticks']
    monkeypatch.setattr(callbacks, 'callback_context', SimpleNamespace(triggered=[{'prop_id':'pt-layout-opts.value'}]))
    edit = cbs['user_edit_settings']
    changed = edit['callback'].__wrapped__(*[values.get(item['id']) for item in edit['inputs']], result[0])
    callbacks._save_settings(store, 'shared:raw:a', changed)
    assert hydrate['callback'].__wrapped__('shared:raw:b', None)[0]['show_frame'] is True
    restored = hydrate['callback'].__wrapped__('shared:raw:a', None)[0]
    assert restored['show_frame'] is False
    source = {'data':[{'x':[0,1],'y':[1,2]}]}
    _, tab, figures = publication_snapshot(source, [], {}, plot_settings=restored)
    figure = editable_publication_figure(source, figures[tab]['plot_settings'])
    assert figure.layout.xaxis.showline is False
    assert figure.layout.yaxis.showline is False


def test_default_frame_restores_neutral_visible_lines_from_inherited_white_axis_style():
    source = go.Figure(data=[go.Scatter(x=[0,1],y=[1,2])], layout={
        'xaxis':{'showline':False,'linecolor':'white'}, 'yaxis':{'showline':False,'linecolor':'white'}})
    result = PlotSettingsService.apply_to_figure(source, PlotSettingsService.get_defaults())
    for axis in [result.layout.xaxis, result.layout.yaxis]:
        assert axis.showline is True
        assert axis.mirror is True
        assert axis.linecolor == '#1f2328'


def test_theme_checklist_output_is_applied_when_color_and_checklist_arrive_together(monkeypatch):
    _, cbs = settings_fixture()
    hydrate = cbs['hydrate_plot_settings']
    result = hydrate['callback'].__wrapped__('shared:raw:a', None)
    values = {out.component_id:value for out,value in zip(hydrate['output'], result)}
    values.update({'pt-layout-opts':['grid_x','grid_y','ticks','frame'], 'pt-bg-color':'#111111'})
    monkeypatch.setattr(callbacks, 'callback_context', SimpleNamespace(triggered=[
        {'prop_id':'pt-bg-color.value'}, {'prop_id':'pt-layout-opts.value'}]))
    edit = cbs['user_edit_settings']
    changed = edit['callback'].__wrapped__(*[values.get(item['id']) for item in edit['inputs']], result[0])
    assert changed['show_grid_x'] is True
    assert changed['show_frame'] is True
