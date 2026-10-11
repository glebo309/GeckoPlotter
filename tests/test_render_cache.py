from services.render_cache import RenderCache


def test_cache_invalidates_when_inputs_change_and_prunes_closed_tabs():
    cache = RenderCache()
    inputs = {'settings': {'layout_mode': 'stacked'}, 'revision': 1}
    cache.put('lcms', inputs, {'data': [1]})
    assert cache.get('lcms', dict(inputs)) == {'data': [1]}
    assert cache.get('lcms', {**inputs, 'revision': 2}) is None
    assert cache.get('spectra', inputs) is None
    cache.prune(['spectra'])
    assert cache.get('lcms', inputs) is None
