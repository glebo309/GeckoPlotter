import pandas as pd
import sys
import pytest
from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult
from services.plot_manager import PlotManager
from services.plot_settings_service import PlotSettingsService
from services.axis_linking import apply_axis_linking
from services.peak_service import Peak
from callbacks.peak_overlay import overlay_peaks_on_figure


@pytest.fixture(autouse=True)
def ingestion_import(monkeypatch):
    import src.ingestion.types as types
    monkeypatch.setitem(sys.modules, 'ingestion.types', types)


def files():
    result = []
    for cid, role, name, height in [
        ('ms1','ms_positive','+TIC',5e6), ('ms2','ms_negative','-TIC',4e6),
        ('uv1','vwd_a','UV 280 nm',200), ('uv2','vwd_b','UV 250 nm',1200),
    ]:
        df = pd.DataFrame({'time':[0.,1.,2.], 'intensity':[0.,height,0.]})
        sr = StandardizedResult(data=df,
            column_roles={'time':ColumnRole.X,'intensity':ColumnRole.Y},
            identity=FileIdentity(cid+'.cdf','cdf','preset',1),
            plot_hint=PlotHint.LINE, source_category=SourceCategory.CHROMATOGRAM)
        result.append((name, {'record':{'id':cid,'type':role},'standardized':sr}))
    return result


def test_overlay_shares_axes_by_measurement_unit_without_rescaling_raw_data():
    fig = PlotManager().create_multi_file_plot({'lcms':files()}, 'overlay')
    assert [t.yaxis or 'y' for t in fig.data] == ['y','y','y2','y2']
    assert list(fig.data[2].y) == [0.,200.,0.]
    assert fig.layout.yaxis2.overlaying == 'y'
    assert fig.layout.yaxis2.autoshift
    assert fig.layout.yaxis.title.text == 'Ion Count'
    assert fig.layout.yaxis2.title.text == 'Absorbance (mAU)'
    assert fig.layout.meta['gecko_axis_units'] == {'yaxis': 'Ion Count', 'yaxis2': 'Absorbance (mAU)'}
    assert 'yaxis3' not in fig.layout.to_plotly_json()
    PlotSettingsService.apply_to_figure(fig, PlotSettingsService.from_dict({}))
    apply_axis_linking(fig, True, False)
    assert fig.layout.yaxis2.tickfont.color == '#1f2328'
    assert fig.layout.yaxis2.matches is None
    apply_axis_linking(fig, True, True)
    assert fig.layout.yaxis2.matches is None


def test_uv_peak_fill_and_baseline_use_the_uv_axis():
    fig = PlotManager().create_multi_file_plot({'lcms':files()}, 'overlay')
    peak = Peak('peak1','uv1','UV peak',1.,.5,1.5,100.,200.,1.,
                poly_x=[.5,1.,1.5],poly_y=[0.,200.,0.], p_line=[(.5,0.),(1.5,0.)])
    fig = overlay_peaks_on_figure([peak],fig,[0.,1.,2.],[0.,200.,0.],'peak1')
    assert all(trace.yaxis == 'y2' for trace in fig.data if trace.meta == 'peak_overlay')
    assert fig.layout.shapes[0].yref == 'y2'


def test_overlay_axes_stay_neutral_when_each_unit_has_only_one_trace():
    fig = PlotManager().create_multi_file_plot({'lcms': [files()[0], files()[2]]}, 'overlay')
    for key in ['yaxis', 'yaxis2']:
        axis = fig.layout[key]
        assert axis.color == '#444'
        assert axis.tickfont.color == '#444'
        assert axis.title.font.color == '#444'
    PlotSettingsService.apply_to_figure(fig, PlotSettingsService.from_dict({}))
    apply_axis_linking(fig)
    assert fig.layout.yaxis.color == fig.layout.yaxis2.color == '#1f2328'
