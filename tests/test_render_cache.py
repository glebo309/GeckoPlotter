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


def test_cache_match_checks_do_not_copy_the_cached_figure(monkeypatch):
    import services.render_cache as module
    cache=RenderCache();cache.put('plot',{'version':1},{'data':[1,2,3]})
    def forbidden(*args):raise AssertionError('No figure copy needed for a cache match')
    monkeypatch.setattr(module,'deepcopy',forbidden)
    assert cache.matches('plot',{'version':1}) is True
    assert cache.matches('plot',{'version':2}) is False
