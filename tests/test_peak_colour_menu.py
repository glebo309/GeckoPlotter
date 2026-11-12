"""A peak colour choice is visible, persistent, scoped, and undoable."""
from dataclasses import asdict

import pytest
from dash.exceptions import PreventUpdate

from services.peak_service import Peak, PeakService
from services.plot_settings_service import COLOR_PALETTES
from test_peak_baseline_context import setup_peak


def service():
    ps=PeakService(color_scope_resolver=lambda fid: 'other-ion' if fid=='ion2' else 'main')
    for fid,name,rt in [('a','MHET',1.884),('b','MHET',1.887),('c','BHET',1.905),('ion2','MHET',1.885)]:
        ps._peaks[fid]=[Peak(fid,fid,name,rt,rt-.01,rt+.01,2,5,.02,label=name)]
    ps.group_peaks_across_samples();ps.sync_named_colors()
    return ps


def test_colour_choice_follows_named_compound_and_survives_render_and_save():
    ps=service()
    before={fid:asdict(pp[0]) for fid,pp in ps._peaks.items()}
    assert ps.set_peak_color('a','a','#123456')
    ps.group_peaks_across_samples();ps.sync_named_colors()
    assert ps.get_peaks('a')[0].color==ps.get_peaks('b')[0].color=='#123456'
    assert ps.get_peaks('c')[0].color==before['c']['color']
    assert ps.get_peaks('ion2')[0].color==before['ion2']['color']
    fresh=PeakService(color_scope_resolver=ps._color_scope_resolver)
    fresh.deserialize(ps.serialize())
    fresh.set_palette('pastel',COLOR_PALETTES['pastel'])
    fresh.group_peaks_across_samples();fresh.sync_named_colors()
    assert fresh.get_peaks('a')[0].color==fresh.get_peaks('b')[0].color=='#123456'
    for fid,pp in ps._peaks.items():
        for key in ('rt','rt_start','rt_end','area','height','name','label'):
            assert asdict(pp[0])[key]==before[fid][key]


def test_colour_choice_is_undoable_after_the_next_render():
    ps=service()
    before={fid:pp[0].color for fid,pp in ps._peaks.items()}
    ps.save_undo();ps.set_peak_color('a','a','#123456');ps.sync_named_colors()
    assert ps.undo();ps.sync_named_colors()
    assert {fid:pp[0].color for fid,pp in ps._peaks.items()}==before
    assert ps.redo();ps.sync_named_colors()
    assert ps.get_peaks('b')[0].color=='#123456'


def test_menu_opens_on_the_clicked_peaks_actual_colour_and_current_palette():
    store,p,app=setup_peak()
    colour,swatches=app.functions['hydrate_peak_colour']({'peak_id':p.peak_id},{'palette':'pastel'})
    assert colour==p.color
    assert swatches==COLOR_PALETTES['pastel']
    with pytest.raises(PreventUpdate):
        app.functions['save_peak_colour'](colour,{'peak_id':p.peak_id},0,0)
    assert not store.peak_service.can_undo


def test_picking_a_colour_changes_the_peak_and_requests_a_visible_redraw():
    store,p,app=setup_peak()
    assert app.functions['save_peak_colour']('#ABCDEF',{'peak_id':p.peak_id},4,9)==(5,10)
    store.peak_service.sync_named_colors()
    assert p.color=='#ABCDEF'
    assert store.peak_service.can_undo


@pytest.mark.parametrize('colour',['#12','not a colour','',None])
def test_partial_or_invalid_hex_does_not_modify_the_peak(colour):
    store,p,app=setup_peak()
    before=asdict(p)
    with pytest.raises(PreventUpdate):
        app.functions['save_peak_colour'](colour,{'peak_id':p.peak_id},4,9)
    assert asdict(p)==before


def test_picker_offers_soft_pastels_even_with_black_signal_traces():
    _store,p,app=setup_peak()
    colour,swatches=app.functions['hydrate_peak_colour']({'peak_id':p.peak_id},{'palette':'muted_black'})
    assert colour==p.color
    assert swatches==COLOR_PALETTES['pastel']
