"""A peak's name dragged in the plot: kept with the peak, drawn there (with a leader line on request), saved."""
import plotly.graph_objects as go

from callbacks.peak_overlay import add_peak_traces, cleanup_peak_traces
from services.peak_service import Peak, PeakService


def _peak(**kw):
    return Peak('p1', 'f1', 'Ala', 2.5, 2.4, 2.6, 10.0, 5.0, 0.2, poly_x=[2.4, 2.5, 2.6, 2.6, 2.5, 2.4],
                poly_y=[0, 5, 0, 0, 0, 0], **kw)


def _labels(fig):
    texts = [t.text[0] for t in fig.data if t.mode == 'text']
    moved = [a for a in fig.layout.annotations if str(a.name).startswith('peak-label:')]
    return texts, moved


def test_a_moved_label_is_an_annotation_offset_from_the_peak_top_and_comes_back_when_reset():
    service = PeakService()
    service._peaks['f1'] = [_peak()]
    fig = go.Figure(go.Scatter(x=[2.4, 2.5, 2.6], y=[0, 5, 0], meta={'file_id': 'f1'}))
    add_peak_traces(fig, service.get_peaks('f1'), [2.4, 2.5, 2.6], [0, 5, 0])
    assert _labels(fig) == (['Ala'], [])

    assert service.set_label_position('f1', 'p1', (30, 20), leader=False)
    cleanup_peak_traces(fig)
    add_peak_traces(fig, service.get_peaks('f1'), [2.4, 2.5, 2.6], [0, 5, 0])
    texts, moved = _labels(fig)
    assert texts == [] and len(moved) == 1
    assert (moved[0].x, moved[0].y, moved[0].xshift, moved[0].yshift, moved[0].showarrow) == (2.5, 5, 30, 20, False)

    service.set_label_position('f1', 'p1', (30, 20), leader=True)
    cleanup_peak_traces(fig)
    add_peak_traces(fig, service.get_peaks('f1'), [2.4, 2.5, 2.6], [0, 5, 0])
    texts, moved = _labels(fig)
    assert len(moved) == 1 and moved[0].showarrow and (moved[0].ax, moved[0].ay) == (30, -20)

    service.set_label_position('f1', 'p1', None)
    cleanup_peak_traces(fig)
    add_peak_traces(fig, service.get_peaks('f1'), [2.4, 2.5, 2.6], [0, 5, 0])
    assert _labels(fig) == (['Ala'], [])


def test_the_position_is_saved_with_the_peaks():
    service = PeakService()
    service._peaks['f1'] = [_peak()]
    service.set_label_position('f1', 'p1', (12.34, -8), leader=True)
    again = PeakService()
    again.deserialize(service.serialize())
    peak = again.get_peaks('f1')[0]
    assert peak.label_offset == [12.3, -8.0] and peak.label_leader is True
