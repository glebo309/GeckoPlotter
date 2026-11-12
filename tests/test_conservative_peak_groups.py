"""Nearby peaks must not inherit each other's names through broad or stale groups."""
import plotly.graph_objects as go

from services.peak_service import Peak, PeakService
from services.plot_settings_service import DEFAULT_PLOT_SETTINGS, PlotSettingsService


def peak(fid, rt, name='Peak 1', label='', gid=None, source='manual'):
    return Peak(fid+'-'+str(rt),fid,name,rt,rt-.005,rt+.005,1,5,.01,
                label=label,group_id=gid,source=source,
                deconv_group=gid if source=='deconvolved' else None,
                poly_x=[rt-.005,rt,rt+.005,rt-.005],poly_y=[0,5,0,0])


def test_default_keeps_tpa_and_mhet_apart():
    ps=PeakService()
    a=peak('tpa',1.844);b=peak('mhet',1.885)
    ps._peaks={'tpa':[a],'mhet':[b]}
    ps.group_peaks_across_samples()
    assert a.group_id != b.group_id
    assert ps._grouping_window == .01


def test_nearby_replicates_still_match_without_chaining_into_later_peaks():
    ps=PeakService()
    ps._peaks={fid:[peak(fid,rt)] for fid,rt in [('a',1.884),('b',1.889),('c',1.899)]}
    ps.group_peaks_across_samples()
    assert ps._peaks['a'][0].group_id==ps._peaks['b'][0].group_id
    assert ps._peaks['c'][0].group_id!=ps._peaks['a'][0].group_id


def test_reused_deconvolution_indices_do_not_identify_compounds():
    ps=PeakService()
    a=peak('a',1.847,'TPA','TPA','deconv_1.9_c0','deconvolved')
    b=peak('b',1.885,'MHET','MHET','deconv_1.9_c0','deconvolved')
    c=peak('c',1.886,'MHET','MHET','deconv_1.9_c1','deconvolved')
    ps._peaks={'a':[a],'b':[b],'c':[c]}
    ps.group_peaks_across_samples()
    assert a.group_id!=b.group_id
    assert b.group_id==c.group_id
    assert (a.deconv_group,b.deconv_group,c.deconv_group)==('deconv_1.9_c0','deconv_1.9_c0','deconv_1.9_c1')


def test_grouping_keeps_distinct_explicit_names_even_with_a_wide_window():
    ps=PeakService()
    a=peak('a',1.884,'MHET','MHET');b=peak('b',1.899,'BHET','BHET')
    ps._peaks={'a':[a],'b':[b]}
    ps.group_peaks_across_samples(rt_window=.2)
    assert (a.name,b.name)==('MHET','BHET')
    assert a.group_id!=b.group_id


def test_rename_does_not_spread_via_a_stale_or_distant_group():
    ps=PeakService()
    a=peak('a',1.844,'TPA standard','TPA standard','compound_rt1.844')
    b=peak('b',1.885,'TPA standard','TPA standard','compound_rt1.844')
    ps._peaks={'a':[a],'b':[b]};ps._grouping_window=.2
    ps.rename_peak('b',b.peak_id,'MHET')
    assert a.name=='TPA standard'
    assert b.name=='MHET'


def test_rename_does_not_replace_a_distinct_name_or_cross_an_ion_scope():
    ps=PeakService(color_scope_resolver=lambda fid: 'ion2' if fid=='c' else 'ion1')
    a=peak('a',1.884,'MHET','MHET','bad-old-group')
    b=peak('b',1.885,'BHET','BHET','bad-old-group')
    c=peak('c',1.884,'MHET','MHET','bad-old-group')
    ps._peaks={'a':[a],'b':[b],'c':[c]}
    ps.rename_peak('a',a.peak_id,'new name')
    assert b.name=='BHET' and c.name=='MHET'


def test_comparison_default_is_narrow_and_preserves_named_species():
    from callbacks.tab_callbacks import group_peaks_by_retention_time
    rows=[{'sample_name':'TPA standard','retention_time':1.844,'peak_name':'TPA'},
          {'sample_name':'MHET standard','retention_time':1.885,'peak_name':'MHET'}]
    assert len(group_peaks_by_retention_time(rows))==2
    assert len(group_peaks_by_retention_time(rows,.2))==2


def test_thinner_defaults_apply_to_signal_and_fitted_peak_outline():
    assert DEFAULT_PLOT_SETTINGS['line_width']==1.0
    fig=go.Figure(go.Scatter(x=[0,1],y=[0,1]))
    PlotSettingsService.apply_to_figure(fig,PlotSettingsService.get_defaults())
    assert fig.data[0].line.width==1.0
    from callbacks.peak_overlay import add_peak_traces
    p=peak('a',1.885,'MHET','MHET','fit','deconvolved')
    overlay=go.Figure();add_peak_traces(overlay,[p],[1.8,1.885,1.95],[0,5,0])
    assert next(t for t in overlay.data if t.fill=='toself').line.width<=1.0


def test_legacy_group_anchor_does_not_follow_a_distant_peak_after_regrouping():
    ps=PeakService()
    p=peak('mhet',1.885,'MHET','MHET','compound_rt1.844')
    ps._peaks={'mhet':[p]};ps._grouping_window=.2
    ps.group_peaks_across_samples()
    assert p.group_id!='compound_rt1.844'
