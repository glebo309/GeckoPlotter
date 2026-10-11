import numpy as np
import pytest
from types import SimpleNamespace
from test_render_tab_performance import App
from test_file_controls import component
from services.data_store import DataStore, Bundle, BundleType, ComponentRole
from callbacks.lcms_callbacks import register_lcms_callbacks


def fixture(modes=('positive', 'negative')):
    store = DataStore()
    components = [component(mode, ComponentRole.MS_POSITIVE if mode == 'positive' else ComponentRole.MS_NEGATIVE)
                  for mode in modes]
    components.append(component('uv', ComponentRole.VWD_A))
    store.add_bundle(Bundle('sample', 'Sample', BundleType.LCMS, component_list=components))
    calls = []
    store.lcms_service = SimpleNamespace(has_spectral_data=lambda entry: entry['record']['id'] in modes,
        get_averaged_spectrum=lambda entry, start, end: (calls.append((entry['record']['id'], start, end)) or
            (np.array([100., 200.]), np.array([10., 20.]))))
    peak = SimpleNamespace(peak_id='peak', file_id='negative', rt=1., rt_start=.8, rt_end=1.2,
                           label='Peak', name='Peak')
    store.peak_service.get_peaks = lambda fid: [peak] if fid == 'negative' else []
    app = App(); register_lcms_callbacks(app, store)
    return app.functions, calls


@pytest.mark.parametrize('negative,expected', [(False, 'positive'), (True, 'negative')])
def test_peak_mass_resolves_explicit_mode_even_when_source_is_negative(monkeypatch, negative, expected):
    functions, calls = fixture()
    monkeypatch.setattr('callbacks.lcms_callbacks._build_peak_mass_figure', lambda *args: ('figure', args[-1]))
    result = functions['show_peak_mass']('peak', negative, 'negative')
    assert calls == [(expected, .8, 1.2)]
    assert result[1] == ('−' if negative else '+')


def test_peak_mass_keeps_valid_mode_when_selecting_another_signal():
    functions, _ = fixture()
    result = functions['peak_mass_polarity_visibility']('uv', True)
    assert result[0] is True
    assert result[1]['display'] == 'flex'
    assert result[4] is False


@pytest.mark.parametrize('mode,negative', [('positive', False), ('negative', True)])
def test_single_mode_mass_controls_remain_visible_but_disable_unavailable_choice(mode, negative):
    functions, _ = fixture((mode,))
    result = functions['sync_polarity_toggle'](mode)
    assert result[0] is negative
    assert result[1]['display'] == 'flex'
    assert result[8:10] == (True, True)
    result = functions['peak_mass_polarity_visibility']('uv', not negative)
    assert result[0] is negative
    assert result[1]['display'] == 'flex'
    assert result[4] is True
    assert mode in result[5].lower()


def test_scan_and_eic_keep_negative_mode_when_selecting_uv():
    functions, _ = fixture()
    # File selection and slider configuration use the same spectral resolver.
    from callbacks.lcms_callbacks import _resolve_lcms_spectral_entry
    callback = functions['sync_polarity_toggle']
    store = next(cell.cell_contents for cell in callback.__closure__ if isinstance(cell.cell_contents, DataStore))
    assert _resolve_lcms_spectral_entry(store, 'negative', store.lcms_service)[0] == 'negative'
    assert _resolve_lcms_spectral_entry(store, 'uv', store.lcms_service)[0] == 'negative'
    assert callback('uv')[0] is True
    # Explicitly selecting positive is still respected.
    assert _resolve_lcms_spectral_entry(store, 'positive', store.lcms_service)[0] == 'positive'
    assert _resolve_lcms_spectral_entry(store, 'uv', store.lcms_service)[0] == 'positive'
