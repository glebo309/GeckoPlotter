"""The same compound has one name in every sample, and is labelled once when samples are overlaid."""
import plotly.graph_objects as go

from services.peak_service import Peak, PeakService
from callbacks.peak_overlay import add_peak_traces


def _peak(pid, fid, name, rt, height):
    return Peak(pid, fid, name, rt, rt - .05, rt + .05, height / 10, height, .1,
                poly_x=[rt - .05, rt, rt + .05, rt + .05, rt, rt - .05], poly_y=[0, height, 0, 0, 0, 0])


def _service():
    ps = PeakService()
    # sample a integrated 2.26 and 2.54 (Peak 1, Peak 2); sample b only 2.54, so b called it "Peak 1"
    ps._peaks = {'a': [_peak('a1', 'a', 'Peak 1', 2.26, 50), _peak('a2', 'a', 'Peak 2', 2.54, 140)],
                 'b': [_peak('b1', 'b', 'Peak 1', 2.54, 800)]}
    ps.group_peaks_across_samples()
    return ps


def test_automatic_names_are_numbered_per_compound_not_per_sample():
    ps = _service()
    names = {p.peak_id: p.name for peaks in ps._peaks.values() for p in peaks}
    assert names == {'a1': 'Peak 1', 'a2': 'Peak 2', 'b1': 'Peak 2'}


def test_a_name_given_to_one_sample_names_the_compound_in_every_sample():
    ps = _service()
    ps.rename_peak('b', 'b1', 'Alanine')
    ps.group_peaks_across_samples()
    assert {p.peak_id: p.name for peaks in ps._peaks.values() for p in peaks} == \
        {'a1': 'Peak 1', 'a2': 'Alanine', 'b1': 'Alanine'}
    ps._peaks['c'] = [_peak('c1', 'c', 'Peak 1', 2.55, 300)]   # a new sample's peak joins the named compound
    ps.group_peaks_across_samples()
    assert ps._peaks['c'][0].name == 'Alanine'


def test_overlaid_samples_show_one_label_per_compound():
    ps = _service()
    fig = go.Figure()
    labelled = {'a1', 'b1'}                                      # the tallest member of each group
    for fid in ('a', 'b'):
        add_peak_traces(fig, ps.get_peaks(fid), [2.0, 3.0], [0, 0], labelled=labelled)
    texts = [t.text[0] for t in fig.data if t.mode == 'text']
    assert sorted(texts) == ['Peak 1', 'Peak 2']
