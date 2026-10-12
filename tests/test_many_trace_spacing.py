import pytest
from test_overlay_axes import files, ingestion_import
from services.plot_manager import PlotManager


@pytest.mark.parametrize('count', [14, 60])
@pytest.mark.parametrize('grouped', [False, True])
def test_many_separate_traces_keep_positive_domains_and_bounded_gaps(count, grouped):
    sample = files()[0]
    groups = ({str(i): [sample] for i in range(count)} if grouped else {'runs': [sample] * count})
    figure = PlotManager().create_multi_file_plot(groups, 'stacked', subplot_spacing=.08)
    assert len(figure.data) == count
    domains = [figure.layout['yaxis' + (str(i) if i > 1 else '')].domain for i in range(1, count + 1)]
    assert all(0 <= low < high <= 1 for low, high in domains)
    assert sum(high-low for low,high in domains) >= .5 - 1e-12


def test_ordinary_spacing_remains_as_requested():
    figure = PlotManager().create_multi_file_plot({'runs': files()}, 'stacked', subplot_spacing=.12)
    upper = figure.layout.yaxis.domain
    lower = figure.layout.yaxis2.domain
    assert upper[0] - lower[1] == pytest.approx(.12)
