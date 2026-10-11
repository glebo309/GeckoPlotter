from copy import deepcopy
from services.workspace_inspector import active_figure, signal_choices, edit_signal, result_options


def test_inspector_rejects_late_figures_from_another_tab():
    stale={'data':[{'name':'Other'}], 'layout':{'meta':{'gecko_tab_id':'other'}}}
    assert active_figure('lcms',[{'id':'lcms','type':'raw'}],stale,{}) is None
    pub={'data':[{'name':'Published'}],'layout':{'meta':{'gecko_tab_id':'pub'}}}
    assert active_figure('pub',[{'id':'pub','type':'publication'}],stale,pub) == pub


def test_duplicate_signal_names_have_distinct_targets_and_peak_fills_are_omitted():
    fig={'data':[{'name':'+TIC','meta':{'file_id':'a'}}, {'name':'+TIC','meta':{'file_id':'b'}},
                 {'name':'peak:1','fill':'toself'}]}
    options=signal_choices(fig)
    assert len(options)==2
    assert options[0]['value'] != options[1]['value']
    assert options[0]['label'] != options[1]['label']


def test_signal_edit_is_scoped_to_owner_and_only_selected_trace():
    current={'_context_key':'shared:raw:lcms','trace_overrides':{}}
    before=deepcopy(current)
    result=edit_signal(current,'shared:raw:lcms','id:a:+TIC',{'line_width':3,'color':'#123456'})
    assert result['trace_overrides']['id:a:+TIC']['line_width']==3
    assert current == before
    assert edit_signal(current,'shared:raw:other','id:a:+TIC',{'line_width':3}) is None


def test_mass_spectral_results_are_only_added_when_available():
    assert 'ms-scan' not in [o['value'] for o in result_options(False)]
    assert {'ms-scan','ms-eic','ms-peak-mass'} <= {o['value'] for o in result_options(True)}
