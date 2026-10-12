"""Outputs equal to what the browser already shows are dropped; everything else passes through."""
import dash
import pytest
from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from services.output_dedupe import dedupe_results, eligible, install, _SKIP


def test_identical_value_becomes_no_update_and_changes_pass_through():
    assert dedupe_results({'a': 1}, Output('x', 'data'), [{'a': 1.0}]) is no_update
    assert dedupe_results({'a': 2}, Output('x', 'data'), [{'a': 1}]) == {'a': 2}
    assert dedupe_results(True, Output('x', 'disabled'), [False]) is True


def test_multiple_outputs_are_compared_independently():
    outputs = [Output('a', 'style'), Output('b', 'disabled'), Output('c', 'data')]
    result = dedupe_results(({'display': 'none'}, False, [1]), outputs, [{'display': 'none'}, True, _SKIP])
    assert result[0] is no_update and result[1] is False and result[2] == [1]


def test_non_json_and_unchanged_markers_are_left_alone():
    assert dedupe_results(object(), Output('x', 'data'), [None]) is not no_update
    assert dedupe_results(None, Output('x', 'data'), [None]) is no_update
    assert dedupe_results(no_update, Output('x', 'data'), [1]) is no_update


def test_large_and_trigger_style_outputs_are_never_compared():
    assert not eligible(Output('main-plot', 'figure'))
    assert not eligible(Output('render-trigger', 'data'))
    assert not eligible(Output('active-file', 'data'))
    assert not eligible(Output('pub-data-store', 'data'))
    assert not eligible(Output('table-editor-container', 'children'))
    assert not eligible(Output('some-div', 'children'))
    assert eligible(Output('ms-polarity-toolbar', 'style')) and eligible(Output('cal-peak-picker', 'data'))
    assert not eligible(Output('some-div', 'style'))              # outside the safe families
    assert not eligible(Output('baseline-draw-btn', 'disabled'))  # integration path


def test_wrapper_adds_the_current_values_as_trailing_states_and_keeps_direct_calls_working():
    app = dash.Dash(__name__)
    install(app)
    calls = []

    @app.callback(Output('ms-panel', 'style'), Input('go', 'n_clicks'), State('other', 'value'))
    def show(n_clicks, other):
        calls.append((n_clicks, other))
        return {'display': 'block'}

    entry = next(v for v in app.callback_map.values())
    assert [s['id'] for s in entry['state']] == ['other', 'ms-panel']
    # Browser call: inputs, states..., then the browser's current value of the output
    with pytest.raises(PreventUpdate):  # identical to the client's value: nothing is sent, nothing downstream runs
        entry['callback'](1, 'x', {'display': 'block'}, outputs_list={'id': 'ms-panel', 'property': 'style'})
    # Direct call without the extra State still works (tools and tests)
    assert entry['callback'].__wrapped__(1, 'x') == {'display': 'block'}
    assert calls[-1] == (1, 'x')


def test_unusual_registrations_fall_back_to_plain_dash_behaviour():
    app = dash.Dash(__name__)
    install(app)

    @app.callback(Output('a', 'style'), Input('b', 'n_clicks'), True)
    def positional_flag(n):
        return {}

    @app.callback(Output('a2', 'main-plot'), Input('b2', 'n_clicks'), prevent_initial_call=True)
    def ok(n):
        return None


def test_inputs_declared_inside_the_state_list_keep_their_argument_position():
    """update_pda_views style: Inputs appended to the State list must not move ahead of the States."""
    app = dash.Dash(__name__)
    install(app)
    seen = {}

    @app.callback(Output('ms-out', 'style'), [Input('a', 'data'), Input('b', 'data')],
                  [State('s1', 'data'), Input('late', 'data'), State('s2', 'data')])
    def fn(a, b, s1, late, s2):
        seen.update(a=a, b=b, s1=s1, late=late, s2=s2)
        return {'x': 1}

    entry = next(iter(app.callback_map.values()))
    with pytest.raises(PreventUpdate):   # the browser's value of the output equals the result
        entry['callback']('A', 'B', 'LATE', 'S1', 'S2', {'x': 1}, outputs_list={'id': 'ms-out', 'property': 'style'})
    assert seen == {'a': 'A', 'b': 'B', 's1': 'S1', 'late': 'LATE', 's2': 'S2'}
    # Dash hands over typed order (Inputs, then States); the function still receives its declared order.
    assert [d['id'] for d in entry['inputs']] == ['a', 'b', 'late']
    assert [d['id'] for d in entry['state']] == ['s1', 's2', 'ms-out']
