"""Inspector controls have one visible, clearly scoped home."""
import json
import subprocess
import sys
import pytest


@pytest.fixture(scope='module')
def sections():
    # Other tests intentionally stub ingestion modules. Import the complete UI
    # in its own process so this check exercises the actual application layout.
    script = '''
import json
import app
from components.workspace_layout import walk
result = {}
for section in [n for n in walk(app.app.layout) if getattr(n,'className','') == 'inspector-section']:
    nodes = list(walk(section.children[1]))
    result.setdefault(section.children[0].children, {
        'ids':[n.id for n in nodes if isinstance(getattr(n,'id',None),str)],
        'nested':any(getattr(n,'className','')=='inspector-section' for n in nodes),
        'texts':[n.children for n in nodes if isinstance(getattr(n,'children',None),str)]})
print(json.dumps(result))
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_signal_controls_and_figure_defaults_have_separate_flat_sections(sections):
    assert {'Signal style','Figure style','Smoothing'} <= sections.keys()
    assert {'signal-inspector-select','signal-color','signal-width','signal-opacity'} <= set(sections['Signal style']['ids'])
    assert not {'pt-line-width','pt-trace-opacity','pt-smooth-window'} & set(sections['Signal style']['ids'])
    assert {'pt-line-width','pt-trace-opacity','pt-marker-size','pt-palette'} <= set(sections['Figure style']['ids'])
    assert {'pt-smooth-window','smooth-value'} <= set(sections['Smoothing']['ids'])
    assert not any(section['nested'] for name, section in sections.items() if name in ('Signal style','Figure style','Smoothing'))
    assert 'pt-theme' not in sections['Figure style']['ids'] and 'pt-theme-wrapper' not in sections['Signal style']['ids']


def test_smoothing_explains_measurements_use_original_signal(sections):
    assert 'Display only · peak areas unchanged' in sections['Smoothing']['texts']


@pytest.fixture(scope='module')
def analysis_navigation():
    script = '''
import json
import app
from components.workspace_layout import walk
nodes = list(walk(app.app.layout))
tabs = next(n for n in nodes if getattr(n,'id',None)=='analysis-tabs')
nav = tabs.children[0]
print(json.dumps({
    'keepMounted':tabs.keepMounted,
    'selected':tabs.value,
    'active_tab_store':next(n for n in nodes if getattr(n,'id',None)=='active-tab').data,
    'ids':[n.id for n in nodes if isinstance(getattr(n,'id',None),str)],
    'tabs':[{'value':n.value,'label':n.children,'style':getattr(n,'style',{})}
            for n in walk(nav) if type(n).__name__=='TabsTab'],
    'dropdown':any(getattr(n,'id',None)=='results-more' for n in nodes),
    'scroll':any(getattr(n,'style',{}).get('overflowX')=='auto' for n in walk(nav)),
    'panels':[n.value for n in walk(tabs) if type(n).__name__=='TabsPanel'],
    'side_tabs':[{'value':n.value,'label':n.children,'style':getattr(n,'style',{})}
                 for n in walk(next(n for n in nodes if getattr(n,'id',None)=='side-tabs')) if type(n).__name__=='TabsTab'],
    'side_panels':[n.value for n in walk(next(n for n in nodes if getattr(n,'id',None)=='side-tabs')) if type(n).__name__=='TabsPanel'],
    'side_keepMounted':next(n for n in nodes if getattr(n,'id',None)=='side-tabs').keepMounted,
    'kept_drawn':[n.value for n in walk(next(n for n in nodes if getattr(n,'id',None)=='side-tabs'))
                  if type(n).__name__=='TabsPanel' and getattr(n,'keepMounted',None)],
    'row':[getattr(c,'id',None) for c in next(n for n in nodes if isinstance(getattr(n,'children',None),list)
           and any(getattr(c,'id',None)=='right-column' for c in n.children)).children],
}))
'''
    result = subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,check=True)
    return json.loads(result.stdout)


def test_results_pane_opens_on_peaks_so_the_data_table_is_built_only_when_asked(analysis_navigation):
    assert analysis_navigation['selected'] == 'peak-analysis'
    assert analysis_navigation['active_tab_store'] == 'peak-analysis'


def test_results_pane_holds_the_tables_and_the_views_panel_holds_the_signal_views(analysis_navigation):
    tables = {'data-overview':'Data','peak-analysis':'Peaks','across-samples':'Compare samples','calibration':'Calibration'}
    views = {'metadata':'Metadata','pda':'PDA','ms-scan':'MS scan','ms-peak-mass':'Peak mass','ms-eic':'EIC'}
    assert {tab['value']:tab['label'] for tab in analysis_navigation['tabs']} == tables
    assert {tab['value']:tab['label'] for tab in analysis_navigation['side_tabs']} == views
    assert set(analysis_navigation['panels']) == set(tables)
    assert set(analysis_navigation['side_panels']) == set(views)
    # MS and PDA views appear only for data that has them; Metadata is always there.
    for tab in analysis_navigation['side_tabs']:
        assert (tab['style'].get('display') == 'none') == (tab['value'] != 'metadata')
    assert not analysis_navigation['dropdown']
    assert analysis_navigation['scroll']
    # Inactive panels are not drawn (panel-refresh.js keeps their contents current); PDA stays drawn for its cursors.
    assert analysis_navigation['keepMounted'] is False and analysis_navigation['side_keepMounted'] is False
    assert analysis_navigation['kept_drawn'] == ['pda']
    # The Views panel is its own column to the right of the plot column.
    row = analysis_navigation['row']
    assert row.index('right-column') < row.index('side-divider') < row.index('side-panel')


def test_mass_polarity_and_peak_empty_state_are_reachable(analysis_navigation):
    assert {'ms-polarity-control','ms-polarity-toolbar','peak-analysis-empty'} <= set(analysis_navigation['ids'])
    assert {'ms-polarity-toggle','eic-polarity-toggle','peak-mass-polarity-toggle'} <= set(analysis_navigation['ids'])


def test_analysis_position_control_is_reachable(analysis_navigation):
    assert {'analysis-dock', 'analysis-dock-owner'} <= set(analysis_navigation['ids'])
